package com.neoscan.player

import android.graphics.Rect
import android.widget.FrameLayout

/** THE BRAWLER APP (flavor "brawler"): no Assembly. Brawler Dev's (src/dev: the Lab's web page in a WebView with a
 *  JavaScript bridge) is not compiled into this app; the Character lab that opens it does not exist here. */
class Assembly(act: MainActivity, root: FrameLayout, sent: (String, Int) -> Unit) {
    val open = false
    fun show(fighter: String, r: Rect) {}
    fun hide() {}
    fun place(r: Rect) {}
}
