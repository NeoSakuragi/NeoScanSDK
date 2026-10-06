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
    private var emu: EmuThread? = null
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
        val hints = if (android.os.Build.VERSION.SDK_INT >= 31) getSystemService(android.os.PerformanceHintManager::class.java) else null
        emu = EmuThread(sys.absolutePath, save.absolutePath, rom.absolutePath, hints, hwOf(Prefs(this)), { if (VsyncPacer.perFrame < 2) gl.requestRender() }) { msg ->
            runOnUiThread { setContentView(TextView(this).apply { text = msg; gravity = Gravity.CENTER }) }
        }.also { it.start() }
        pollUpdates()
        refreshBadge()
    }

    /** the list button: his notes (FeedbackListActivity); the game pauses while it is in front (onPause) and resumes on
     *  back (onResume, which also refreshes the badge) */
    private fun openList() {
        if (noteOpen) return
        val q = testQueue()
        if (q.isEmpty() || testMode?.active == true) { startActivity(android.content.Intent(this, FeedbackListActivity::class.java)); return }
        emu?.paused = true                                         // 0.0.22: his notes, or the test queue
        android.app.AlertDialog.Builder(this).setTitle("Feedback")
            .setItems(arrayOf("My notes", "Test queue (${q.size}): test each fixed note in turn")) { _, i ->
                if (i == 0) startActivity(android.content.Intent(this, FeedbackListActivity::class.java)) else testMode?.start(q) }
            .setOnDismissListener { if (testMode?.active != true) emu?.paused = noteOpen }.show()
    }
    var testMode: TestMode? = null
    @Volatile private var rowsCache: org.json.JSONArray? = null
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
        pad.badge = testQueue().size; pad.invalidate()
    }
    /** the badge: the notes of the test queue (0.0.23: only those; reopened ones wait in Open for a newer fix) */
    private fun refreshBadge() {
        if (!::pad.isInitialized) return
        Thread {
            Feedback.mine(this).onSuccess { j ->
                rowsCache = j.getJSONArray("rows")
                val n = testQueue().size
                runOnUiThread { pad.badge = n; pad.invalidate() }
            }
        }.start()
    }

    /** the mic button (docs/feedback.md): press = the game is captured and the voice records, release = the bundle is
     *  sent (or queued). The microphone permission is asked once, on the first press (that press records nothing);
     *  refused, bundles go without the voice. From the press the frozen screenshot is a drawing canvas ([Ink]): red /
     *  green pen, undo, clear, while he talks; at the release the note box comes under it (the canvas stays live). */
    private lateinit var feedback: Feedback
    private lateinit var root: android.widget.FrameLayout
    private var noteOpen = false                                       // the scribble + note box is up: the game stays paused
    private var sheet: Sheet? = null
    private var pending: android.graphics.Bitmap? = null               // the screenshot, if it came before the sheet
    private fun onFeedback(down: Boolean) {
        val granted = checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) == android.content.pm.PackageManager.PERMISSION_GRANTED
        val fp = getSharedPreferences("feedback", 0)
        if (down) {
            if (noteOpen) return
            if (!granted && !fp.getBoolean("micAsked", false)) {
                fp.edit().putBoolean("micAsked", true).apply()
                requestPermissions(arrayOf(android.Manifest.permission.RECORD_AUDIO), 1); return
            }
            emu?.paused = true; noteOpen = true                        // frozen at the press, until Send / Cancel
            var sh: Sheet? = null
            feedback.start(granted) { b -> runOnUiThread { sh?.ink?.shot = b; if (sh == null) pending = b } }
            sh = Sheet().also { sheet = it; pending?.let { b -> it.ink.shot = b }; pending = null }
        } else if (feedback.recording) {
            val voice = feedback.stop() >= Feedback.MIN_MS
            sheet?.noteBox(voice)
        }
    }

    /** the scribble sheet over the whole screen: a tool row (pen colour, undo, clear, the recording time), the
     *  screenshot canvas, and after the release the note box (the transcript to correct, or a typed note) with Send /
     *  Cancel; both resume the game */
    private inner class Sheet {
        val dp = resources.displayMetrics.density
        val ink = Ink.View(this@MainActivity)
        val col = android.widget.LinearLayout(this@MainActivity).apply { orientation = android.widget.LinearLayout.VERTICAL; setBackgroundColor(android.graphics.Color.BLACK) }
        val status = TextView(this@MainActivity).apply { textSize = 15f; setTextColor(android.graphics.Color.rgb(255, 90, 90)); setPadding((10 * dp).toInt(), 0, 0, 0) }
        val panel = android.widget.LinearLayout(this@MainActivity).apply { orientation = android.widget.LinearLayout.VERTICAL; visibility = View.GONE
            val m = (12 * dp).toInt(); setPadding(m, m / 2, m, m / 2); setBackgroundColor(android.graphics.Color.rgb(28, 28, 34)) }
        var raw = ""; var model = ""; var failed = false
        lateinit var edit: android.widget.EditText
        private val ticker = object : Runnable { override fun run() {
            if (!feedback.recording) return
            status.text = "\u25CF Recording ${(android.os.SystemClock.uptimeMillis() - t0) / 1000}s: draw on the picture, release the mic to finish"
            status.postDelayed(this, 250) } }
        private val t0 = android.os.SystemClock.uptimeMillis()

        init {
            val bar = android.widget.LinearLayout(this@MainActivity).apply { orientation = android.widget.LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                val m = (6 * dp).toInt(); setPadding(m, m, m, m) }
            val sz = (52 * dp).toInt()
            val pen = object : View(this@MainActivity) {
                val pt = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG)
                override fun onDraw(c: android.graphics.Canvas) {
                    pt.style = android.graphics.Paint.Style.FILL; pt.color = ink.color; c.drawCircle(width / 2f, height / 2f, width * 0.36f, pt)
                    pt.style = android.graphics.Paint.Style.STROKE; pt.strokeWidth = 3 * dp; pt.color = android.graphics.Color.WHITE
                    c.drawCircle(width / 2f, height / 2f, width * 0.42f, pt)
                }
            }.apply { contentDescription = "pen colour"; setOnClickListener { ink.color = if (ink.color == Ink.RED) Ink.GREEN else Ink.RED; invalidate() } }
            fun btn(t: String, f: () -> Unit) = android.widget.Button(this@MainActivity).apply { text = t; textSize = 15f; setOnClickListener { f() } }
            bar.addView(pen, android.widget.LinearLayout.LayoutParams(sz, sz))
            bar.addView(btn("Undo") { ink.undo() }, android.widget.LinearLayout.LayoutParams(-2, sz).apply { leftMargin = (8 * dp).toInt() })
            bar.addView(btn("Clear") { ink.clear() }, android.widget.LinearLayout.LayoutParams(-2, sz))
            bar.addView(status, android.widget.LinearLayout.LayoutParams(0, -2, 1f))
            col.addView(bar, android.widget.LinearLayout.LayoutParams(-1, -2))
            col.addView(ink, android.widget.LinearLayout.LayoutParams(-1, 0, 1f))
            col.addView(panel, android.widget.LinearLayout.LayoutParams(-1, -2))
            col.isClickable = true                                        // nothing under the sheet gets a touch
            root.addView(col, android.widget.FrameLayout.LayoutParams(-1, -1))
            window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_PAN or WindowManager.LayoutParams.SOFT_INPUT_STATE_HIDDEN)
            if (feedback.recording) ticker.run() else status.text = "Draw on the picture"
        }

        /** the release: the note box under the canvas; the transcript (fetched now, ~2 s) to correct or extend, or empty
         *  for a typed note (a tap) or when the transcription is unavailable */
        fun noteBox(voice: Boolean) {
            status.removeCallbacks(ticker); status.setTextColor(android.graphics.Color.rgb(200, 200, 210))
            status.text = "Draw on the picture"
            edit = android.widget.EditText(this@MainActivity).apply {
                minLines = 2; maxLines = 5; gravity = Gravity.TOP or Gravity.START
                inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE or
                    android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
                hint = if (voice) "Transcribing..." else "Type a note"
            }
            val info = TextView(this@MainActivity).apply { textSize = 13f; alpha = 0.7f; text = if (voice) "Transcribing your voice..." else "A note with the last minute's replay" }
            // the buttons share the line above the box: the keyboard (pan mode) never hides them
            val row = android.widget.LinearLayout(this@MainActivity).apply { orientation = android.widget.LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
            row.addView(info, android.widget.LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(android.widget.Button(this@MainActivity).apply { text = "Reply to..."; isAllCaps = false; setOnClickListener { pickNote() } })
            row.addView(android.widget.Button(this@MainActivity).apply { text = "Cancel"; setOnClickListener { feedback.cancel(); close() } })
            row.addView(android.widget.Button(this@MainActivity).apply { text = "Send"; setOnClickListener {
                feedback.send(edit.text.toString().trim(), raw, model, failed, ArrayList(ink.strokes)) { sent -> runOnUiThread { toast(if (sent) "Feedback sent" else "Queued") } }
                close() } })
            panel.addView(row, android.widget.LinearLayout.LayoutParams(-1, -2)); panel.addView(edit, android.widget.LinearLayout.LayoutParams(-1, -2))
            panel.visibility = View.VISIBLE
            if (voice) Thread {
                val r = feedback.transcribe()
                runOnUiThread {
                    if (r != null) {
                        raw = r.first; model = r.second
                        if (edit.text.isEmpty()) { edit.setText(r.first); edit.setSelection(edit.text.length) }
                        info.text = "Correct or add to it, then Send"
                    } else { failed = true; info.text = "Transcription unavailable: your voice goes with the bundle"; edit.hint = "Type a note (optional)" }
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
            status.removeCallbacks(ticker)
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
        else @Suppress("DEPRECATION") super.onBackPressed()
    }
    private fun toast(t: String) = android.widget.Toast.makeText(this, t, android.widget.Toast.LENGTH_SHORT).show()

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
        val b = android.app.AlertDialog.Builder(this).setOnDismissListener { emu?.paused = noteOpen }
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
    private fun restart() {
        emu?.paused = true
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
        emu?.let { if (it.hw != hwOf(p)) { restart(); return } }    // arcade <-> console: the core reloads
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
    override fun onPause() { super.onPause(); emu?.paused = true; if (::gl.isInitialized) gl.onPause() }
    override fun onResume() { super.onResume(); applySettings(); emu?.paused = noteOpen || testMode?.active == true; if (::gl.isInitialized) gl.onResume(); refreshBadge()
        TestQueue.pending?.let { q -> TestQueue.pending = null; testMode?.let { if (it.active) it.end(); it.start(q) } } }
    override fun onDestroy() { polling = false; emu?.running = false; super.onDestroy() }

    /** the notification OK asked before the self-update (PlayerUpdate): granted or not, the install goes on */
    override fun onRequestPermissionsResult(code: Int, perms: Array<out String>, res: IntArray) {
        super.onRequestPermissionsResult(code, perms, res)
        if (code == PlayerUpdate.NOTIFY_REQ) PlayerUpdate.install(this)
    }
}
