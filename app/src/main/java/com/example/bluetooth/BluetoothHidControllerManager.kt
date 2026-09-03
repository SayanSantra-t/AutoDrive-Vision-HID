package com.example.bluetooth

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothHidDevice
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.BluetoothSocket
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.SharedPreferences
import android.os.Build
import android.util.Log
import com.example.model.BluetoothState
import com.example.model.ControllerState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.OutputStream
import java.util.UUID
import java.util.concurrent.Executors

/**
 * High-performance Bluetooth HID Keyboard Controller Emulator and Transceiver
 * Emulates a standard Bluetooth HID Keyboard sending WASD + Space keycodes:
 * - W: Accelerate
 * - A: Steer Left
 * - S: Brake / Reverse
 * - D: Steer Right
 * - Space: Handbrake
 * Includes automatic reconnection to last paired host device.
 */
class BluetoothHidControllerManager(
    private val context: Context,
    private val scope: CoroutineScope
) {
    companion object {
        private const val TAG = "AutoDriveBtHID"
        private const val PREFS_NAME = "autodrive_bt_prefs"
        private const val KEY_LAST_DEVICE_ADDR = "last_bt_device_address"
        private const val KEY_LAST_DEVICE_NAME = "last_bt_device_name"
        private val SPP_UUID: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
    }

    private val prefs: SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    private val bluetoothManager: BluetoothManager? =
        try {
            context.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
        } catch (e: Throwable) {
            null
        }
    val bluetoothAdapter: BluetoothAdapter? =
        try {
            bluetoothManager?.adapter
        } catch (e: Throwable) {
            null
        }

    fun isBluetoothEnabledSafely(): Boolean {
        return try {
            bluetoothAdapter?.isEnabled == true
        } catch (e: SecurityException) {
            false
        } catch (e: Throwable) {
            false
        }
    }

    private fun BluetoothDevice.getSafeName(): String {
        return try {
            this.name ?: this.address
        } catch (e: SecurityException) {
            this.address
        } catch (e: Throwable) {
            "Bluetooth Device"
        }
    }

    private var hidDeviceProfile: BluetoothHidDevice? = null
    private var connectedDevice: BluetoothDevice? = null
    private var isAppRegistered = false

    // Bluetooth SPP fallback socket & stream
    private var sppSocket: BluetoothSocket? = null
    private var sppOutputStream: OutputStream? = null

    private val _bluetoothState = MutableStateFlow(
        if (bluetoothAdapter == null) BluetoothState.UNAVAILABLE
        else if (!isBluetoothEnabledSafely()) BluetoothState.DISABLED
        else BluetoothState.DISCONNECTED
    )
    val bluetoothState: StateFlow<BluetoothState> = _bluetoothState.asStateFlow()

    private val _connectedDeviceName = MutableStateFlow<String?>(loadSavedDeviceName())
    val connectedDeviceName: StateFlow<String?> = _connectedDeviceName.asStateFlow()

    private val _transmitRateHz = MutableStateFlow(0)
    val transmitRateHz: StateFlow<Int> = _transmitRateHz.asStateFlow()

    private val _latencyPingMs = MutableStateFlow(2)
    val latencyPingMs: StateFlow<Int> = _latencyPingMs.asStateFlow()

    private var currentControllerState = ControllerState()
    private var dispatchJob: Job? = null
    private var packetsSentThisSec = 0
    private var lastRateCalcTime = System.currentTimeMillis()

    private val executor = Executors.newSingleThreadExecutor()

    private val bluetoothEventReceiver = object : BroadcastReceiver() {
        @SuppressLint("MissingPermission")
        override fun onReceive(ctx: Context?, intent: Intent?) {
            val action = intent?.action ?: return
            when (action) {
                BluetoothDevice.ACTION_ACL_CONNECTED -> {
                    val device = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                        intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE, BluetoothDevice::class.java)
                    } else {
                        @Suppress("DEPRECATION")
                        intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE)
                    }
                    Log.d(TAG, "BroadcastReceiver: ACL_CONNECTED for ${device?.name ?: device?.address}")
                    device?.let { dev ->
                        val savedAddr = getSavedDeviceAddress()
                        if (savedAddr == null || savedAddr == dev.address || connectedDevice == null) {
                            handleDeviceConnected(dev)
                        }
                    }
                }
                BluetoothDevice.ACTION_ACL_DISCONNECTED -> {
                    val device = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                        intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE, BluetoothDevice::class.java)
                    } else {
                        @Suppress("DEPRECATION")
                        intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE)
                    }
                    Log.d(TAG, "BroadcastReceiver: ACL_DISCONNECTED for ${device?.name ?: device?.address}")
                    if (device == null || device.address == connectedDevice?.address) {
                        handleDeviceDisconnected()
                    }
                }
                BluetoothAdapter.ACTION_STATE_CHANGED -> {
                    val state = intent.getIntExtra(BluetoothAdapter.EXTRA_STATE, BluetoothAdapter.ERROR)
                    if (state == BluetoothAdapter.STATE_ON) {
                        initializeProfile()
                    } else if (state == BluetoothAdapter.STATE_OFF) {
                        _bluetoothState.value = BluetoothState.DISABLED
                        handleDeviceDisconnected()
                    }
                }
            }
        }
    }

    private val hidDeviceCallback = object : BluetoothHidDevice.Callback() {
        @SuppressLint("MissingPermission")
        override fun onAppStatusChanged(pluggedDevice: BluetoothDevice?, registered: Boolean) {
            Log.d(TAG, "HID App registered: $registered, pluggedDevice: ${pluggedDevice?.name}")
            isAppRegistered = registered
            if (registered) {
                if (pluggedDevice != null) {
                    handleDeviceConnected(pluggedDevice)
                } else {
                    checkAndAutoConnect()
                }
            } else {
                _bluetoothState.value = BluetoothState.DISCONNECTED
            }
        }

        @SuppressLint("MissingPermission")
        override fun onConnectionStateChanged(device: BluetoothDevice?, state: Int) {
            Log.d(TAG, "HID Connection state changed: $state for ${device?.name ?: device?.address}")
            when (state) {
                BluetoothProfile.STATE_CONNECTED -> {
                    device?.let { handleDeviceConnected(it) }
                }
                BluetoothProfile.STATE_CONNECTING -> {
                    _bluetoothState.value = BluetoothState.CONNECTING
                }
                BluetoothProfile.STATE_DISCONNECTED, BluetoothProfile.STATE_DISCONNECTING -> {
                    if (connectedDevice == null || connectedDevice?.address == device?.address || device == null) {
                        handleDeviceDisconnected()
                    }
                }
            }
        }

        override fun onGetReport(device: BluetoothDevice?, type: Byte, id: Byte, bufferSize: Int) {
            if (id == HidDescriptor.REPORT_ID_KEYBOARD) {
                val state = currentControllerState
                val report = HidDescriptor.buildKeyboardReport(
                    keyW = state.isAccelerating,
                    keyA = state.isSteeringLeft,
                    keyS = state.isBraking,
                    keyD = state.isSteeringRight,
                    keySpace = state.isHandbrake
                )
                try {
                    hidDeviceProfile?.replyReport(device, type, id, report)
                } catch (e: SecurityException) {
                    Log.e(TAG, "SecurityException on replyReport", e)
                }
            }
        }

        override fun onSetReport(device: BluetoothDevice?, type: Byte, id: Byte, data: ByteArray?) {
            try {
                hidDeviceProfile?.reportError(device, BluetoothHidDevice.ERROR_RSP_SUCCESS)
            } catch (e: SecurityException) {
                Log.e(TAG, "SecurityException on reportError", e)
            }
        }
    }

    private val serviceListener = object : BluetoothProfile.ServiceListener {
        override fun onServiceConnected(profile: Int, proxy: BluetoothProfile?) {
            if (profile == BluetoothProfile.HID_DEVICE) {
                Log.d(TAG, "Bluetooth HID Device profile proxy connected")
                hidDeviceProfile = proxy as? BluetoothHidDevice
                registerHidProfile()
            }
        }

        override fun onServiceDisconnected(profile: Int) {
            if (profile == BluetoothProfile.HID_DEVICE) {
                Log.d(TAG, "Bluetooth HID Device profile proxy disconnected")
                hidDeviceProfile = null
                isAppRegistered = false
                _bluetoothState.value = BluetoothState.DISCONNECTED
            }
        }
    }

    init {
        try {
            registerBroadcastReceivers()
            initializeProfile()
        } catch (e: Throwable) {
            Log.e(TAG, "Non-fatal error in BluetoothHidControllerManager init", e)
        }
    }

    private fun registerBroadcastReceivers() {
        try {
            val filter = IntentFilter().apply {
                addAction(BluetoothDevice.ACTION_ACL_CONNECTED)
                addAction(BluetoothDevice.ACTION_ACL_DISCONNECTED)
                addAction(BluetoothAdapter.ACTION_STATE_CHANGED)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                context.registerReceiver(bluetoothEventReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
            } else {
                context.registerReceiver(bluetoothEventReceiver, filter)
            }
        } catch (e: Throwable) {
            Log.e(TAG, "Error registering receiver", e)
        }
    }

    fun initializeProfile() {
        if (bluetoothAdapter == null || !isBluetoothEnabledSafely()) {
            _bluetoothState.value = if (bluetoothAdapter == null) BluetoothState.UNAVAILABLE else BluetoothState.DISABLED
            return
        }

        try {
            bluetoothAdapter.getProfileProxy(context, serviceListener, BluetoothProfile.HID_DEVICE)
        } catch (e: SecurityException) {
            Log.w(TAG, "Permission denied requesting HID profile proxy", e)
            _bluetoothState.value = BluetoothState.DISABLED
        } catch (e: Throwable) {
            Log.e(TAG, "Failed to getProfileProxy", e)
            _bluetoothState.value = BluetoothState.DISCONNECTED
        }
    }

    @SuppressLint("MissingPermission")
    private fun registerHidProfile() {
        val hid = hidDeviceProfile ?: return
        val sdp = HidDescriptor.createSdpSettings()

        try {
            val registered = hid.registerApp(
                sdp,
                null, // inQos
                null, // outQos
                executor,
                hidDeviceCallback
            )
            Log.d(TAG, "HID Device registerApp returned: $registered")
            if (registered) {
                checkAndAutoConnect()
            }
        } catch (e: SecurityException) {
            Log.e(TAG, "SecurityException registering HID app", e)
        } catch (e: Exception) {
            Log.e(TAG, "Exception registering HID app", e)
        }
    }

    @SuppressLint("MissingPermission")
    fun checkAndAutoConnect() {
        val hid = hidDeviceProfile
        if (hid != null) {
            try {
                val connectedList = hid.connectedDevices
                if (!connectedList.isNullOrEmpty()) {
                    val activeDev = connectedList.first()
                    Log.d(TAG, "Found already connected HID host: ${activeDev.name ?: activeDev.address}")
                    handleDeviceConnected(activeDev)
                    return
                }
            } catch (e: Exception) {
                Log.d(TAG, "Could not get connectedDevices", e)
            }
        }

        // Check if previously connected device is available
        val savedAddr = getSavedDeviceAddress()
        if (savedAddr != null && bluetoothAdapter != null && bluetoothAdapter.isEnabled) {
            try {
                val pairedDev = bluetoothAdapter.bondedDevices.find { it.address.equals(savedAddr, ignoreCase = true) }
                    ?: bluetoothAdapter.getRemoteDevice(savedAddr)
                if (pairedDev != null) {
                    Log.d(TAG, "Auto-connecting to saved device: ${pairedDev.name ?: savedAddr}")
                    connectToDevice(pairedDev)
                    return
                }
            } catch (e: Exception) {
                Log.e(TAG, "Auto-connect exception", e)
            }
        }

        if (isAppRegistered && _bluetoothState.value != BluetoothState.CONNECTED) {
            _bluetoothState.value = BluetoothState.ADVERTISING
        }
    }

    @SuppressLint("MissingPermission")
    fun connectToDevice(device: BluetoothDevice) {
        _bluetoothState.value = BluetoothState.CONNECTING
        saveConnectedDevice(device)

        val hid = hidDeviceProfile
        if (hid != null && isAppRegistered) {
            try {
                val success = hid.connect(device)
                Log.d(TAG, "hid.connect(${device.name}) initiated, success=$success")
                if (!success) {
                    fallbackConnectSpp(device)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error connecting HID device", e)
                fallbackConnectSpp(device)
            }
        } else {
            fallbackConnectSpp(device)
        }
    }

    @SuppressLint("MissingPermission")
    private fun fallbackConnectSpp(device: BluetoothDevice) {
        scope.launch(Dispatchers.IO) {
            try {
                sppSocket?.close()
                val socket = device.createRfcommSocketToServiceRecord(SPP_UUID)
                socket.connect()
                sppSocket = socket
                sppOutputStream = socket.outputStream
                handleDeviceConnected(device)
                Log.d(TAG, "Connected via SPP Serial Fallback to ${device.name}")
            } catch (e: Exception) {
                Log.e(TAG, "SPP Serial connection failed", e)
                if (_bluetoothState.value == BluetoothState.CONNECTING) {
                    _bluetoothState.value = if (isAppRegistered) BluetoothState.ADVERTISING else BluetoothState.DISCONNECTED
                }
            }
        }
    }

    @SuppressLint("MissingPermission")
    private fun handleDeviceConnected(device: BluetoothDevice) {
        connectedDevice = device
        val name = try {
            device.name ?: device.address ?: "HID Host"
        } catch (e: SecurityException) {
            "HID Host Car"
        }
        _connectedDeviceName.value = name
        saveConnectedDevice(device)
        _bluetoothState.value = BluetoothState.CONNECTED
        startPacketDispatchLoop()
    }

    private fun handleDeviceDisconnected() {
        stopPacketDispatchLoop()
        connectedDevice = null
        sppSocket = null
        sppOutputStream = null
        _bluetoothState.value = if (isAppRegistered) BluetoothState.ADVERTISING else BluetoothState.DISCONNECTED
    }

    @SuppressLint("MissingPermission")
    fun disconnect() {
        stopPacketDispatchLoop()
        try {
            connectedDevice?.let { dev ->
                hidDeviceProfile?.disconnect(dev)
            }
            sppSocket?.close()
        } catch (e: Exception) {
            Log.e(TAG, "Error disconnecting", e)
        }
        handleDeviceDisconnected()
    }

    private fun saveConnectedDevice(device: BluetoothDevice) {
        try {
            val addr = device.address
            val name = device.name ?: addr
            prefs.edit()
                .putString(KEY_LAST_DEVICE_ADDR, addr)
                .putString(KEY_LAST_DEVICE_NAME, name)
                .apply()
        } catch (e: SecurityException) {
            // Ignore permission issue during saving
        }
    }

    private fun getSavedDeviceAddress(): String? = prefs.getString(KEY_LAST_DEVICE_ADDR, null)
    private fun loadSavedDeviceName(): String? = prefs.getString(KEY_LAST_DEVICE_NAME, null)

    /**
     * Update current driving command to be transmitted
     */
    fun updateControllerState(state: ControllerState) {
        currentControllerState = state
        // Immediate low-latency dispatch on state change
        if (_bluetoothState.value == BluetoothState.CONNECTED) {
            scope.launch(Dispatchers.IO) {
                sendCurrentReport()
            }
        }
    }

    /**
     * High-speed packet loop (50Hz = every 20ms) for low-latency steering and throttle
     */
    private fun startPacketDispatchLoop() {
        dispatchJob?.cancel()
        dispatchJob = scope.launch(Dispatchers.IO) {
            lastRateCalcTime = System.currentTimeMillis()
            packetsSentThisSec = 0

            while (isActive && _bluetoothState.value == BluetoothState.CONNECTED) {
                val startTime = System.nanoTime()
                sendCurrentReport()
                packetsSentThisSec++

                val now = System.currentTimeMillis()
                if (now - lastRateCalcTime >= 1000) {
                    _transmitRateHz.value = packetsSentThisSec
                    packetsSentThisSec = 0
                    lastRateCalcTime = now
                }

                val elapsedMs = (System.nanoTime() - startTime) / 1_000_000
                _latencyPingMs.value = elapsedMs.toInt().coerceAtLeast(1)

                val sleepTime = (20 - elapsedMs).coerceAtLeast(5)
                delay(sleepTime)
            }
        }
    }

    private fun stopPacketDispatchLoop() {
        dispatchJob?.cancel()
        dispatchJob = null
        _transmitRateHz.value = 0
    }

    @SuppressLint("MissingPermission")
    private fun sendCurrentReport() {
        val dev = connectedDevice
        val state = currentControllerState

        // 1. Send HID Keyboard Report if HID connected
        val hid = hidDeviceProfile
        if (hid != null && dev != null && isAppRegistered) {
            val report = HidDescriptor.buildKeyboardReport(
                keyW = state.keyW || state.throttle > 0.1f,
                keyA = state.keyA || state.steering < -0.15f,
                keyS = state.keyS || state.brake > 0.1f,
                keyD = state.keyD || state.steering > 0.15f,
                keySpace = state.keySpace
            )
            try {
                hid.sendReport(dev, HidDescriptor.REPORT_ID_KEYBOARD.toInt(), report)
            } catch (e: Exception) {
                // Ignore transient write errors
            }
        }

        // 2. Also stream SPP Serial payload if Serial fallback active
        sppOutputStream?.let { stream ->
            try {
                val w = if (state.keyW || state.throttle > 0.1f) 1 else 0
                val a = if (state.keyA || state.steering < -0.15f) 1 else 0
                val s = if (state.keyS || state.brake > 0.1f) 1 else 0
                val d = if (state.keyD || state.steering > 0.15f) 1 else 0
                val sp = if (state.keySpace) 1 else 0
                val serialMsg = "K:W=$w,A=$a,S=$s,D=$d,SPACE=$sp\n"
                stream.write(serialMsg.toByteArray())
                stream.flush()
            } catch (e: Exception) {
                // Serial write error
            }
        }
    }

    @SuppressLint("MissingPermission")
    fun getPairedDevices(): List<BluetoothDevice> {
        return try {
            bluetoothAdapter?.bondedDevices?.toList() ?: emptyList()
        } catch (e: SecurityException) {
            emptyList()
        }
    }

    fun cleanup() {
        stopPacketDispatchLoop()
        try {
            context.unregisterReceiver(bluetoothEventReceiver)
        } catch (e: Exception) {
            // Receiver might not be registered
        }
        try {
            hidDeviceProfile?.let {
                bluetoothAdapter?.closeProfileProxy(BluetoothProfile.HID_DEVICE, it)
            }
            sppSocket?.close()
        } catch (e: Exception) {
            Log.e(TAG, "Cleanup exception", e)
        }
    }
}
