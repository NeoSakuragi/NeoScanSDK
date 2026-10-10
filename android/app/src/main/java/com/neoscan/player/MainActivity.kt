package com.neoscan.player

import android.app.Activity
import android.content.pm.ActivityInfo
import android.opengl.GLSurfaceView
import android.os.Bundle
import android.view.Gravity
import android.view.InputDevice
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.TextView
import java.io.File

/** The picture and the touch pad, both full screen, stacked: the layout of each orientation comes from [Screen]
 *  (portrait: picture on top, pad under it; landscape: picture centred, pad over its sides). Rotation follows the
 *  sensor; no restart on rotation (configChanges), the views just get their new size. BIOS (neogeo.zip, APK assets)
 *  copied to files/system once; the game = brawler.neo in the app's external files dir (fetched by RomFetch). */
class MainActivity : Activity() {
    /** the process's emulation thread (EmuThread.claim, TODO #183), seen only while this activity owns it: an older
     *  MainActivity still around after a newer one claimed the thread neither pauses nor drives it */
    private var mine: EmuThread? = null
    private val emu: EmuThread? get() = mine?.takeIf { it.ownedBy(this) }
    private var game: Array<File>? = null                              // sys, save, rom once the game started here
    private lateinit var gl: GLSurfaceView
    private lateinit var renderer: EmuRenderer
    private lateinit var pad: PadView
    private var touchMask = 0
    private val padSlot = HashMap<Int, Int>()                         // gamepad device id -> player (0 = P1, 1 = P2)
    private val padMask = IntArray(2)

    /** P1 = touch + the first gamepad, P2 = the second gamepad (a third one also drives P2) */
    private fun pushPads() { Native.setPad(0, touchMask or padMask[0]); Native.setPad(1, padMask[1]) }
    private fun slot(dev: Int) = padSlot.getOrPut(dev) { minOf(padSlot.size, 1) }
    private fun bitFor(code: Int): Int = when (code) {
        KeyEvent.KEYCODE_BUTTON_A -> Pad.A; KeyEvent.KEYCODE_BUTTON_B -> Pad.B             // bottom, right
        KeyEvent.KEYCODE_BUTTON_X -> Pad.C; KeyEvent.KEYCODE_BUTTON_Y -> Pad.D             // left, top
        KeyEvent.KEYCODE_BUTTON_R1 -> Pad.A or Pad.B; KeyEvent.KEYCODE_BUTTON_L1 -> Pad.C or Pad.D
        KeyEvent.KEYCODE_BUTTON_START -> Pad.START; KeyEvent.KEYCODE_BUTTON_SELECT -> Pad.COIN
        KeyEvent.KEYCODE_DPAD_UP -> Pad.UP; KeyEvent.KEYCODE_DPAD_DOWN -> Pad.DOWN
        KeyEvent.KEYCODE_DPAD_LEFT -> Pad.LEFT; KeyEvent.KEYCODE_DPAD_RIGHT -> Pad.RIGHT
        else -> 0
    }
    override fun dispatchKeyEvent(e: KeyEvent): Boolean {
        if (e.keyCode == KeyEvent.KEYCODE_BUTTON_MODE) { if (e.action == KeyEvent.ACTION_UP) openSettings(); return true }
        val bit = bitFor(e.keyCode)
        if (bit == 0 || e.repeatCount > 0 && e.action == KeyEvent.ACTION_DOWN) return bit != 0 || super.dispatchKeyEvent(e)
        val p = slot(e.deviceId)
        if (e.action == KeyEvent.ACTION_DOWN) padMask[p] = padMask[p] or bit
        else if (e.action == KeyEvent.ACTION_UP) padMask[p] = padMask[p] and bit.inv()
        pushPads(); return true
    }
    override fun dispatchGenericMotionEvent(e: MotionEvent): Boolean {
        if (e.source and InputDevice.SOURCE_JOYSTICK != InputDevice.SOURCE_JOYSTICK || e.action != MotionEvent.ACTION_MOVE)
            return super.dispatchGenericMotionEvent(e)
        val x = e.getAxisValue(MotionEvent.AXIS_HAT_X).let { if (it != 0f) it else e.getAxisValue(MotionEvent.AXIS_X) }
        val y = e.getAxisValue(MotionEvent.AXIS_HAT_Y).let { if (it != 0f) it else e.getAxisValue(MotionEvent.AXIS_Y) }
        var d = 0
        if (x < -0.5f) d = d or Pad.LEFT; if (x > 0.5f) d = d or Pad.RIGHT
        if (y < -0.5f) d = d or Pad.UP; if (y > 0.5f) d = d or Pad.DOWN
        val p = slot(e.deviceId)
        padMask[p] = (padMask[p] and (Pad.UP or Pad.DOWN or Pad.LEFT or Pad.RIGHT).inv()) or d
        pushPads(); return true
    }

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        if (!Auth.signedIn(this)) { toLogin(); return }                // Player 0.0.15: the Oros login first
        Auth.onSignedOut = { runOnUiThread { toLogin() } }
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_FULLSCREEN or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        val sys = File(filesDir, "system").apply { mkdirs() }; val save = File(filesDir, "save").apply { mkdirs() }
        val bios = File(sys, "neogeo.zip")
        if (!bios.exists()) assets.open("neogeo.zip").use { i -> bios.outputStream().use { i.copyTo(it) } }
        val rom = File(getExternalFilesDir(null), "brawler.neo")
        RomFetch.configure(this, intent.getStringExtra("url"))
        PlayerUpdate.setChannel(this, intent.getStringExtra("channel")); PlayerUpdate.cleanup(this)
        val msg = TextView(this).apply { textSize = 18f; gravity = Gravity.CENTER; text = "Checking for a new build..." }
        val launch = android.widget.LinearLayout(this).apply { orientation = android.widget.LinearLayout.VERTICAL; gravity = Gravity.CENTER }
        launch.addView(msg)
        setContentView(launch)
        Thread {                                                       // fetch first (off the UI thread), then play
            val ok = if (Prefs(this).autoUpdate) RomFetch.update(this, rom) { t -> runOnUiThread { msg.text = t } } else rom.exists()
            RomFetch.loaded(this)                                      // the ROM's version (hashes a new file): off the UI thread
            runOnUiThread { msg.text = "Brawler '27  v${RomFetch.installed(this)}\nplayer ${BuildConfig.VERSION_NAME}" }
            Thread.sleep(1200)                                         // the version, readable, before the game starts
            runOnUiThread {
                // replaced meanwhile (after a reinstall the update receiver and the launcher both start one: TODO #183)
                if (isFinishing || isDestroyed) return@runOnUiThread
                val pu = PlayerUpdate.ready(this)
                if (ok && pu != null) updateBanner(launch, pu) { startGame(sys, save, rom) }
                else if (ok) startGame(sys, save, rom)
                else msg.text = "No game yet.\n\nCheck the connection (builds: canneji.duckdns.org/brawler), or\nadb push brawler.neo ${rom.absolutePath}"
            }
        }.start()
    }

    /** the launch screen (the title, before any fight): a newer player already downloaded = "Player 0.0.x is ready",
     *  Update (the in-app install) or Play */
    private fun updateBanner(launch: android.widget.LinearLayout, pu: PlayerUpdate.Info, play: () -> Unit) {
        val dp = resources.displayMetrics.density
        val box = android.widget.LinearLayout(this).apply { orientation = android.widget.LinearLayout.VERTICAL; gravity = Gravity.CENTER
            val m = (16 * dp).toInt(); setPadding(m, m, m, m)
            background = android.graphics.drawable.GradientDrawable().apply { setColor(android.graphics.Color.BLACK); setStroke((3 * dp).toInt(), android.graphics.Color.WHITE) } }
        box.addView(TextView(this).apply { textSize = 18f; gravity = Gravity.CENTER; setTextColor(android.graphics.Color.WHITE)
            text = "Player ${pu.version} is ready" })
        val row = android.widget.LinearLayout(this).apply { gravity = Gravity.CENTER }
        row.addView(android.widget.Button(this).apply { text = "Update"; setOnClickListener { PlayerUpdate.install(this@MainActivity) } })
        row.addView(android.widget.Button(this).apply { text = "Play"; setOnClickListener { play() } })
        box.addView(row)
        launch.addView(box, android.widget.LinearLayout.LayoutParams(-2, -2).apply { topMargin = (24 * dp).toInt() })
    }

    private fun toLogin() {
        emu?.paused = true
        startActivity(android.content.Intent(this, LoginActivity::class.java)); finish()
    }

    private fun startGame(sys: File, save: File, rom: File) {
        val root = android.widget.FrameLayout(this); this.root = root
        gl = GLSurfaceView(this).apply {
            setEGLContextClientVersion(2)
            renderer = EmuRenderer { emu }
            setRenderer(renderer)
            renderMode = GLSurfaceView.RENDERMODE_WHEN_DIRTY
        }
        // the game surface declares its own rate (a fixed-source 59.19 Hz, like a video): the display picks 60 Hz and
        // keeps it; MIUI overrode the window's preferredDisplayModeId alone after ~20 s
        if (android.os.Build.VERSION.SDK_INT >= 30) gl.holder.addCallback(object : android.view.SurfaceHolder.Callback {
            override fun surfaceCreated(h: android.view.SurfaceHolder) {
                h.surface.setFrameRate(59.185606f, android.view.Surface.FRAME_RATE_COMPATIBILITY_FIXED_SOURCE) }
            override fun surfaceChanged(h: android.view.SurfaceHolder, f: Int, w: Int, ht: Int) {}
            override fun surfaceDestroyed(h: android.view.SurfaceHolder) {}
        })
        feedback = Feedback(this, rom) { emu }
        testMode = TestMode(this, root, { emu }, feedback, rom) { refreshBadge() }
        lab = CharacterLab(this, root, { emu }, ::playRom, { h -> if (h >= 0) pad.labH = h; android.graphics.Rect(pad.labArea) }) { playRom(rom) }
        feedback.lab = { lab?.noteInfo() }                         // 0.0.29: a note in the lab records its shell + pack
        pad = PadView(this, ::openSettings, ::chooseUpdate, { emu?.resetReq = true }, ::onFeedback, ::openList) { m -> touchMask = m; pushPads() }
        root.addView(gl, android.widget.FrameLayout.LayoutParams(-1, -1))
        root.addView(pad, android.widget.FrameLayout.LayoutParams(-1, -1))
        setContentView(root)
        // the game runs at 59.2 fps: ask for the display's 60 Hz mode (the Redmi Pad 2 Pro defaults to 120 / 48 Hz)
        @Suppress("DEPRECATION") val d = windowManager.defaultDisplay
        val cur = d.mode
        d.supportedModes.filter { it.physicalWidth == cur.physicalWidth && it.physicalHeight == cur.physicalHeight }
            .minByOrNull { Math.abs(it.refreshRate - 60f) }?.let { m ->
                window.attributes = window.attributes.also { it.preferredDisplayModeId = m.modeId } }
        VsyncPacer.hz = d.refreshRate.toDouble()
        getSystemService(android.hardware.display.DisplayManager::class.java).registerDisplayListener(object :
            android.hardware.display.DisplayManager.DisplayListener {
            override fun onDisplayChanged(id: Int) { if (id == d.displayId) VsyncPacer.hz = d.refreshRate.toDouble() }
            override fun onDisplayAdded(id: Int) {}
            override fun onDisplayRemoved(id: Int) {}
        }, null)
        VsyncPacer.draw = { gl.requestRender() }
        VsyncPacer.start()
        applySettings()
        FrameStats.start(getExternalFilesDir(null)!!)
        game = arrayOf(sys, save, rom)
        claimEmu(); emu?.paused = false                            // a thread handed over may have been paused by its last owner
        pollUpdates()
        refreshBadge()
        root.post { showTip() }                                    // 0.0.26: once, after the first layout (the picture's place)
        if (admin && intent.getBooleanExtra("lab", false)) root.post { openLab() }   // adb: --ez lab true
    }

    /** CHARACTER LAB (0.0.28, admin): the faces screen; the core switches to the Lab shell when a fighter is picked */
    var lab: CharacterLab? = null
    private fun openLab() { if (!admin) return; if (testMode?.active == true) testMode?.end(); lab?.open() }
    /** the core on another ROM (the Lab shell, or the game again): the process's emulation thread is replaced (claim:
     *  the old one stops and lets the core go first), the picture and the pad stay */
    private fun playRom(rom: File) {
        val g = game ?: return
        game = arrayOf(g[0], g[1], rom)
        claimEmu(); emu?.paused = held()
    }

    /** take the process's emulation thread (a new one, or the live one handed over from another MainActivity of this
     *  process: TODO #183); at the game's start and on every resume, so the activity in front always drives it */
    private fun claimEmu() {
        val (sys, save, rom) = game ?: return
        val hints = if (android.os.Build.VERSION.SDK_INT >= 31) getSystemService(android.os.PerformanceHintManager::class.java) else null
        mine = EmuThread.claim(this, sys.absolutePath, save.absolutePath, rom.absolutePath, hints, hwOf(Prefs(this)),
            { if (VsyncPacer.perFrame < 2) gl.requestRender() }) { msg ->
            runOnUiThread { setContentView(TextView(this).apply { text = msg; gravity = Gravity.CENTER }) }
        }
        VsyncPacer.draw = { gl.requestRender() }
    }

    /** the list button: his notes (FeedbackListActivity); the game pauses while it is in front (onPause) and resumes on
     *  back (onResume, which also refreshes the badge) */
    private fun openList() {
        if (noteOpen || !admin) return
        val q = testQueue(); val d = openDecisions()
        val list = { f: String? -> startActivity(android.content.Intent(this, FeedbackListActivity::class.java).apply { if (f != null) putExtra("filter", f) }) }
        if (testMode?.active == true) { list(null); return }
        val inLab = lab?.active == true
        emu?.paused = true                                         // 0.0.22: his notes, or the test queue; 0.0.24: the decisions
        val items = ArrayList<Pair<String, () -> Unit>>()
        if (d > 0) items.add("Decisions ($d): pictures waiting for your answer" to { list("decisions") })
        items.add("My notes" to { list(null) })
        if (q.isNotEmpty() && !inLab) items.add("Test queue (${q.size}): test each fixed note in turn" to { testMode?.start(q); Unit })
        items.add((if (inLab) "Character lab: the faces" else "Character lab: fighters + live config") to { openLab() })   // 0.0.28
        android.app.AlertDialog.Builder(this).setTitle("Feedback")
            .setItems(items.map { it.first }.toTypedArray()) { _, i -> items[i].second() }
            .setOnDismissListener { if (testMode?.active != true) emu?.paused = held() }.show()
    }
    var testMode: TestMode? = null
    /** TESTER MODE (0.0.26): the Oros account's role (Auth.admin: "admin" = everything; any other account = a tester,
     *  who sees only the game, the pad and the Feedback button: no list / test queue / decisions, no badge, no update
     *  button; the updates still come, offered on the launch screen) */
    private val admin get() = Auth.admin(this)
    @Volatile private var rowsCache: org.json.JSONArray? = null
    @Volatile private var reviewsCache: org.json.JSONArray? = null
    /** 0.0.24: the decisions waiting for his answer (Decisions.kt); the badge counts them with the test queue */
    private fun openDecisions(): Int { val v = reviewsCache ?: return 0; return (0 until v.length()).count { Decisions.isOpen(v.getJSONObject(it)) } }
    /** the notes he can test now (Feedback.wantsTest: shipped in his build, not yet judged on it; with a state for his
     *  build and system), oldest first */
    private fun testQueue(): List<org.json.JSONObject> {
        val rows = rowsCache ?: return emptyList(); val e = emu ?: return emptyList()
        val rom = File(getExternalFilesDir(null), "brawler.neo"); val sha = Feedback.sha(rom); val key = Feedback.systemKey(e.hw)
        val running = RomFetch.installed(this)
        return (0 until rows.length()).map { rows.getJSONObject(it) }.filter { Feedback.wantsTest(it, running) && Feedback.testable(it, sha, key) }.reversed()
    }
    /** a 👍 / 👎 just given in the test banner: the cached row leaves the queue now (the server's to_test agrees on
     *  the next refresh), so neither the menu nor the badge serves it again */
    fun judged(id: String, status: String) {
        val rows = rowsCache ?: return
        for (k in 0 until rows.length()) rows.getJSONObject(k).takeIf { it.optString("id") == id }
            ?.put("status", status)?.put("to_test", false)?.put("tested_on", RomFetch.installed(this))
        pad.badge = testQueue().size + openDecisions(); pad.invalidate()
    }
    /** the badge: the notes of the test queue (0.0.23: only those; reopened ones wait in Open for a newer fix) + the
     *  decisions waiting for his answer (0.0.24) */
    private fun refreshBadge() {
        if (!::pad.isInitialized) return
        pad.tester = !admin                                            // the role may change with a renewed sign-in
        if (!admin) { pad.badge = 0; return }                          // a tester: no list, no badge, no /mine calls
        Thread {
            Feedback.mine(this).onSuccess { j ->
                rowsCache = j.getJSONArray("rows"); reviewsCache = j.optJSONArray("reviews")
                val n = testQueue().size + openDecisions()
                runOnUiThread { pad.badge = n; pad.invalidate() }
            }
        }.start()
    }

    /** the mic button, labelled "Feedback" (docs/feedback.md): press = the game is captured and the voice records,
     *  release = the note sheet. The microphone permission is asked once, on the first press (that press records
     *  nothing); refused, bundles go without the voice. From the press the frozen screenshot is a drawing canvas ([Ink],
     *  one red pen) while he talks; at the release the steps come up around it (the canvas stays live). */
    private lateinit var feedback: Feedback
    private lateinit var root: android.widget.FrameLayout
    private var noteOpen = false                                       // the scribble + note box is up: the game stays paused
    private var tipOpen = false                                        // the first-launch tip is up: the game stays paused
    private fun held() = noteOpen || tipOpen || lab?.facesShown == true   // what keeps the game paused once a dialog closes
    private var sheet: Sheet? = null
    private var pending: android.graphics.Bitmap? = null               // the screenshot, if it came before the sheet
    private fun onFeedback(down: Boolean) {
        val granted = checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) == android.content.pm.PackageManager.PERMISSION_GRANTED
        val fp = getSharedPreferences("feedback", 0)
        if (down) {
            if (noteOpen) return
            if (tipOpen) closeTip()                                    // the tip's own button: the press goes on
            if (!granted && !fp.getBoolean("micAsked", false)) {
                fp.edit().putBoolean("micAsked", true).apply()
                requestPermissions(arrayOf(android.Manifest.permission.RECORD_AUDIO), 1); return
            }
            emu?.paused = true; noteOpen = true                        // frozen at the press, until Send / Discard
            var sh: Sheet? = null
            feedback.start(granted) { b -> runOnUiThread { sh?.ink?.shot = b; if (sh == null) pending = b } }
            sh = Sheet().also { sheet = it; pending?.let { b -> it.ink.shot = b }; pending = null }
        } else if (feedback.recording) {
            val voice = feedback.stop() >= Feedback.MIN_MS
            sheet?.noteBox(voice)
        }
    }

    /** 0.0.26: the first launch's tip, once (prefs "feedback" tipShown, set when it is dismissed): a card over the
     *  picture, the mic ringed on the pad; the game waits under it. "Got it", or a press on the mic itself, closes it. */
    private var tip: android.view.View? = null
    private fun showTip() {
        if (getSharedPreferences("feedback", 0).getBoolean("tipShown", false)) return
        val dp = resources.displayMetrics.density
        val card = android.widget.LinearLayout(this).apply { orientation = android.widget.LinearLayout.VERTICAL; gravity = Gravity.CENTER_HORIZONTAL
            val m = (16 * dp).toInt(); setPadding(m, m, m, m); isClickable = true
            background = android.graphics.drawable.GradientDrawable().apply { setColor(android.graphics.Color.BLACK)
                setStroke((3 * dp).toInt(), android.graphics.Color.WHITE); cornerRadius = 12 * dp } }
        card.addView(TextView(this).apply { textSize = 15f; setTextColor(android.graphics.Color.WHITE); alpha = 0.8f; text = "The Feedback button (the microphone)" })
        card.addView(TextView(this).apply { textSize = 19f; setTextColor(android.graphics.Color.WHITE); setTypeface(typeface, android.graphics.Typeface.BOLD)
            gravity = Gravity.CENTER; setPadding(0, (8 * dp).toInt(), 0, (8 * dp).toInt())
            text = "Hold to describe a problem. The game freezes while you talk. Release when you're done." })
        card.addView(android.widget.Button(this).apply { text = "Got it"; textSize = 16f; setOnClickListener { closeTip() } })
        val pic = Screen.picture(root.width, root.height)
        val w = minOf(pic.width(), (420 * dp).toInt()) - (24 * dp).toInt()
        root.addView(card, android.widget.FrameLayout.LayoutParams(w, -2, Gravity.TOP or Gravity.CENTER_HORIZONTAL).apply { topMargin = pic.top + pic.height() / 6 })
        tip = card; tipOpen = true; emu?.paused = true; pad.hint = true
    }
    private fun closeTip() {
        tip?.let { root.removeView(it) }; tip = null
        if (!tipOpen) return
        tipOpen = false; pad.hint = false
        getSharedPreferences("feedback", 0).edit().putBoolean("tipShown", true).apply()
        emu?.paused = held()
    }

    /** 0.0.26: a short message over the picture (the note's fate: sending, sent, saved for later), ~3 s; touches go through */
    private var noticeView: TextView? = null
    private val hideNotice = Runnable { noticeView?.let { root.removeView(it) }; noticeView = null }
    private fun notice(t: String, ms: Long = 3000) {
        val dp = resources.displayMetrics.density
        val v = noticeView ?: TextView(this).apply { textSize = 18f; setTextColor(android.graphics.Color.WHITE); gravity = Gravity.CENTER
            setTypeface(typeface, android.graphics.Typeface.BOLD); val m = (16 * dp).toInt(); setPadding(m, m * 3 / 4, m, m * 3 / 4)
            background = android.graphics.drawable.GradientDrawable().apply { setColor(android.graphics.Color.argb(230, 0, 0, 0))
                setStroke((2 * dp).toInt(), android.graphics.Color.WHITE); cornerRadius = 12 * dp } }.also { noticeView = it
                val pic = Screen.picture(root.width, root.height)
                root.addView(it, android.widget.FrameLayout.LayoutParams(-2, -2, Gravity.TOP or Gravity.CENTER_HORIZONTAL).apply { topMargin = pic.top + pic.height() / 3 }) }
        v.text = t; v.removeCallbacks(hideNotice); v.postDelayed(hideNotice, ms)
    }

    /** the note sheet over the whole screen (0.0.26: numbered steps for a first-time tester). While the mic is held:
     *  the red banner "● Recording… release to finish" with the seconds, over the screenshot (already drawable). At the
     *  release: ① Your words (the transcript to correct, or a typed note after a tap), ② Point at the problem
     *  (optional): the red pen on the screenshot, Undo / Clear, ③ Send feedback (the big button) or Discard (small);
     *  both resume the game. The admin also gets "Reply to..." (one of his notes). */
    private inner class Sheet {
        val dp = resources.displayMetrics.density
        val ink = Ink.View(this@MainActivity)
        val col = android.widget.LinearLayout(this@MainActivity).apply { orientation = android.widget.LinearLayout.VERTICAL; setBackgroundColor(android.graphics.Color.BLACK) }
        private val m = (10 * dp).toInt()
        private val panelColor = android.graphics.Color.rgb(28, 28, 34)
        val banner = TextView(this@MainActivity).apply { textSize = 20f; setTypeface(typeface, android.graphics.Typeface.BOLD); gravity = Gravity.CENTER
            setTextColor(android.graphics.Color.WHITE); setBackgroundColor(android.graphics.Color.rgb(200, 20, 20)); setPadding(m, m, m, m) }
        val step1 = android.widget.LinearLayout(this@MainActivity).apply { orientation = android.widget.LinearLayout.VERTICAL; visibility = View.GONE
            setPadding(m, m / 2, m, m / 2); setBackgroundColor(panelColor) }
        val step3 = android.widget.LinearLayout(this@MainActivity).apply { orientation = android.widget.LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            visibility = View.GONE; setPadding(m, m / 2, m, m / 2); setBackgroundColor(panelColor) }
        var raw = ""; var model = ""; var failed = false
        lateinit var edit: android.widget.EditText
        private val ticker = object : Runnable { override fun run() {
            if (!feedback.recording) return
            banner.text = "● Recording… release to finish   ${(android.os.SystemClock.uptimeMillis() - t0) / 1000}s"
            banner.postDelayed(this, 250) } }
        private val t0 = android.os.SystemClock.uptimeMillis()
        /** the keyboard's height read from the window's insets every 150 ms while the sheet is up (API 30+): the sheet's
         *  bottom padding, so ③ sits right above the keyboard */
        private val imeWatch = object : Runnable { override fun run() {
            if (android.os.Build.VERSION.SDK_INT < 30) return
            val h = col.rootWindowInsets?.getInsets(android.view.WindowInsets.Type.ime())?.bottom ?: 0
            if (h != col.paddingBottom) col.setPadding(0, 0, 0, h)
            col.postDelayed(this, 150) } }
        private fun heading(t: String) = TextView(this@MainActivity).apply { text = t; textSize = 16f; setTextColor(android.graphics.Color.WHITE)
            setTypeface(typeface, android.graphics.Typeface.BOLD) }

        init {
            fun btn(t: String, f: () -> Unit) = android.widget.Button(this@MainActivity).apply { text = t; textSize = 14f; isAllCaps = false; setOnClickListener { f() } }
            val step2 = android.widget.LinearLayout(this@MainActivity).apply { orientation = android.widget.LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                setPadding(m, m / 2, m, m / 2); setBackgroundColor(panelColor) }
            val s2 = android.widget.LinearLayout(this@MainActivity).apply { orientation = android.widget.LinearLayout.VERTICAL }
            s2.addView(heading("② Point at the problem (optional)"))
            s2.addView(TextView(this@MainActivity).apply { textSize = 13f; setTextColor(android.graphics.Color.WHITE); alpha = 0.8f
                text = "Draw on the picture to circle what's wrong" })
            step2.addView(s2, android.widget.LinearLayout.LayoutParams(0, -2, 1f))
            step2.addView(btn("Undo") { ink.undo() }, android.widget.LinearLayout.LayoutParams(-2, -2))
            step2.addView(btn("Clear") { ink.clear() }, android.widget.LinearLayout.LayoutParams(-2, -2))
            col.addView(banner, android.widget.LinearLayout.LayoutParams(-1, -2))
            col.addView(step1, android.widget.LinearLayout.LayoutParams(-1, -2))
            col.addView(step2, android.widget.LinearLayout.LayoutParams(-1, -2))
            col.addView(ink, android.widget.LinearLayout.LayoutParams(-1, 0, 1f))
            col.addView(step3, android.widget.LinearLayout.LayoutParams(-1, -2))
            col.isClickable = true                                        // nothing under the sheet gets a touch
            root.addView(col, android.widget.FrameLayout.LayoutParams(-1, -1))
            // the keyboard: the sheet shrinks above it (API 30+, the IME insets of this full-screen window), so ③ stays
            // on screen while he types; older Androids pan the window to the box
            if (android.os.Build.VERSION.SDK_INT >= 30) {
                window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_NOTHING or WindowManager.LayoutParams.SOFT_INPUT_STATE_HIDDEN)
                imeWatch.run()                                            // polled: this full-screen window dispatches no IME insets
            } else window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_PAN or WindowManager.LayoutParams.SOFT_INPUT_STATE_HIDDEN)
            if (feedback.recording) ticker.run() else banner.visibility = View.GONE
        }

        /** the release: the recording banner goes, ① (the transcript, fetched now, ~2 s, to correct or extend; empty for a
         *  typed note after a tap or when the transcription is unavailable) and ③ come up */
        fun noteBox(voice: Boolean) {
            banner.removeCallbacks(ticker); banner.visibility = View.GONE
            edit = android.widget.EditText(this@MainActivity).apply {
                minLines = 2; maxLines = 4; gravity = Gravity.TOP or Gravity.START; textSize = 16f
                setTextColor(android.graphics.Color.WHITE); setHintTextColor(android.graphics.Color.GRAY)
                setBackgroundColor(android.graphics.Color.rgb(55, 55, 64)); setPadding(m, m / 2, m, m / 2)
                inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE or
                    android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
                hint = if (voice) "Transcribing..." else "Type what's wrong"
            }
            val info = TextView(this@MainActivity).apply { textSize = 13f; setTextColor(android.graphics.Color.WHITE); alpha = 0.8f
                text = if (voice) "Turning your voice into text..." else "What happened, and what you expected" }
            step1.addView(heading("① Your words"))
            step1.addView(info)
            step1.addView(edit, android.widget.LinearLayout.LayoutParams(-1, -2).apply { topMargin = m / 2 })
            step1.visibility = View.VISIBLE
            val discard = android.widget.Button(this@MainActivity).apply { text = "Discard"; textSize = 13f; isAllCaps = false
                setOnClickListener { feedback.cancel(); close() } }
            val send = android.widget.Button(this@MainActivity).apply { text = "③ Send feedback"; textSize = 18f; isAllCaps = false
                setTypeface(typeface, android.graphics.Typeface.BOLD); setTextColor(android.graphics.Color.WHITE)
                background = android.graphics.drawable.GradientDrawable().apply { setColor(android.graphics.Color.rgb(25, 110, 210)); cornerRadius = 8 * dp
                    setStroke((2 * dp).toInt(), android.graphics.Color.WHITE) }
                setOnClickListener {
                    feedback.send(edit.text.toString().trim(), raw, model, failed, ArrayList(ink.strokes)) { sent ->
                        runOnUiThread { notice(if (sent) "Thanks, your note was sent" else "Saved, will send when online") } }
                    close(); notice("Sending your note…", 15000) } }
            step3.addView(discard, android.widget.LinearLayout.LayoutParams(-2, -2))
            if (Auth.admin(this@MainActivity)) step3.addView(android.widget.Button(this@MainActivity).apply { text = "Reply to..."; textSize = 13f; isAllCaps = false
                setOnClickListener { pickNote() } }, android.widget.LinearLayout.LayoutParams(-2, -2))
            step3.addView(send, android.widget.LinearLayout.LayoutParams(0, (56 * dp).toInt(), 1f).apply { leftMargin = m })
            step3.visibility = View.VISIBLE
            if (voice) Thread {
                val r = feedback.transcribe()
                runOnUiThread {
                    if (r != null) {
                        raw = r.first; model = r.second
                        if (edit.text.isEmpty()) { edit.setText(r.first); edit.setSelection(edit.text.length) }
                        info.text = "Correct or add to it if needed"
                    } else { failed = true; info.text = "No text this time: your voice is sent as it is"; edit.hint = "Type a note (optional)" }
                }
            }.start()
        }

        /** 0.0.17: this voice / text goes as a reply to one of his notes (open, or shipped in the build he runs) instead
         *  of a new note; the replay and the drawing are dropped */
        private fun pickNote() {
            val running = RomFetch.installed(this@MainActivity)
            Thread {
                val r = Feedback.mine(this@MainActivity)
                runOnUiThread {
                    r.onFailure { toast("Your notes are unavailable: ${it.message}") }
                    r.onSuccess { j ->
                        val all = j.getJSONArray("rows")
                        val notes = (0 until all.length()).map { all.getJSONObject(it) }.filter { Feedback.isOpen(it) || Feedback.isReady(it, running) }
                        if (notes.isEmpty()) { toast("No open notes to reply to"); return@onSuccess }
                        val labels = notes.map { n -> Feedback.local(n.optString("created")) + "  " +
                            (if (n.optString("status") == "shipped") "SHIPPED " + n.optString("release") else n.optString("status").uppercase()) + "\n" +
                            n.optString("title").takeIf { it.isNotEmpty() && it != "null" }
                                ?: n.optString("final_text").ifEmpty { n.optString("raw_transcript") }.take(90) }
                        android.app.AlertDialog.Builder(this@MainActivity).setTitle("Reply to which note?")
                            .setItems(labels.toTypedArray()) { _, i ->
                                feedback.replyTo(notes[i].optString("id"), edit.text.toString().trim(), raw) { err ->
                                    runOnUiThread { toast(if (err == null) "Reply sent" else "Reply not sent: $err") } }
                                close()
                            }.setNegativeButton("Back", null).show()
                    }
                }
            }.start()
        }

        fun close() {
            banner.removeCallbacks(ticker); col.removeCallbacks(imeWatch)
            (getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager).hideSoftInputFromWindow(col.windowToken, 0)
            root.removeView(col); sheet = null
            noteOpen = false; emu?.paused = false
            window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_FULLSCREEN or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        }
    }
    @Deprecated("the back key cancels an open note") override fun onBackPressed() {
        val sh = sheet
        if (sh != null) { if (feedback.recording) feedback.stop(); feedback.cancel(); sh.close() }
        else if (testMode?.active == true) testMode?.end()
        else if (lab?.active == true) lab?.back()
        else @Suppress("DEPRECATION") super.onBackPressed()
    }
    private fun toast(t: String) = android.widget.Toast.makeText(this, t, android.widget.Toast.LENGTH_SHORT).show()

    /** test hook (0.0.26, like feedback_test_audio): test_scenario.json (a note row: id, title, scenario {title, do,
     *  expect}) + test_scenario.state pushed to the external files dir open that note in VERIFY mode on the next resume
     *  (the state copied where Feedback.scenarioState caches it for this build and system); both files are consumed */
    private fun localTest() {
        val d = getExternalFilesDir(null) ?: return; val j = File(d, "test_scenario.json"); val st = File(d, "test_scenario.state")
        val e = emu ?: return
        if (!j.exists() || !st.exists()) return
        val n = try { org.json.JSONObject(j.readText()) } catch (x: Exception) { j.delete(); return }
        val rom = File(d, "brawler.neo")
        val f = File(cacheDir, "scenario/${n.optString("id")}_${Feedback.sha(rom).take(12)}_${Feedback.systemKey(e.hw)}.state")
        f.parentFile?.mkdirs(); st.copyTo(f, true); j.delete(); st.delete()
        TestQueue.pending = listOf(n)
    }

    /** every 5 s: is there a newer game build than the installed one? every hour (and at the start): a newer player
     *  (PlayerUpdate: downloaded in the background, nothing on screen moves but the button); the update button blinks
     *  while either is there; every minute: send the queued feedback */
    @Volatile private var polling = true
    private fun pollUpdates() = Thread {
        var n = 0
        while (polling) {
            if (n % 12 == 0) Feedback.flush(this)
            if (n % 720 == 0) PlayerUpdate.check(this)
            n++
            val b = RomFetch.latest(this)
            gameNewer = b > 0 && b > RomFetch.installedBuild(this)
            val ready = gameNewer || PlayerUpdate.available() != null
            runOnUiThread { if (::pad.isInitialized) pad.updateReady = ready }
            try { Thread.sleep(5000) } catch (e: InterruptedException) { }
        }
    }.apply { isDaemon = true; start() }

    @Volatile private var gameNewer = false
    /** the update button (0.0.21): the game pauses and a list says what is newer, "Player 0.0.x" (the in-app install)
     *  and / or "Game 0.0.x" (download + restart on it); nothing newer = "Up to date" with a Check now */
    private fun chooseUpdate() {
        emu?.paused = true
        val items = ArrayList<Pair<String, () -> Unit>>()
        val pu = PlayerUpdate.ready(this); val pa = PlayerUpdate.available()
        if (pu != null) items += "Player ${pu.version} is ready: Update" to { PlayerUpdate.install(this) }
        else if (pa != null) items += "Player ${pa.version}: downloading ${maxOf(0, PlayerUpdate.progress)} %" to {
            Thread { PlayerUpdate.check(this) }.start(); toast("Downloading Player ${pa.version}") }
        if (gameNewer) items += "Game ${RomFetch.latestVersion ?: "?"}: download and restart" to { downloadLatest() }
        val b = android.app.AlertDialog.Builder(this).setOnDismissListener { emu?.paused = held() }
        if (items.isEmpty()) b.setTitle("Up to date").setMessage("Player ${BuildConfig.VERSION_NAME}, game ${RomFetch.installed(this)}")
            .setPositiveButton("Check now") { _, _ -> Thread {
                val r = PlayerUpdate.check(this); val g = RomFetch.latest(this); gameNewer = g > 0 && g > RomFetch.installedBuild(this)
                runOnUiThread { pad.updateReady = gameNewer || PlayerUpdate.available() != null
                    toast(if (r != null) "Player ${r.version} is ready" else if (gameNewer) "A new game build is ready" else "Up to date") } }.start() }
            .setNegativeButton("Back", null)
        else b.setTitle("Update").setItems(items.map { it.first }.toTypedArray()) { _, i -> items[i].second() }.setNegativeButton("Back", null)
        b.show()
    }

    /** the game update: download the latest build (checked: size + sha256), then restart the app on it (a fresh
     *  process: the core is loaded once per process) */
    private fun downloadLatest() {
        val rom = File(getExternalFilesDir(null), "brawler.neo")
        pad.updateText = "0%"
        Thread {
            val before = RomFetch.installedBuild(this)
            RomFetch.update(this, rom) { t ->                      // "Downloading v0.0.8: 45 %" -> "45%"
                Regex("(\\d+) %").find(t)?.let { m -> runOnUiThread { pad.updateText = m.groupValues[1] + "%" } } }
            val got = RomFetch.installedBuild(this) > before
            runOnUiThread {
                pad.updateText = null
                if (got) restart()
            }
        }.start()
    }

    /** a fresh process (new ROM, other system): the game pauses, its saves are written (flushSaves), then restart */
    @Volatile private var restarting = false
    private fun restart() {
        restarting = true; emu?.paused = true
        Thread {
            val t0 = System.currentTimeMillis()
            while (emu?.flushed == false && System.currentTimeMillis() - t0 < 1500) Thread.sleep(10)
            runOnUiThread {
                val i = packageManager.getLaunchIntentForPackage(packageName)!!
                    .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK or android.content.Intent.FLAG_ACTIVITY_CLEAR_TASK)
                startActivity(i); Runtime.getRuntime().exit(0)
            }
        }.start()
    }

    private fun openSettings() = startActivity(android.content.Intent(this, SettingsActivity::class.java))
    private fun hwOf(p: Prefs) = if (p.system == "console") "aes" else "mvs"
    private fun applySettings() {
        val p = Prefs(this)
        mine?.let { if (it.hw != hwOf(p)) { restart(); return } }   // arcade <-> console: the core reloads
        requestedOrientation = when (p.orientation) {
            "portrait" -> ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT
            "landscape" -> ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
            else -> ActivityInfo.SCREEN_ORIENTATION_FULL_SENSOR
        }
        FrameStats.show = p.frameStats; if (::pad.isInitialized) pad.invalidate()
        Screen.four3 = p.aspect == "4:3"
        Screen.integer = p.scale == "integer" || p.filter == "subpixel"     // the subpixel pattern needs whole pixels
        if (::renderer.isInitialized) {
            renderer.smooth = p.filter == "smooth"; renderer.mode = when (p.filter) { "scanlines" -> 1; "subpixel" -> 2; else -> 0 }
            renderer.dark = p.scanlines / 100f
        }
        if (::pad.isInitialized) { pad.opacity = p.opacity / 100f; pad.size = p.size / 100f; pad.vibrate = p.vibrate }   // size: relayout
    }

    /** the game pauses (picture, sound, emulation) whenever the activity is not in front: settings, home, screen off */
    override fun onPause() { super.onPause(); emu?.paused = true; lab?.paused = true; if (::gl.isInitialized) gl.onPause() }
    override fun onResume() { super.onResume(); applySettings(); if (game != null && !isFinishing && !restarting) claimEmu(); emu?.paused = held() || testMode?.active == true || lab?.facesShown == true; lab?.paused = false; if (::gl.isInitialized) gl.onResume(); refreshBadge()
        if (admin) localTest()
        if (admin) TestQueue.pending?.let { q -> TestQueue.pending = null; testMode?.let { if (it.active) it.end(); it.start(q) } } }
    override fun onDestroy() { polling = false; lab?.stop(); EmuThread.release(this); super.onDestroy() }

    /** the notification OK asked before the self-update (PlayerUpdate): granted or not, the install goes on */
    override fun onRequestPermissionsResult(code: Int, perms: Array<out String>, res: IntArray) {
        super.onRequestPermissionsResult(code, perms, res)
        if (code == PlayerUpdate.NOTIFY_REQ) PlayerUpdate.install(this)
    }
}
