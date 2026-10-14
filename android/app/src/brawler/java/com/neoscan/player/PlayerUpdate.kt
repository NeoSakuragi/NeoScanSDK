package com.neoscan.player

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri

/** THE BRAWLER APP (flavor "brawler"): no self-install. Brawler Dev's PlayerUpdate (src/dev: an APK downloaded and
 *  installed through a PackageInstaller session, with REQUEST_INSTALL_PACKAGES) is not compiled into this app, nor its
 *  permissions (src/brawler/AndroidManifest.xml). Instead: the feedback service's GET me names the newest Brawler APK
 *  ({version, code, url}, the url with a 24 h download ticket); a higher versionCode than this app's = "A new version
 *  of the app is available", and Download opens that link in the phone's browser: Android's own installer does the
 *  rest (the user confirms it there). Same API as Brawler Dev's, so MainActivity has one code path. */
object PlayerUpdate {
    class Info(val version: String, val code: Int, val file: String, val size: Long, val sha: String)
    @Volatile var latest: Info? = null
    @Volatile var progress = -1
    @Volatile var error = ""
    const val NOTIFY_REQ = 7
    /** the launch screen's line and its button */
    fun readyText(i: Info) = "A new version of the app is available (${i.version})"
    const val ACTION = "Download"
    fun channel(ctx: Context): String = "live"
    fun setChannel(ctx: Context, ch: String?) {}
    fun available(): Info? = latest?.takeIf { it.code > BuildConfig.VERSION_CODE }
    fun ready(ctx: Context): Info? = available()
    fun cleanup(ctx: Context) {}
    /** blocking: asks GET me (Auth.me) for the newest Brawler APK */
    fun check(ctx: Context): Info? {
        val app = Auth.me(ctx)?.optJSONObject("app") ?: return available()
        val url = Auth.feedbackUrl(app.optString("url"))
        latest = Info(app.optString("version", "?"), app.optInt("code", 0), url, 0, "")
        return available()
    }
    /** opens the download link in the browser (Android's installer takes the APK from there) */
    fun install(act: Activity) {
        val i = available() ?: return
        try { act.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(i.file)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
        catch (x: Exception) { error = "No browser to open the download" }
    }
}
