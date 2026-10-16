package com.neoscan.player

import android.content.Context
import android.content.res.Configuration
import java.util.Locale

/** THE APP'S LANGUAGE (app 0.0.44, both apps): English or French, whatever the phone's locale. Every app string is an
 *  Android string resource (res/values = English, res/values-fr = French); the game itself (the Neo Geo ROM) stays in
 *  English. The choice: the first launch's picker (LoginActivity, before the sign-in), later the profile menu's
 *  "Language / Langue" (the app restarts in it). Stored in the "settings" prefs as "language" ("en" | "fr"; none yet =
 *  the phone's own, French if it is French, else English) and synced per account with the other settings
 *  ([SettingsSync]: the feedback service's GET / PUT settings). Applied by a Configuration wrapper on every activity's
 *  base context ([wrap], attachBaseContext) and on the app context the objects use ([tr]). */
object Lang {
    val CODES = listOf("en", "fr")
    @Volatile private var res: Context? = null

    /** the chosen language, null = never chosen (the first launch shows the picker) */
    fun chosen(ctx: Context): String? = ctx.getSharedPreferences("settings", 0).getString("language", null)?.takeIf { it in CODES }
    /** the language in use: the chosen one, else the phone's (fr or en) */
    fun current(ctx: Context): String = chosen(ctx) ?: if (Locale.getDefault().language == "fr") "fr" else "en"

    /** a new choice: stored, marked changed (the settings' newest-wins sync), sent to the account when signed in */
    fun set(ctx: Context, code: String) {
        ctx.getSharedPreferences("settings", 0).edit().putString("language", code).commit()
        SettingsSync.touched(ctx); res = null; init(ctx)
    }

    /** the base context in the app's language (each activity's attachBaseContext) */
    fun wrap(base: Context): Context {
        val c = Configuration(base.resources.configuration)
        c.setLocale(Locale(current(base)))
        return base.createConfigurationContext(c)
    }

    fun init(ctx: Context) { if (res == null) res = wrap(ctx.applicationContext ?: ctx) }
    fun s(id: Int, vararg a: Any?): String = (res ?: throw IllegalStateException("Lang.init first")).getString(id, *a)
}

/** an app string in the app's language (objects without an activity: Auth, PlayerUpdate, Feedback ...) */
fun tr(id: Int, vararg a: Any?): String = Lang.s(id, *a)
