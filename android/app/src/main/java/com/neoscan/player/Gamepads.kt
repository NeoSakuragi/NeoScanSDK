package com.neoscan.player

/** PHYSICAL CONTROLLERS (app 0.0.45, both apps; tester note 20261016-193119-e2ef): the gamepads / joysticks connected,
 *  which decide whether the touch pad shows. MainActivity feeds it: every input device at start and on each
 *  InputManager add / change ([device]), each removal ([removed]), and the input itself ([input]: a pad that declares
 *  itself a keyboard is still caught by its first button or stick move). A device counts when it is not virtual (the
 *  phone's own keys and `adb shell input` are virtual or keyboard-only) and declares SOURCE_GAMEPAD or SOURCE_JOYSTICK.
 *  The touch controls setting ([visible]): "auto" (default) = the pad hidden while a controller is connected and shown
 *  again when the last one goes; "show" = always; "hide" = never. A touch never brings it back (no flicker): only the
 *  last controller leaving or the profile menu's setting does. Pure logic (no Android calls): unit-tested. */
class Gamepads {
    private val ids = HashSet<Int>()
    val connected get() = ids.isNotEmpty()
    val count get() = ids.size

    /** a device seen (at start, or added / changed): true when the connected state changed */
    fun device(id: Int, sources: Int, virtual: Boolean): Boolean {
        val was = connected
        if (isPad(sources, virtual)) ids.add(id) else ids.remove(id)
        return connected != was
    }
    /** input from a device: a gamepad button key or a joystick move from a real device marks it connected */
    fun input(id: Int, virtual: Boolean, gamepadKey: Boolean, joystick: Boolean): Boolean {
        if (virtual || !(gamepadKey || joystick) || id in ids) return false
        val was = connected; ids.add(id); return connected != was
    }
    fun removed(id: Int): Boolean { val was = connected; ids.remove(id); return connected != was }

    companion object {
        const val SOURCE_GAMEPAD = 0x00000401                       // android.view.InputDevice's values
        const val SOURCE_JOYSTICK = 0x01000010
        val MODES = listOf("auto", "show", "hide")
        fun isPad(sources: Int, virtual: Boolean) =
            !virtual && (sources and SOURCE_GAMEPAD == SOURCE_GAMEPAD || sources and SOURCE_JOYSTICK == SOURCE_JOYSTICK)
        /** the touch pad's buttons + stick drawn and live */
        fun visible(mode: String, connected: Boolean) = when (mode) { "show" -> true; "hide" -> false; else -> !connected }
    }
}

/** THE CONTROLLER'S MENU COMBOS (0.0.45): with SELECT held, START = the profile menu, A held = the Feedback mic (press
 *  = recording, release of A or SELECT = the note sheet), so a controller alone reaches menus and voice notes. SELECT
 *  alone still reaches the game (COIN, the AES SELECT) at once; the button pressed with it does not. Pure logic: fed
 *  key downs / ups of the Neo Geo bits, answers what to do. */
class Combos {
    enum class Act { NONE, PASS, PROFILE, FEEDBACK_ON, FEEDBACK_OFF }
    private var select = false
    private var mic = false
    private var swallow = 0                                          // bits whose release the combo keeps from the game
    fun key(bit: Int, down: Boolean): Act {
        if (bit == Pad.COIN) {
            select = down
            if (!down && mic) { mic = false; return Act.FEEDBACK_OFF }
            return Act.PASS
        }
        if (down && select && bit == Pad.START) { swallow = swallow or bit; return Act.PROFILE }
        if (down && select && bit == Pad.A && !mic) { swallow = swallow or bit; mic = true; return Act.FEEDBACK_ON }
        if (!down && swallow and bit != 0) {
            swallow = swallow and bit.inv()
            if (bit == Pad.A && mic) { mic = false; return Act.FEEDBACK_OFF }
            return Act.NONE
        }
        return Act.PASS
    }
    /** focus lost (a dialog took the keys): every button is up */
    fun reset(): Act { select = false; swallow = 0; return if (mic) { mic = false; Act.FEEDBACK_OFF } else Act.NONE }
}
