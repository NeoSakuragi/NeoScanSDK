package com.neoscan.player

import android.content.Context
import android.os.Build
import android.util.Log
import java.util.UUID
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/** Auto-fetch of the latest build: <base>/latest.json = {version, build, file, size, sha256} (examples/brawler
 *  `make publish-vps`), base = canneji.duckdns.org/brawler/download/ (public); every request carries X-Device /
 *  X-Android / X-App-Version / X-Rom-Version / X-Install-Id for the server's update log.
 *  A newer build than the one installed is downloaded next to the ROM, checked (size + sha256) and swapped in; any
 *  failure (offline, server down, bad file) keeps the cached ROM. Base URL: BuildConfig.ROM_URL, or another one set
 *  with `adb shell am start ... --es url <base>` (kept in the app's preferences). */
object RomFetch {
    private const val TAG = "NeoScanPlayer"

    fun configure(ctx: Context, url: String?) {
        if (url != null) ctx.getSharedPreferences("fetch", 0).edit().putString("url", url.trimEnd('/') + "/").apply()
    }

    /** blocking: call off the UI thread; [status] gets progress text; returns true when [rom] is usable */
    fun update(ctx: Context, rom: File, status: (String) -> Unit): Boolean {
        val prefs = ctx.getSharedPreferences("fetch", 0)
        val base = base(ctx)
        if (base == null) return rom.exists()
        val id = prefs.getString("install", null) ?: UUID.randomUUID().toString().also { prefs.edit().putString("install", it).apply() }
        val hdr = mapOf("X-Device" to "${Build.MANUFACTURER} ${Build.MODEL}", "X-Android" to "${Build.VERSION.RELEASE} (SDK ${Build.VERSION.SDK_INT})",
                        "X-App-Version" to BuildConfig.VERSION_NAME, "X-Rom-Version" to (if (rom.exists()) installed(ctx) else "none"),
                        "X-Install-Id" to id)
        try {
            val info = JSONObject(get(base + "latest.json", hdr).inputStream.use { it.readBytes() }
                .toString(Charsets.UTF_8))
            val build = info.getLong("build"); val version = info.optString("version", "?")
            if (rom.exists() && prefs.getLong("build", 0) >= build) return true
            val size = info.getLong("size"); val sha = info.getString("sha256")
            val tmp = File(rom.parentFile, rom.name + ".part")
            val md = MessageDigest.getInstance("SHA-256")
            val conn = get(base + info.getString("file"), hdr)
            conn.inputStream.use { inp -> tmp.outputStream().use { out ->
                val buf = ByteArray(1 shl 16); var done = 0L; var shown = -1L
                while (true) {
                    val n = inp.read(buf); if (n < 0) break
                    out.write(buf, 0, n); md.update(buf, 0, n); done += n
                    if (done * 20 / size != shown) { shown = done * 20 / size; status("Downloading v$version: ${done * 100 / size} %") }
                }
            } }
            val got = md.digest().joinToString("") { "%02x".format(it) }
            if (tmp.length() != size || got != sha) { tmp.delete(); Log.e(TAG, "fetch: bad file ($got)"); return rom.exists() }
            if (!tmp.renameTo(rom)) { tmp.delete(); return rom.exists() }
            prefs.edit().putLong("build", build).putString("version", version).apply()
            Log.i(TAG, "fetch: v$version (build $build) installed (${size / 1024} KB)")
        } catch (e: Exception) {
            Log.w(TAG, "fetch: ${e.message}; playing the cached ROM")
        }
        return rom.exists()
    }

    fun base(ctx: Context): String? = ctx.getSharedPreferences("fetch", 0).getString("url", null)
        ?: BuildConfig.ROM_URL.ifEmpty { null }?.trimEnd('/')?.plus("/")

    fun installed(ctx: Context): String = ctx.getSharedPreferences("fetch", 0).getString("version", null) ?: "?"

    private fun get(url: String, hdr: Map<String, String>): HttpURLConnection =
        (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 3000; readTimeout = 10000
            for ((k, v) in hdr) setRequestProperty(k, v)
            if (responseCode != 200) throw java.io.IOException("$url: HTTP $responseCode")
        }
}
