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
    /** BANNED: blocked by an admin (0.0.44); SIGNED_OUT: signed out everywhere by an admin, the saved password no longer
     *  renews; MUST_CHANGE: a temporary password, a new one first ([changePassword]); SIGNUP: refused, see [signupError] */
    enum class Result { OK, BAD_CREDENTIALS, TOO_MANY, OFFLINE, NO_ROLE, NOT_ADMIN, BANNED, SIGNED_OUT, MUST_CHANGE, SIGNUP }

    /** the sign-in screen's line for a refused account */
    fun refusal(r: Result): String = when (r) {
        Result.NO_ROLE -> tr(R.string.auth_no_role)
        Result.NOT_ADMIN -> tr(R.string.auth_not_admin)
        Result.BANNED -> tr(R.string.auth_banned)
        Result.SIGNED_OUT -> tr(R.string.auth_signed_out)
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
        var got = fetchMe(tok)
        if (got.second == Result.BAD_CREDENTIALS && refresh(ctx) == Result.OK) memo?.let { t -> got = fetchMe(t) }   // revoked: renewed once
        val (j, r) = got
        if (j != null) { meCache = j; prefs(ctx).edit().putString("brole", j.optString("role")).apply() }
        else if (r == Result.NO_ROLE) prefs(ctx).edit().putString("brole", "none").apply()
        return j
    }

    /** at every start (blocking): the role asked again; a role this app refuses = signed out with [refusal]'s reason
     *  (returned); offline = the last known role stands (the cached build still plays) */
    fun recheck(ctx: Context): Result {
        me(ctx)
        if (!signedIn(ctx)) return Result.SIGNED_OUT                     // the renewal was refused (blocked, signed out everywhere)
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

    /** blocking (off the UI thread): a typed sign-in, or a renewal with the saved password ([since] = the old token's
     *  iat_ms: an Oros "sign out everywhere" since then = 401 signed_out, the saved password goes) */
    fun login(ctx: Context, user: String, pass: String, since: Long = 0): Result {
        val body = JSONObject().put("username", user).put("password", pass).apply { if (since > 0) put("since", since) }
        val (code, j) = post(loginUrl(), body, null) ?: return Result.OFFLINE
        when {
            code == 401 && j?.optString("error") == "signed_out" -> return Result.SIGNED_OUT
            code == 401 -> return Result.BAD_CREDENTIALS
            code == 403 && j?.optString("error") == "banned" -> return Result.BANNED
            code == 429 -> return Result.TOO_MANY
            code != 200 || j == null -> { Log.w(TAG, "auth: login HTTP $code"); return Result.OFFLINE }
        }
        return finish(ctx, j!!, user, pass)
    }

    /** SIGN-UP (app 0.0.44, docs/feedback.md "Sign-up and the player admin"): POST <AUTH_URL>api/signup {code,
     *  username, password, device} -> the same answer as api/login (then signed in as by [login]); refused = Result.SIGNUP
     *  with [signupError] = the server's error code (name_taken, code_used_up ... : the screen's own words for it) */
    @Volatile var signupError = ""
    fun signup(ctx: Context, code: String, user: String, pass: String): Result {
        val dev = "${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL} / Android ${android.os.Build.VERSION.RELEASE}"
        val body = JSONObject().put("code", code).put("username", user).put("password", pass).put("device", dev)
        val (c, j) = post(URL(URL(BuildConfig.AUTH_URL), "api/signup"), body, null) ?: return Result.OFFLINE
        if (c != 200 || j == null || !j.has("token")) { signupError = j?.optString("error") ?: "http_$c"; Log.w(TAG, "auth: signup refused: $signupError"); return Result.SIGNUP }
        Log.i(TAG, "auth: account $user created")
        return finish(ctx, j, user, pass)
    }

    /** A TEMPORARY PASSWORD (an admin's reset): the sign-in answered must_change; the new password replaces it
     *  (POST api/password with that sign-in's token), then the sign-in goes on with the new one. Result.SIGNUP + [signupError]
     *  = refused (password_short, password_same, wrong_password) */
    @Volatile private var pending: Triple<String, String, String>? = null   // user, temporary password, its token
    fun changePassword(ctx: Context, newPass: String): Result {
        val (user, old, tok) = pending ?: return Result.BAD_CREDENTIALS
        val (c, j) = post(URL(URL(BuildConfig.AUTH_URL), "api/password"), JSONObject().put("old_password", old).put("new_password", newPass), tok) ?: return Result.OFFLINE
        if (c != 200 || j == null) { signupError = j?.optString("error") ?: "http_$c"; return if (c == 401) Result.BAD_CREDENTIALS else Result.SIGNUP }
        pending = null
        return login(ctx, user, newPass)
    }

    /** POST json -> (HTTP code, the JSON answer or null); null = no answer at all (offline) */
    private fun post(u: URL, body: JSONObject, tok: String?): Pair<Int, JSONObject?>? {
        val c = try {
            (u.openConnection() as HttpURLConnection).apply {
                connectTimeout = 8000; readTimeout = 15000; requestMethod = "POST"; doOutput = true
                setRequestProperty("Content-Type", "application/json"); setRequestProperty("X-App-Version", BuildConfig.VERSION_NAME)
                if (tok != null) setRequestProperty("Authorization", "Bearer $tok")
                outputStream.use { it.write(body.toString().toByteArray()) }
            }
        } catch (x: Exception) { Log.w(TAG, "auth: ${x.message}"); return null }
        val code = try { c.responseCode } catch (x: Exception) { Log.w(TAG, "auth: ${x.message}"); return null }
        val t = try { (if (code in 200..299) c.inputStream else c.errorStream)?.use { it.readBytes().toString(Charsets.UTF_8) } } catch (x: Exception) { null }
        return code to (t?.let { try { JSONObject(it) } catch (x: Exception) { null } })
    }

    /** a sign-in's answer (login or sign-up): the brawler role asked (this app may refuse it), then stored */
    private fun finish(ctx: Context, j: JSONObject, user: String, pass: String): Result {
        val tok = j.getString("token")
        if (j.optBoolean("must_change")) { pending = Triple(j.optString("username", user), pass, tok); return Result.MUST_CHANGE }
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
        val r = login(ctx, user, pass, (memo ?: p.getString("token", null)?.let { decrypt(it) })?.let { issuedMs(it) } ?: 0)
        if (r == Result.NO_ROLE || r == Result.NOT_ADMIN || r == Result.BANNED || r == Result.SIGNED_OUT) prefs(ctx).edit().putString("refused", refusal(r)).commit()
        if (r != Result.OK) Log.w(TAG, "auth: renewal refused: $r")
        if (r == Result.MUST_CHANGE) prefs(ctx).edit().putString("refused", tr(R.string.auth_reset)).commit()
        if (r == Result.BAD_CREDENTIALS) prefs(ctx).edit().putString("refused", tr(R.string.auth_signed_out)).commit()   // the password changed (a reset)
        if (r == Result.BAD_CREDENTIALS || r == Result.NO_ROLE || r == Result.NOT_ADMIN || r == Result.BANNED || r == Result.SIGNED_OUT || r == Result.MUST_CHANGE) signedOut(ctx)
        return r
    }

    @Synchronized private fun signedOut(ctx: Context) {
        val p = prefs(ctx)
        val had = p.contains("token") || p.contains("pass")             // once: several threads may find it refused
        p.edit().remove("token").remove("pass").remove("exp").commit(); memo = null
        if (!had) return
        Log.w(TAG, "auth: the saved sign-in was refused")
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

    /** the JWT's iat_ms (Oros 2026-10-16: when it was issued, ms; the revocation check), 0 = an older token without it */
    private fun issuedMs(tok: String): Long = try {
        JSONObject(String(Base64.decode(tok.split(".")[1], Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP))).optLong("iat_ms")
    } catch (x: Exception) { 0 }

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
