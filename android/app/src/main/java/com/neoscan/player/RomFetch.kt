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
 *  `make publish-vps`), base = canneji.duckdns.org/brawler/download/ (behind the Oros login since 0.0.15: [Auth]); every request carries X-Device /
 *  X-Android / X-App-Version / X-Rom-Version / X-Install-Id for the server's update log.
 *  A newer build than the one installed is downloaded next to the ROM, checked (size + sha256) and swapped in; any
 *  failure (offline, server down, bad file) keeps the cached ROM. Base URL: BuildConfig.ROM_URL, or another one set
 *  with `adb shell am start ... --es url <base>` (kept in the app's preferences). */
object RomFetch {
    private const val TAG = "NeoScanPlayer"

    fun configure(ctx: Context, url: String?) {
        this.ctx = ctx.applicationContext
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
            // commit, not apply: the update button restarts the process right after (exit(0)) and an async write was
            // lost, so the restarted player fetched the same build again
            prefs.edit().putLong("build", build).putString("version", version).putString("sha256", sha)
                .putString("id_key", key(rom)).putString("id_sha", sha).putString("id_version", version).putLong("id_build", build).commit()
            Log.i(TAG, "fetch: v$version (build $build) installed (${size / 1024} KB)")
        } catch (e: Exception) {
            Log.w(TAG, "fetch: ${e.message}; playing the cached ROM")
        }
        return rom.exists()
    }

    /** the server's latest build number, -1 when it cannot be asked (offline, no URL); light: latest.json only */
    fun latest(ctx: Context): Long {
        val base = base(ctx) ?: return -1
        val id = ctx.getSharedPreferences("fetch", 0).getString("install", null) ?: "?"
        return try {
            val c = get(base + "latest.json", mapOf("X-Install-Id" to id, "X-Rom-Version" to installed(ctx), "X-Poll" to "1"))
            JSONObject(c.inputStream.use { it.readBytes() }.toString(Charsets.UTF_8)).getLong("build")
        } catch (e: Exception) { -1 }
    }

    /** the build number of the last download (the update decision: is the server's newer?) */
    fun installedBuild(ctx: Context): Long = ctx.getSharedPreferences("fetch", 0).getLong("build", 0)

    fun base(ctx: Context): String? = ctx.getSharedPreferences("fetch", 0).getString("url", null)
        ?: BuildConfig.ROM_URL.ifEmpty { null }?.trimEnd('/')?.plus("/")

    /** the version of the game actually in brawler.neo (Player 0.0.19): the "version" pref alone went stale when a ROM
     *  was pushed by hand (it said 0.0.74 under a 0.0.77 ROM, so the list and the notes' game_version were wrong) */
    fun installed(ctx: Context): String = loaded(ctx).version
    /** the build number of the ROM actually there: the download's when its sha256 matches, else 0 (pushed by hand) */
    fun loadedBuild(ctx: Context): Long = loaded(ctx).build

    class Loaded(val sha: String, val version: String, val build: Long)
    fun romFile(ctx: Context) = File(ctx.getExternalFilesDir(null), "brawler.neo")
    private fun key(f: File) = "${f.length()}:${f.lastModified()}"
    /** who the ROM file is, worked out once per file (size + mtime; a download records it directly): its sha256 equal to
     *  the downloaded one = that download's version and build; any other file = the version on its own title screen
     *  ("V" GAME_VERSION in the P ROM), build 0. Hashes the file (~40 MB) on a new file: first call off the UI thread. */
    @Synchronized fun loaded(ctx: Context): Loaded {
        val rom = romFile(ctx); val p = ctx.getSharedPreferences("fetch", 0)
        if (!rom.exists()) return Loaded("", "?", 0)
        if (p.getString("id_key", null) == key(rom))
            return Loaded(p.getString("id_sha", "")!!, p.getString("id_version", "?")!!, p.getLong("id_build", 0))
        val sha = Feedback.sha(rom)
        val l = if (sha == p.getString("sha256", null)) Loaded(sha, p.getString("version", "?")!!, p.getLong("build", 0))
                else Loaded(sha, versionInRom(rom) ?: "?", 0)
        p.edit().putString("id_key", key(rom)).putString("id_sha", l.sha).putString("id_version", l.version).putLong("id_build", l.build).apply()
        Log.i(TAG, "rom: v${l.version} build ${l.build} sha ${l.sha.take(12)}")
        return l
    }

    /** the title screen's "V0.0.77" in the P ROM (.neo: P size at header 0x04, P from 0x1000, 16-bit words byte-swapped) */
    fun versionInRom(rom: File): String? = try {
        java.io.RandomAccessFile(rom, "r").use { f ->
            val h = ByteArray(8); f.readFully(h)
            val n = (h[4].toInt() and 255) or (h[5].toInt() and 255 shl 8) or (h[6].toInt() and 255 shl 16) or (h[7].toInt() and 255 shl 24)
            val b = ByteArray(minOf(n, 8 shl 20)); f.seek(4096); f.readFully(b)
            for (i in 0 until b.size - 1 step 2) { val t = b[i]; b[i] = b[i + 1]; b[i + 1] = t }
            Regex("V(\\d+\\.\\d+\\.\\d+)\u0000").find(String(b, Charsets.ISO_8859_1))?.groupValues?.get(1)
        }
    } catch (e: Exception) { Log.w(TAG, "rom version: ${e.message}"); null }

    /** the builds are behind the Oros login since Player 0.0.15: every request carries the token ([Auth]) */
    private var ctx: Context? = null
    private fun get(url: String, hdr: Map<String, String>): HttpURLConnection {
        val open = { tok: String? -> (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 3000; readTimeout = 10000
            for ((k, v) in hdr) setRequestProperty(k, v)
            if (tok != null) setRequestProperty("Authorization", "Bearer $tok")
        } }
        val c = ctx?.let { Auth.call(it, open) } ?: open(null)
        if (c.responseCode != 200) throw java.io.IOException("$url: HTTP ${c.responseCode}")
        return c
    }
}
