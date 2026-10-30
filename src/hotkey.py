"""
A system-wide "clip that" key for live mode: Ctrl+Alt+C on Windows, Control+Option+C (⌃⌥C) on macOS.

It works while you're watching the stream in another window or playing a game:
Clip Radar hears the key, clips the last 30 seconds and plays a short sound.
Elsewhere (or if another app already owns the shortcut) it simply reports that
it isn't available.

On macOS it's a Carbon hot key (RegisterEventHotKey), the kind that needs no Accessibility permission.
Its presses arrive through the app window's event loop, so it works while Clip Radar's own window is
open (not in browser mode).
"""

from __future__ import annotations

import json
import sys
import threading
from typing import Callable

import paths

IS_MAC = sys.platform == "darwin"
KEYS = "⌃⌥C" if IS_MAC else "Ctrl+Alt+C"
PREFS = paths.DATA_DIR / "hotkey.json"
WM_HOTKEY, WM_APP = 0x0312, 0x8000
MOD_ALT, MOD_CONTROL, MOD_NOREPEAT, VK_C = 0x0001, 0x0002, 0x4000, 0x43

state = {"supported": sys.platform in ("win32", "darwin"), "enabled": True, "registered": False, "keys": KEYS,
         "error": "", "presses": 0}
_tid = [0]
_ready = threading.Event()
_callback: list = [lambda: None]


def _load_enabled() -> bool:
    try:
        return bool(json.loads(PREFS.read_text("utf-8")).get("enabled", True))
    except Exception:
        return True


def status() -> dict:
    return dict(state)


def set_enabled(on: bool):
    state["enabled"] = bool(on)
    try:
        PREFS.parent.mkdir(parents=True, exist_ok=True)
        PREFS.write_text(json.dumps({"enabled": bool(on)}), "utf-8")
    except OSError:
        pass
    if IS_MAC:
        if _mac["carbon"] is not None:
            _mac_apply()
        return
    if _tid[0]:
        import ctypes
        ctypes.windll.user32.PostThreadMessageW(_tid[0], WM_APP, 0, 0)
        _ready.clear()
        _ready.wait(2)


def simulate() -> bool:
    """Post a hotkey message as if the keys were pressed (tests)."""
    if IS_MAC:
        if not state["registered"]:
            return False
        _pressed()
        return True
    if not _tid[0]:
        return False
    import ctypes
    return bool(ctypes.windll.user32.PostThreadMessageW(_tid[0], WM_HOTKEY, 1, 0))


def beep(ok: bool = True):
    if IS_MAC:
        import subprocess
        try:
            subprocess.Popen(["/usr/bin/afplay", f"/System/Library/Sounds/{'Tink' if ok else 'Basso'}.aiff"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass
        return
    if sys.platform != "win32":
        return
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_OK if ok else winsound.MB_ICONHAND)
    except Exception:
        pass


def start(on_press: Callable):
    _callback[0] = on_press
    state["enabled"] = _load_enabled()
    if not state["supported"]:
        state["error"] = "The clip hotkey is only available on Windows and macOS."
        return
    if IS_MAC:
        try:
            _mac_start()
        except Exception as e:
            state.update(supported=False, registered=False, error=f"The clip hotkey couldn't be set up ({e}).")
        return
    threading.Thread(target=_loop, daemon=True, name="clip-hotkey").start()
    _ready.wait(3)


def _loop():
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    msg = wintypes.MSG()
    user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)    # create this thread's message queue
    _tid[0] = kernel32.GetCurrentThreadId()

    def apply():
        if state["enabled"] and not state["registered"]:
            if user32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_C):
                state.update(registered=True, error="")
            else:
                state.update(registered=False, error=f"Another app is already using {KEYS}.")
        elif not state["enabled"] and state["registered"]:
            user32.UnregisterHotKey(None, 1)
            state.update(registered=False, error="")
        _ready.set()

    apply()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        if msg.message == WM_HOTKEY:
            state["presses"] += 1
            try:
                _callback[0]()
            except Exception:
                pass
        elif msg.message == WM_APP:
            apply()


def _pressed():
    state["presses"] += 1
    # off the event thread: clipping takes a moment, and the window's event loop must keep going
    threading.Thread(target=_run_callback, daemon=True, name="clip-hotkey-press").start()


def _run_callback():
    try:
        _callback[0]()
    except Exception:
        pass


# ---- macOS (Carbon hot keys) ----
_mac: dict = {"carbon": None, "ref": None, "handler": None}
_KVK_C, _CONTROL, _OPTION = 0x08, 0x1000, 0x0800          # kVK_ANSI_C, controlKey, optionKey
_SIGNATURE = int.from_bytes(b"ClRd", "big")
_KEYBOARD, _HOTKEY_PRESSED = int.from_bytes(b"keyb", "big"), 5       # kEventClassKeyboard, kEventHotKeyPressed


def _mac_start():
    """Set up on the main thread (server.start is called there, before the window opens)."""
    import ctypes

    class EventTypeSpec(ctypes.Structure):
        _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]

    carbon = ctypes.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")
    carbon.GetEventDispatcherTarget.restype = ctypes.c_void_p
    carbon.InstallEventHandler.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p,
                                           ctypes.c_void_p, ctypes.c_void_p]
    carbon.InstallEventHandler.restype = ctypes.c_int32
    handler_t = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)

    def on_event(_call, _event, _data):
        try:
            _pressed()
        except Exception:
            pass
        return 0      # noErr: handled

    handler = handler_t(on_event)           # kept in _mac: Carbon calls it for as long as the app runs
    spec = EventTypeSpec(_KEYBOARD, _HOTKEY_PRESSED)
    rc = carbon.InstallEventHandler(carbon.GetEventDispatcherTarget(), ctypes.cast(handler, ctypes.c_void_p), 1,
                                    ctypes.byref(spec), None, None)
    if rc != 0:
        raise OSError(f"InstallEventHandler failed ({rc})")
    _mac.update(carbon=carbon, handler=handler)
    _mac_apply()


def _mac_apply():
    import ctypes

    class EventHotKeyID(ctypes.Structure):
        _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]

    carbon = _mac["carbon"]
    if state["enabled"] and not state["registered"]:
        carbon.RegisterEventHotKey.argtypes = [ctypes.c_uint32, ctypes.c_uint32, EventHotKeyID, ctypes.c_void_p,
                                               ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
        carbon.RegisterEventHotKey.restype = ctypes.c_int32
        ref = ctypes.c_void_p()
        rc = carbon.RegisterEventHotKey(_KVK_C, _CONTROL | _OPTION, EventHotKeyID(_SIGNATURE, 1),
                                        carbon.GetEventDispatcherTarget(), 0, ctypes.byref(ref))
        if rc == 0:
            _mac["ref"] = ref
            state.update(registered=True, error="")
        else:            # eventHotKeyExistsErr (-9878): another app has it
            state.update(registered=False, error=f"Another app is already using {KEYS}.")
    elif not state["enabled"] and state["registered"]:
        carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
        if _mac["ref"] is not None:
            carbon.UnregisterEventHotKey(_mac["ref"])
        _mac["ref"] = None
        state.update(registered=False, error="")
    _ready.set()


def no_window():
    """macOS in browser mode: there's no app event loop to deliver the key, so say so instead of
    showing it as on."""
    if IS_MAC:
        state.update(supported=False, registered=False,
                     error="On a Mac the clip hotkey works while Clip Radar's own window is open.")
