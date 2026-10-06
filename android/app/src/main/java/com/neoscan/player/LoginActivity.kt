package com.neoscan.player

import android.app.Activity
import android.content.Intent
import android.graphics.Typeface
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView

/** The sign-in screen (Player 0.0.15): shown at the first start and after a logout or a refused sign-in. The Oros
 *  account (canneji.duckdns.org/oros/): username + password typed here, sent to Oros's /api/login ([Auth]); on success
 *  the player starts. Built in code, like the settings. */
class LoginActivity : Activity() {
    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        val dp = resources.displayMetrics.density
        val pad = (24 * dp).toInt()
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(pad, pad * 2, pad, pad); gravity = Gravity.CENTER_HORIZONTAL }
        col.addView(TextView(this).apply { text = "NeoScan Player"; textSize = 26f; setTypeface(typeface, Typeface.BOLD) })
        col.addView(TextView(this).apply {
            text = "Sign in with your Oros account (the one of canneji.duckdns.org/oros). The builds and the feedback need it."
            textSize = 14f; alpha = 0.75f; setPadding(0, (8 * dp).toInt(), 0, (20 * dp).toInt())
        })
        val user = EditText(this).apply {
            hint = "Username"; isSingleLine = true; inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            setText(Auth.user(this@LoginActivity) ?: ""); setAutofillHints(android.view.View.AUTOFILL_HINT_USERNAME)
        }
        val pass = EditText(this).apply {
            hint = "Password"; isSingleLine = true; inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            imeOptions = EditorInfo.IME_ACTION_DONE; setAutofillHints(android.view.View.AUTOFILL_HINT_PASSWORD)
        }
        val err = TextView(this).apply { textSize = 14f; setTextColor(0xFFFF6060.toInt()); setPadding(0, (10 * dp).toInt(), 0, 0) }
        val busy = ProgressBar(this).apply { visibility = android.view.View.GONE }
        val go = Button(this).apply { text = "Sign in" }
        fun submit() {
            val u = user.text.toString().trim(); val p = pass.text.toString()
            if (u.isEmpty() || p.isEmpty()) { err.text = "Type your username and password"; return }
            go.isEnabled = false; busy.visibility = android.view.View.VISIBLE; err.text = ""
            Thread {
                val r = Auth.login(this, u, p)
                runOnUiThread {
                    go.isEnabled = true; busy.visibility = android.view.View.GONE
                    when (r) {
                        Auth.Result.OK -> {
                            getSystemService(android.view.autofill.AutofillManager::class.java)?.commit()
                            startActivity(Intent(this, MainActivity::class.java)); finish()
                        }
                        Auth.Result.BAD_CREDENTIALS -> err.text = "Wrong username or password"
                        Auth.Result.TOO_MANY -> err.text = "Too many attempts: wait 5 minutes"
                        Auth.Result.OFFLINE -> err.text = "No connection to canneji.duckdns.org"
                    }
                }
            }.start()
        }
        go.setOnClickListener { submit() }
        pass.setOnEditorActionListener { _, a, _ -> if (a == EditorInfo.IME_ACTION_DONE) { submit(); true } else false }
        col.addView(user, LinearLayout.LayoutParams(-1, -2))
        col.addView(pass, LinearLayout.LayoutParams(-1, -2))
        col.addView(err, LinearLayout.LayoutParams(-1, -2))
        col.addView(go, LinearLayout.LayoutParams(-1, -2).apply { topMargin = (16 * dp).toInt() })
        col.addView(busy)
        col.addView(TextView(this).apply {
            text = "Player ${BuildConfig.VERSION_NAME}"; textSize = 12f; alpha = 0.5f; setPadding(0, (24 * dp).toInt(), 0, 0)
        })
        setContentView(ScrollView(this).apply { addView(col) })
    }
}
