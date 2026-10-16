package com.neoscan.player

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class GamepadsTest {
    private val keyboard = 0x00000101                                // SOURCE_KEYBOARD: the phone's own keys (gpio-keys)
    private val touch = 0x00001002                                   // SOURCE_TOUCHSCREEN
    private val pad = Gamepads.SOURCE_GAMEPAD or Gamepads.SOURCE_JOYSTICK or keyboard   // an Xbox / 8BitDo pad
    private val stickOnly = Gamepads.SOURCE_JOYSTICK                 // an arcade stick without buttons declared

    @Test fun which_devices_count() {
        assertTrue(Gamepads.isPad(pad, false))
        assertTrue(Gamepads.isPad(Gamepads.SOURCE_GAMEPAD, false))
        assertTrue(Gamepads.isPad(stickOnly, false))
        assertFalse(Gamepads.isPad(keyboard, false))                   // volume / power keys
        assertFalse(Gamepads.isPad(touch, false))
        assertFalse(Gamepads.isPad(pad, true))                         // virtual (adb input, the IME)
        assertFalse(Gamepads.isPad(0x00000401 and 0x400, false))       // SOURCE_CLASS-less partial bits
    }

    @Test fun connect_and_disconnect() {
        val g = Gamepads()
        assertFalse(g.device(1, keyboard, false))                      // the phone's keys at start: nothing
        assertFalse(g.device(-1, keyboard, true))
        assertFalse(g.connected)
        assertTrue(g.device(7, pad, false))                            // a pad plugged: changed
        assertFalse(g.device(7, pad, false))                           // the same one again (onInputDeviceChanged)
        assertFalse(g.device(8, pad, false))                           // a second one: no change of state
        assertEquals(2, g.count)
        assertFalse(g.removed(7))                                      // one left
        assertTrue(g.connected)
        assertTrue(g.removed(8))                                       // the last: shown again
        assertFalse(g.connected)
        assertFalse(g.removed(42))                                     // an unknown removal
    }

    @Test fun input_marks_a_keyboard_declared_pad() {
        val g = Gamepads()
        g.device(5, keyboard, false)
        assertFalse(g.input(5, false, false, false))                   // a plain key: not a controller
        assertFalse(g.input(-1, true, true, false))                    // a virtual device's gamepad key
        assertTrue(g.input(5, false, true, false))                     // BUTTON_A from it: a controller
        assertFalse(g.input(5, false, true, false))
        assertTrue(g.removed(5))
        assertTrue(g.input(9, false, false, true))                     // a joystick move
    }

    @Test fun visibility_setting() {
        assertTrue(Gamepads.visible("auto", false))
        assertFalse(Gamepads.visible("auto", true))
        assertTrue(Gamepads.visible("show", true))
        assertFalse(Gamepads.visible("hide", false))
        assertFalse(Gamepads.visible("hide", true))
        assertFalse(Gamepads.visible("bogus", true))                   // anything else = auto
    }

    @Test fun combos() {
        val c = Combos()
        assertEquals(Combos.Act.PASS, c.key(Pad.START, true))          // START alone: the game
        assertEquals(Combos.Act.PASS, c.key(Pad.START, false))
        assertEquals(Combos.Act.PASS, c.key(Pad.A, true))              // A alone: the game
        assertEquals(Combos.Act.PASS, c.key(Pad.A, false))
        assertEquals(Combos.Act.PASS, c.key(Pad.COIN, true))           // SELECT: the game at once
        assertEquals(Combos.Act.PROFILE, c.key(Pad.START, true))       // + START: the profile menu
        assertEquals(Combos.Act.NONE, c.key(Pad.START, false))         // its release kept from the game
        assertEquals(Combos.Act.FEEDBACK_ON, c.key(Pad.A, true))       // + A: the mic
        assertEquals(Combos.Act.PASS, c.key(Pad.UP, true))             // other buttons still play
        assertEquals(Combos.Act.FEEDBACK_OFF, c.key(Pad.A, false))     // A released: the sheet
        assertEquals(Combos.Act.PASS, c.key(Pad.COIN, false))
        // SELECT released first while A is held: the mic ends there, A's later release stays out of the game
        c.key(Pad.COIN, true); assertEquals(Combos.Act.FEEDBACK_ON, c.key(Pad.A, true))
        assertEquals(Combos.Act.FEEDBACK_OFF, c.key(Pad.COIN, false))
        assertEquals(Combos.Act.NONE, c.key(Pad.A, false))
        assertEquals(Combos.Act.PASS, c.key(Pad.A, true))              // and A plays again
        c.key(Pad.A, false)
        // a dialog took the keys mid-recording
        c.key(Pad.COIN, true); c.key(Pad.A, true)
        assertEquals(Combos.Act.FEEDBACK_OFF, c.reset())
        assertEquals(Combos.Act.PASS, c.key(Pad.START, true))          // SELECT forgotten
        assertEquals(Combos.Act.NONE, c.reset())
    }
}
