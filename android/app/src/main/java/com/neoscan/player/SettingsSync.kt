package com.neoscan.player

import android.content.Context
import android.util.Log
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/** SETTINGS PER ACCOUNT (app 0.0.44, both apps): the app's settings (the "settings" prefs: the language, and in Brawler
 *  Dev the display / controls / system ones of [Prefs]) are kept on the feedback service per Oros account (GET / PUT
 *  <FEEDBACK_URL>settings {settings, updated (ms)}, tools/feedback/server.py) and restored after a sign-in on any
 *  device. Newest wins: every local change stamps "settings_meta" updated = now ([touched]); [pull] after a sign-in and
 *  at every start takes the server's when it is newer, else sends ours (a first-launch language pick, made before the
 *  sign-in, is newer than nothing and goes up). Offline: nothing changes, the next start tries again. */
object SettingsSync {
    private const val TAG = "NeoScanPlayer"
    private val KEYS = setOf("language", "orientation", "filter", "aspect", "scale", "scanlines", "opacity", "size", "vibrate",
                             "autoUpdate", "system", "frameStats", "touch")

    private fun meta(ctx: Context) = ctx.getSharedPreferences("settings_meta", 0)
    fun touched(ctx: Context) { meta(ctx).edit().putLong("updated", System.currentTimeMillis()).commit(); if (Auth.user(ctx) != null) push(ctx) }

    private fun local(ctx: Context): JSONObject {
        val j = JSONObject()
        for ((k, v) in ctx.getSharedPreferences("settings", 0).all) if (k in KEYS && (v is String || v is Int || v is Boolean)) j.put(k, v)
        return j
    }

    /** off the UI thread: true when the server's settings were newer and are now the local ones (the language may have changed) */
    fun pull(ctx: Context): Boolean {
        val (code, j) = call(ctx, "GET", null)
        val mine = meta(ctx).getLong("updated", 0)
        if (code == 200 && j != null && j.optLong("updated") > mine) {
            val s = j.optJSONObject("settings") ?: return false
            val before = Lang.chosen(ctx)
            val e = ctx.getSharedPreferences("settings", 0).edit()
            for (k in s.keys()) if (k in KEYS) when (val v = s.get(k)) { is Boolean -> e.putBoolean(k, v); is Int -> e.putInt(k, v); is String -> e.putString(k, v) }
            e.commit(); meta(ctx).edit().putLong("updated", j.optLong("updated")).commit()
            Log.i(TAG, "settings: the account's restored (language ${s.optString("language")})")
            return Lang.chosen(ctx) != before
        }
        if ((code == 404 && mine > 0) || (code == 200 && mine > (j?.optLong("updated") ?: 0))) sendNow(ctx)   // ours is newer (or the first)
        return false
    }

    fun push(ctx: Context) { Thread { sendNow(ctx) }.start() }

    private fun sendNow(ctx: Context) {
        val body = JSONObject().put("settings", local(ctx)).put("updated", meta(ctx).getLong("updated", System.currentTimeMillis()))
        val (code, _) = call(ctx, "PUT", body)
        Log.i(TAG, "settings: sent (HTTP $code)")
    }

    private fun call(ctx: Context, method: String, body: JSONObject?): Pair<Int, JSONObject?> = try {
        val u = URL(Auth.feedbackUrl("settings"))
        val c = Auth.call(ctx) { tok -> (u.openConnection() as HttpURLConnection).apply {
            connectTimeout = 8000; readTimeout = 15000; requestMethod = method
            setRequestProperty("X-App-Version", BuildConfig.VERSION_NAME)
            if (tok != null) setRequestProperty("Authorization", "Bearer $tok")
            if (body != null) { doOutput = true; setRequestProperty("Content-Type", "application/json")
                outputStream.use { it.write(body.toString().toByteArray()) } }
        } }
        val code = c.responseCode
        val t = (if (code in 200..299) c.inputStream else c.errorStream)?.use { it.readBytes().toString(Charsets.UTF_8) }
        code to (t?.let { try { JSONObject(it) } catch (x: Exception) { null } })
    } catch (x: Exception) { Log.w(TAG, "settings: ${x.message}"); -1 to null }
}
