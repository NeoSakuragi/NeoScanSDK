package com.neoscan.player

import android.app.Activity
import android.app.AlertDialog
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.util.Log
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest

/** The player's self-update (Player 0.0.21). The server (tools/brawler/publish_vps.sh) writes <base>/player.json =
 *  {version, code, file, size, sha256} next to latest.json whenever an APK is published; a player switched to the test
 *  channel (`adb shell am start -n com.neoscan.player/.MainActivity --es channel test`, `--es channel live` back) reads
 *  player-test.json instead. [check] runs at launch, every hour while the game is open (MainActivity's poll thread) and
 *  from Settings' "Check for update": a newer versionCode is downloaded in the background (the Oros token, as the ROM;
 *  resumable: a Range request continues files/update/player-<code>.apk.part), its size and sha256 checked, then kept as
 *  player-<code>.apk = [ready]. Nothing interrupts the game: the update button blinks, the launch screen and Settings
 *  offer "Update". [install] = a PackageInstaller session (REQUEST_INSTALL_PACKAGES; the first time, a guide to
 *  Android's "Install unknown apps" switch); on Android 12+ it asks for no user action, so where the system allows it
 *  (Android 12+, the player installed it itself) later updates go through silently, else Android shows its own
 *  confirmation (always on Android 10/11, the Huawei). After the install [Restart] opens the new player (or, where
 *  Android 10+ forbids that, its notification "installed: tap to play"); the login, settings, queued notes and the ROM are app data and stay. Same signing key as every build so
 *  far: the debug key of the build machine (~/.android/debug.keystore, docs/feedback.md). */
object PlayerUpdate {
    private const val TAG = "NeoScanPlayer"
    class Info(val version: String, val code: Int, val file: String, val size: Long, val sha: String)

    /** the newest player the server offers (any version), as the last [check] read it */
    @Volatile var latest: Info? = null
    /** download progress (0..100) while one runs, else -1 */
    @Volatile var progress = -1
    /** the last check's or download's failure, for Settings ("" = none) */
    @Volatile var error = ""

    private fun prefs(ctx: Context) = ctx.getSharedPreferences("fetch", 0)
    fun channel(ctx: Context): String = prefs(ctx).getString("channel", "live")!!
    fun setChannel(ctx: Context, ch: String?) { if (ch != null) prefs(ctx).edit().putString("channel", if (ch == "test") "test" else "live").commit() }
    private fun dir(ctx: Context) = File(ctx.filesDir, "update").apply { mkdirs() }
    private fun apk(ctx: Context, code: Int) = File(dir(ctx), "player-$code.apk")

    /** a newer player than this one is on the server (downloaded or not) */
    fun available(): Info? = latest?.takeIf { it.code > BuildConfig.VERSION_CODE }

    /** the downloaded, checked APK of a newer player, or null */
    fun ready(ctx: Context): Info? {
        val p = prefs(ctx); val code = p.getInt("upd_code", 0)
        if (code <= BuildConfig.VERSION_CODE || !apk(ctx, code).exists()) return null
        return Info(p.getString("upd_version", "?")!!, code, "", apk(ctx, code).length(), p.getString("upd_sha", "")!!)
    }

    /** the files of an update already installed (or older): gone */
    fun cleanup(ctx: Context) {
        dir(ctx).listFiles()?.forEach { f ->
            val c = Regex("player-(\\d+)\\.apk").find(f.name)?.groupValues?.get(1)?.toIntOrNull() ?: 0
            if (c <= BuildConfig.VERSION_CODE) f.delete()
        }
    }

    /** blocking (off the UI thread): read player.json; a newer player is downloaded and checked. Returns the newer
     *  player ready to install, or null (up to date, offline, or the download failed: [error]) */
    @Synchronized fun check(ctx: Context): Info? {
        val base = RomFetch.base(ctx) ?: return null
        val json = if (channel(ctx) == "test") "player-test.json" else "player.json"
        val id = prefs(ctx).getString("install", null) ?: "?"
        val hdr = mapOf("X-Install-Id" to id, "X-App-Version" to BuildConfig.VERSION_NAME, "X-Poll" to "player")
        val info = try {
            val j = JSONObject(RomFetch.get(base + json, hdr).inputStream.use { it.readBytes() }.toString(Charsets.UTF_8))
            Info(j.getString("version"), j.getInt("code"), j.getString("file"), j.getLong("size"), j.getString("sha256"))
        } catch (e: Exception) { error = "check: ${e.message}"; Log.w(TAG, "player update: ${e.message}"); return ready(ctx) }
        latest = info; error = ""
        if (info.code <= BuildConfig.VERSION_CODE) { cleanup(ctx); return null }
        ready(ctx)?.let { if (it.code == info.code && it.sha == info.sha) return it }
        return if (download(ctx, base, info, hdr)) ready(ctx) else null
    }

    /** resumable: what the .part already holds is asked from its end (Range); 200 instead of 206 = from scratch */
    private fun download(ctx: Context, base: String, info: Info, hdr: Map<String, String>): Boolean {
        val part = File(dir(ctx), "player-${info.code}.apk.part")
        val p = prefs(ctx)
        if (p.getString("upd_part_sha", null) != info.sha) part.delete()       // another build under the same code
        p.edit().putString("upd_part_sha", info.sha).commit()
        try {
            if (part.length() > info.size) part.delete()
            if (part.length() < info.size) {
                val have = part.length()
                val c = RomFetch.get(base + info.file, if (have > 0) hdr + ("Range" to "bytes=$have-") else hdr)
                val append = have > 0 && c.responseCode == 206
                var done = if (append) have else 0L
                progress = (done * 100 / info.size).toInt()
                c.inputStream.use { inp -> FileOutputStream(part, append).use { out ->
                    val buf = ByteArray(1 shl 16)
                    while (true) {
                        val n = inp.read(buf); if (n < 0) break
                        out.write(buf, 0, n); done += n; progress = (done * 100 / info.size).toInt()
                    }
                } }
            }
            val md = MessageDigest.getInstance("SHA-256")
            part.inputStream().use { i -> val b = ByteArray(1 shl 16); while (true) { val n = i.read(b); if (n < 0) break; md.update(b, 0, n) } }
            val got = md.digest().joinToString("") { "%02x".format(it) }
            if (part.length() != info.size || got != info.sha) {
                part.delete(); error = "download: bad file (${part.length()} bytes, sha256 ${got.take(12)})"; Log.e(TAG, "player update: $error"); return false
            }
            dir(ctx).listFiles()?.forEach { if (it != part) it.delete() }
            if (!part.renameTo(apk(ctx, info.code))) { error = "download: rename failed"; return false }
            p.edit().putInt("upd_code", info.code).putString("upd_version", info.version).putString("upd_sha", info.sha).commit()
            Log.i(TAG, "player update: ${info.version} (code ${info.code}) downloaded and checked")
            error = ""; return true
        } catch (e: Exception) {
            error = "download: ${e.message}"; Log.w(TAG, "player update: ${e.message} (kept ${part.length()} bytes, resumed next time)"); return false
        } finally { progress = -1 }
    }

    /** the Update button: Android's permission first (a guide to it, once per tap while it is off), then the session */
    fun install(act: Activity) {
        val r = ready(act) ?: return
        if (!act.packageManager.canRequestPackageInstalls()) {
            AlertDialog.Builder(act).setTitle("Allow the player to update itself")
                .setMessage("Android asks once: on the next screen turn on \"Allow from this source\" for NeoScan Player, " +
                            "then come back and tap Update again.\n\nThe update keeps your login, settings, notes and the game.")
                .setPositiveButton("Open the setting") { _, _ ->
                    act.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + act.packageName))) }
                .setNegativeButton("Later", null).show()
            return
        }
        if (askNotify(act)) return
        Thread {
            try {
                val pi = act.packageManager.packageInstaller
                val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL).apply {
                    setAppPackageName(act.packageName)
                    if (Build.VERSION.SDK_INT >= 31) setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED)
                }
                val id = pi.createSession(params)
                pi.openSession(id).use { s ->
                    s.openWrite("player.apk", 0, r.size).use { out -> apk(act, r.code).inputStream().use { it.copyTo(out) }; s.fsync(out) }
                    val flags = PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0)
                    val status = PendingIntent.getBroadcast(act, id, Intent(act, Status::class.java).setPackage(act.packageName), flags)
                    Log.i(TAG, "player update: installing ${r.version} (session $id)")
                    s.commit(status.intentSender)
                }
            } catch (e: Exception) {
                Log.e(TAG, "player update: install ${e.message}")
                act.runOnUiThread { android.widget.Toast.makeText(act, "Update failed: ${e.message}", android.widget.Toast.LENGTH_LONG).show() }
            }
        }.start()
    }

    /** the session's result: Android's confirmation when it wants one (the player is in front then, so it may open
     *  it), a failure shown; success is [Restart]'s (this process is gone by then) */
    class Status : BroadcastReceiver() {
        override fun onReceive(ctx: Context, i: Intent) {
            val st = i.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
            val m = i.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE) ?: ""
            Log.i(TAG, "player update: status $st $m (running ${BuildConfig.VERSION_NAME})")
            when (st) {
                PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                    @Suppress("DEPRECATION") i.getParcelableExtra<Intent>(Intent.EXTRA_INTENT)?.let { ctx.startActivity(it.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
                }
                PackageInstaller.STATUS_SUCCESS -> {}
                else -> android.widget.Toast.makeText(ctx, "Update not installed: ${m.ifEmpty { "status $st" }}", android.widget.Toast.LENGTH_LONG).show()
            }
        }
    }

    /** the new player is in place (MY_PACKAGE_REPLACED, in the new process): open it. Android 10+ refuses an activity
     *  start from the background (tested: Android 14 blocks it from this receiver and from the session's own
     *  PendingIntent), so a notification "Player 0.0.x installed: tap to play" goes up too; the direct start works
     *  where Android still allows it (9 and older). */
    class Restart : BroadcastReceiver() {
        override fun onReceive(ctx: Context, i: Intent) {
            if (i.action != Intent.ACTION_MY_PACKAGE_REPLACED) return
            Log.i(TAG, "player update: now ${BuildConfig.VERSION_NAME}")
            val open = ctx.packageManager.getLaunchIntentForPackage(ctx.packageName)!!
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
            try { ctx.startActivity(open) } catch (e: Exception) { Log.w(TAG, "player update: restart ${e.message}") }
            val nm = ctx.getSystemService(android.app.NotificationManager::class.java)
            nm.createNotificationChannel(android.app.NotificationChannel("update", "Player updates", android.app.NotificationManager.IMPORTANCE_HIGH))
            val pi = PendingIntent.getActivity(ctx, 0, open, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
            nm.notify(1, android.app.Notification.Builder(ctx, "update").setSmallIcon(android.R.drawable.stat_sys_download_done)
                .setContentTitle("NeoScan Player ${BuildConfig.VERSION_NAME} installed").setContentText("Tap to play")
                .setContentIntent(pi).setAutoCancel(true).build())
        }
    }

    /** Android 13+: the notification above needs his OK, asked once, the first time he taps Update; [install] goes on
     *  from the activity's onRequestPermissionsResult (request code [NOTIFY_REQ]) */
    const val NOTIFY_REQ = 7
    private fun askNotify(act: Activity): Boolean {
        if (Build.VERSION.SDK_INT < 33 || act.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) ==
            android.content.pm.PackageManager.PERMISSION_GRANTED) return false
        val p = prefs(act); if (p.getBoolean("notifyAsked", false)) return false
        p.edit().putBoolean("notifyAsked", true).commit()
        act.requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), NOTIFY_REQ); return true
    }
}
