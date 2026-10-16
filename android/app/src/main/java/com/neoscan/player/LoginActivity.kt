package com.neoscan.player

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Typeface
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView

/** The sign-in screen (Player 0.0.15; 0.0.44: the language, the sign-up, a temporary password). Shown at the first
 *  start and after a logout or a refused sign-in. Built in code, like the settings. Its pages:
 *   - LANGUAGE (the very first launch only, [Lang]): two big flags, English / Français
 *   - START: "I have an invite code" / "I already have an account" (an account already used on this phone: straight
 *     to the sign-in)
 *   - SIGN UP: invite code, login, password, repeat -> Create account (Oros POST api/signup, [Auth.signup]); checked
 *     here first in plain words (3-16 letters, digits or _; 8+ characters; both the same), the server's refusals in
 *     the same words; one line says what this beta records
 *   - SIGN IN: today's (the Oros account: username + password, [Auth.login])
 *   - NEW PASSWORD: after a sign-in with a temporary password (an admin's reset: must_change), [Auth.changePassword]
 *  Signed in: the account's settings come back ([SettingsSync.pull]: the language too), then the game. */
class LoginActivity : Activity() {
    override fun attachBaseContext(base: Context) { super.attachBaseContext(Lang.wrap(base)); Lang.init(base) }

    private val dp get() = resources.displayMetrics.density
    private lateinit var col: LinearLayout
    private var page = ""

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        title = getString(R.string.app_signin)
        val refused = Auth.takeRefusal(this)                          // signed out at the start: why
        when {
            Lang.chosen(this) == null -> languagePage()
            BuildConfig.DEV || refused != null || Auth.user(this) != null || intent.getBooleanExtra("signin", false) -> signInPage(refused)
            else -> startPage()
        }
    }

    private fun shell(): LinearLayout {
        val pad = (24 * dp).toInt()
        col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(pad, pad * 2, pad, pad); gravity = Gravity.CENTER_HORIZONTAL }
        col.addView(TextView(this).apply { text = if (!BuildConfig.DEV) "Brawler" else "Brawler Dev"; textSize = 26f; setTypeface(typeface, Typeface.BOLD) })
        setContentView(ScrollView(this).apply { addView(col) })
        return col
    }
    private fun line(t: String, size: Float = 14f, top: Int = 8, bottom: Int = 16) = TextView(this).apply {
        text = t; textSize = size; alpha = 0.75f; setPadding(0, (top * dp).toInt(), 0, (bottom * dp).toInt()) }
    private fun field(hint: String, pass: Boolean = false) = EditText(this).apply {
        this.hint = hint; isSingleLine = true
        inputType = if (pass) InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD else InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        typeface = Typeface.DEFAULT                                     // (a password field defaults to monospace)
    }
    private fun big(t: String, f: () -> Unit) = Button(this).apply { text = t; textSize = 17f; isAllCaps = false; setOnClickListener { f() } }
    private fun small(t: String, f: () -> Unit) = Button(this, null, android.R.attr.borderlessButtonStyle).apply { text = t; textSize = 14f; isAllCaps = false; setOnClickListener { f() } }
    private fun errLine() = TextView(this).apply { textSize = 14f; setTextColor(0xFFFF6060.toInt()); setPadding(0, (10 * dp).toInt(), 0, 0) }
    private fun footer() {
        col.addView(TextView(this).apply {
            text = (if (BuildConfig.DEV) "Brawler Dev " else "Brawler ") + BuildConfig.VERSION_NAME; textSize = 12f; alpha = 0.5f; setPadding(0, (24 * dp).toInt(), 0, 0) })
    }
    private fun lp(top: Int = 0) = LinearLayout.LayoutParams(-1, -2).apply { topMargin = (top * dp).toInt() }

    // ---- LANGUAGE ----------------------------------------------------------------------------------------------------
    private fun languagePage() {
        page = "language"; shell()
        col.addView(line("Choose your language\nChoisissez votre langue", 16f, 12, 20).apply { gravity = Gravity.CENTER; alpha = 0.9f })
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER }
        for ((code, name) in listOf("en" to "English", "fr" to "Français")) {
            val cell = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER_HORIZONTAL; isClickable = true
                val m = (10 * dp).toInt(); setPadding(m, m, m, m); contentDescription = name
                setOnClickListener { Lang.set(this@LoginActivity, code); recreate() } }
            cell.addView(Flag(this, code), LinearLayout.LayoutParams((120 * dp).toInt(), (80 * dp).toInt()))
            cell.addView(TextView(this).apply { text = name; textSize = 18f; setTypeface(typeface, Typeface.BOLD); gravity = Gravity.CENTER
                setPadding(0, (8 * dp).toInt(), 0, 0) })
            row.addView(cell, LinearLayout.LayoutParams(0, -2, 1f))
        }
        col.addView(row, lp(8))
        footer()
    }

    /** a flag drawn as plain shapes with a solid outline (readable on an e-ink screen too: the language name is under it) */
    private class Flag(ctx: Context, val code: String) : View(ctx) {
        private val p = Paint(Paint.ANTI_ALIAS_FLAG)
        override fun onDraw(c: Canvas) {
            val w = width.toFloat(); val h = height.toFloat()
            if (code == "fr") {
                p.style = Paint.Style.FILL
                p.color = Color.rgb(0, 35, 149); c.drawRect(0f, 0f, w / 3, h, p)
                p.color = Color.WHITE; c.drawRect(w / 3, 0f, 2 * w / 3, h, p)
                p.color = Color.rgb(237, 41, 57); c.drawRect(2 * w / 3, 0f, w, h, p)
            } else {
                p.style = Paint.Style.FILL; p.color = Color.rgb(1, 33, 105); c.drawRect(0f, 0f, w, h, p)
                p.style = Paint.Style.STROKE; p.strokeCap = Paint.Cap.BUTT
                p.color = Color.WHITE; p.strokeWidth = h / 5; c.drawLine(0f, 0f, w, h, p); c.drawLine(w, 0f, 0f, h, p)
                p.color = Color.rgb(200, 16, 46); p.strokeWidth = h / 15; c.drawLine(0f, 0f, w, h, p); c.drawLine(w, 0f, 0f, h, p)
                p.style = Paint.Style.FILL; p.color = Color.WHITE
                c.drawRect(w / 2 - h / 6, 0f, w / 2 + h / 6, h, p); c.drawRect(0f, h / 2 - h / 6, w, h / 2 + h / 6, p)
                p.color = Color.rgb(200, 16, 46)
                c.drawRect(w / 2 - h / 10, 0f, w / 2 + h / 10, h, p); c.drawRect(0f, h / 2 - h / 10, w, h / 2 + h / 10, p)
            }
            p.style = Paint.Style.STROKE; p.strokeWidth = 3 * resources.displayMetrics.density; p.color = Color.WHITE
            c.drawRect(0f, 0f, w, h, p)
        }
    }

    // ---- START -------------------------------------------------------------------------------------------------------
    private fun startPage() {
        page = "start"; shell()
        col.addView(line(getString(R.string.login_welcome), 15f, 8, 24))
        col.addView(big(getString(R.string.login_have_code)) { signUpPage() }, lp())
        col.addView(big(getString(R.string.login_have_account)) { signInPage(null) }, lp(12))
        col.addView(small(getString(R.string.lang_switch)) { Lang.set(this, if (Lang.current(this) == "fr") "en" else "fr"); recreate() }, lp(28))
        footer()
    }

    // ---- SIGN UP -----------------------------------------------------------------------------------------------------
    private fun signUpPage() {
        page = "signup"; shell()
        col.addView(line(getString(R.string.signup_intro)))
        val code = field(getString(R.string.signup_code)).apply { inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS }
        val user = field(getString(R.string.signup_login)).apply { setAutofillHints(View.AUTOFILL_HINT_USERNAME) }
        val pass = field(getString(R.string.signup_password), true).apply { setAutofillHints("newPassword") }
        val pass2 = field(getString(R.string.signup_password2), true).apply { imeOptions = EditorInfo.IME_ACTION_DONE }
        val hint = TextView(this).apply { textSize = 12f; alpha = 0.7f; text = getString(R.string.signup_rules) }
        val err = errLine()
        val busy = ProgressBar(this).apply { visibility = View.GONE }
        val go = big(getString(R.string.signup_create)) {}
        fun check(): String? {
            val u = user.text.toString().trim(); val p = pass.text.toString()
            return when {
                code.text.toString().trim().isEmpty() -> getString(R.string.signup_err_code_empty)
                !Regex("^[A-Za-z0-9_]{3,16}$").matches(u) -> getString(R.string.signup_err_name_invalid)
                p.length < 8 -> getString(R.string.signup_err_password_short)
                p != pass2.text.toString() -> getString(R.string.signup_err_mismatch)
                else -> null
            }
        }
        fun submit() {
            check()?.let { err.text = it; return }
            go.isEnabled = false; busy.visibility = View.VISIBLE; err.text = ""
            val c = code.text.toString().trim(); val u = user.text.toString().trim(); val p = pass.text.toString()
            Thread {
                val r = Auth.signup(this, c, u, p)
                runOnUiThread {
                    go.isEnabled = true; busy.visibility = View.GONE
                    if (r == Auth.Result.SIGNUP) err.text = signupWords(Auth.signupError) else done(r, err, u, p)
                }
            }.start()
        }
        go.setOnClickListener { submit() }
        pass2.setOnEditorActionListener { _, a, _ -> if (a == EditorInfo.IME_ACTION_DONE) { submit(); true } else false }
        col.addView(code, lp()); col.addView(user, lp()); col.addView(pass, lp()); col.addView(pass2, lp()); col.addView(hint, lp(4))
        col.addView(err, lp()); col.addView(go, lp(16)); col.addView(busy)
        col.addView(line(getString(R.string.signup_recorded), 13f, 16, 0))
        col.addView(small(getString(R.string.signup_have_account)) { signInPage(null) }, lp(16))
        footer()
    }

    private fun signupWords(e: String): String = getString(when (e) {
        "name_taken" -> R.string.signup_err_name_taken
        "name_invalid" -> R.string.signup_err_name_invalid
        "name_rude" -> R.string.signup_err_name_rude
        "password_short" -> R.string.signup_err_password_short
        "password_same" -> R.string.pw_err_same
        "wrong_password" -> R.string.pw_err_wrong
        "code_unknown" -> R.string.signup_err_code_unknown
        "code_off" -> R.string.signup_err_code_off
        "code_used_up" -> R.string.signup_err_code_used_up
        "ip_blocked" -> R.string.signup_err_ip_blocked
        "too_many" -> R.string.signup_err_too_many
        else -> R.string.signup_err_server
    })

    // ---- SIGN IN -----------------------------------------------------------------------------------------------------
    private fun signInPage(refused: String?) {
        page = "signin"; shell()
        col.addView(line(getString(if (!BuildConfig.DEV) R.string.login_intro_brawler else R.string.login_intro_dev)))
        val user = field(getString(R.string.login_username)).apply { setText(Auth.user(this@LoginActivity) ?: ""); setAutofillHints(View.AUTOFILL_HINT_USERNAME) }
        val pass = field(getString(R.string.login_password), true).apply { imeOptions = EditorInfo.IME_ACTION_DONE; setAutofillHints(View.AUTOFILL_HINT_PASSWORD) }
        val err = errLine()
        val busy = ProgressBar(this).apply { visibility = View.GONE }
        val go = big(getString(R.string.login_signin)) {}
        fun submit() {
            val u = user.text.toString().trim(); val p = pass.text.toString()
            if (u.isEmpty() || p.isEmpty()) { err.text = getString(R.string.login_err_empty); return }
            go.isEnabled = false; busy.visibility = View.VISIBLE; err.text = ""
            Thread {
                val r = Auth.login(this, u, p)
                runOnUiThread { go.isEnabled = true; busy.visibility = View.GONE; done(r, err, u, p) }
            }.start()
        }
        refused?.let { err.text = it }
        go.setOnClickListener { submit() }
        pass.setOnEditorActionListener { _, a, _ -> if (a == EditorInfo.IME_ACTION_DONE) { submit(); true } else false }
        col.addView(user, lp()); col.addView(pass, lp()); col.addView(err, lp()); col.addView(go, lp(16)); col.addView(busy)
        col.addView(line(getString(R.string.login_recorded), 13f, 16, 0))
        if (!BuildConfig.DEV) col.addView(small(getString(R.string.login_have_code)) { signUpPage() }, lp(16))
        footer()
    }

    // ---- NEW PASSWORD (a temporary one was used) ---------------------------------------------------------------------
    private fun newPasswordPage(user: String) {
        page = "password"; shell()
        col.addView(line(getString(R.string.pw_intro, user)))
        val pass = field(getString(R.string.pw_new), true).apply { setAutofillHints("newPassword") }
        val pass2 = field(getString(R.string.signup_password2), true).apply { imeOptions = EditorInfo.IME_ACTION_DONE }
        val err = errLine()
        val busy = ProgressBar(this).apply { visibility = View.GONE }
        val go = big(getString(R.string.pw_save)) {}
        fun submit() {
            val p = pass.text.toString()
            when { p.length < 8 -> { err.text = getString(R.string.signup_err_password_short); return }
                   p != pass2.text.toString() -> { err.text = getString(R.string.signup_err_mismatch); return } }
            go.isEnabled = false; busy.visibility = View.VISIBLE; err.text = ""
            Thread {
                val r = Auth.changePassword(this, p)
                runOnUiThread {
                    go.isEnabled = true; busy.visibility = View.GONE
                    when (r) { Auth.Result.SIGNUP -> err.text = signupWords(Auth.signupError)
                               Auth.Result.BAD_CREDENTIALS -> signInPage(getString(R.string.pw_expired))
                               else -> done(r, err, user, p) }
                }
            }.start()
        }
        go.setOnClickListener { submit() }
        pass2.setOnEditorActionListener { _, a, _ -> if (a == EditorInfo.IME_ACTION_DONE) { submit(); true } else false }
        col.addView(pass, lp()); col.addView(pass2, lp()); col.addView(TextView(this).apply { textSize = 12f; alpha = 0.7f; text = getString(R.string.pw_rules) }, lp(4))
        col.addView(err, lp()); col.addView(go, lp(16)); col.addView(busy)
        footer()
    }

    /** a sign-in's (or sign-up's) result: OK = the account's settings back (the language may change), then the game */
    private fun done(r: Auth.Result, err: TextView, user: String, pass: String) {
        when (r) {
            Auth.Result.OK -> {
                getSystemService(android.view.autofill.AutofillManager::class.java)?.commit()
                err.text = ""
                Thread { SettingsSync.pull(this); runOnUiThread { startActivity(Intent(this, MainActivity::class.java)); finish() } }.start()
            }
            Auth.Result.MUST_CHANGE -> newPasswordPage(user)
            Auth.Result.BAD_CREDENTIALS -> err.text = getString(R.string.login_err_wrong)
            Auth.Result.TOO_MANY -> err.text = getString(R.string.login_err_too_many)
            Auth.Result.OFFLINE -> err.text = getString(R.string.login_err_offline)
            else -> err.text = Auth.refusal(r)
        }
    }

    @Deprecated("back: the previous page") override fun onBackPressed() {
        when (page) { "signup", "signin" -> if (Auth.user(this) == null && !BuildConfig.DEV) startPage() else @Suppress("DEPRECATION") super.onBackPressed()
                      "password" -> signInPage(null)
                      else -> @Suppress("DEPRECATION") super.onBackPressed() }
    }
}
