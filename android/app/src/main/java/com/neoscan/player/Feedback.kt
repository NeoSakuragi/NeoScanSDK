package com.neoscan.player

import android.content.Context
import android.graphics.Bitmap
import android.media.MediaRecorder
import android.os.Build
import android.util.Log
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/** Voice feedback (docs/feedback.md). Hold the mic button: at the press the emulation thread writes an exact replay of
 *  the last minute (the oldest kept save state, the inputs since, the state now: player.c Native.feedback) and the
 *  picture; the voice records while the button is held. Release ([stop]): the game pauses, the voice goes to
 *  <ROM base>/../feedback/transcribe and its text comes back ([transcribe], ~2 s) into an editable box (MainActivity);
 *  Send ([send]): the bundle (states, inputs.bin, screen.png, audio.m4a, meta.json with the final text) is zipped into
 *  files/feedback/queue and POSTed to ../feedback/upload (tools/feedback/server.py); a failed upload stays queued and
 *  is retried ([flush]: at start and every minute). A tap (no voice) opens the box empty: a typed note. Test hook: a file feedback_test_audio.(wav|m4a|mp3|ogg) in the app's external files dir is sent in
 *  place of the microphone (adb push; the emulator has no voice). */
class Feedback(private val ctx: Context, private val rom: File, private val emu: () -> EmuThread?) {
    /** 0.0.29: the Character lab's shell + pack while the core runs them (CharacterLab.noteInfo): a note then records
     *  those (rom_* = the shell, rom_version "lab <shell> + <fighter> <pack>", "lab" = the details), not brawler.neo's */
    var lab: (() -> JSONObject?)? = null
    private var dir: File? = null
    private var rec: MediaRecorder? = null
    private var t0 = 0L
    private var frames: LongArray? = null
    @Volatile private var captured = java.util.concurrent.CountDownLatch(0)   // the press capture is on disk

    val recording get() = dir != null

    /** button down: capture the game now, start the voice ([mic] = the permission is granted) */
    fun start(mic: Boolean, onScreen: (Bitmap) -> Unit = {}) {
        val id = SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(Date()) + "-" + installId(ctx).take(4)
        val d = File(ctx.filesDir, "feedback/work/$id").apply { deleteRecursively(); mkdirs() }
        dir = d; t0 = android.os.SystemClock.uptimeMillis(); frames = null; txId = ""
        val latch = java.util.concurrent.CountDownLatch(1); captured = latch
        val e = emu()
        if (e != null) e.feedbackReq = d to { r, px, w, h ->
            frames = r
            Thread { try { Bitmap.createBitmap(px, w, h, Bitmap.Config.ARGB_8888).also { b ->
                onScreen(b)                                            // the scribble canvas shows it at once
                File(d, "screen.png").outputStream().use { b.compress(Bitmap.CompressFormat.PNG, 100, it) } }
            } catch (x: Exception) { Log.w(TAG, "feedback: screenshot ${x.message}") }
                latch.countDown() }.start()
        } else latch.countDown()
        if (testAudio() == null && mic) try {
            rec = (if (Build.VERSION.SDK_INT >= 31) MediaRecorder(ctx) else @Suppress("DEPRECATION") MediaRecorder()).apply {
                setAudioSource(MediaRecorder.AudioSource.MIC)
                setOutputFormat(MediaRecorder.OutputFormat.MPEG_4); setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                setAudioSamplingRate(16000); setAudioChannels(1); setAudioEncodingBitRate(32000)
                setMaxDuration(180_000)
                setOutputFile(File(d, "audio.m4a").absolutePath); prepare(); start()
            }
        } catch (x: Exception) { Log.w(TAG, "feedback: mic ${x.message}"); rec = null }
    }

    private var work: File? = null                                   // the bundle being written (after stop, until send / cancel)
    private var heldMs = 0L
    @Volatile private var txId = ""                                   // the server's id of this voice's transcription (its cost)

    /** button up: the voice stops; returns how long the button was held (shorter than [MIN_MS] = a tap: a text note) */
    fun stop(): Long {
        val d = dir ?: return 0; dir = null; work = d
        heldMs = android.os.SystemClock.uptimeMillis() - t0
        val r = rec; rec = null
        try { r?.stop() } catch (x: Exception) { Log.w(TAG, "feedback: mic stop ${x.message}"); File(d, "audio.m4a").delete() }
        r?.release()
        if (heldMs < MIN_MS) File(d, "audio.m4a").delete()                 // a tap: no voice
        else testAudio()?.let { it.copyTo(File(d, "audio." + it.extension), true) }
        return heldMs
    }

    /** the voice of the bundle being written, transcribed by the server at once (blocking: off the UI thread);
     *  null = no voice, or offline / the server failed */
    fun transcribe(): Pair<String, String>? {
        val a = audio() ?: return null
        return transcribeFile(ctx, a)?.let { txId = it.third; it.first to it.second }
    }

    /** "Reply to a note" in the note box (0.0.17): the text and the voice (if any) go as a reply to note [id] instead
     *  of a new note; the replay bundle is dropped. [done] gets null = sent, else the error (on that thread) */
    fun replyTo(id: String, text: String, raw: String, done: (String?) -> Unit) {
        val d = work ?: return; work = null
        val a = d.listFiles()?.firstOrNull { it.name.startsWith("audio.") }
        val tx = txId
        Thread {
            val r = reply(ctx, id, if (a != null) "voice" else "text", text, raw, tx, a)
            d.deleteRecursively()
            done(r.exceptionOrNull()?.message)
        }.start()
    }

    private fun audio(): File? = work?.listFiles()?.firstOrNull { it.name.startsWith("audio.") }

    /** Send: the final text (+ the server's transcript) goes with the bundle; zipped into the queue and sent in the
     *  background, [done] gets true = sent, false = queued (on that thread) */
    fun send(text: String, raw: String, model: String, transcribeError: Boolean, ink: List<Ink.Stroke>, done: (Boolean) -> Unit) {
        val d = work ?: return; work = null
        val latch = captured
        Thread {
            latch.await(3, java.util.concurrent.TimeUnit.SECONDS)
            val marked = ink.isNotEmpty() && try { Ink.write(d, ink) } catch (x: Exception) { Log.w(TAG, "feedback: scribble ${x.message}"); false }
            File(d, "meta.json").writeText(meta(d.name, heldMs).apply {
                put("final_text", text); put("raw_transcript", raw); put("transcript_model", model)
                put("transcribe_error", transcribeError); put("transcribe_tx", txId)
                if (marked) put("annotation", JSONObject().put("strokes", ink.size).put("scale", Ink.SCALE)
                    .put("files", org.json.JSONArray(listOf("annotation.png", "screen_marked.png"))))
                put("kind", if (d.listFiles()!!.any { it.name.startsWith("audio.") }) "voice" else "text")
            }.toString(2))
            val q = File(ctx.filesDir, "feedback/queue").apply { mkdirs() }
            val zip = File(q, d.name + ".zip"); val part = File(q, d.name + ".zip.part")
            ZipOutputStream(part.outputStream().buffered()).use { z ->
                for (f in d.listFiles()!!.sortedBy { it.name }) {
                    z.setLevel(if (f.extension in setOf("m4a", "mp3", "ogg", "png")) 0 else 6)
                    z.putNextEntry(ZipEntry(f.name)); f.inputStream().use { it.copyTo(z) }; z.closeEntry()
                }
            }
            part.renameTo(zip); d.deleteRecursively()
            done(flush(ctx) && !zip.exists())
        }.start()
    }

    /** a test attempt's replay (Player 0.0.22, TestMode's 👎): the bundle being written (states + inputs since the
     *  scenario state, the screenshot, the voice) with its meta.json, handed over instead of sent as a note; null = none */
    fun takeAttempt(text: String, raw: String): File? {
        val d = work ?: return null; work = null
        captured.await(3, java.util.concurrent.TimeUnit.SECONDS)
        File(d, "meta.json").writeText(meta(d.name, heldMs).apply { put("final_text", text); put("raw_transcript", raw); put("kind", "test") }.toString(2))
        return d
    }

    /** Cancel: the bundle is dropped */
    fun cancel() { work?.deleteRecursively(); work = null }

    private fun testAudio(): File? = testAudio(ctx)

    /** a voice reply's recording (the list's "Hold to talk", 0.0.17): the same AAC settings as a note's voice; the
     *  test file replaces the microphone when present */
    class VoiceRec(private val ctx: Context) {
        private var rec: MediaRecorder? = null
        private var t0 = 0L
        var file: File? = null; private set
        fun start(): Boolean {
            stopQuiet(); t0 = android.os.SystemClock.uptimeMillis()
            val f = File(ctx.cacheDir, "reply_audio.m4a").apply { delete() }
            if (testAudio(ctx) != null) return true
            return try {
                rec = (if (Build.VERSION.SDK_INT >= 31) MediaRecorder(ctx) else @Suppress("DEPRECATION") MediaRecorder()).apply {
                    setAudioSource(MediaRecorder.AudioSource.MIC)
                    setOutputFormat(MediaRecorder.OutputFormat.MPEG_4); setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                    setAudioSamplingRate(16000); setAudioChannels(1); setAudioEncodingBitRate(32000); setMaxDuration(180_000)
                    setOutputFile(f.absolutePath); prepare(); start()
                }; true
            } catch (x: Exception) { Log.w(TAG, "reply: mic ${x.message}"); rec = null; false }
        }
        /** -> the voice file, or null (held under [MIN_MS], or no voice) */
        fun stop(): File? {
            val held = android.os.SystemClock.uptimeMillis() - t0
            val r = rec; rec = null
            val f = File(ctx.cacheDir, "reply_audio.m4a")
            try { r?.stop() } catch (x: Exception) { f.delete() }
            r?.release()
            val t = testAudio(ctx)
            file = if (held < MIN_MS) null else if (t != null) File(ctx.cacheDir, "reply_audio." + t.extension).also { t.copyTo(it, true) }
                   else f.takeIf { it.exists() && it.length() > 0 }
            return file
        }
        fun stopQuiet() { try { rec?.stop() } catch (x: Exception) { }; rec?.release(); rec = null }
        fun clear() { stopQuiet(); file = null }
    }

    private fun meta(id: String, held: Long): JSONObject {
        val p = ctx.getPackageManager().getPackageInfo(ctx.packageName, 0)
        val fetch = ctx.getSharedPreferences("fetch", 0)
        val e = emu()
        return JSONObject().apply {
            put("id", id); put("created", iso(System.currentTimeMillis())); put("held_ms", held)
            put("app_version", p.versionName)
            put("app_code", if (Build.VERSION.SDK_INT >= 28) p.longVersionCode else @Suppress("DEPRECATION") p.versionCode.toLong())
            val lab = try { lab?.invoke() } catch (x: Exception) { null }
            if (lab != null) {
                put("rom_file", "lab-shell-" + lab.optString("shell_version") + ".neo"); put("rom_size", lab.optLong("shell_size"))
                put("rom_sha256", lab.optString("shell_sha256"))
                put("rom_version", "lab ${lab.optString("shell_version")} + ${lab.optString("pack_fighter")} ${lab.optString("pack_version")}")
                put("rom_build", "lab"); put("lab", lab)
            } else {
                put("rom_file", rom.name); put("rom_size", rom.length()); put("rom_sha256", sha(rom))
                put("rom_version", RomFetch.installed(ctx)); put("rom_build", RomFetch.loadedBuild(ctx))
            }
            put("latest_sha256", fetch.getString("sha256", ""))
            put("bios_sha256", sha(File(ctx.filesDir, "system/neogeo.zip")))
            put("hw", e?.hw ?: "?"); put("system_type", if (e != null) Native.systemType() else "?"); put("region", "us")
            put("memcard", if (e != null) Native.memcard() else "?")
            put("device", "${Build.MANUFACTURER} ${Build.MODEL}"); put("android", "${Build.VERSION.RELEASE} (SDK ${Build.VERSION.SDK_INT})")
            put("install_id", installId(ctx)); put("user", Auth.user(ctx) ?: "")   // the server's user comes from the token
            put("tester", !Auth.admin(ctx))
            frames?.let { put("window_frame", it[0]); put("press_frame", it[1]) }
            put("audio", File(ctx.filesDir, "feedback/work/$id").listFiles()?.firstOrNull { it.name.startsWith("audio.") }?.name ?: "")
        }
    }

    companion object {
        private const val TAG = "NeoScanPlayer"
        const val MIN_MS = 400L                                      // shorter = a stray touch: cancelled

        fun installId(ctx: Context): String {
            val p = ctx.getSharedPreferences("fetch", 0)
            return p.getString("install", null) ?: java.util.UUID.randomUUID().toString().also { p.edit().putString("install", it).apply() }
        }

        /** the upload URL: <ROM base>/../feedback/upload (canneji.duckdns.org/brawler/feedback/upload) */
        fun url(ctx: Context, what: String = "upload"): URL? = RomFetch.base(ctx)?.let { URL(URL(it), "../feedback/$what") }

        /** a voice file transcribed by the server at once (blocking: off the UI thread) -> (text, model, tx_id);
         *  null = offline / the server failed */
        fun transcribeFile(ctx: Context, a: File): Triple<String, String, String>? {
            val u = url(ctx, "transcribe") ?: return null
            return try {
                val c = Auth.call(ctx) { tok -> (u.openConnection() as HttpURLConnection).apply {
                    connectTimeout = 5000; readTimeout = 60000; requestMethod = "POST"; doOutput = true
                    setFixedLengthStreamingMode(a.length())
                    setRequestProperty("Content-Type", "application/octet-stream"); setRequestProperty("X-Audio-Name", a.name)
                    setRequestProperty("X-Install-Id", installId(ctx)); setRequestProperty("X-App-Version", BuildConfig.VERSION_NAME)
                    if (tok != null) setRequestProperty("Authorization", "Bearer $tok")
                    outputStream.use { o -> a.inputStream().use { it.copyTo(o) } }
                } }
                if (c.responseCode != 200) { Log.w(TAG, "feedback: transcribe HTTP ${c.responseCode}"); null }
                else JSONObject(c.inputStream.use { it.readBytes().toString(Charsets.UTF_8) }).let {
                    Triple(it.getString("text"), it.optString("model"), it.optString("tx_id")) }
            } catch (x: Exception) { Log.w(TAG, "feedback: transcribe ${x.message}"); null }
        }

        /** a reply to one of his notes (0.0.17, POST ../feedback/reply): [kind] voice | text | up (verified fixed) |
         *  down (still broken: reopened); the voice goes along in base64. Blocking. -> the note's row, or the error */
        fun reply(ctx: Context, id: String, kind: String, text: String, raw: String = "", tx: String = "", audio: File? = null): Result<JSONObject> {
            val u = url(ctx, "reply") ?: return Result.failure(Exception("no server"))
            val body = JSONObject().apply {
                put("id", id); put("kind", kind); put("text", text); put("raw_transcript", raw); put("tx_id", tx)
                put("device", "${Build.MANUFACTURER} ${Build.MODEL}"); put("android", "${Build.VERSION.RELEASE} (SDK ${Build.VERSION.SDK_INT})")
                if (audio != null) { put("audio_name", audio.name); put("audio_b64", android.util.Base64.encodeToString(audio.readBytes(), android.util.Base64.NO_WRAP)) }
            }.toString().toByteArray()
            return try {
                val c = Auth.call(ctx) { tok -> (u.openConnection() as HttpURLConnection).apply {
                    connectTimeout = 5000; readTimeout = 30000; requestMethod = "POST"; doOutput = true
                    setFixedLengthStreamingMode(body.size); setRequestProperty("Content-Type", "application/json")
                    setRequestProperty("X-Install-Id", installId(ctx)); setRequestProperty("X-App-Version", BuildConfig.VERSION_NAME)
                    if (tok != null) setRequestProperty("Authorization", "Bearer $tok")
                    outputStream.use { it.write(body) }
                } }
                val code = c.responseCode
                val txt = (if (code == 200) c.inputStream else c.errorStream)?.use { it.readBytes().toString(Charsets.UTF_8) } ?: ""
                if (code == 200) JSONObject(txt).let { j -> Result.success(j.getJSONObject("row").put("last_reply_id", j.optJSONObject("reply")?.optInt("id", -1) ?: -1)) }
                else Result.failure(Exception("HTTP $code " + (try { JSONObject(txt).optString("error") } catch (x: Exception) { "" })))
            } catch (x: Exception) { Result.failure(Exception("No connection (${x.message})")) }
        }

        /** a test attempt (Player 0.0.22, POST ../feedback/test): a zip of test.json ([t]: id, result up | down | abandoned,
         *  rom_sha, game_version, system, seconds, reply_id, note) + the attempt's replay [dir] (optional). Blocking. */
        fun postTest(ctx: Context, t: JSONObject, dir: File?): Result<JSONObject> {
            val u = url(ctx, "test") ?: return Result.failure(Exception("no server"))
            val bos = java.io.ByteArrayOutputStream()
            ZipOutputStream(bos).use { z ->
                t.put("device", "${Build.MANUFACTURER} ${Build.MODEL}")
                z.putNextEntry(ZipEntry("test.json")); z.write(t.toString().toByteArray()); z.closeEntry()
                dir?.listFiles()?.sortedBy { it.name }?.forEach { f ->
                    if (!Regex("^[a-z0-9_]{1,40}\\.(state|bin|png|json|m4a|wav|mp3|ogg|txt)$").matches(f.name) || f.name == "test.json") return@forEach
                    z.putNextEntry(ZipEntry(f.name)); f.inputStream().use { it.copyTo(z) }; z.closeEntry() }
            }
            val body = bos.toByteArray()
            return try {
                val c = Auth.call(ctx) { tok -> (u.openConnection() as HttpURLConnection).apply {
                    connectTimeout = 5000; readTimeout = 30000; requestMethod = "POST"; doOutput = true
                    setFixedLengthStreamingMode(body.size); setRequestProperty("Content-Type", "application/zip")
                    setRequestProperty("X-Install-Id", installId(ctx)); setRequestProperty("X-App-Version", BuildConfig.VERSION_NAME)
                    if (tok != null) setRequestProperty("Authorization", "Bearer $tok")
                    outputStream.use { it.write(body) }
                } }
                val code = c.responseCode
                val txt = (if (code == 200) c.inputStream else c.errorStream)?.use { it.readBytes().toString(Charsets.UTF_8) } ?: ""
                if (code == 200) Result.success(JSONObject(txt)) else Result.failure(Exception("HTTP $code $txt"))
            } catch (x: Exception) { Result.failure(Exception("No connection (${x.message})")) }
        }

        /** a note's test state for this build and system (GET ../feedback/mine/scenario/<id>/<sha>/<key>.state), cached;
         *  blocking; the file, or the reason it is not there */
        fun scenarioState(ctx: Context, id: String, sha: String, key: String): Result<File> {
            val f = File(ctx.cacheDir, "scenario/${id}_${sha.take(12)}_$key.state")
            if (f.exists() && f.length() > 0) return Result.success(f)
            val u = url(ctx, "mine/scenario/$id/$sha/$key.state") ?: return Result.failure(Exception("no server"))
            return try {
                val c = Auth.call(ctx) { tok -> (u.openConnection() as HttpURLConnection).apply {
                    connectTimeout = 5000; readTimeout = 30000
                    setRequestProperty("X-Install-Id", installId(ctx)); setRequestProperty("X-App-Version", BuildConfig.VERSION_NAME)
                    if (tok != null) setRequestProperty("Authorization", "Bearer $tok")
                } }
                if (c.responseCode == 404) return Result.failure(Exception("No test state for the build you run yet"))
                if (c.responseCode != 200) return Result.failure(Exception("The server answered HTTP ${c.responseCode}"))
                f.parentFile?.mkdirs(); val part = File(f.path + ".part")
                c.inputStream.use { i -> part.outputStream().use { i.copyTo(it) } }
                part.renameTo(f); Result.success(f)
            } catch (x: Exception) { Result.failure(Exception("No connection (${x.message})")) }
        }

        /** the state key the player asks for: the BIOS it boots + its hardware (scenario.py SYSTEMS) */
        fun systemKey(hw: String) = Native.systemType() + "-" + hw

        /** a note can be tested on this build: it has a scenario with a state for [sha] / [key] */
        fun testable(r: JSONObject, sha: String, key: String): Boolean {
            val b = r.optJSONArray("scenario_builds") ?: return false
            return r.optJSONObject("scenario") != null && (0 until b.length()).any { b.optString(it) == "$sha/$key" }
        }
        /** the test queue and "Shipped: test it" (0.0.23, docs/feedback.md "The test queue"): the server's to_test (shipped,
         *  and no 👍 / 👎 yet on that release or a later build) and the release at or before the build he runs. A
         *  verdict takes the note out (reopened ones stay in Open); a later ship with a newer release brings it back. */
        fun wantsTest(r: JSONObject, running: String) = r.optBoolean("to_test", false) && isReady(r, running)

        /** "44 min ago", "3 h ago", "yesterday", "Oct 3" (beyond 7 days) */
        fun ago(iso: String): String = try {
            val p = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }
            val t = p.parse(iso)!!.time; val s = (System.currentTimeMillis() - t) / 1000
            when {
                s < 60 -> "just now"; s < 3600 -> "${s / 60} min ago"; s < 86400 -> "${s / 3600} h ago"
                s < 2 * 86400 -> "yesterday"; s < 7 * 86400 -> "${s / 86400} days ago"
                else -> SimpleDateFormat("MMM d", Locale.US).format(Date(t))
            }
        } catch (x: Exception) { iso.take(10) }

        /** his notes (GET ../feedback/mine): {user, rows: [... each with history + replies]}. Blocking. */
        fun mine(ctx: Context): Result<JSONObject> = try {
            val u = url(ctx, "mine")
            val c = if (u == null) null else Auth.call(ctx) { tok -> (u.openConnection() as HttpURLConnection).apply {
                connectTimeout = 5000; readTimeout = 20000
                setRequestProperty("X-Install-Id", installId(ctx)); setRequestProperty("X-App-Version", BuildConfig.VERSION_NAME)
                if (tok != null) setRequestProperty("Authorization", "Bearer $tok")
            } }
            if (c == null) Result.failure(Exception("no server"))
            else if (c.responseCode == 401) Result.failure(Exception("Not signed in: log out and in again (settings)"))
            else if (c.responseCode != 200) Result.failure(Exception("The server answered HTTP ${c.responseCode}"))
            else Result.success(JSONObject(c.inputStream.use { it.readBytes().toString(Charsets.UTF_8) }))
        } catch (x: Exception) { Result.failure(Exception("No connection (${x.message})")) }

        /** the filters of his list (0.0.17): open = not closed and not waiting for him; ready = shipped in a build
         *  at or before the one he runs (he can test it) */
        fun isOpen(r: JSONObject) = r.optString("status") !in setOf("shipped", "wont_do", "duplicate", "verified")
        fun isReady(r: JSONObject, running: String) = r.optString("status") == "shipped" && versionLE(r.optString("release"), running)
        fun versionLE(a: String, b: String): Boolean {
            val x = a.split('.').map { it.toIntOrNull() ?: return false }; val y = b.split('.').map { it.toIntOrNull() ?: return false }
            for (i in 0 until maxOf(x.size, y.size)) { val p = x.getOrElse(i) { 0 }; val q = y.getOrElse(i) { 0 }; if (p != q) return p < q }
            return true
        }

        fun testAudio(ctx: Context): File? = ctx.getExternalFilesDir(null)?.listFiles()?.firstOrNull { it.name.startsWith("feedback_test_audio.") }

        /** send every queued bundle (blocking; off the UI thread); true when the queue is empty afterwards */
        @Synchronized fun flush(ctx: Context): Boolean {
            val q = File(ctx.filesDir, "feedback/queue")
            // 0.0.15: the bundles an older player had queued and the server refused once it needed the login (401) go again
            val fp = ctx.getSharedPreferences("feedback", 0)
            if (!fp.getBoolean("requeued015", false)) {
                q.listFiles { f -> f.name.endsWith(".zip.rejected") }?.forEach { it.renameTo(File(it.path.removeSuffix(".rejected"))) }
                fp.edit().putBoolean("requeued015", true).apply()
            }
            val zips = q.listFiles { f -> f.name.endsWith(".zip") }?.sortedBy { it.name } ?: return true
            val u = url(ctx) ?: return zips.isEmpty()
            for (z in zips) try {
                val c = Auth.call(ctx) { tok -> (u.openConnection() as HttpURLConnection).apply {
                    connectTimeout = 5000; readTimeout = 30000; requestMethod = "POST"; doOutput = true
                    setFixedLengthStreamingMode(z.length())
                    setRequestProperty("Content-Type", "application/zip"); setRequestProperty("X-Bundle", z.nameWithoutExtension)
                    setRequestProperty("X-Install-Id", installId(ctx)); setRequestProperty("X-App-Version", BuildConfig.VERSION_NAME)
                    setRequestProperty("X-Device", "${Build.MANUFACTURER} ${Build.MODEL}")
                    if (tok != null) setRequestProperty("Authorization", "Bearer $tok")
                    outputStream.use { o -> z.inputStream().use { it.copyTo(o) } }
                } }
                val code = c.responseCode
                if (code == 200) { Log.i(TAG, "feedback: ${z.name} sent: " + c.inputStream.use { it.readBytes().toString(Charsets.UTF_8) }); z.delete() }
                else if (code == 401) { Log.w(TAG, "feedback: ${z.name}: not signed in, kept queued"); return false }
                else { Log.w(TAG, "feedback: ${z.name}: HTTP $code"); if (code in 400..499 && code != 408 && code != 429) z.renameTo(File(z.path + ".rejected")); return false }
            } catch (x: Exception) { Log.w(TAG, "feedback: ${z.name} queued (${x.message})"); return false }
            return true
        }

        /** sha256 of a file, cached by (path, size, mtime) */
        private val shas = HashMap<String, String>()
        fun sha(f: File): String {
            if (!f.exists()) return ""
            val k = "${f.path}:${f.length()}:${f.lastModified()}"
            return synchronized(shas) { shas[k] } ?: MessageDigest.getInstance("SHA-256").let { md ->
                f.inputStream().use { i -> val b = ByteArray(1 shl 16); while (true) { val n = i.read(b); if (n < 0) break; md.update(b, 0, n) } }
                md.digest().joinToString("") { "%02x".format(it) }
            }.also { synchronized(shas) { shas[k] = it } }
        }

        /** a server time (UTC ISO) in the device's time zone, "yyyy-MM-dd HH:mm" */
        fun local(iso: String): String = try {
            val p = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }
            SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.US).format(p.parse(iso)!!)
        } catch (x: Exception) { iso.take(16).replace('T', ' ') }

        private fun iso(t: Long) = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }.format(Date(t))
    }
}
