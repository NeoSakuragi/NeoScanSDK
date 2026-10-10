package com.neoscan.player

import android.annotation.SuppressLint
import android.graphics.Color
import android.graphics.Rect
import android.graphics.drawable.GradientDrawable
import android.util.Log
import android.view.Gravity
import android.view.View
import android.webkit.ConsoleMessage
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.TextView
import java.net.HttpURLConnection
import java.net.URL

/** THE ASSEMBLY IN THE PLAYER (0.0.32, admin, Bruno 2026-10-10: "implement the assembly page within the player as
 *  well (not the workshop) for quick tweaks within the app"). ONE PATH: not a second sheet in Kotlin, the SAME web
 *  Assembly page in a WebView next to the running game: lab.html?f=<fighter>&tab=assembly&embed=1 (the unified Lab,
 *  compact) once the site has it, the arbitration sheet arbitrage.html?f=<fighter> until then (a probe picks). The page
 *  sends every change to the live config by itself; the game takes it through the lab's own poll (CharacterLab), the
 *  source of truth. A BRIDGE only makes it quicker: `window.NeoScanPlayer.configSent(fighter, rev)` (the page may call
 *  it; the Player also wraps the page's fetch so a PUT .../lab/config/<f> calls it) -> the lab polls at once.
 *  SIGN-IN: the page reads the Oros cookie (oros_token = the same JWT /api/login gives, Oros auth.go), so the Player's
 *  own token goes into the WebView's CookieManager for the site; no password is asked or kept here. A trip to the
 *  login page = the token was refused: renewed once (Auth.refresh), else a message, never the login form.
 *  LAYOUT (CharacterLab.place gives the rect): portrait = under the lab's strip (the picture stays on top, the pad's
 *  controls hidden), landscape = the right side (Screen.assemblyW: the picture moves left, the pad hidden). */
@SuppressLint("SetJavaScriptEnabled")
class Assembly(private val act: MainActivity, private val root: FrameLayout, private val sent: (String, Int) -> Unit) {
    private val dp = act.resources.displayMetrics.density
    private val site = URL(BuildConfig.LAB_WEB_URL)                         // https://canneji.duckdns.org/brawler-lab/
    private val origin = "${site.protocol}://${site.host}"
    private var frame: FrameLayout? = null
    private var web: WebView? = null
    private var msg: TextView? = null
    private var loaded: String? = null                                       // the URL in the WebView
    private var unified: Boolean? = null                                     // the site has lab.html (probe, once a session)
    private var retried = false
    var open = false; private set

    /** the panel over [r] (root coordinates), the page of [fighter] (loaded once per fighter, kept while hidden) */
    fun show(fighter: String, r: Rect) {
        open = true
        val f = frame ?: build()
        f.visibility = View.VISIBLE
        place(r)
        Thread {
            val tok = Auth.token(act)
            if (unified == null) unified = probe(tok)
            act.runOnUiThread {
                if (!open) return@runOnUiThread
                if (tok == null) { say("Not signed in: the Player's Oros sign-in is needed (Settings)."); return@runOnUiThread }
                cookie(tok)
                val u = url(fighter)
                if (u != loaded) { loaded = u; retried = false; say("Loading the Assembly of ${fighter.uppercase()}..."); web?.loadUrl(u) }
            }
        }.start()
    }

    fun hide() { open = false; frame?.visibility = View.GONE }

    fun place(r: Rect) {
        val f = frame ?: return
        f.layoutParams = FrameLayout.LayoutParams(r.width(), r.height(), Gravity.LEFT or Gravity.TOP).apply { leftMargin = r.left; topMargin = r.top }
        f.post { val p = IntArray(2); f.getLocationOnScreen(p); Log.i(TAG, "assembly ${p[0]},${p[1]} - ${p[0] + f.width},${p[1] + f.height} ($loaded)") }
    }

    private fun url(f: String) = if (unified == true) URL(site, "lab.html?f=$f&tab=assembly&embed=1").toString()
                                 else URL(site, "arbitrage.html?f=$f").toString()

    /** lab.html served (200, not a redirect to the login) = the unified Lab is deployed */
    private fun probe(tok: String?): Boolean = try {
        val c = (URL(site, "lab.html").openConnection() as HttpURLConnection).apply {
            requestMethod = "HEAD"; instanceFollowRedirects = false; connectTimeout = 4000; readTimeout = 6000; useCaches = false
            if (tok != null) setRequestProperty("Authorization", "Bearer $tok") }
        (c.responseCode == 200).also { Log.i(TAG, "assembly: lab.html -> ${c.responseCode}"); c.disconnect() }
    } catch (x: Exception) { Log.w(TAG, "assembly: probe ${x.message}"); false }

    /** the Player's token as the site's Oros cookie (what /oros/api/login sets for a browser) */
    private fun cookie(tok: String) {
        val cm = CookieManager.getInstance()
        cm.setAcceptCookie(true)
        cm.setCookie(origin, "oros_token=$tok; Path=/; Max-Age=${30 * 24 * 3600}; Secure; HttpOnly; SameSite=Lax")
        cm.flush()
    }

    private fun say(t: String?) { msg?.apply { text = t ?: ""; visibility = if (t == null) View.GONE else View.VISIBLE } }

    private fun build(): FrameLayout {
        val f = FrameLayout(act).apply {
            val b = (2 * dp).toInt(); setPadding(b, b, b, b); isClickable = true
            background = GradientDrawable().apply { setColor(Color.WHITE); setStroke(b, Color.BLACK) } }
        val w = WebView(act)
        w.setBackgroundColor(Color.WHITE)
        w.settings.apply { javaScriptEnabled = true; domStorageEnabled = true; mediaPlaybackRequiresUserGesture = false
            setSupportZoom(false); allowFileAccess = false; allowContentAccess = false }
        CookieManager.getInstance().setAcceptThirdPartyCookies(w, false)
        w.addJavascriptInterface(Bridge(), "NeoScanPlayer")
        w.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(v: WebView, r: WebResourceRequest): Boolean {
                val u = r.url
                if (u.host == site.host && u.path?.startsWith(site.path) == true && !login(u.toString())) return false
                if (login(u.toString())) { refused(); return true }
                android.widget.Toast.makeText(act, "Opens only the Lab's pages here", android.widget.Toast.LENGTH_SHORT).show()
                return true
            }
            override fun onPageStarted(v: WebView, url: String, favicon: android.graphics.Bitmap?) {
                if (login(url)) { v.stopLoading(); refused() }
            }
            override fun onPageFinished(v: WebView, url: String) {
                if (login(url)) return
                say(null); v.evaluateJavascript(HOOK, null)
                Log.i(TAG, "assembly: page $url")
            }
        }
        w.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(m: ConsoleMessage): Boolean { Log.i(TAG, "assembly js: ${m.message()} (${m.sourceId()}:${m.lineNumber()})"); return true }
            // the page's mic note (micnote.js): the microphone only, only for the Lab's site, only when the Player has it
            override fun onPermissionRequest(r: PermissionRequest) {
                val mic = act.checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) == android.content.pm.PackageManager.PERMISSION_GRANTED
                if (r.origin.host == site.host && mic && PermissionRequest.RESOURCE_AUDIO_CAPTURE in r.resources)
                    r.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE)) else r.deny()
            }
        }
        f.addView(w, FrameLayout.LayoutParams(-1, -1))
        val m = TextView(act).apply { textSize = 15f; setTextColor(Color.BLACK); setBackgroundColor(Color.WHITE)
            val p = (12 * dp).toInt(); setPadding(p, p, p, p); visibility = View.GONE }
        f.addView(m, FrameLayout.LayoutParams(-1, -2, Gravity.TOP))
        root.addView(f)
        frame = f; web = w; msg = m
        return f
    }

    private fun login(u: String) = u.contains("login.html")

    /** the site sent the WebView to its login: the token renewed once (a new login with the saved password, Auth),
     *  then the page again; refused twice = a message (the login form never shows here) */
    private fun refused() {
        val u = loaded ?: return
        if (retried) { say("The Lab site refused the Player's sign-in. Sign in again in the Player (Settings), then reopen the Assembly."); return }
        retried = true
        say("Renewing the sign-in...")
        Thread {
            val ok = Auth.refresh(act) == Auth.Result.OK
            val tok = Auth.token(act)
            act.runOnUiThread { if (ok && tok != null) { cookie(tok); web?.loadUrl(u) } else say("The Lab site refused the Player's sign-in (renewal failed).") }
        }.start()
    }

    /** window.NeoScanPlayer (a page thread): the page saved a live config -> the lab polls now */
    inner class Bridge {
        @JavascriptInterface fun configSent(fighter: String, rev: Int) {
            Log.i(TAG, "assembly: the page sent $fighter r$rev")
            sent(fighter, rev)
        }
    }

    companion object {
        private const val TAG = "NeoScanLab"
        /** the page's fetch, wrapped: a PUT to .../lab/config/<f> answered OK = configSent(f, its revision) */
        private const val HOOK = """(function(){ if (window.__nspHook || !window.NeoScanPlayer) return; window.__nspHook = 1;
  var f0 = window.fetch;
  window.fetch = function(u, o) {
    var p = f0.apply(this, arguments);
    try {
      var m = ((o && o.method) || (u && u.method) || 'GET').toUpperCase(), s = String((u && u.url) || u);
      var k = s.match(/lab\/config\/([A-Za-z0-9_-]+)(\?|$)/);
      if (m === 'PUT' && k) p.then(function(r) { if (r.ok) r.clone().json().then(function(j) { NeoScanPlayer.configSent(k[1], (j && j.version) | 0); },
        function() { NeoScanPlayer.configSent(k[1], 0); }); }, function() {});
    } catch (e) {}
    return p;
  };
})();"""
    }
}
