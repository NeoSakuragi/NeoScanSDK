package com.neoscan.player

import android.graphics.Rect
import android.widget.FrameLayout

/** THE SHARED PLAYER (TODO T2): no Assembly. The house Player's (src/devtools: the Lab's web page in a WebView with a
 *  JavaScript bridge) is not in this build; the Character lab that opens it never starts here (BuildConfig.SHARED). */
class Assembly(act: MainActivity, root: FrameLayout, sent: (String, Int) -> Unit) {
    val open = false
    fun show(fighter: String, r: Rect) {}
    fun hide() {}
    fun place(r: Rect) {}
}
