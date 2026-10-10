package com.neoscan.player

import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.BitmapDrawable
import android.graphics.drawable.GradientDrawable
import android.util.Log
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/** CHARACTER LAB (Player 0.0.28, admin only; docs/feedback.md "Character Lab: the Player"). One Lab SHELL build + a
 *  CHARACTER PACK per fighter (docs/feedback.md "Character Lab: shell and packs"), served by the feedback service
 *  (`/brawler/lab/`: catalogue, config, downloads; the Oros token as for the builds).
 *  - FACES: GET catalogue -> the fighters' faces with the shell / pack versions. A tap: the shell (once) and that pack
 *    downloaded (cached by sha256 in files/lab, resumed with Range, sha256 checked as RomFetch does), the core switched
 *    to the shell (it boots into its practice by itself), then the pack swapped in (Native.swapPack: a reset into the
 *    practice with that fighter). Another face = another swap, no reboot.
 *  - LIVE CONFIG: every 2 s GET config/<f>/hash with If-None-Match (304 = nothing); a new hash -> GET config/<f> and its
 *    blob (a TRY blob, chainlab/lab.js encodeTry) written into the game's RAM exactly as lab.js installTry does (tblob,
 *    lstat 0, tnow 0, magic LAB1, fighter, load 6) once the practice runs (lab.active 1); the game applies it at neutral
 *    (lab.lstat 2 pending -> 1 applied). The blob's fighter byte is set to the pack's slot (in the shell P1 is the slot
 *    fighter, the last roster index). "Apply now" writes lab.tnow = 1. The RAM addresses: the pack's manifest `ram`
 *    (lab_pack.py ram_map: the shell's lab_t, prac, P1's state), the same for every pack of a shell.
 *  - NEW VERSIONS: the catalogue rides the same poll (ETag); a newer pack of the fighter on screen (or a newer shell) is
 *    downloaded, then swapped at the next safe moment: P1 back in neutral (standing / walking), or at once on a tap.
 *  - THE CHAIN (0.0.29): a live config is chainlab/lab.js liveBlob: the TRY blob, + 'LC' u16 n + a chain override when a
 *    page set one (the sheet's chain, the chain tool). The chain goes first, as lab.js installChain does (lab.buf, magic,
 *    fighter = the slot, load 5; its retime rows of the blob's fighter renamed to the slot); the TRY blob once the game
 *    took it. A config without a chain after one with: load 2 (the ROM's tree back) first.
 *  - LIGHTS (Bruno: "surface this intuitively with blinkers or lights whenever there is a change"): a strip OFF the
 *    picture (0.0.29: it hid the practice's HITS / DAMAGE row) and off the pad: between the picture and the pad's
 *    buttons in portrait, above the picture in landscape (0.0.31: the left gutter's strip covered the d-pad on a phone;
 *    PadView.labH / labArea, Screen.labTop): one row, a light + a word label (green IN SYNC, blinking amber NEW
 *    CONFIG pending, a flash APPLIED, red REFUSED, grey NO CONFIG / OFFLINE), a blue badge NEW PACK / NEW SHELL with its
 *    version, Apply now, Faces.
 *  - NOTES (0.0.29): a feedback note taken in the lab records the shell + pack (+ config) it ran (noteInfo), not
 *    brawler.neo's.
 *  The in-ROM practice menu is on the game's START (the pad's START). */
class CharacterLab(private val act: MainActivity, private val root: FrameLayout, private val emu: () -> EmuThread?,
                   private val play: (File) -> Unit, private val reserve: (Int) -> android.graphics.Rect, private val leave: () -> Unit) {
    private val dp = act.resources.displayMetrics.density
    private val dir = File(act.filesDir, "lab").apply { mkdirs() }
    private val base: URL? get() = RomFetch.base(act)?.let { URL(URL(it), "../lab/") }

    /** the RAM map of a shell (pack manifest `ram`): 68000 addresses */
    class Ram(j: JSONObject) {
        val lab = j.getInt("lab"); private val o = j.getJSONObject("lab_off"); private val lf = j.getJSONObject("lab_fields")
        val magic = lab + o.getInt("magic"); val fighter = lab + o.getInt("fighter"); val load = lab + o.getInt("load")
        val active = lab + o.getInt("active"); val tnow = lab + lf.getInt("tnow"); val lstat = lab + lf.getInt("lstat")
        val tblob = lab + lf.getInt("tblob"); val p1State = j.getInt("p1_state")
        /** lab_t.tblob's bytes (fighter.h TRY_MAX; lab_pack.py ram_map): the longest TRY blob the game holds (the game
         *  checks and clamps what is in it). Packs before Player 0.0.30 lack it: version 1's 576 then */
        val tblobSize = j.optInt("tblob_size", 576)
        val buf = lab + o.optInt("buf", 400)                           // lab.js LAB.buf (packs before 0.0.29 lack it)
        val neutral = j.getJSONArray("neutral").let { a -> IntArray(a.length()) { a.getInt(it) } }
    }
    class Pack(val fighter: String, val display: String, val version: String, val sha: String, val engine: String,
               val file: File, val ram: Ram?, val slot: Int)
    class Cfg(val fighter: String, val version: Int, val hash: String, val blob: ByteArray)
    /** a live config's parts (lab.js liveParts): the TRY blob, the chain override (null: none); null = not a live config */
    class Live(val tryBlob: ByteArray, val chain: ByteArray?)
    private fun liveParts(b: ByteArray): Live? {
        if (b.size < 8 || b[0] != 'L'.code.toByte() || b[1] != 'T'.code.toByte()) return null
        var n = 8 + 2 * (b[5].toInt() and 255)
        for (s in 0 until (b[6].toInt() and 255)) { if (n + 2 > b.size) return null; n += 2 + 2 * (b[n + 1].toInt() and 255) }
        if (n > b.size) return null
        if (n == b.size) return Live(b, null)
        if (n + 4 > b.size || b[n] != 'L'.code.toByte() || b[n + 1] != 'C'.code.toByte()) return null
        val len = (b[n + 2].toInt() and 255 shl 8) or (b[n + 3].toInt() and 255)
        if (n + 4 + len != b.size) return null
        return Live(b.copyOfRange(0, n), b.copyOfRange(n + 4, b.size))
    }
    /** the chain override for the shell: its retime rows of [from] (the fighter it was made for) renamed to [slot]
     *  (fighter.h rt_head_t: nnodes at 3, 16 + 24 n bytes, then gretime_t rows of 8 bytes, fighter 0xFF ends them) */
    private fun chainFor(c: ByteArray, from: Int, slot: Int): ByteArray? {
        if (c.size < 16 || c.size > LAB_BUF || c[0] != 'R'.code.toByte() || c[1] != 'T'.code.toByte()) return null
        val out = c.copyOf(); var a = 16 + 24 * (c[3].toInt() and 255)
        while (true) {
            if (a + 8 > out.size) return null
            val f = out[a].toInt() and 255
            if (f == 0xFF) return out
            if (f == from) out[a] = slot.toByte()
            a += 8
        }
    }

    var active = false; private set
    @Volatile private var shell: File? = null                       // the shell the core runs (lab mode)
    @Volatile private var shellSha: String? = null
    @Volatile private var shellEngine: String? = null
    @Volatile private var pack: Pack? = null                         // the pack in the core
    @Volatile private var swapReq: Pack? = null                      // a pack to swap in: at neutral, or now
    @Volatile private var swapNow = false
    @Volatile private var reloadReq: Pair<File, Pack>? = null        // a new shell: the core restarts on it, then the pack
    @Volatile private var reloadNow = false
    @Volatile private var cfgWant: Cfg? = null                       // the fighter's live config (the poll)
    @Volatile private var applyNow = false
    @Volatile private var noConfig = false
    @Volatile private var offline = false
    @Volatile private var catalogue: JSONObject? = null
    @Volatile private var catTag: String? = null
    @Volatile private var cfgTag: String? = null
    @Volatile private var cfgFor: String? = null                     // the fighter cfgTag belongs to
    @Volatile var paused = false                                     // the activity is not in front: no polls
    private var sent: Cfg? = null                                    // (emu thread) the config written into this boot
    private var treeSent: Cfg? = null                                // (emu thread) the config whose tree step is written
    private var chainIn = false                                      // (emu thread) a chain override is in this boot
    private var lastStat = -1; private var n = 0
    private var downloading: String? = null                          // (download thread) the sha being fetched
    private val dl = java.util.concurrent.Executors.newSingleThreadExecutor()
    private var poller: Thread? = null
    var polls200 = 0; var polls304 = 0; var polls404 = 0; var pollsErr = 0

    // ---- network -------------------------------------------------------------------------------------------------
    private class Resp(val code: Int, val etag: String?, val body: ByteArray?)
    private fun conn(u: URL, tok: String?) = (u.openConnection() as HttpURLConnection).apply {
        connectTimeout = 4000; readTimeout = 15000; useCaches = false
        setRequestProperty("X-Install-Id", Feedback.installId(act)); setRequestProperty("X-App-Version", BuildConfig.VERSION_NAME)
        if (tok != null) setRequestProperty("Authorization", "Bearer $tok")
    }
    /** an authorised GET of [path] (relative to /brawler/lab/, or a /brawler/lab/dl/ path), If-None-Match [etag] */
    private fun get(path: String, etag: String? = null): Resp {
        val u = URL(base ?: throw IOException("no server"), path)
        val c = Auth.call(act) { tok -> conn(u, tok).apply { if (etag != null) setRequestProperty("If-None-Match", etag) } }
        val code = c.responseCode
        val body = if (code == 200) c.inputStream.use { it.readBytes() } else { try { c.errorStream?.close() } catch (x: Exception) { }; null }
        return Resp(code, c.getHeaderField("ETag"), body).also { c.disconnect() }
    }

    /** a file of the catalogue into files/lab/<sha256><ext>: cached, resumed (Range), checked (size + sha256) */
    private fun fetch(path: String, sha: String, size: Long, ext: String, progress: (Int) -> Unit): File {
        val out = File(dir, sha + ext)
        if (out.exists() && out.length() == size) return out
        val part = File(dir, "$sha$ext.part")
        var have = if (part.exists()) part.length() else 0L
        if (have > size) { part.delete(); have = 0 }
        val md = MessageDigest.getInstance("SHA-256")
        if (have < size) {
            val u = URL(base ?: throw IOException("no server"), path)
            val c = Auth.call(act) { tok -> conn(u, tok).apply { readTimeout = 30000; if (have > 0) setRequestProperty("Range", "bytes=$have-") } }
            when (c.responseCode) { 200 -> have = 0; 206 -> {}; else -> throw IOException("$path: HTTP ${c.responseCode}") }
            if (have > 0) part.inputStream().use { i -> val b = ByteArray(1 shl 16); while (true) { val k = i.read(b); if (k < 0) break; md.update(b, 0, k) } }
            java.io.FileOutputStream(part, have > 0).use { o -> c.inputStream.use { i ->
                val b = ByteArray(1 shl 16); var done = have; var shown = -1L
                while (true) { val k = i.read(b); if (k < 0) break; o.write(b, 0, k); md.update(b, 0, k); done += k
                    if (done * 20 / size != shown) { shown = done * 20 / size; progress((done * 100 / size).toInt()) } }
            } }
            c.disconnect()
        } else part.inputStream().use { i -> val b = ByteArray(1 shl 16); while (true) { val k = i.read(b); if (k < 0) break; md.update(b, 0, k) } }
        val got = md.digest().joinToString("") { "%02x".format(it) }
        if (part.length() != size || got != sha) { part.delete(); throw IOException("bad download ($path)") }
        if (!part.renameTo(out)) throw IOException("cannot keep $path")
        Log.i(TAG, "downloaded $path (${size / 1024} KB, sha256 ok)")
        return out
    }

    /** a pack's manifest (lab_pack.py: 'NGPK', u16 version, u16 regions, u32 manifest bytes, u32 x 6, the JSON) */
    private fun manifest(f: File): JSONObject = java.io.RandomAccessFile(f, "r").use { r ->
        val h = ByteArray(36); r.readFully(h)
        if (String(h, 0, 4, Charsets.ISO_8859_1) != "NGPK") throw IOException("not a character pack")
        val len = (h[8].toInt() and 255) or (h[9].toInt() and 255 shl 8) or (h[10].toInt() and 255 shl 16) or (h[11].toInt() and 255 shl 24)
        val m = ByteArray(len); r.readFully(m); JSONObject(String(m, Charsets.UTF_8))
    }

    private fun packOf(p: JSONObject, progress: (Int) -> Unit): Pack {
        val f = fetch(p.getString("url"), p.getString("sha256"), p.getLong("size"), ".pack", progress)
        val m = manifest(f)
        val ram = m.optJSONObject("ram")?.let { try { Ram(it) } catch (x: Exception) { null } }
        return Pack(p.getString("fighter"), p.optString("display", p.getString("fighter")), p.getString("version"),
                    p.getString("sha256"), p.optString("engine"), f, ram, m.getJSONObject("slot").getInt("id"))
    }

    private fun readCatalogue(): JSONObject? {
        val r = get("catalogue", catTag)
        count(r.code, "catalogue")
        if (r.code == 200 && r.body != null) { catTag = r.etag; catalogue = JSONObject(String(r.body, Charsets.UTF_8)); return catalogue }
        if (r.code == 304) return null
        throw IOException("catalogue: HTTP ${r.code}")
    }

    private fun count(code: Int, what: String) {
        when (code) { 200 -> polls200++; 304 -> polls304++; 404 -> polls404++; else -> pollsErr++ }
        Log.i(TAG, "poll $what -> $code (200: $polls200, 304: $polls304, 404: $polls404, errors: $pollsErr)")
    }

    // ---- the faces -----------------------------------------------------------------------------------------------
    private var faces: FrameLayout? = null
    private var facesMsg: TextView? = null
    private var grid: LinearLayout? = null
    private val facesOpen get() = faces != null
    val facesShown get() = faces != null

    /** the faces screen over the game (paused): the catalogue's fighters, the shell / pack versions */
    fun open() {
        if (!active) { active = true; startPoll() }
        emu()?.paused = true
        if (faces == null) {
            val panel = FrameLayout(act).apply { setBackgroundColor(Color.BLACK); isClickable = true }
            val col = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; val m = (16 * dp).toInt(); setPadding(m, m, m, m) }
            col.addView(text("CHARACTER LAB", 22f, true))
            facesMsg = text("Asking the server for the fighters...", 15f)
            col.addView(facesMsg)
            grid = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL }
            col.addView(grid, LinearLayout.LayoutParams(-1, -2).apply { topMargin = (12 * dp).toInt() })
            val row = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL }
            row.addView(button("Leave the lab", Color.rgb(60, 60, 70)) { leaveLab() }, LinearLayout.LayoutParams(0, (52 * dp).toInt(), 1f))
            if (pack != null) row.addView(button("Back to the game", Color.rgb(60, 60, 70)) { close() },
                LinearLayout.LayoutParams(0, (52 * dp).toInt(), 1f).apply { leftMargin = (12 * dp).toInt() })
            col.addView(row, LinearLayout.LayoutParams(-1, -2).apply { topMargin = (20 * dp).toInt() })
            panel.addView(ScrollView(act).apply { addView(col) }, FrameLayout.LayoutParams(-1, -1))
            root.addView(panel, FrameLayout.LayoutParams(-1, -1)); faces = panel
        }
        catalogue?.let { showFaces(it) }
        Thread {
            val r = try { readCatalogue() ?: catalogue } catch (x: Exception) { act.runOnUiThread { facesMsg?.text = "The server does not answer: ${x.message}" }; null }
            if (r != null) act.runOnUiThread { showFaces(r) }
        }.start()
    }

    private fun close() {
        faces?.let { root.removeView(it) }; faces = null; facesMsg = null; grid = null
        emu()?.paused = false
    }

    private fun showFaces(cat: JSONObject) {
        val g = grid ?: return
        g.removeAllViews()
        val sh = cat.optJSONObject("shell")
        val packs = cat.optJSONArray("packs")
        facesMsg?.text = if (sh == null) "No shell published yet (labpub.py publish-shell)."
            else "Shell ${sh.optString("version")}  (engine ${sh.optString("engine")}, ${sh.optLong("size") / (1 shl 20)} MB" +
                 (if (File(dir, sh.optString("sha256") + ".neo").exists()) ", downloaded)" else ")") +
                 "\nTap a fighter: his pack goes into the shell's practice."
        if (packs == null || packs.length() == 0) { g.addView(text("No character pack published yet.", 15f)); return }
        val perRow = maxOf(2, (root.width / dp / 170).toInt())
        var row: LinearLayout? = null
        for (i in 0 until packs.length()) {
            val p = packs.getJSONObject(i)
            if (i % perRow == 0) row = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL }.also {
                g.addView(it, LinearLayout.LayoutParams(-1, -2).apply { topMargin = (10 * dp).toInt() }) }
            row!!.addView(card(p, sh), LinearLayout.LayoutParams(0, -2, 1f).apply { if (i % perRow > 0) leftMargin = (10 * dp).toInt() })
        }
        for (k in packs.length() % perRow until perRow) if (packs.length() % perRow != 0) row!!.addView(View(act), LinearLayout.LayoutParams(0, 1, 1f))
    }

    /** a fighter's card: his face (pixel-exact), his name, his pack's version; a tap loads him */
    private fun card(p: JSONObject, sh: JSONObject?): View {
        val f = p.getString("fighter")
        val mine = pack?.fighter == f
        val c = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER_HORIZONTAL
            val m = (8 * dp).toInt(); setPadding(m, m, m, m); isClickable = true; contentDescription = "Load ${p.optString("display", f)}"
            background = GradientDrawable().apply { setColor(if (mine) Color.rgb(30, 50, 90) else Color.rgb(28, 28, 34))
                setStroke(((if (mine) 4 else 2) * dp).toInt(), Color.WHITE); cornerRadius = 10 * dp } }
        val img = ImageView(act).apply { scaleType = ImageView.ScaleType.FIT_CENTER; setBackgroundColor(Color.BLACK) }
        c.addView(img, LinearLayout.LayoutParams((96 * dp).toInt(), (96 * dp).toInt()))
        c.addView(text(p.optString("display", f).uppercase(), 18f, true).apply { gravity = Gravity.CENTER })
        val same = sh == null || p.optString("engine") == sh.optString("engine")
        c.addView(text("pack ${p.optString("version")}" + (if (mine) "\nON SCREEN" else "") +
            (if (!same) "\nbuilt for another shell" else ""), 12f).apply { gravity = Gravity.CENTER })
        c.setOnClickListener { if (same) pick(p) else facesMsg?.text = "${p.optString("display", f)}'s pack is built for another shell (engine ${p.optString("engine")})." }
        p.optString("face").takeIf { it.isNotEmpty() && it != "null" }?.let { url ->
            Thread {
                val bmp = try { val r = get(url); r.body?.let { BitmapFactory.decodeByteArray(it, 0, it.size) } } catch (x: Exception) { null }
                if (bmp != null) act.runOnUiThread { img.setImageDrawable(BitmapDrawable(act.resources, bmp).apply { paint.isFilterBitmap = false }) }
            }.start()
        }
        return c
    }

    /** a face tapped: shell (once) + pack downloaded, the core on the shell, the pack swapped in at once */
    private fun pick(p: JSONObject) {
        val cat = catalogue ?: return
        val sh = cat.optJSONObject("shell") ?: return
        val name = p.optString("display", p.getString("fighter"))
        facesMsg?.text = "Loading $name..."
        dl.execute {
            try {
                val sf = fetch(sh.getString("url"), sh.getString("sha256"), sh.getLong("size"), ".neo") { pc ->
                    act.runOnUiThread { facesMsg?.text = "Downloading the shell ${sh.optString("version")}: $pc %" } }
                val pk = packOf(p) { pc -> act.runOnUiThread { facesMsg?.text = "Downloading $name's pack: $pc %" } }
                act.runOnUiThread {
                    cfgWant = null; cfgTag = null; cfgFor = pk.fighter; noConfig = false
                    swapReq = pk; swapNow = true
                    if (shell?.absolutePath != sf.absolutePath || emu()?.rom != sf.absolutePath) {
                        shell = sf; shellSha = sh.getString("sha256"); shellEngine = sh.optString("engine"); play(sf)
                        shellVersions[sh.getString("sha256")] = sh.optString("version")
                    }
                    close(); strip(); light(State.WAIT, "LOADING $name")
                }
            } catch (x: Exception) {
                Log.w(TAG, "lab: ${x.message}")
                act.runOnUiThread { facesMsg?.text = "Not loaded: ${x.message}" }
            }
        }
    }

    private fun leaveLab() {
        stop()
        faces?.let { root.removeView(it) }; faces = null
        bar?.let { root.removeView(it) }; bar = null; reserve(0)
        shell = null; pack = null; swapReq = null; reloadReq = null; cfgWant = null
        leave()
    }

    /** the back key: the faces close (back to the game), or open over it */
    fun back() { if (facesOpen && pack != null) close() else if (facesOpen) leaveLab() else open() }

    /** what a feedback note taken now ran (0.0.29): the shell + the pack in the core (+ the live config written), not
     *  brawler.neo; null = the core is not on the lab's shell */
    private val shellVersions = java.util.concurrent.ConcurrentHashMap<String, String>()
    fun noteInfo(): JSONObject? {
        val sh = shell ?: return null; val pk = pack ?: return null
        if (emu()?.rom != sh.absolutePath) return null
        val sha = sh.name.substringBefore('.')                          // files/lab/<sha256>.neo
        return JSONObject().apply {
            put("shell_version", shellVersions[sha] ?: "?"); put("shell_sha256", sha); put("shell_size", sh.length()); put("engine", pk.engine)
            put("pack_fighter", pk.fighter); put("pack_version", pk.version); put("pack_sha256", pk.sha)
            sent?.let { put("config_rev", it.version); put("config_hash", it.hash) }
        }
    }

    // ---- the poll (2 s) ------------------------------------------------------------------------------------------
    private fun startPoll() {
        if (poller != null) return
        EmuThread.hook = { t -> tick(t) }
        poller = Thread {
            while (active) {
                if (!paused) try { pollOnce(); if (offline) { offline = false; act.runOnUiThread { refreshLight() } } }
                    catch (x: Exception) { pollsErr++; Log.w(TAG, "poll: ${x.message}"); if (!offline) { offline = true; act.runOnUiThread { refreshLight() } } }
                try { Thread.sleep(2000) } catch (x: InterruptedException) { break }
            }
        }.apply { isDaemon = true; name = "lab-poll"; start() }
    }

    fun stop() {
        active = false; poller?.interrupt(); poller = null
        if (EmuThread.hook != null) EmuThread.hook = null
        blink(false)
    }

    private fun pollOnce() {
        val f = pack?.fighter ?: swapReq?.fighter
        if (f != null) {
            if (cfgFor != f) { cfgTag = null; cfgFor = f }
            val r = get("config/$f/hash", cfgTag)
            count(r.code, "config/$f/hash")
            when (r.code) {
                200 -> {
                    val h = JSONObject(String(r.body!!, Charsets.UTF_8))
                    val full = get("config/$f")
                    count(full.code, "config/$f")
                    if (full.code == 200 && full.body != null) {
                        val j = JSONObject(String(full.body, Charsets.UTF_8))
                        val blob = android.util.Base64.decode(j.getString("blob"), android.util.Base64.DEFAULT)
                        if (cfgFor == f) { cfgWant = Cfg(f, j.getInt("version"), j.getString("hash"), blob); cfgTag = r.etag ?: "\"${h.getString("hash")}\""
                            noConfig = false; Log.i(TAG, "lab: config $f r${j.getInt("version")} (${blob.size} bytes) arrived") }
                    }
                }
                404 -> if (!noConfig) { noConfig = true; act.runOnUiThread { refreshLight() } }
            }
        }
        val cat = readCatalogue() ?: return
        act.runOnUiThread { if (facesOpen) showFaces(cat) }
        newVersions(cat)
    }

    /** the catalogue changed: a newer shell, or a newer pack of the fighter on screen -> downloaded, then swapped at
     *  the next neutral (or at once on the badge's tap) */
    private fun newVersions(cat: JSONObject) {
        val cur = pack ?: return
        val sh = cat.optJSONObject("shell") ?: return
        val p = (0 until (cat.optJSONArray("packs")?.length() ?: 0)).map { cat.getJSONArray("packs").getJSONObject(it) }
            .firstOrNull { it.getString("fighter") == cur.fighter } ?: return
        val newShell = sh.getString("sha256") != shellSha
        if (newShell && p.optString("engine") != sh.optString("engine")) {
            act.runOnUiThread { badge("NEW SHELL ${sh.optString("version")}: waits for a ${cur.display} pack built for it", null) }
            return
        }
        if (!newShell && p.getString("sha256") == cur.sha) return
        val key = if (newShell) sh.getString("sha256") else p.getString("sha256")
        if (downloading == key || swapReq?.sha == key || reloadReq?.second?.sha == p.getString("sha256") && !newShell) return
        downloading = key
        val what = if (newShell) "NEW SHELL ${sh.optString("version")}" else "NEW PACK ${cur.display} ${p.optString("version")}"
        dl.execute {
            try {
                val sf = if (newShell) fetch(sh.getString("url"), sh.getString("sha256"), sh.getLong("size"), ".neo") { pc ->
                    act.runOnUiThread { badge("$what: downloading $pc %", null) } } else null
                val pk = packOf(p) { pc -> act.runOnUiThread { badge("$what: downloading $pc %", null) } }
                act.runOnUiThread {
                    if (sf != null) { reloadReq = sf to pk; shellSha = sh.getString("sha256"); shellEngine = sh.optString("engine")
                        shellVersions[sh.getString("sha256")] = sh.optString("version") }
                    else { swapReq = pk; swapNow = false }
                    badge("$what: loads at neutral (tap: now)", { if (sf != null) reloadNow = true else swapNow = true })
                }
            } catch (x: Exception) { act.runOnUiThread { badge("$what: download failed (${x.message})", null) } }
            finally { downloading = null }
        }
    }

    // ---- the emulation thread: swaps and RAM loads, between frames -----------------------------------------------
    private fun r8(a: Int) = Native.ramRead(a, 1)?.let { it[0].toInt() and 255 } ?: -1
    private fun neutral(r: Ram): Boolean = r8(r.active) == 1 && r8(r.p1State) in r.neutral

    private fun tick(t: EmuThread) {
        val sh = shell ?: return
        if (t.rom != sh.absolutePath) return
        n++
        reloadReq?.let { (sf, pk) ->                                   // a new shell: the core restarts on it (UI thread)
            val r = pack?.ram
            if (reloadNow || r == null || neutral(r)) { reloadReq = null; reloadNow = false
                act.runOnUiThread { shell = sf; swapReq = pk; swapNow = true; play(sf); badge("NEW SHELL: loading...", null) } }
            return
        }
        swapReq?.let { pk ->
            val r = pack?.ram ?: pk.ram
            if (swapNow || r == null || neutral(r)) {
                swapReq = null; swapNow = false
                val code = Native.swapPack(pk.file.absolutePath)
                sent = null; treeSent = null; chainIn = false; lastStat = -1
                Log.i(TAG, "lab: pack ${pk.fighter} ${pk.version} -> $code")
                if (code == 0) { val first = pack?.fighter != pk.fighter; pack = pk
                    act.runOnUiThread { if (first) light(State.WAIT, "${pk.display} BOOTING") else badge("PACK ${pk.display} ${pk.version} loaded", null, 4000) } }
                else act.runOnUiThread { badge("PACK ${pk.display} refused (code $code): another shell?", null) }
            }
            return
        }
        val pk = pack ?: return; val r = pk.ram ?: return
        if (n % 4 != 0) return
        if (r8(r.active) != 1) return                                  // the practice not running yet (a boot)
        val want = cfgWant
        if (want != null && want !== sent && want.fighter == pk.fighter) {
            val lv = liveParts(want.blob)
            val lc = lv?.chain
            val chain = if (lv != null && lc != null) chainFor(lc, lv.tryBlob[3].toInt() and 255, pk.slot) else null
            if (lv == null || lv.tryBlob.size > r.tblobSize || (lv.chain != null && chain == null)) { sent = want
                val why = if (lv != null && lv.tryBlob.size > r.tblobSize) "its TRY blob is ${lv.tryBlob.size} bytes, the game holds ${r.tblobSize}"
                          else "not a live config (${want.blob.size} bytes)"
                act.runOnUiThread { light(State.REFUSED, "REFUSED r${want.version}: $why") }; return }
            if (treeSent !== want && (chain != null || chainIn)) {     // the tree first: load 5 (the chain) or 2 (the ROM's)
                if (r8(r.load) != 0) return                            // (the game has not taken the last load yet)
                if (chain != null) Native.ramWrite(r.buf, chain)
                Native.ramWrite(r.magic, "LAB1".toByteArray()); Native.ramWrite(r.fighter, byteArrayOf(pk.slot.toByte()))
                Native.ramWrite(r.load, byteArrayOf(if (chain != null) 5 else 2))
                treeSent = want; chainIn = chain != null
                Log.i(TAG, "lab: config ${want.fighter} r${want.version}: " + (if (chain != null) "chain ${chain.size} bytes (load 5)" else "the ROM's tree back (load 2)"))
                return
            }
            if (r8(r.load) != 0) return                                // the TRY blob once the game took the tree
            val b = lv.tryBlob.copyOf(); b[3] = pk.slot.toByte()       // P1 = the slot fighter in the shell
            Native.ramWrite(r.tblob, b); Native.ramWrite(r.lstat, byteArrayOf(0)); Native.ramWrite(r.tnow, byteArrayOf(0))
            Native.ramWrite(r.magic, "LAB1".toByteArray()); Native.ramWrite(r.fighter, byteArrayOf(pk.slot.toByte()))
            Native.ramWrite(r.load, byteArrayOf(6))
            sent = want; treeSent = want; lastStat = -1
            Log.i(TAG, "lab: config ${want.fighter} r${want.version} written (${b.size} bytes, load 6" + (if (chainIn) ", after its chain)" else ")"))
        }
        if (applyNow) { applyNow = false; if (r8(r.lstat) == 2) Native.ramWrite(r.tnow, byteArrayOf(1)) }
        val ls = r8(r.lstat)
        if (ls != lastStat) {
            val prev = lastStat; lastStat = ls; val s = sent
            Log.i(TAG, "lab: lstat $prev -> $ls (r${s?.version})")
            act.runOnUiThread { stat(ls, s, prev) }
        }
    }

    // ---- the strip: light, label, badge, buttons -----------------------------------------------------------------
    enum class State { SYNC, PENDING, APPLIED, REFUSED, NONE, OFFLINE, WAIT }
    private var bar: LinearLayout? = null
    private lateinit var lamp: View
    private lateinit var label: TextView
    private lateinit var badgeView: TextView
    private var state = State.WAIT
    private var steady = State.WAIT                                 // the last light that was not OFFLINE / NONE
    private var steadyText = "no answer"
    private val ui = android.os.Handler(android.os.Looper.getMainLooper())

    private fun text(t: String, size: Float, bold: Boolean = false) = TextView(act).apply { text = t; textSize = size; setTextColor(Color.WHITE)
        if (bold) setTypeface(typeface, Typeface.BOLD) }
    private fun button(t: String, fill: Int, f: () -> Unit) = Button(act).apply { text = t; isAllCaps = false; textSize = 14f; setTextColor(Color.WHITE)
        setTypeface(typeface, Typeface.BOLD); minWidth = 0; minimumWidth = 0; minHeight = 0; minimumHeight = 0; stateListAnimator = null
        val m = (8 * dp).toInt(); setPadding(m, 0, m, 0)
        background = GradientDrawable().apply { setColor(fill); setStroke((2 * dp).toInt(), Color.WHITE); cornerRadius = 8 * dp }
        setOnClickListener { f() } }

    /** the strip, OFF the picture and OFF the pad (PadView.labH / labArea via [reserve]): one row, a light, the label
     *  (2 lines at most), Apply now, Faces. Portrait (0.0.29): between the picture and the pad's panel, the badge under
     *  the row while it shows. Landscape (0.0.31): above the picture (it shrinks under it), between the top corners'
     *  buttons, the badge in the row (0.0.29 stacked it in the left gutter: on a phone it covered the d-pad) */
    private lateinit var applyBtn: Button
    private lateinit var facesBtn: Button
    private var barPortrait: Boolean? = null
    private var listening = false
    private val barFill get() = Color.rgb(8, 8, 12)
    private fun strip() {
        if (bar != null) { place(); return }
        val b = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; val m = (4 * dp).toInt(); setPadding(m * 2, m, m * 2, m)
            background = GradientDrawable().apply { setColor(barFill); setStroke((2 * dp).toInt(), Color.WHITE); cornerRadius = 8 * dp } }
        lamp = View(act)
        label = text("", 13f, true).apply { setPadding((8 * dp).toInt(), 0, (8 * dp).toInt(), 0) }
        applyBtn = button("Apply now", Color.rgb(150, 100, 0)) { now() }
        facesBtn = button("Faces", Color.rgb(60, 60, 70)) { open() }
        badgeView = text("", 13f, true).apply { visibility = View.GONE; val m = (6 * dp).toInt(); setPadding(m, m / 2, m, m / 2)
            background = GradientDrawable().apply { setColor(Color.rgb(20, 70, 170)); setStroke((2 * dp).toInt(), Color.WHITE); cornerRadius = 6 * dp } }
        root.addView(b); bar = b; barPortrait = null
        if (!listening) { listening = true
            root.addOnLayoutChangeListener { _, l, t, r, btm, ol, ot, or_, ob -> if (r - l != or_ - ol || btm - t != ob - ot) root.post { place() } } }
        place(); refreshLight()
    }
    /** the strip's views for the orientation: one row; the badge under it (portrait) or in it (landscape) */
    private fun arrange(portrait: Boolean) {
        val b = bar ?: return
        if (barPortrait == portrait) return
        barPortrait = portrait
        listOf(lamp, label, applyBtn, facesBtn, badgeView).forEach { (it.parent as? android.view.ViewGroup)?.removeView(it) }
        b.removeAllViews()
        val bh = (36 * dp).toInt(); val g = (6 * dp).toInt()
        val head = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        head.addView(lamp, LinearLayout.LayoutParams((18 * dp).toInt(), (18 * dp).toInt()))
        label.maxLines = 2; label.ellipsize = android.text.TextUtils.TruncateAt.END
        head.addView(label, LinearLayout.LayoutParams(0, -2, 1f))
        if (!portrait) head.addView(badgeView, LinearLayout.LayoutParams(-2, -2).apply { rightMargin = g })
        head.addView(applyBtn, LinearLayout.LayoutParams(-2, bh))
        head.addView(facesBtn, LinearLayout.LayoutParams(-2, bh).apply { leftMargin = g })
        b.addView(head, LinearLayout.LayoutParams(-1, -2))
        if (portrait) b.addView(badgeView, LinearLayout.LayoutParams(-1, -2).apply { topMargin = (4 * dp).toInt() })
    }
    private fun place() {
        val b = bar ?: return
        if (root.width == 0) { root.post { place() }; return }
        arrange(Screen.portrait(root.width, root.height))
        var a = reserve(-1)                                            // the strip's width for this orientation
        for (i in 0 until 3) {                                         // landscape: its height moves the picture, the
            b.measure(View.MeasureSpec.makeMeasureSpec(a.width(), View.MeasureSpec.EXACTLY),   // corners' buttons and
                View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))              // so its width: settle
            val n = reserve(b.measuredHeight)                          // the pad makes room for it
            val same = n.width() == a.width(); a = n
            if (same) break
        }
        b.layoutParams = FrameLayout.LayoutParams(a.width(), b.measuredHeight, Gravity.LEFT or Gravity.TOP).apply {
            leftMargin = a.left; topMargin = a.top }
        b.post { val r = IntArray(2); b.getLocationOnScreen(r)                      // the proof reads it (PadView logs the pad)
            Log.i(TAG, "strip ${r[0]},${r[1]} - ${r[0] + b.width},${r[1] + b.height}") }
    }

    private fun now() {
        val r = reloadReq; val s = swapReq
        if (r != null) { reloadNow = true; return }
        if (s != null) { swapNow = true; return }
        if (state == State.PENDING) { applyNow = true; label.text = "APPLYING r${sentVersion()} NOW" }
        else act.runOnUiThread { android.widget.Toast.makeText(act, "Nothing waiting to apply", android.widget.Toast.LENGTH_SHORT).show() }
    }
    private fun sentVersion() = cfgWant?.version ?: 0

    /** lab.lstat changed: 2 pending (amber, blinking), 1 applied (a flash, then green), 0x80 | n refused (red) */
    private fun stat(ls: Int, s: Cfg?, prev: Int) {
        if (s == null) { if (noConfig || offline) refreshLight() else light(State.WAIT, "WAITING FOR THE CONFIG"); return }
        when {
            ls == 2 -> light(State.PENDING, "NEW CONFIG r${s.version}${ch()}: applies at neutral")
            ls == 1 -> { light(State.APPLIED, "APPLIED r${s.version}${ch()}"); ui.postDelayed({ if (state == State.APPLIED) light(State.SYNC, "IN SYNC r${s.version}${ch()}") }, 1500) }
            ls and 0x80 != 0 -> light(State.REFUSED, "REFUSED r${s.version}: ${LSTAT.getOrElse(ls and 0x7F) { "check ${ls and 0x7F}" }}")
            else -> light(State.WAIT, "SENDING r${s.version}")
        }
    }
    private fun ch() = if (chainIn) " + CHAIN" else ""
    private fun refreshLight() {
        if (bar == null) return
        when {
            offline -> light(State.OFFLINE, "OFFLINE: last $steadyText")
            pack != null && pack?.ram == null -> light(State.NONE, "THIS PACK HAS NO RAM MAP: configs off")
            noConfig -> light(State.NONE, "NO LIVE CONFIG: the game's own moves")
            state == State.OFFLINE || state == State.NONE -> light(steady, steadyText)
        }
    }

    private fun light(s: State, t: String) {
        if (bar == null) strip()
        if (s != State.OFFLINE && s != State.NONE) { steady = s; steadyText = t }
        state = s; val grew = label.text.length != t.length; label.text = t
        if (grew) place()                                             // (the label's lines set the strip's height)
        val (fill, ring) = when (s) {
            State.SYNC -> Color.rgb(40, 200, 70) to Color.WHITE
            State.PENDING -> Color.rgb(255, 170, 0) to Color.WHITE
            State.APPLIED -> Color.WHITE to Color.rgb(40, 200, 70)
            State.REFUSED -> Color.rgb(220, 30, 30) to Color.WHITE
            State.NONE, State.WAIT -> Color.rgb(120, 120, 120) to Color.WHITE
            State.OFFLINE -> Color.TRANSPARENT to Color.rgb(160, 160, 160)
        }
        lamp.background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(fill); setStroke((3 * dp).toInt(), ring) }
        lamp.alpha = 1f; lamp.scaleX = 1f; lamp.scaleY = 1f
        blink(s == State.PENDING)
        if (s == State.APPLIED) { lamp.scaleX = 1.6f; lamp.scaleY = 1.6f; lamp.animate().scaleX(1f).scaleY(1f).setDuration(900).start()
            bar?.let { b -> b.background = GradientDrawable().apply { setColor(Color.argb(230, 20, 110, 40)); setStroke((2 * dp).toInt(), Color.WHITE); cornerRadius = 8 * dp }
                ui.postDelayed({ b.background = GradientDrawable().apply { setColor(barFill); setStroke((2 * dp).toInt(), Color.WHITE); cornerRadius = 8 * dp } }, 700) } }
    }
    private val blinker = object : Runnable { override fun run() { lamp.alpha = if (lamp.alpha > 0.5f) 0.15f else 1f; ui.postDelayed(this, 450) } }
    private fun blink(on: Boolean) { ui.removeCallbacks(blinker); if (on && bar != null) ui.postDelayed(blinker, 450) }

    /** the blue badge: a new pack / shell (its version), [tap] = load it now; hidden after [ms] when given */
    private val hideBadge = Runnable { if (::badgeView.isInitialized) badgeView.visibility = View.GONE }
    private fun badge(t: String, tap: (() -> Unit)?, ms: Long = 0) {
        if (bar == null) strip()
        ui.removeCallbacks(hideBadge)
        badgeView.text = (if (tap != null) "▶ " else "") + t; badgeView.visibility = View.VISIBLE
        badgeView.isClickable = tap != null; badgeView.setOnClickListener(if (tap != null) View.OnClickListener { tap(); badgeView.text = "$t: loading now" } else null)
        if (ms > 0) ui.postDelayed(hideBadge, ms)
        place()
    }

    companion object {
        private const val TAG = "NeoScanLab"
        /** lab.lstat's refusals (fighter.h; lab.js LSTAT) */
        private const val LAB_BUF = 16 + 128 * 24                   // fighter.h LAB_BUF (lab.js)
        private val LSTAT = listOf("", "an animation this build lacks", "a special the pool lacks", "a throw the fighter lacks",
            "a throw outside a grab slot", "a list too long", "not a TRY blob v1", "the blob runs past its room", "no such slot")
    }
}
