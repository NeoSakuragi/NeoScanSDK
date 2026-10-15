package com.neoscan.player

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.util.Log
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** The Oros sign-in (Player 0.0.15, docs/feedback.md): the same accounts as canneji.duckdns.org/oros/. POST
 *  <AUTH_URL>api/login {username, password} -> {token (a JWT, 30 days), username, role}; every call to the builds and
 *  to the feedback service then carries `Authorization: Bearer <token>` (nginx auth_request = Oros's /api/authcheck).
 *  Stored as Oros stores it: SharedPreferences "auth" with the token and the password encrypted by an AES/GCM key held in
 *  the Android Keystore (never in the clear: no keystore = nothing saved, sign in again next start).
 *  Refresh, as the Oros app does (its server has no refresh call): a new login with the saved password, when the token
 *  is under [REFRESH_S] from its expiry or a call is refused (401). A password the server rejects is dropped (sign in
 *  again); a network failure keeps everything (offline play goes on with the cached build). */
object Auth {
    private const val TAG = "NeoScanPlayer"
    private const val ALIAS = "neoscan_auth_key"
    private const val PREFIX = "enc1:"
    private const val REFRESH_S = 7 * 24 * 3600L

    /** NO_ROLE: an Oros account without a brawler role; NOT_ADMIN: a tester signing in to Brawler Dev */
    enum class Result { OK, BAD_CREDENTIALS, TOO_MANY, OFFLINE, NO_ROLE, NOT_ADMIN }

    /** the sign-in screen's line for a refused account */
    fun refusal(r: Result): String = when (r) {
        Result.NO_ROLE -> "This account has no access to the brawler. Ask Bruno for a brawler tester role."
        Result.NOT_ADMIN -> "Brawler Dev is for brawler admins. Use the Brawler app with this account."
        else -> ""
    }

    /** set by MainActivity: the saved sign-in was refused, the login screen must come back */
    @Volatile var onSignedOut: (() -> Unit)? = null

    private fun prefs(ctx: Context) = ctx.getSharedPreferences("auth", 0)
    fun user(ctx: Context): String? = prefs(ctx).getString("user", null)
    /** THE BRAWLER ROLE (Player 0.0.36, docs/feedback.md "Roles and the two apps"): the Oros account's brawler role as
     *  the feedback service's GET me gives it (the Oros tags brawler_admin / brawler_tester), read at every sign-in,
     *  every renewal and every start ([recheck]). Brawler Dev: admins only, everything; the Brawler app: anyone with a
     *  role, and an admin there plays it as a tester (the game, the pad and the Feedback button) */
    fun role(ctx: Context): String = prefs(ctx).getString("brole", "") ?: ""
    fun admin(ctx: Context): Boolean = BuildConfig.DEV && role(ctx) == "admin"   // the Brawler app: never (an admin plays it as a tester)
    fun loginUrl(): URL = URL(URL(BuildConfig.AUTH_URL), "api/login")
    /** a feedback service URL (BuildConfig.FEEDBACK_URL = .../brawler/feedback/) */
    fun feedbackUrl(rel: String): String = URL(URL(BuildConfig.FEEDBACK_URL), rel).toString()

    /** blocking: GET me with [tok] -> the JSON, or a refusal: Result.NO_ROLE (403), Result.OFFLINE (no answer) */
    private fun fetchMe(tok: String): Pair<JSONObject?, Result> = try {
        val c = (URL(feedbackUrl("me")).openConnection() as HttpURLConnection).apply {
            connectTimeout = 8000; readTimeout = 15000; setRequestProperty("Authorization", "Bearer $tok")
            setRequestProperty("X-App-Version", BuildConfig.VERSION_NAME) }
        when (c.responseCode) {
            200 -> JSONObject(c.inputStream.use { it.readBytes().toString(Charsets.UTF_8) }) to Result.OK
            403 -> null to Result.NO_ROLE
            401 -> null to Result.BAD_CREDENTIALS
            else -> null to Result.OFFLINE
        }
    } catch (x: Exception) { Log.w(TAG, "auth: me ${x.message}"); null to Result.OFFLINE }

    /** what this app lets the role do: Brawler Dev = admins only */
    private fun allowed(role: String): Result = when {
        role != "admin" && role != "tester" -> Result.NO_ROLE
        BuildConfig.DEV && role != "admin" -> Result.NOT_ADMIN
        else -> Result.OK
    }

    @Volatile private var meCache: JSONObject? = null
    /** blocking: GET me now (the role + the Brawler app's update link); null when it cannot be asked */
    fun me(ctx: Context): JSONObject? {
        val tok = token(ctx) ?: return null
        val (j, r) = fetchMe(tok)
        if (j != null) { meCache = j; prefs(ctx).edit().putString("brole", j.optString("role")).apply() }
        else if (r == Result.NO_ROLE) prefs(ctx).edit().putString("brole", "none").apply()
        return j
    }

    /** at every start (blocking): the role asked again; a role this app refuses = signed out with [refusal]'s reason
     *  (returned); offline = the last known role stands (the cached build still plays) */
    fun recheck(ctx: Context): Result {
        me(ctx)
        val r = allowed(role(ctx))
        if (r != Result.OK) { logout(ctx); prefs(ctx).edit().putString("refused", refusal(r)).commit() }
        return r
    }
    /** the reason of the last refusal (the sign-in screen shows it once) */
    fun takeRefusal(ctx: Context): String? = prefs(ctx).getString("refused", null)?.also { prefs(ctx).edit().remove("refused").apply() }

    /** someone is signed in: a token not expired yet, or a saved password to get a new one */
    fun signedIn(ctx: Context): Boolean {
        val p = prefs(ctx)
        if (p.getString("user", null) == null) return false
        return (p.getString("token", null) != null && p.getLong("exp", 0) > now()) || p.getString("pass", null) != null
    }

    /** blocking (off the UI thread) */
    fun login(ctx: Context, user: String, pass: String): Result {
        val c = try {
            (loginUrl().openConnection() as HttpURLConnection).apply {
                connectTimeout = 8000; readTimeout = 15000; requestMethod = "POST"; doOutput = true
                setRequestProperty("Content-Type", "application/json")
                outputStream.use { it.write(JSONObject().put("username", user).put("password", pass).toString().toByteArray()) }
            }
        } catch (x: Exception) { Log.w(TAG, "auth: ${x.message}"); return Result.OFFLINE }
        val code = try { c.responseCode } catch (x: Exception) { Log.w(TAG, "auth: ${x.message}"); return Result.OFFLINE }
        if (code == 401) return Result.BAD_CREDENTIALS
        if (code == 429) return Result.TOO_MANY
        if (code != 200) { Log.w(TAG, "auth: login HTTP $code"); return Result.OFFLINE }
        val j = try { JSONObject(c.inputStream.use { it.readBytes().toString(Charsets.UTF_8) }) } catch (x: Exception) { return Result.OFFLINE }
        val tok = j.getString("token")
        val (me, mr) = fetchMe(tok)                                     // the brawler role: this app may refuse the account
        if (me == null && mr != Result.OFFLINE) return if (mr == Result.NO_ROLE) Result.NO_ROLE else Result.OFFLINE
        val brole = me?.optString("role") ?: prefs(ctx).getString("brole", "")!!   // offline: the last known role
        allowed(brole).let { if (it != Result.OK) { Log.w(TAG, "auth: ${j.optString("username", user)} refused here (role '$brole')"); return it } }
        if (me != null) meCache = me
        val e = prefs(ctx).edit().putString("user", j.optString("username", user)).putString("role", j.optString("role")).putString("brole", brole)
            .putLong("exp", expiry(tok))
        val et = encrypt(tok); val ep = encrypt(pass)
        if (et != null) e.putString("token", et) else e.remove("token")
        if (ep != null) e.putString("pass", ep) else { e.remove("pass"); Log.w(TAG, "auth: keystore unavailable, the password is not saved") }
        e.commit()
        memo = tok
        Log.i(TAG, "auth: signed in as ${j.optString("username", user)}, token until ${java.util.Date(expiry(tok) * 1000)}")
        return Result.OK
    }

    private var tried = 0L                                              // the last renewal attempt (s)
    @Volatile private var memo: String? = null                          // the token in memory (no keystore round trip per call)

    /** the token to send, renewed first when it is close to its expiry (blocking: off the UI thread); null = none */
    @Synchronized fun token(ctx: Context): String? {
        val p = prefs(ctx)
        val tok = memo ?: p.getString("token", null)?.let { decrypt(it) }?.also { memo = it }
        if (tok != null && p.getLong("exp", 0) - now() > REFRESH_S) return tok
        if (tok != null && p.getLong("exp", 0) > now() && now() - tried < 600) return tok   // offline: renewal retried every 10 min
        tried = now()
        return if (refresh(ctx) == Result.OK) memo else tok?.takeIf { p.getLong("exp", 0) > now() }
    }

    /** a new login with the saved password; a rejected password is dropped and [onSignedOut] runs */
    @Synchronized fun refresh(ctx: Context): Result {
        val p = prefs(ctx)
        val user = p.getString("user", null); val pass = p.getString("pass", null)?.let { decrypt(it) }
        if (user == null || pass.isNullOrEmpty()) { if (user != null && p.getLong("exp", 0) <= now()) signedOut(ctx); return Result.BAD_CREDENTIALS }
        val r = login(ctx, user, pass)
        if (r == Result.NO_ROLE || r == Result.NOT_ADMIN) prefs(ctx).edit().putString("refused", refusal(r)).commit()
        if (r == Result.BAD_CREDENTIALS || r == Result.NO_ROLE || r == Result.NOT_ADMIN) signedOut(ctx)
        return r
    }

    private fun signedOut(ctx: Context) {
        Log.w(TAG, "auth: the saved sign-in was refused")
        prefs(ctx).edit().remove("token").remove("pass").remove("exp").commit(); memo = null
        onSignedOut?.invoke()
    }

    fun logout(ctx: Context) { prefs(ctx).edit().clear().commit(); memo = null }

    /** LOG OUT (0.0.37: Settings' Account in Brawler Dev, the account button in the Brawler app): the sign-in and the
     *  downloaded build go (the next account gets ITS allowed build), the sign-in screen, the game process ends (a
     *  fresh start after the login) */
    fun signOut(a: android.app.Activity) {
        SaveSync.drain()                                                // 0.0.39: a cloud save still being sent
        logout(a); RomFetch.forget(a)
        a.startActivity(android.content.Intent(a, LoginActivity::class.java)
            .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK or android.content.Intent.FLAG_ACTIVITY_CLEAR_TASK))
        Runtime.getRuntime().exit(0)
    }

    /** a request with the token; refused (401) once = renew the token and ask again. [open] makes the connection
     *  (headers set, body written) for a given token; the returned connection has its response code read */
    fun call(ctx: Context, open: (String?) -> HttpURLConnection): HttpURLConnection {
        val c = open(token(ctx))
        if (c.responseCode != 401) return c
        c.disconnect()
        return if (refresh(ctx) == Result.OK) open(memo) else open(null).also { it.responseCode }
    }

    fun HttpURLConnection.bearer(tok: String?): HttpURLConnection { if (tok != null) setRequestProperty("Authorization", "Bearer $tok"); return this }

    private fun now() = System.currentTimeMillis() / 1000

    /** the JWT's exp claim (seconds), 0 when unreadable */
    private fun expiry(tok: String): Long = try {
        JSONObject(String(Base64.decode(tok.split(".")[1], Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP))).getLong("exp")
    } catch (x: Exception) { 0 }

    // ---- the Keystore key (as Oros's SecureStore) -------------------------------------------------------------------
    private fun key(): SecretKey? = try {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)?.secretKey ?: KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").run {
            init(KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
            generateKey()
        }
    } catch (x: Exception) { Log.w(TAG, "auth: keystore ${x.message}"); null }

    private fun encrypt(plain: String): String? {
        val k = key() ?: return null
        return try {
            val c = Cipher.getInstance("AES/GCM/NoPadding"); c.init(Cipher.ENCRYPT_MODE, k)
            PREFIX + Base64.encodeToString(c.iv + c.doFinal(plain.toByteArray()), Base64.NO_WRAP)
        } catch (x: Exception) { Log.w(TAG, "auth: encrypt ${x.message}"); null }
    }

    private fun decrypt(stored: String): String? {
        if (!stored.startsWith(PREFIX)) return null
        val k = key() ?: return null
        return try {
            val raw = Base64.decode(stored.removePrefix(PREFIX), Base64.NO_WRAP)
            val c = Cipher.getInstance("AES/GCM/NoPadding"); c.init(Cipher.DECRYPT_MODE, k, GCMParameterSpec(128, raw.copyOfRange(0, 12)))
            String(c.doFinal(raw.copyOfRange(12, raw.size)))
        } catch (x: Exception) { Log.w(TAG, "auth: decrypt ${x.message}"); null }
    }
}
