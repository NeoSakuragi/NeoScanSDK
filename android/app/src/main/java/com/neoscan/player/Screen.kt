package com.neoscan.player

import android.graphics.Rect

/** The one layout rule, shared by the GL picture and the touch pad. Portrait: the picture full width at the top, the
 *  controls in the space under it. Landscape: the picture full height, centred, the controls over its sides. The
 *  picture keeps its shape, letterboxed, never stretched: square pixels (304:224 = 1.357:1), or [four3] = a plain 4:3
 *  rectangle (the 304 x 224 picture scaled to 4:3, pixels 0.98 as wide as tall). */
object Screen {
    const val PIC_W = 304; const val PIC_H = 224
    @Volatile var four3 = false                                     // settings: Display / Aspect
    @Volatile var integer = false                                   // settings: Display / Scale (whole multiples)
    /** 0.0.31: landscape only, the px kept ABOVE the picture for the Character lab's strip (PadView.labH + its margins);
     *  the picture shrinks to the height left under it (a phone's gutters are too narrow for the strip: it covered the
     *  d-pad). 0 = no strip. Portrait ignores it (the strip goes between the picture and the pad's panel). */
    @Volatile var labTop = 0

    /** picture width per unit of height */
    private fun ratio() = if (four3) 4.0 / 3.0 else PIC_W.toDouble() / PIC_H

    fun portrait(w: Int, h: Int) = h > w

    /** where the picture goes in a w x h screen (top-left origin) */
    fun picture(w: Int, h: Int): Rect {
        val k = ratio()
        val top = if (portrait(w, h)) 0 else labTop
        val areaH = if (portrait(w, h)) minOf(h, (w / k).toInt()) else h - top
        var pw = w; var ph = (w / k).toInt()                         // fit the picture inside w x areaH
        if (ph > areaH) { ph = areaH; pw = (areaH * k).toInt() }
        val n = ph / PIC_H                                           // integer: the largest whole multiple of the
        if (integer && n >= 1) { ph = n * PIC_H; pw = (ph * k).toInt() }   // 224 lines that fits (width follows the aspect)
        val x = (w - pw) / 2; val y = if (portrait(w, h)) 0 else top + (h - top - ph) / 2
        return Rect(x, y, x + pw, y + ph)
    }

    /** "3x portrait, 4x landscape" on this phone, for the settings page */
    fun multiples(ctx: android.content.Context): String {
        val m = ctx.resources.displayMetrics; val a = minOf(m.widthPixels, m.heightPixels); val b = maxOf(m.widthPixels, m.heightPixels)
        val keep = integer; integer = true; val lt = labTop; labTop = 0
        val p = picture(a, b).height() / PIC_H; val l = picture(b, a).height() / PIC_H
        integer = keep; labTop = lt
        return "${p}x portrait, ${l}x landscape"
    }
}
