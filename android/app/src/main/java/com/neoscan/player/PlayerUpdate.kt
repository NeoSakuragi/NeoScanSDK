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

/** The app's self-update (Player 0.0.21; both apps since 0.0.42, docs/feedback.md "Roles and the two apps"). One code
 *  path, two sources of the offer ([offer]):
 *   - Brawler Dev (flavor dev): <base>/player.json = {version, code, file, size, sha256} next to latest.json, written by
 *     tools/brawler/publish_vps.sh (behind the Oros token); a player switched to the test channel (`adb shell am start
 *     -n com.neoscan.player/.MainActivity --es channel test`, `--es channel live` back) reads player-test.json.
 *   - Brawler (flavor brawler): the feedback service's GET me -> app {version, code, url, size, sha256} (the url with a
 *     24 h download ticket; tools/brawler/publish_app.sh). The same link is the browser fallback ([Info.link]).
 *  [check] runs at launch (MainActivity's poll thread), every hour while the game is open and from Settings' "Check for
 *  update": a newer versionCode is downloaded in the background (resumable: a Range request continues
 *  files/update/player-<code>.apk.part), its size and sha256 checked (when the server names them; else the HTTP
 *  length), then kept as player-<code>.apk = [ready]. Nothing interrupts the game: the update button blinks, the launch
 *  screen offers "Update" (which also downloads, with progress, when the background one has not finished). [install] =
 *  a PackageInstaller session (REQUEST_INSTALL_PACKAGES; the first time, one line and Android's "Install unknown apps"
 *  switch for this app, then it goes on by itself when the user comes back: [resume]); on Android 12+ it asks for no
 *  user action, so where the system allows it later updates go through silently, else Android shows its own
 *  confirmation (always on Android 10/11, the Huawei). If anything fails, the Brawler app offers its download link in
 *  the browser. After the install [Restart] opens the new app (or, where Android 10+ forbids that, its notification
 *  "installed: tap to play"); the login, settings, queued notes and the ROM are app data and stay. The update must be
 *  signed with the installed app's key: Brawler Dev = the build machine's debug key, Brawler = its release key
 *  (/data/brawler-share/signing.properties). */
object PlayerUpdate {
    private const val TAG = "NeoScanPlayer"
    /** [file] = the APK's absolute URL (the app's token goes with it), [link] = a URL the phone's browser can open
     *  without a token (the Brawler app's ticket link; "" for Brawler Dev), [size] / [sha] = 0 / "" when not given */
    class Info(val version: String, val code: Int, val file: String, val size: Long, val sha: String, val link: String = "")

    /** the newest app the server offers (any version), as the last [offer] read it */
    @Volatile var latest: Info? = null
    /** download progress (0..100) while one runs, else -1 */
    @Volatile var progress = -1
    /** the last check's or download's failure ("" = none) */
    @Volatile var error = ""
    /** the user was sent to "Install unknown apps": coming back with it on goes on with the install ([resume]) */
    @Volatile private var pendingInstall = false

    private fun prefs(ctx: Context) = ctx.getSharedPreferences("fetch", 0)
    fun channel(ctx: Context): String = prefs(ctx).getString("channel", "live")!!
    fun setChannel(ctx: Context, ch: String?) { if (ch != null) prefs(ctx).edit().putString("channel", if (ch == "test") "test" else "live").commit() }
    private fun dir(ctx: Context) = File(ctx.filesDir, "update").apply { mkdirs() }
    private fun apk(ctx: Context, code: Int) = File(dir(ctx), "player-$code.apk")
    private fun label(ctx: Context) = ctx.applicationInfo.loadLabel(ctx.packageManager).toString()

    /** the launch screen's line: downloaded / offered; the button */
    fun readyText(i: Info) = tr(R.string.pu_ready, i.version)
    fun offerText(i: Info) = tr(R.string.pu_offer, i.version)
    val ACTION get() = tr(R.string.pu_action)

    /** a newer app than this one is on the server (downloaded or not) */
    fun available(): Info? = latest?.takeIf { it.code > BuildConfig.VERSION_CODE }

    /** the downloaded, checked APK of a newer app, or null */
    fun ready(ctx: Context): Info? {
        val p = prefs(ctx); val code = p.getInt("upd_code", 0)
        if (code <= BuildConfig.VERSION_CODE || !apk(ctx, code).exists()) return null
        return Info(p.getString("upd_version", "?")!!, code, "", apk(ctx, code).length(), p.getString("upd_sha", "")!!,
            latest?.takeIf { it.code == code }?.link ?: "")
    }

    /** the files of an update already installed (or older): gone */
    fun cleanup(ctx: Context) {
        dir(ctx).listFiles()?.forEach { f ->
            val c = Regex("player-(\\d+)\\.apk").find(f.name)?.groupValues?.get(1)?.toIntOrNull() ?: 0
            if (c <= BuildConfig.VERSION_CODE) f.delete()
        }
    }

    private fun headers(ctx: Context) = mapOf("X-Install-Id" to (prefs(ctx).getString("install", null) ?: "?"),
        "X-App-Version" to BuildConfig.VERSION_NAME, "X-Poll" to "player")

    /** blocking (off the UI thread), no download: what the server offers -> [latest]; returns the newer one or null */
    fun offer(ctx: Context): Info? {
        val info = try {
            if (BuildConfig.DEV) {
                val base = RomFetch.base(ctx) ?: return null
                val json = if (channel(ctx) == "test") "player-test.json" else "player.json"
                val j = JSONObject(RomFetch.get(base + json, headers(ctx)).inputStream.use { it.readBytes() }.toString(Charsets.UTF_8))
                Info(j.getString("version"), j.getInt("code"), base + j.getString("file"), j.getLong("size"), j.getString("sha256"))
            } else {
                val me = Auth.me(ctx) ?: run { error = "check: offline"; return available() }
                val a = me.optJSONObject("app") ?: run { latest = null; error = ""; return null }
                val url = Auth.feedbackUrl(a.getString("url"))
                Info(a.optString("version", "?"), a.optInt("code", 0), url, a.optLong("size", 0), a.optString("sha256", ""), url)
            }
        } catch (e: Exception) { error = "check: ${e.message}"; Log.w(TAG, "player update: ${e.message}"); return available() }
        latest = info; error = ""
        return available()
    }

    /** blocking (off the UI thread): [offer], then a newer app is downloaded and checked. Returns the newer app ready
     *  to install, or null (up to date, offline, or the download failed: [error]) */
    @Synchronized fun check(ctx: Context): Info? {
        offer(ctx)
        val info = latest ?: return ready(ctx)
        if (info.code <= BuildConfig.VERSION_CODE) { cleanup(ctx); return null }
        ready(ctx)?.let { if (it.code == info.code && (it.sha == info.sha || info.sha.isEmpty())) return it }
        return if (download(ctx, info)) ready(ctx) else null
    }

    /** resumable: what the .part already holds is asked from its end (Range); 200 instead of 206 = from scratch. A
     *  server that names no size / sha256: the HTTP length is checked, no resume */
    private fun download(ctx: Context, info: Info): Boolean {
        val part = File(dir(ctx), "player-${info.code}.apk.part")
        val p = prefs(ctx); val hdr = headers(ctx)
        val id = info.sha.ifEmpty { "v${info.version}-${info.code}" }
        if (p.getString("upd_part_sha", null) != id || info.size <= 0) part.delete()   // another build under the same code
        p.edit().putString("upd_part_sha", id).commit()
        try {
            if (info.size > 0 && part.length() > info.size) part.delete()
            var size = info.size
            if (size <= 0 || part.length() < size) {
                val have = part.length()
                val c = RomFetch.get(info.file, if (have > 0) hdr + ("Range" to "bytes=$have-") else hdr)
                val append = have > 0 && c.responseCode == 206
                if (size <= 0) size = c.contentLengthLong
                var done = if (append) have else 0L
                progress = if (size > 0) (done * 100 / size).toInt() else 0
                c.inputStream.use { inp -> FileOutputStream(part, append).use { out ->
                    val buf = ByteArray(1 shl 16)
                    while (true) {
                        val n = inp.read(buf); if (n < 0) break
                        out.write(buf, 0, n); done += n; if (size > 0) progress = (done * 100 / size).toInt()
                    }
                } }
            }
            val md = MessageDigest.getInstance("SHA-256")
            part.inputStream().use { i -> val b = ByteArray(1 shl 16); while (true) { val n = i.read(b); if (n < 0) break; md.update(b, 0, n) } }
            val got = md.digest().joinToString("") { "%02x".format(it) }
            if ((size > 0 && part.length() != size) || (info.sha.isNotEmpty() && got != info.sha)) {
                val len = part.length(); part.delete()
                error = "download: bad file ($len bytes, sha256 ${got.take(12)})"; Log.e(TAG, "player update: $error"); return false
            }
            dir(ctx).listFiles()?.forEach { if (it != part) it.delete() }
            if (!part.renameTo(apk(ctx, info.code))) { error = "download: rename failed"; return false }
            p.edit().putInt("upd_code", info.code).putString("upd_version", info.version).putString("upd_sha", info.sha.ifEmpty { got })
                .remove("upd_failed").commit()
            Log.i(TAG, "player update: ${info.version} (code ${info.code}) downloaded and checked")
            error = ""; return true
        } catch (e: Exception) {
            error = "download: ${e.message}"; Log.w(TAG, "player update: ${e.message} (kept ${part.length()} bytes, resumed next time)"); return false
        } finally { progress = -1 }
    }

    /** the Update button, in every place: downloaded = install; offered = download now (the background one if it runs:
     *  [check] is synchronized; [progress] shows), then install; failed = the browser fallback */
    fun install(act: Activity) {
        val r = ready(act)
        if (r == null) {
            val a = available() ?: return
            android.widget.Toast.makeText(act, tr(R.string.pu_downloading, a.version), android.widget.Toast.LENGTH_SHORT).show()
            Thread {
                val got = check(act)
                act.runOnUiThread { if (act.isFinishing || act.isDestroyed) return@runOnUiThread
                    if (got != null) install(act) else failed(act, error.ifEmpty { tr(R.string.pu_dl_failed) }) }
            }.start()
            return
        }
        prefs(act).getString("upd_failed", null)?.takeIf { it.startsWith("${r.code}:") }?.let {
            prefs(act).edit().remove("upd_failed").commit(); failed(act, it.substringAfter(':'), retry = true); return }
        if (!act.packageManager.canRequestPackageInstalls()) {
            AlertDialog.Builder(act).setTitle(tr(R.string.pu_allow_title))
                .setMessage(tr(R.string.pu_allow_msg, label(act)))
                .setPositiveButton(tr(R.string.pu_open_setting)) { _, _ ->
                    pendingInstall = true
                    try { act.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + act.packageName))) }
                    catch (e: Exception) { pendingInstall = false; failed(act, tr(R.string.pu_no_setting)) } }
                .setNegativeButton(tr(R.string.build_later), null).show()
            return
        }
        if (askNotify(act)) return
        session(act, r)
    }

    /** onResume of the activities that offer Update: back from "Install unknown apps" with it on = install */
    fun resume(act: Activity) {
        if (!pendingInstall) return
        pendingInstall = false
        if (act.packageManager.canRequestPackageInstalls()) install(act)
    }

    /** the in-app path failed: say why; the Brawler app's download link in the browser, or try again */
    private fun failed(act: Activity, why: String, retry: Boolean = false) {
        val link = available()?.link ?: ""
        val b = AlertDialog.Builder(act).setTitle(tr(R.string.pu_not_installed)).setMessage(why)
        if (link.isNotEmpty()) b.setPositiveButton(tr(R.string.pu_open_browser)) { _, _ ->
            try { act.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(link)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
            catch (x: Exception) { android.widget.Toast.makeText(act, tr(R.string.pu_no_browser), android.widget.Toast.LENGTH_LONG).show() } }
        if (retry) b.setNeutralButton(tr(R.string.pu_try_again)) { _, _ -> ready(act)?.let { session(act, it) } }
        b.setNegativeButton(tr(R.string.pu_close), null).show()
    }

    private fun session(act: Activity, r: Info) = Thread {
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
                val status = PendingIntent.getBroadcast(act, id, Intent(act, Status::class.java).setPackage(act.packageName)
                    .putExtra("code", r.code), flags)
                Log.i(TAG, "player update: installing ${r.version} (session $id)")
                s.commit(status.intentSender)
            }
        } catch (e: Exception) {
            Log.e(TAG, "player update: install ${e.message}")
            act.runOnUiThread { if (!act.isFinishing) failed(act, tr(R.string.pu_refused, e.message)) }
        }
    }.start()

    /** the session's result: Android's confirmation when it wants one (the app is in front then, so it may open it), a
     *  failure shown and kept for the next Update tap (its browser fallback); success is [Restart]'s (this process is
     *  gone by then) */
    class Status : BroadcastReceiver() {
        override fun onReceive(ctx: Context, i: Intent) {
            Lang.init(ctx)
            val st = i.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
            val m = i.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE) ?: ""
            Log.i(TAG, "player update: status $st $m (running ${BuildConfig.VERSION_NAME})")
            when (st) {
                PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                    @Suppress("DEPRECATION") i.getParcelableExtra<Intent>(Intent.EXTRA_INTENT)?.let { ctx.startActivity(it.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
                }
                PackageInstaller.STATUS_SUCCESS -> {}
                PackageInstaller.STATUS_FAILURE_ABORTED -> android.widget.Toast.makeText(ctx, tr(R.string.pu_cancelled), android.widget.Toast.LENGTH_SHORT).show()
                else -> {
                    val why = tr(R.string.pu_not_installed_why, m.ifEmpty { "status $st" })
                    ctx.getSharedPreferences("fetch", 0).edit().putString("upd_failed", "${i.getIntExtra("code", 0)}:$why").apply()
                    android.widget.Toast.makeText(ctx, tr(R.string.pu_not_installed) + ": " + m.ifEmpty { "status $st" }, android.widget.Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    /** the new app is in place (MY_PACKAGE_REPLACED, in the new process): open it. Android 10+ refuses an activity
     *  start from the background (tested: Android 14 blocks it from this receiver and from the session's own
     *  PendingIntent), so a notification "<app> 0.0.x installed: tap to play" goes up too; the direct start works where
     *  Android still allows it (9 and older). */
    class Restart : BroadcastReceiver() {
        override fun onReceive(ctx: Context, i: Intent) {
            if (i.action != Intent.ACTION_MY_PACKAGE_REPLACED) return
            Lang.init(ctx)
            Log.i(TAG, "player update: now ${BuildConfig.VERSION_NAME}")
            val open = ctx.packageManager.getLaunchIntentForPackage(ctx.packageName)!!
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
            try { ctx.startActivity(open) } catch (e: Exception) { Log.w(TAG, "player update: restart ${e.message}") }
            val nm = ctx.getSystemService(android.app.NotificationManager::class.java)
            nm.createNotificationChannel(android.app.NotificationChannel("update", tr(R.string.pu_channel), android.app.NotificationManager.IMPORTANCE_HIGH))
            val pi = PendingIntent.getActivity(ctx, 0, open, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
            nm.notify(1, android.app.Notification.Builder(ctx, "update").setSmallIcon(android.R.drawable.stat_sys_download_done)
                .setContentTitle(tr(R.string.pu_installed, label(ctx), BuildConfig.VERSION_NAME)).setContentText(tr(R.string.pu_tap_play))
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
