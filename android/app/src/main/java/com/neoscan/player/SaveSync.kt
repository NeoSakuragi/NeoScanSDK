package com.neoscan.player

import android.content.Context
import android.util.Base64
import android.util.Log
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/** CLOUD SAVES (Player 0.0.39, docs/feedback.md "Cloud saves"; both apps): the emulator's backup data of a game (the
 *  save dir's <rom>.nv MVS backup RAM, .srm, .mcr AES memory card, .brm, as player.c's flushSaves writes them) kept
 *  per Oros account on the feedback service (GET / PUT / DELETE saves/<rom name>), so a save follows the account to
 *  another Player. Any .neo game, keyed by the ROM's name.
 *  - Local: one save dir PER ACCOUNT (files/save/<user>/, [dir]); the next account after a log out never sees another's.
 *  - [pull] at the game's start (after the sign-in, before the core loads): the server's save replaces the local one
 *    when it is a revision this Player has not synced and the local save has not changed since its last sync; both
 *    changed = newest wins (the times the saves changed), the other kept on the server as a backup revision.
 *  - [flushed] after every flushSaves (each pause, the thread's end, every [EmuThread] SYNC_MS while playing): a changed
 *    save is sent (PUT with the last synced revision; 409 = another Player saved meanwhile: newest wins as above).
 *    Offline = the local save stays, sent at the next flush.
 *  - [reset]: Reset game save also deletes the server's copy (retried until it goes through).
 *  The state per game: <rom>.cloud.json in the save dir {rev synced, hash synced, seen (the last local hash),
 *  updated (ms, when the local save last changed), reset (a DELETE pending), gen}. */
object SaveSync {
    private const val TAG = "NeoScanPlayer"
    val EXT = arrayOf("nv", "srm", "mcr", "brm")
    private val net = java.util.concurrent.Executors.newSingleThreadExecutor()
    private val pulled = java.util.Collections.synchronizedSet(HashSet<String>())   // games whose start pull ran (dir|base)
    @Volatile private var app: Context? = null

    /** this account's save dir (the files of the pre-0.0.39 shared dir move into the first account's own) */
    fun dir(ctx: Context): File {
        app = ctx.applicationContext
        val root = File(ctx.filesDir, "save").apply { mkdirs() }
        val u = (Auth.user(ctx) ?: "_").replace(Regex("[^A-Za-z0-9._@-]"), "_")
        val d = File(root, u)
        if (!d.exists()) {
            d.mkdirs()
            root.listFiles()?.filter { it.isFile && it.extension in EXT }?.forEach { f ->
                Log.i(TAG, "save: ${f.name} -> ${u}/ (the account's own save dir)"); f.renameTo(File(d, f.name)) }
        }
        return d
    }

    private class Meta(val f: File) {
        var rev = 0; var hash = ""; var seen = ""; var updated = 0L; var reset = false; var gen = 0
        init { try { JSONObject(f.readText()).let { rev = it.optInt("rev"); hash = it.optString("hash"); seen = it.optString("seen")
            updated = it.optLong("updated"); reset = it.optBoolean("reset"); gen = it.optInt("gen") } } catch (_: Exception) {} }
        fun save() { val t = File(f.path + ".part"); t.writeText(JSONObject().put("rev", rev).put("hash", hash).put("seen", seen)
            .put("updated", updated).put("reset", reset).put("gen", gen).toString()); t.renameTo(f) }
    }
    private fun meta(dir: File, base: String) = Meta(File(dir, "$base.cloud.json"))
    private val lock = Any()
    /** the state read, changed and written under one lock (the emulation thread and the network thread both write it) */
    private fun <T> edit(dir: File, base: String, f: (Meta) -> T): T = synchronized(lock) { val m = meta(dir, base); f(m).also { m.save() } }

    private fun snapshot(dir: File, base: String): Map<String, ByteArray> =
        EXT.mapNotNull { x -> File(dir, "$base.$x").takeIf { it.isFile }?.let { x to it.readBytes() } }.toMap()
    private fun hash(s: Map<String, ByteArray>): String {
        if (s.isEmpty()) return ""
        val md = MessageDigest.getInstance("SHA-256")
        for (x in EXT) s[x]?.let { md.update(x.toByteArray()); md.update(it) }
        return md.digest().joinToString("") { "%02x".format(it) }
    }
    /** the local save changed since it was last looked at: its change time is now */
    private fun look(m: Meta, h: String) { if (h != m.seen) { m.seen = h; m.updated = System.currentTimeMillis() } }

    private fun url(base: String, q: String = "") = URL(Auth.feedbackUrl("saves/$base$q"))
    /** one call with the token: (HTTP code, the JSON answer); code -1 = no answer (offline) */
    private fun call(ctx: Context, method: String, u: URL, body: ByteArray? = null, ifMatch: Int? = null): Pair<Int, JSONObject?> = try {
        val c = Auth.call(ctx) { tok -> (u.openConnection() as HttpURLConnection).apply {
            connectTimeout = 8000; readTimeout = 20000; requestMethod = method
            setRequestProperty("X-Install-Id", Feedback.installId(ctx)); setRequestProperty("X-App-Version", BuildConfig.VERSION_NAME)
            if (tok != null) setRequestProperty("Authorization", "Bearer $tok")
            if (ifMatch != null) setRequestProperty("If-Match", "\"$ifMatch\"")
            if (body != null) { doOutput = true; setFixedLengthStreamingMode(body.size); setRequestProperty("Content-Type", "application/json")
                outputStream.use { it.write(body) } }
        } }
        val code = c.responseCode
        val txt = (if (code in 200..299) c.inputStream else c.errorStream)?.use { it.readBytes().toString(Charsets.UTF_8) } ?: ""
        code to (try { JSONObject(txt) } catch (_: Exception) { null })
    } catch (x: Exception) { Log.w(TAG, "cloud save: $method ${x.message}"); -1 to null }

    private fun put(ctx: Context, base: String, s: Map<String, ByteArray>, updated: Long, rev: Int, backup: Boolean = false): Pair<Int, JSONObject?> {
        val files = JSONObject(); for ((x, b) in s) files.put(x, Base64.encodeToString(b, Base64.NO_WRAP))
        val body = JSONObject().put("base_rev", rev).put("updated", updated).put("files", files).toString().toByteArray()
        return call(ctx, "PUT", url(base, if (backup) "?backup=1" else ""), body, if (backup) null else rev)
    }
    private fun apply(dir: File, base: String, m: Meta, j: JSONObject) {
        val files = j.getJSONObject("files")
        for (x in EXT) { val f = File(dir, "$base.$x")
            if (files.has(x)) { val t = File(f.path + ".part"); t.writeBytes(Base64.decode(files.getString(x), Base64.NO_WRAP)); t.renameTo(f) } else f.delete() }
        m.rev = j.getInt("rev"); m.hash = hash(snapshot(dir, base)); m.seen = m.hash; m.updated = j.optLong("updated")
        Log.i(TAG, "cloud save: $base rev ${m.rev} from the server (${j.optInt("size")} bytes, saved ${j.optString("saved_at")})")
    }
    /** a pending Reset game save: the server's copy deleted first (false = not yet, offline) */
    private fun deletePending(ctx: Context, dir: File, base: String): Boolean {
        val gen = synchronized(lock) { meta(dir, base).let { if (!it.reset) return true; it.gen } }
        val (code, _) = call(ctx, "DELETE", url(base))
        if (code != 200) { Log.w(TAG, "cloud save: $base delete HTTP $code, retried later"); return false }
        edit(dir, base) { m -> if (m.gen == gen) { m.reset = false; m.rev = 0 } }; Log.i(TAG, "cloud save: $base deleted on the server"); return true
    }
    /** the local save sent; 409 = another Player saved meanwhile: newest wins */
    private fun send(ctx: Context, dir: File, base: String, s: Map<String, ByteArray>, h: String) {
        val m = synchronized(lock) { meta(dir, base) }
        var r1 = put(ctx, base, s, m.updated, m.rev)
        val c = r1.second
        if (r1.first == 409 && c != null) {
            if (m.updated >= c.optLong("updated")) { Log.i(TAG, "cloud save: $base conflict, this one is newer: it replaces rev ${c.optInt("rev")}")
                r1 = put(ctx, base, s, m.updated, c.optInt("rev")) }
            else { Log.i(TAG, "cloud save: $base conflict, the server's rev ${c.optInt("rev")} is newer: this one kept there as a backup")
                put(ctx, base, s, m.updated, m.rev, backup = true); edit(dir, base) { it.hash = h }; return }   // the next start takes the server's
        }
        val (code, j) = r1
        if (code == 200 && j != null) { val r = j.getInt("rev"); edit(dir, base) { it.rev = r; it.hash = h }; Log.i(TAG, "cloud save: $base sent, rev $r (${s.values.sumOf { it.size }} bytes)") }
        else Log.w(TAG, "cloud save: $base not sent (HTTP $code), retried at the next flush")
    }

    /** at the game's start, before the core loads (blocking, off the UI thread) */
    fun pull(ctx: Context, dir: File, rom: File) {
        val base = rom.name.substringBeforeLast('.')
        if (!pulled.add(dir.path + "|" + base)) return                  // once per process: a second activity (TODO #183) finds the core running
        val s = snapshot(dir, base); val h = hash(s)
        edit(dir, base) { look(it, h) }
        if (!deletePending(ctx, dir, base)) return
        val m = meta(dir, base)                                         // nothing else runs this game yet: the core loads after
        val (code, j) = call(ctx, "GET", url(base))
        when {
            code == 404 -> {
                val del = j?.optLong("deleted") ?: 0L
                val erase = m.rev > 0 && del > 0 && h == m.hash && del >= m.updated   // a Reset game save on another Player
                if (erase) { for (x in EXT) File(dir, "$base.$x").delete(); Log.i(TAG, "cloud save: $base was reset on another Player: the local one erased") }
                m.rev = 0; m.hash = ""; if (erase) m.seen = ""; m.save()
                if (!erase && s.isNotEmpty()) net.execute { send(ctx, dir, base, s, h) }   // a save the server lacks
                else Log.i(TAG, "cloud save: $base none on the server")
            }
            code == 200 && j != null -> {
                val rev = j.getInt("rev")
                if (rev == m.rev) { Log.i(TAG, "cloud save: $base rev $rev, in sync"); if (h != m.hash && s.isNotEmpty()) net.execute { send(ctx, dir, base, s, h) }; return }
                if (s.isEmpty() || h == m.hash) { apply(dir, base, m, j); m.save(); return }
                if (j.optLong("updated") >= m.updated) {                // both changed, the server's is newer
                    Log.i(TAG, "cloud save: $base both changed, the server's rev $rev is newer: this one kept there as a backup")
                    put(ctx, base, s, m.updated, m.rev, backup = true); apply(dir, base, m, j); m.save()
                } else { Log.i(TAG, "cloud save: $base both changed, this one is newer"); net.execute { send(ctx, dir, base, s, h) } }
            }
            else -> Log.w(TAG, "cloud save: $base GET HTTP $code: the local save plays (offline)")
        }
    }

    /** after a flushSaves, on the emulation thread: the files read now, sent on the network thread when changed */
    fun flushed(saveDir: String, rom: String) {
        val ctx = app ?: return
        val dir = File(saveDir); val base = File(rom).name.substringBeforeLast('.')
        if (!pulled.contains(dir.path + "|" + base)) return               // only a game started through pull (not the Lab shell)
        val s = snapshot(dir, base); val h = hash(s)
        val (go, gen) = edit(dir, base) { m -> look(m, h); ((h != m.hash && s.isNotEmpty()) || m.reset) to m.gen }
        if (!go) return
        net.execute {
            if (synchronized(lock) { meta(dir, base).gen } != gen) return@execute   // a Reset game save came after this snapshot
            if (!deletePending(ctx, dir, base) || s.isEmpty()) return@execute
            if (h != synchronized(lock) { meta(dir, base).hash }) send(ctx, dir, base, s, h)   // a send before this one may have sent it
        }
    }

    /** Reset game save: the local files are already gone (emulation thread, before the new core loads) */
    fun reset(dir: File, rom: File) {
        val ctx = app ?: return
        val base = rom.name.substringBeforeLast('.')
        edit(dir, base) { m -> m.reset = true; m.hash = ""; m.seen = ""; m.updated = System.currentTimeMillis(); m.gen++ }
        net.execute { deletePending(ctx, dir, base) }
    }

    /** before the process ends (Log out): the pending calls get a few seconds */
    fun drain(ms: Long = 4000) { try { net.submit {}.get(ms, java.util.concurrent.TimeUnit.MILLISECONDS) } catch (_: Exception) {} }
}
