package com.example.bluetooth

import android.bluetooth.BluetoothHidDevice
import android.bluetooth.BluetoothHidDeviceAppSdpSettings

/**
 * Standard Bluetooth HID Keyboard Descriptor Definitions
 * Emulates a standard USB / Bluetooth HID Keyboard for WASD + Space vehicle driving:
 * - W: Accelerate (USB HID Usage 0x1A)
 * - A: Steer Left (USB HID Usage 0x04)
 * - S: Brake / Reverse (USB HID Usage 0x16)
 * - D: Steer Right (USB HID Usage 0x07)
 * - Space: Handbrake (USB HID Usage 0x2C)
 *
 * Compatible with Windows, Linux, macOS, Raspberry Pi, Android, iOS, ESP32, and WebHID/Gamepad-to-Keyboard.
 */
object HidDescriptor {

    const val REPORT_ID_KEYBOARD: Byte = 0x01

    // USB HID Keyboard Usage Codes (Page 0x07)
    const val KEY_W: Byte = 0x1A.toByte()     // 'w' / 'W' -> Accelerate
    const val KEY_A: Byte = 0x04.toByte()     // 'a' / 'A' -> Steer Left
    const val KEY_S: Byte = 0x16.toByte()     // 's' / 'S' -> Brake / Reverse
    const val KEY_D: Byte = 0x07.toByte()     // 'd' / 'D' -> Steer Right
    const val KEY_SPACE: Byte = 0x2C.toByte() // Spacebar  -> Handbrake

    /**
     * Standard 8-Byte Boot Protocol HID Keyboard Report Descriptor
     * 100% Recognized by all operating systems as a standard Bluetooth Keyboard.
     */
    val KEYBOARD_REPORT_DESCRIPTOR = byteArrayOf(
        0x05.toByte(), 0x01.toByte(), // USAGE_PAGE (Generic Desktop)
        0x09.toByte(), 0x06.toByte(), // USAGE (Keyboard)
        0xA1.toByte(), 0x01.toByte(), // COLLECTION (Application)
        0x85.toByte(), REPORT_ID_KEYBOARD, // REPORT_ID (1)

        // --- Byte 0: 8-bit Modifier Keys (Ctrl, Shift, Alt, GUI) ---
        0x05.toByte(), 0x07.toByte(), // USAGE_PAGE (Keyboard/Keypad)
        0x19.toByte(), 0xE0.toByte(), // USAGE_MINIMUM (Keyboard LeftControl)
        0x29.toByte(), 0xE7.toByte(), // USAGE_MAXIMUM (Keyboard Right GUI)
        0x15.toByte(), 0x00.toByte(), // LOGICAL_MINIMUM (0)
        0x25.toByte(), 0x01.toByte(), // LOGICAL_MAXIMUM (1)
        0x75.toByte(), 0x01.toByte(), // REPORT_SIZE (1 bit)
        0x95.toByte(), 0x08.toByte(), // REPORT_COUNT (8 modifier bits)
        0x81.toByte(), 0x02.toByte(), // INPUT (Data, Var, Abs)

        // --- Byte 1: Reserved byte (0x00) ---
        0x95.toByte(), 0x01.toByte(), // REPORT_COUNT (1 byte)
        0x75.toByte(), 0x08.toByte(), // REPORT_SIZE (8 bits)
        0x81.toByte(), 0x01.toByte(), // INPUT (Cnst, Ary, Abs)

        // --- Optional LED Indicators Output Report (5 bits + 3 bits padding) ---
        0x95.toByte(), 0x05.toByte(), // REPORT_COUNT (5 LEDs)
        0x75.toByte(), 0x01.toByte(), // REPORT_SIZE (1 bit)
        0x05.toByte(), 0x08.toByte(), // USAGE_PAGE (LEDs)
        0x19.toByte(), 0x01.toByte(), // USAGE_MINIMUM (Num Lock)
        0x29.toByte(), 0x05.toByte(), // USAGE_MAXIMUM (Kana)
        0x91.toByte(), 0x02.toByte(), // OUTPUT (Data, Var, Abs)
        0x95.toByte(), 0x01.toByte(), // REPORT_COUNT (1 byte pad)
        0x75.toByte(), 0x03.toByte(), // REPORT_SIZE (3 bits)
        0x91.toByte(), 0x01.toByte(), // OUTPUT (Cnst, Ary, Abs)

        // --- Bytes 2..7: Array of up to 6 Simultaneous Keycodes Pressed ---
        0x95.toByte(), 0x06.toByte(), // REPORT_COUNT (6 keys)
        0x75.toByte(), 0x08.toByte(), // REPORT_SIZE (8 bits)
        0x15.toByte(), 0x00.toByte(), // LOGICAL_MINIMUM (0)
        0x25.toByte(), 0x65.toByte(), // LOGICAL_MAXIMUM (101)
        0x05.toByte(), 0x07.toByte(), // USAGE_PAGE (Keyboard/Keypad)
        0x19.toByte(), 0x00.toByte(), // USAGE_MINIMUM (None)
        0x29.toByte(), 0x65.toByte(), // USAGE_MAXIMUM (Keyboard Application)
        0x81.toByte(), 0x00.toByte(), // INPUT (Data, Ary, Abs)

        0xC0.toByte()                 // END_COLLECTION
    )

    /**
     * Create Bluetooth SDP Settings for Keyboard peripheral profile
     */
    fun createSdpSettings(): BluetoothHidDeviceAppSdpSettings {
        return BluetoothHidDeviceAppSdpSettings(
            "AutoDrive Keyboard Controller",
            "Bluetooth WASD Vehicle Controller",
            "AutoDrive HID",
            BluetoothHidDevice.SUBCLASS1_KEYBOARD,
            KEYBOARD_REPORT_DESCRIPTOR
        )
    }

    /**
     * Build Standard 8-byte Keyboard HID Report from WASD & Space states
     * - Byte 0: Modifiers (0x00)
     * - Byte 1: Reserved (0x00)
     * - Bytes 2..7: Active keycodes (up to 6 keys)
     */
    fun buildKeyboardReport(
        keyW: Boolean,
        keyA: Boolean,
        keyS: Boolean,
        keyD: Boolean,
        keySpace: Boolean
    ): ByteArray {
        val report = ByteArray(8) // Byte 0 = Modifiers, Byte 1 = Reserved, Bytes 2..7 = Keys
        var keyIndex = 2

        if (keyW && keyIndex < 8) {
            report[keyIndex++] = KEY_W
        }
        if (keyA && keyIndex < 8) {
            report[keyIndex++] = KEY_A
        }
        if (keyS && keyIndex < 8) {
            report[keyIndex++] = KEY_S
        }
        if (keyD && keyIndex < 8) {
            report[keyIndex++] = KEY_D
        }
        if (keySpace && keyIndex < 8) {
            report[keyIndex++] = KEY_SPACE
        }

        return report
    }
}
