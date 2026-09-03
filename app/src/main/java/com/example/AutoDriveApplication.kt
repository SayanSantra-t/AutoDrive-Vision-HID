package com.example

import android.app.Application
import android.util.Log

class AutoDriveApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        
        // Guard against fatal crashes
        val defaultHandler = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            Log.e("AutoDriveApp", "Caught unhandled exception in thread ${thread.name}", throwable)
            defaultHandler?.uncaughtException(thread, throwable)
        }
    }
}
