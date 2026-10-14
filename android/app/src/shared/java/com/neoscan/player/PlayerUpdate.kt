package com.neoscan.player

import android.app.Activity
import android.content.Context

/** THE SHARED PLAYER (TODO T2): no self-update. The house Player's PlayerUpdate (src/devtools: an APK downloaded and
 *  installed through a PackageInstaller session) is not in this build, nor its permissions (src/shared/AndroidManifest):
 *  a new shared Player is installed by hand. Same API, nothing ever available. */
object PlayerUpdate {
    class Info(val version: String, val code: Int, val file: String, val size: Long, val sha: String)
    @Volatile var latest: Info? = null
    @Volatile var progress = -1
    @Volatile var error = ""
    const val NOTIFY_REQ = 7
    fun channel(ctx: Context): String = "live"
    fun setChannel(ctx: Context, ch: String?) {}
    fun available(): Info? = null
    fun ready(ctx: Context): Info? = null
    fun cleanup(ctx: Context) {}
    fun check(ctx: Context): Info? = null
    fun install(act: Activity) {}
}
