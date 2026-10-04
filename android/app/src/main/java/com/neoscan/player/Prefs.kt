package com.neoscan.player

import android.content.Context

/** Player settings (SharedPreferences "settings"), read by MainActivity on every resume and applied live. */
class Prefs(ctx: Context) {
    private val p = ctx.getSharedPreferences("settings", 0)
    var orientation: String                                         // auto | portrait | landscape
        get() = p.getString("orientation", "auto")!!; set(v) = p.edit().putString("orientation", v).apply()
    var filter: String                                              // sharp | smooth | scanlines | subpixel
        get() = p.getString("filter", "sharp")!!; set(v) = p.edit().putString("filter", v).apply()
    var aspect: String                                              // square (pixel-exact) | 4:3 (plain rectangle)
        get() = p.getString("aspect", "square")!!; set(v) = p.edit().putString("aspect", v).apply()
    var scale: String                                               // fit | integer
        get() = p.getString("scale", "fit")!!; set(v) = p.edit().putString("scale", v).apply()
    var scanlines: Int                                              // scanline darkness, %
        get() = p.getInt("scanlines", 50); set(v) = p.edit().putInt("scanlines", v).apply()
    var opacity: Int                                                // landscape controls over the picture, %
        get() = p.getInt("opacity", 45); set(v) = p.edit().putInt("opacity", v).apply()
    var size: Int                                                   // touch controls, % of the default size
        get() = p.getInt("size", 100); set(v) = p.edit().putInt("size", v).apply()
    var vibrate: Boolean
        get() = p.getBoolean("vibrate", true); set(v) = p.edit().putBoolean("vibrate", v).apply()
    var autoUpdate: Boolean                                         // fetch a newer build on launch
        get() = p.getBoolean("autoUpdate", true); set(v) = p.edit().putBoolean("autoUpdate", v).apply()
    var frameStats: Boolean                                         // the frame-pacing line over the picture
        get() = p.getBoolean("frameStats", false); set(v) = p.edit().putBoolean("frameStats", v).apply()
}
