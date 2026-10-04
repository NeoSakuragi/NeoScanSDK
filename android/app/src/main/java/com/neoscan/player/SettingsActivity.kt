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

/** Settings, in sections: Display, Controls, Updates, About. Every change is stored at once ([Prefs]); the game
 *  (paused meanwhile) applies them when it resumes. Built in code: no layout XML, no libraries. */
class SettingsActivity : Activity() {
    private lateinit var col: LinearLayout
    private val dp get() = resources.displayMetrics.density

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
        val prefs = Prefs(this)
        col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; val m = (16 * dp).toInt(); setPadding(m, m, m, m * 2) }
        col.addView(TextView(this).apply { text = "Settings"; textSize = 24f; setTypeface(typeface, Typeface.BOLD) })

        section("Display")
        choice("Orientation", listOf("auto" to "Follow the phone", "portrait" to "Portrait", "landscape" to "Landscape"),
               prefs.orientation) { prefs.orientation = it }
        choice("Aspect", listOf("square" to "Square pixels (304 x 224, pixel-exact)", "4:3" to "4:3"), prefs.aspect) { prefs.aspect = it }
        choice("Scale", listOf("fit" to "Fit the screen", "integer" to "Integer (every pixel the same size: ${Screen.multiples(this)})"),
               prefs.scale) { prefs.scale = it }
        choice("Filter", listOf("sharp" to "Sharp pixels", "smooth" to "Smooth (bilinear)", "scanlines" to "Scanlines",
                                "subpixel" to "Subpixel, as the NeoScan desktop emulator (integer scale)"),
               prefs.filter) { prefs.filter = it }
        slider("Scanline darkness", 10, 100, prefs.scanlines, "%") { prefs.scanlines = it }

        section("Controls")
        slider("Opacity over the picture (landscape)", 10, 100, prefs.opacity, "%") { prefs.opacity = it }
        slider("Button size", 70, 140, prefs.size, "%") { prefs.size = it }
        toggle("Vibrate on press", prefs.vibrate) { prefs.vibrate = it }
        note("Gamepads: the first one is P1, the second P2. A B X Y = A B C D, R1 = A+B, L1 = C+D, SELECT = coin, " +
             "START = start, HOME / MODE = these settings.")

        section("Updates")
        toggle("Fetch new builds on launch", prefs.autoUpdate) { prefs.autoUpdate = it }
        toggle("Show frame stats (also logged to files/frames.log)", prefs.frameStats) { prefs.frameStats = it }
        val rom = File(getExternalFilesDir(null), "brawler.neo")
        note("Installed: Brawler '27 v${RomFetch.installed(this)}" + (if (rom.exists()) "  (${rom.length() / 1048576} MB)" else "") +
             "\nSource: ${RomFetch.base(this) ?: "none"}")

        section("About")
        note("NeoScan Player ${BuildConfig.VERSION_NAME}: the Geolith Neo Geo core (Unibios, MVS) with the NeoScanSDK " +
             "front end. Builds and notes: canneji.duckdns.org/brawler")
        col.addView(Button(this).apply { text = "Back to the game"; setOnClickListener { finish() } },
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
}
