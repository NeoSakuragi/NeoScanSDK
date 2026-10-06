package com.neoscan.player

import android.app.Activity
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.media.MediaPlayer
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.widget.Button
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import org.json.JSONObject
import java.net.HttpURLConnection
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

/** His feedback notes (Player 0.0.15, from the settings): GET <ROM base>/../feedback/mine with his token
 *  (tools/feedback/server.py: the signed-in account's notes, newest first, each with its status history). Each card:
 *  the date, the versions, the note as sent, category + fighters, the status (shipped with its release, duplicate
 *  with the other note), the developer's notes, the history, the screenshot (the marked one when he drew on it; tap =
 *  full screen) and the voice (play / stop). Read-only: statuses change on the developer's side. Pull down (or the
 *  Refresh button) to load again. Built in code, no libraries. */
class FeedbackListActivity : Activity() {
    private val dp get() = resources.displayMetrics.density
    private lateinit var list: LinearLayout
    private lateinit var head: TextView
    private lateinit var scroll: PullScroll
    private var player: MediaPlayer? = null
    private var playing: Button? = null
    private val images = HashMap<String, Bitmap>()

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; val m = (14 * dp).toInt(); setPadding(m, 0, m, m * 2) }
        head = TextView(this).apply { gravity = Gravity.CENTER; textSize = 13f; alpha = 0.7f; height = 0; text = "Release to refresh" }
        col.addView(head, LinearLayout.LayoutParams(-1, -2))
        val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, (12 * dp).toInt(), 0, 0) }
        top.addView(TextView(this).apply { text = "My feedback"; textSize = 24f; setTypeface(typeface, Typeface.BOLD) }, LinearLayout.LayoutParams(0, -2, 1f))
        top.addView(Button(this).apply { text = "Refresh"; setOnClickListener { load() } })
        col.addView(top)
        list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        col.addView(list, LinearLayout.LayoutParams(-1, -2))
        scroll = PullScroll().apply { addView(col) }
        setContentView(scroll)
        load()
    }

    override fun onDestroy() { player?.release(); player = null; super.onDestroy() }

    /** pull down at the top: the header grows ("Release to refresh"); released far enough = [load] */
    private inner class PullScroll : ScrollView(this@FeedbackListActivity) {
        private var y0 = -1f
        private val need = 70 * dp
        override fun dispatchTouchEvent(e: MotionEvent): Boolean {
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> y0 = if (scrollY == 0) e.y else -1f
                MotionEvent.ACTION_MOVE -> if (y0 >= 0 && scrollY == 0) {
                    val d = ((e.y - y0) / 2).coerceIn(0f, need * 1.5f)
                    head.height = d.toInt(); head.text = if (d >= need) "Release to refresh" else "Pull to refresh"
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    if (head.height >= need && e.actionMasked == MotionEvent.ACTION_UP) load()
                    head.height = 0; y0 = -1f
                }
            }
            return super.dispatchTouchEvent(e)
        }
    }

    private fun msg(t: String) { list.removeAllViews(); list.addView(TextView(this).apply { text = t; textSize = 15f; setPadding(0, (24 * dp).toInt(), 0, 0) }) }

    private fun get(path: String): HttpURLConnection? {
        val u = Feedback.url(this, path) ?: return null
        return Auth.call(this) { tok -> (u.openConnection() as HttpURLConnection).apply {
            connectTimeout = 5000; readTimeout = 20000
            setRequestProperty("X-Install-Id", Feedback.installId(this@FeedbackListActivity)); setRequestProperty("X-App-Version", BuildConfig.VERSION_NAME)
            if (tok != null) setRequestProperty("Authorization", "Bearer $tok")
        } }
    }

    private fun load() {
        if (list.childCount == 0) msg("Loading...")
        Thread {
            val r = try {
                val c = get("mine")
                if (c == null) Result.failure(Exception("no server"))
                else if (c.responseCode == 401) Result.failure(Exception("Not signed in: log out and in again (settings)"))
                else if (c.responseCode != 200) Result.failure(Exception("The server answered HTTP ${c.responseCode}"))
                else Result.success(JSONObject(c.inputStream.use { it.readBytes().toString(Charsets.UTF_8) }))
            } catch (x: Exception) { Result.failure(Exception("No connection (${x.message})")) }
            runOnUiThread {
                r.onFailure { msg(it.message ?: "?") }
                r.onSuccess { j ->
                    list.removeAllViews()
                    val rows = j.getJSONArray("rows")
                    list.addView(TextView(this).apply { text = "${j.optString("user")}: ${rows.length()} note" + (if (rows.length() == 1) "" else "s") + ", newest first"
                        textSize = 13f; alpha = 0.7f; setPadding(0, (4 * dp).toInt(), 0, (8 * dp).toInt()) })
                    if (rows.length() == 0) msg("No notes yet: hold the mic button in the game and talk, or tap it to type.")
                    for (i in 0 until rows.length()) list.addView(card(rows.getJSONObject(i)))
                }
            }
        }.start()
    }

    private fun when_(iso: String): String = try {
        val p = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }
        SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.US).format(p.parse(iso)!!)
    } catch (x: Exception) { iso.take(16).replace('T', ' ') }

    private fun statusText(r: JSONObject): String = when (val s = r.optString("status")) {
        "shipped" -> "SHIPPED " + r.optString("release")
        "duplicate" -> "DUPLICATE of " + r.optString("duplicate_of")
        "wont_do" -> "WON'T DO"
        "in_progress" -> "IN PROGRESS"
        else -> s.uppercase()
    }

    private fun card(r: JSONObject): View {
        val c = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; val m = (12 * dp).toInt(); setPadding(m, m, m, m)
            background = GradientDrawable().apply { setColor(Color.rgb(30, 30, 36)); setStroke(maxOf(1, dp.toInt()), Color.rgb(90, 90, 100)); cornerRadius = 8 * dp }
        }
        val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        top.addView(TextView(this).apply { text = when_(r.optString("created")); textSize = 15f; setTypeface(typeface, Typeface.BOLD) }, LinearLayout.LayoutParams(0, -2, 1f))
        top.addView(TextView(this).apply {                          // the status: a bordered label, the word itself carries it
            text = statusText(r); textSize = 13f; setTypeface(typeface, Typeface.BOLD); setTextColor(Color.WHITE)
            val m = (6 * dp).toInt(); setPadding(m, m / 2, m, m / 2)
            background = GradientDrawable().apply { setStroke(maxOf(2, (1.5f * dp).toInt()), Color.WHITE); cornerRadius = 4 * dp }
        })
        c.addView(top)
        c.addView(small("game v${r.optString("game_version")}, player ${r.optString("apk_version")}"))
        c.addView(small("sent from ${r.optString("device").ifEmpty { "?" }}" + r.optString("android").let { if (it.isEmpty() || it == "null") "" else ", Android $it" } +
                        ", IP ${r.optString("ip").ifEmpty { "?" }.replace("null", "?")}, install ${r.optString("install_id").take(8)}"))
        val text = r.optString("final_text").ifEmpty { r.optString("raw_transcript") }
        c.addView(TextView(this).apply { this.text = text.ifEmpty { "(no text)" }; textSize = 16f; setPadding(0, (8 * dp).toInt(), 0, 0)
            if (r.optString("final_text").isEmpty()) setTypeface(typeface, Typeface.ITALIC) })
        val tags = listOfNotNull(r.optString("category").ifEmpty { null }?.let { "category: $it" },
                                 r.optString("fighters").ifEmpty { null }?.let { "fighters: $it" })
        if (tags.isNotEmpty()) c.addView(small(tags.joinToString("   ")))
        if (r.optString("notes").isNotEmpty()) c.addView(TextView(this).apply {
            this.text = "Developer's notes: " + r.optString("notes"); textSize = 14f; setPadding(0, (8 * dp).toInt(), 0, 0) })
        val shot = r.optString("screen")
        val audio = r.optString("audio_path")
        if (shot.isNotEmpty() || audio.isNotEmpty()) {
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, (10 * dp).toInt(), 0, 0) }
            if (shot.isNotEmpty()) {
                val iv = ImageView(this).apply { adjustViewBounds = true; scaleType = ImageView.ScaleType.FIT_START; contentDescription = "screenshot"
                    maxWidth = (360 * dp).toInt() }                    // a thumbnail: tap = full screen
                row.addView(iv, LinearLayout.LayoutParams(-2, -2))
                row.addView(View(this), LinearLayout.LayoutParams(0, 1, 1f))
                image(r.optString("id"), shot, iv)
                iv.setOnClickListener { full(r.optString("id"), shot) }
            }
            if (audio.isNotEmpty()) row.addView(Button(this).apply { this.text = "▶ Voice"; setOnClickListener { play(this, r.optString("id"), audio) } },
                                                LinearLayout.LayoutParams(-2, -2).apply { leftMargin = (8 * dp).toInt() })
            c.addView(row)
        }
        val h = r.optJSONArray("history")
        if (h != null && h.length() > 0) {
            c.addView(small("History").apply { setTypeface(typeface, Typeface.BOLD); setPadding(0, (10 * dp).toInt(), 0, 0) })
            for (i in 0 until h.length()) {
                val e = h.getJSONObject(i)
                val from = e.optString("from_status"); val to = e.optString("to_status")
                val what = if (from.isEmpty()) to else if (from == to) "" else "$from → $to"
                val note = e.optString("note")
                c.addView(small("${when_(e.optString("at"))}  " + listOf(what, note).filter { it.isNotEmpty() }.joinToString(": ") + "  (${e.optString("by")})"))
            }
        }
        return LinearLayout(this).apply { setPadding(0, 0, 0, (12 * dp).toInt()); addView(c, LinearLayout.LayoutParams(-1, -2)) }
    }

    private fun small(t: String) = TextView(this).apply { text = t; textSize = 13f; alpha = 0.75f; setPadding(0, (3 * dp).toInt(), 0, 0) }

    /** a bundle image, fetched with the token (thumbnails halved: the marked screenshot is 4x the game's picture) */
    private fun image(id: String, name: String, iv: ImageView, sample: Int = 2) {
        val k = "$id/$name/$sample"
        images[k]?.let { iv.setImageBitmap(it); return }
        Thread {
            val b = try { get("mine/file/$id/$name")?.takeIf { it.responseCode == 200 }?.inputStream?.use {
                BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply { inSampleSize = sample }) } } catch (x: Exception) { null }
            if (b != null) runOnUiThread { images[k] = b; iv.setImageBitmap(b) }
        }.start()
    }

    private fun full(id: String, name: String) {
        val iv = ImageView(this).apply { adjustViewBounds = true; setBackgroundColor(Color.BLACK) }
        image(id, name, iv, 1)
        android.app.Dialog(this, android.R.style.Theme_Black_NoTitleBar_Fullscreen).apply {
            setContentView(iv); iv.setOnClickListener { dismiss() }; show() }
    }

    /** the voice, streamed with the token; the same button stops it */
    private fun play(b: Button, id: String, name: String) {
        val was = playing
        player?.release(); player = null; playing?.text = "▶ Voice"; playing = null
        if (was === b) return
        Thread {
            val tok = Auth.token(this)
            val u = Feedback.url(this, "mine/file/$id/$name") ?: return@Thread
            runOnUiThread {
                try {
                    player = MediaPlayer().apply {
                        setDataSource(this@FeedbackListActivity, Uri.parse(u.toString()), mapOf("Authorization" to "Bearer $tok"))
                        setOnPreparedListener { it.start() }
                        setOnCompletionListener { b.text = "▶ Voice"; if (playing === b) playing = null }
                        prepareAsync()
                    }
                    b.text = "■ Stop"; playing = b
                } catch (x: Exception) { android.widget.Toast.makeText(this, "Cannot play: ${x.message}", android.widget.Toast.LENGTH_SHORT).show() }
            }
        }.start()
    }
}
