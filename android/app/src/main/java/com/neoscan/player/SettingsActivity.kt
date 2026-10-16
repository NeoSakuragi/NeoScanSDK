package com.neoscan.player

import android.app.Activity
import android.content.pm.ActivityInfo
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.Switch
import android.widget.TextView
import java.io.File

/** Settings, in sections: Feedback (the list of his notes), Account (logout), System, Display, Controls, Updates (the game builds and the player's own self-update, PlayerUpdate), About. Every change is stored at once ([Prefs]); the game
 *  (paused meanwhile) applies them when it resumes. Built in code: no layout XML, no libraries. */
class SettingsActivity : Activity() {
    override fun attachBaseContext(base: android.content.Context) { super.attachBaseContext(Lang.wrap(base)); Lang.init(base) }
    override fun onPause() { super.onPause(); if (Prefs.dirty) { Prefs.dirty = false; SettingsSync.touched(this) } }   // 0.0.44: to the account
    private lateinit var col: LinearLayout
    private val dp get() = resources.displayMetrics.density

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        title = getString(R.string.set_title)
        requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
        val prefs = Prefs(this)
        col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; val m = (16 * dp).toInt(); setPadding(m, m, m, m * 2) }
        col.addView(TextView(this).apply { text = getString(R.string.set_title); textSize = 24f; setTypeface(typeface, Typeface.BOLD) })

        if (Auth.admin(this)) {                                         // 0.0.26: a tester has no list (TESTER MODE)
            section(getString(R.string.set_feedback))
            col.addView(Button(this).apply { text = getString(R.string.set_my_notes); setOnClickListener {
                startActivity(android.content.Intent(this@SettingsActivity, FeedbackListActivity::class.java)) } },
                        LinearLayout.LayoutParams(-1, -2).apply { topMargin = (8 * dp).toInt() })
            note(getString(R.string.set_my_notes_note))
        }

        section(getString(R.string.set_account))
        note(if (!BuildConfig.DEV) getString(R.string.set_signed_in, Auth.user(this) ?: "?") else
             getString(R.string.set_signed_in_dev, Auth.user(this) ?: "?", getString(if (Auth.admin(this)) R.string.role_admin else R.string.role_tester)))
        col.addView(Button(this).apply { text = "Language / Langue: " + (if (Lang.current(this@SettingsActivity) == "fr") "Français" else "English"); isAllCaps = false; setOnClickListener {
            Lang.set(this@SettingsActivity, if (Lang.current(this@SettingsActivity) == "fr") "en" else "fr"); recreate() } },
            LinearLayout.LayoutParams(-1, -2).apply { topMargin = (8 * dp).toInt() })
        col.addView(Button(this).apply { text = getString(R.string.menu_logout); setOnClickListener {
            Auth.signOut(this@SettingsActivity)                          // the build goes too: the next account gets its own
        } }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = (8 * dp).toInt() })

        section(getString(R.string.set_system))
        choice(getString(R.string.set_hardware), listOf("arcade" to getString(R.string.set_hw_arcade), "console" to getString(R.string.set_hw_console)),
               prefs.system) { prefs.system = it }
        section(getString(R.string.set_display))
        choice(getString(R.string.set_orientation), listOf("auto" to getString(R.string.set_or_auto), "portrait" to getString(R.string.set_or_portrait), "landscape" to getString(R.string.set_or_landscape)),
               prefs.orientation) { prefs.orientation = it }
        choice(getString(R.string.set_aspect), listOf("square" to getString(R.string.set_aspect_square), "4:3" to "4:3"), prefs.aspect) { prefs.aspect = it }
        choice(getString(R.string.set_scale), listOf("fit" to getString(R.string.set_scale_fit), "integer" to getString(R.string.set_scale_int, Screen.multiples(this))),
               prefs.scale) { prefs.scale = it }
        choice(getString(R.string.set_filter), listOf("sharp" to getString(R.string.set_f_sharp), "smooth" to getString(R.string.set_f_smooth), "scanlines" to getString(R.string.set_f_scan),
                                "subpixel" to getString(R.string.set_f_sub)),
               prefs.filter) { prefs.filter = it }
        slider(getString(R.string.set_scan_dark), 10, 100, prefs.scanlines, "%") { prefs.scanlines = it }

        section(getString(R.string.set_controls))
        slider(getString(R.string.set_opacity), 10, 100, prefs.opacity, "%") { prefs.opacity = it }
        slider(getString(R.string.set_btn_size), 70, 140, prefs.size, "%") { prefs.size = it }
        toggle(getString(R.string.set_vibrate), prefs.vibrate) { prefs.vibrate = it }
        note(getString(R.string.set_gamepads))

        section(getString(R.string.set_updates))
        run {                                                            // the self-install (PlayerUpdate)
        val pl = TextView(this).apply { textSize = 15f; setPadding(0, (10 * dp).toInt(), 0, 0) }
        col.addView(pl)
        val upd = Button(this).apply { setOnClickListener { PlayerUpdate.install(this@SettingsActivity) } }
        col.addView(upd, LinearLayout.LayoutParams(-1, -2).apply { topMargin = (8 * dp).toInt() })
        val show = {
            val r = PlayerUpdate.ready(this); val a = PlayerUpdate.available()
            pl.text = getString(R.string.set_player, BuildConfig.VERSION_NAME) + (if (PlayerUpdate.channel(this) != "live") "  (channel ${PlayerUpdate.channel(this)})" else "") + ": " +
                when { r != null -> PlayerUpdate.readyText(r); a != null -> if (PlayerUpdate.progress >= 0) getString(R.string.upd_app_downloading, a.version, PlayerUpdate.progress) else getString(R.string.set_app_not_dl, a.version)
                       PlayerUpdate.error.isNotEmpty() -> PlayerUpdate.error; PlayerUpdate.latest != null -> getString(R.string.set_uptodate_lc); else -> getString(R.string.set_not_checked) }
            upd.text = if (r != null) "${PlayerUpdate.ACTION} ${r.version}" else ""; upd.visibility = if (r != null) View.VISIBLE else View.GONE
        }
        show()
        col.addView(Button(this).apply { text = getString(R.string.set_check_update); setOnClickListener { b ->
            b.isEnabled = false; pl.text = getString(R.string.set_checking)
            Thread { PlayerUpdate.check(this@SettingsActivity); runOnUiThread { b.isEnabled = true; show() } }.start() } },
            LinearLayout.LayoutParams(-1, -2).apply { topMargin = (8 * dp).toInt() })
        note(getString(if (Auth.admin(this)) R.string.set_upd_note_admin else R.string.set_upd_note))
        }
        toggle(getString(R.string.set_fetch_launch), prefs.autoUpdate) { prefs.autoUpdate = it }
        toggle(getString(R.string.set_frame_stats), prefs.frameStats) { prefs.frameStats = it }
        val rom = File(getExternalFilesDir(null), "brawler.neo")
        note(getString(R.string.set_installed, RomFetch.installed(this)) + (if (rom.exists()) "  (${rom.length() / 1048576} MB)" else "") +
             "\n" + getString(R.string.set_source, RomFetch.base(this) ?: "-"))

        section(getString(R.string.set_about))
        note(getString(R.string.set_about_note, BuildConfig.VERSION_NAME))
        col.addView(Button(this).apply { text = getString(R.string.set_back_game); setOnClickListener { finish() } },
                    LinearLayout.LayoutParams(-1, -2).apply { topMargin = (20 * dp).toInt() })
        setContentView(ScrollView(this).apply { addView(col) })
    }

    private fun section(title: String) {
        col.addView(TextView(this).apply {
            text = title.uppercase(); textSize = 13f; letterSpacing = 0.08f; setTypeface(typeface, Typeface.BOLD)
            setTextColor(Color.rgb(240, 120, 60))
        }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = (28 * dp).toInt(); bottomMargin = (4 * dp).toInt() })
        col.addView(View(this).apply { setBackgroundColor(Color.rgb(80, 80, 90)) }, LinearLayout.LayoutParams(-1, maxOf(1, dp.toInt())))
    }
    private fun label(t: String) = TextView(this).apply { text = t; textSize = 16f; setPadding(0, (12 * dp).toInt(), 0, (4 * dp).toInt()) }
    private fun note(t: String) = col.addView(TextView(this).apply { text = t; textSize = 13f; alpha = 0.7f; setPadding(0, (10 * dp).toInt(), 0, 0) })

    private fun choice(title: String, opts: List<Pair<String, String>>, cur: String, set: (String) -> Unit) {
        col.addView(label(title))
        val g = RadioGroup(this)
        opts.forEachIndexed { i, (key, text) ->
            g.addView(RadioButton(this).apply { id = View.generateViewId(); this.text = text; tag = key; isChecked = key == cur })
        }
        g.setOnCheckedChangeListener { grp, id -> set(grp.findViewById<View>(id).tag as String) }
        col.addView(g)
    }
    private fun slider(title: String, min: Int, max: Int, cur: Int, unit: String, set: (Int) -> Unit) {
        val l = label("$title: $cur$unit"); col.addView(l)
        col.addView(SeekBar(this).apply {
            this.min = min; this.max = max; progress = cur
            setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(s: SeekBar, v: Int, user: Boolean) { l.text = "$title: $v$unit"; set(v) }
                override fun onStartTrackingTouch(s: SeekBar) {}
                override fun onStopTrackingTouch(s: SeekBar) {}
            })
        }, ViewGroup.LayoutParams(-1, -2))
    }
    private fun toggle(title: String, cur: Boolean, set: (Boolean) -> Unit) {
        col.addView(Switch(this).apply { text = title; textSize = 16f; isChecked = cur; gravity = Gravity.CENTER_VERTICAL
            setPadding(0, (12 * dp).toInt(), 0, 0); setOnCheckedChangeListener { _, v -> set(v) } }, ViewGroup.LayoutParams(-1, -2))
    }

    override fun onResume() { super.onResume(); PlayerUpdate.resume(this) }

    /** the notification OK asked before the self-update (PlayerUpdate): granted or not, the install goes on */
    override fun onRequestPermissionsResult(code: Int, perms: Array<out String>, res: IntArray) {
        super.onRequestPermissionsResult(code, perms, res)
        if (code == PlayerUpdate.NOTIFY_REQ) PlayerUpdate.install(this)
    }
}
