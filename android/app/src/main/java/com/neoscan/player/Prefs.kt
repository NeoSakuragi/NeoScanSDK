package com.neoscan.player

import android.content.Context

/** Player settings (SharedPreferences "settings"), read by MainActivity on every resume and applied live.
 *  THE BRAWLER (TESTER) APP (0.0.37, BuildConfig.DEV false): no settings page, every setting FIXED: its default, except
 *  landscape and 50 % scanlines (what a stored value says is ignored). The touch controls ([touch], the profile menu)
 *  are the one setting both apps keep. */
class Prefs(ctx: Context) {
    companion object { @Volatile var dirty = false }               // a setting changed: SettingsActivity sends them (SettingsSync, 0.0.44)
    private val p = ctx.getSharedPreferences("settings", 0)
    private val fixed = !BuildConfig.DEV
    var orientation: String                                         // auto | portrait | landscape
        get() = if (fixed) "landscape" else p.getString("orientation", "auto")!!; set(v) { p.edit().putString("orientation", v).apply(); dirty = true }
    var filter: String                                              // sharp | smooth | scanlines | subpixel
        get() = if (fixed) "scanlines" else p.getString("filter", "sharp")!!; set(v) { p.edit().putString("filter", v).apply(); dirty = true }
    var aspect: String                                              // square (pixel-exact) | 4:3 (plain rectangle)
        get() = if (fixed) "square" else p.getString("aspect", "square")!!; set(v) { p.edit().putString("aspect", v).apply(); dirty = true }
    var scale: String                                               // fit | integer
        get() = if (fixed) "fit" else p.getString("scale", "fit")!!; set(v) { p.edit().putString("scale", v).apply(); dirty = true }
    var scanlines: Int                                              // scanline darkness, %
        get() = if (fixed) 50 else p.getInt("scanlines", 50); set(v) { p.edit().putInt("scanlines", v).apply(); dirty = true }
    var opacity: Int                                                // landscape controls over the picture, %
        get() = if (fixed) 45 else p.getInt("opacity", 45); set(v) { p.edit().putInt("opacity", v).apply(); dirty = true }
    var size: Int                                                   // touch controls, % of the default size
        get() = if (fixed) 100 else p.getInt("size", 100); set(v) { p.edit().putInt("size", v).apply(); dirty = true }
    var vibrate: Boolean
        get() = if (fixed) true else p.getBoolean("vibrate", true); set(v) { p.edit().putBoolean("vibrate", v).apply(); dirty = true }
    var autoUpdate: Boolean                                         // fetch a newer build on launch
        get() = if (fixed) true else p.getBoolean("autoUpdate", true); set(v) { p.edit().putBoolean("autoUpdate", v).apply(); dirty = true }
    var system: String                                              // arcade (MVS hardware) | console (AES)
        get() = if (fixed) "arcade" else p.getString("system", "arcade")!!; set(v) { p.edit().putString("system", v).apply(); dirty = true }
    var frameStats: Boolean                                         // the frame-pacing line over the picture
        get() = if (fixed) false else p.getBoolean("frameStats", false); set(v) { p.edit().putBoolean("frameStats", v).apply(); dirty = true }
    var touch: String                                               // touch controls (0.0.45, both apps, the profile menu): auto | show | hide
        get() = p.getString("touch", "auto")!!.takeIf { it in Gamepads.MODES } ?: "auto"; set(v) { p.edit().putString("touch", v).commit(); dirty = true }
}
