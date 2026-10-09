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

    enum class Result { OK, BAD_CREDENTIALS, TOO_MANY, OFFLINE }

    /** set by MainActivity: the saved sign-in was refused, the login screen must come back */
    @Volatile var onSignedOut: (() -> Unit)? = null

    private fun prefs(ctx: Context) = ctx.getSharedPreferences("auth", 0)
    fun user(ctx: Context): String? = prefs(ctx).getString("user", null)
    /** TESTER MODE (Player 0.0.26): the Oros account's role, as /api/login gives it (and every renewal refreshes it):
     *  "admin" (Oros add-user --role=admin: bruno) sees everything; any other account (role viewer) is a tester and
     *  sees only the game, the pad and the Feedback button */
    fun admin(ctx: Context): Boolean = prefs(ctx).getString("role", "") == "admin"
    fun loginUrl(): URL = URL(URL(BuildConfig.AUTH_URL), "api/login")

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
        val e = prefs(ctx).edit().putString("user", j.optString("username", user)).putString("role", j.optString("role"))
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
        if (r == Result.BAD_CREDENTIALS) signedOut(ctx)
        return r
    }

    private fun signedOut(ctx: Context) {
        Log.w(TAG, "auth: the saved sign-in was refused")
        prefs(ctx).edit().remove("token").remove("pass").remove("exp").commit(); memo = null
        onSignedOut?.invoke()
    }

    fun logout(ctx: Context) { prefs(ctx).edit().clear().commit(); memo = null }

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
