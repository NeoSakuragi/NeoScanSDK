package com.neoscan.player

import android.widget.FrameLayout
import java.io.File
import org.json.JSONObject

/** THE BRAWLER APP (flavor "brawler", docs/feedback.md "Roles and the two apps"): no Character lab. Brawler Dev's
 *  (src/dev: the fighters' live configs pushed into the running game, the shell / pack swaps, the Assembly) is not
 *  compiled into this app; MainActivity never builds one here (BuildConfig.DEV false). Same API, inert. */
class CharacterLab(act: MainActivity, root: FrameLayout, emu: () -> EmuThread?, play: (File) -> Unit,
                   reserve: (Int) -> android.graphics.Rect, leave: () -> Unit) {
    val active = false
    @Volatile var paused = false
    var onAssembly: ((Boolean) -> Unit)? = null
    val facesShown = false
    fun open() {}
    fun back() {}
    fun noteInfo(): JSONObject? = null
    fun stop() {}
}
