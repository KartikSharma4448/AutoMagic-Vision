"""
Mouse Control Module — Lightweight, reliable gesture-to-cursor engine.

Uses Win32 SendInput directly (no pyautogui dependency).
Provides adaptive smoothing & pinch detection with hysteresis.
"""

import math
import time
import ctypes
import ctypes.wintypes

# ─── Win32 constants ─────────────────────────────────────────────────────────────
_MOUSEEVENTF_MOVE       = 0x0001
_MOUSEEVENTF_ABSOLUTE   = 0x8000
_MOUSEEVENTF_LEFTDOWN   = 0x0002
_MOUSEEVENTF_LEFTUP     = 0x0004
_INPUT_MOUSE = 0


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx",          ctypes.wintypes.LONG),
        ("dy",          ctypes.wintypes.LONG),
        ("mouseData",   ctypes.wintypes.DWORD),
        ("dwFlags",     ctypes.wintypes.DWORD),
        ("time",        ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT)]
    _fields_ = [("type", ctypes.wintypes.DWORD), ("u", _U)]


def _mouse_event(dx, dy, flags):
    mi = _MOUSEINPUT(dx, dy, 0, flags, 0, ctypes.pointer(ctypes.c_ulong(0)))
    inp = _INPUT(type=_INPUT_MOUSE)
    inp.u.mi = mi
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


# ─── Pure functions ──────────────────────────────────────────────────────────────

def get_screen_size():
    """Return (w, h) of the primary monitor, DPI-aware."""
    u32 = ctypes.windll.user32
    u32.SetProcessDPIAware()
    return u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)


def map_to_screen(nx, ny, sw, sh, margin=0.15):
    """
    Map normalised hand coords → screen pixels.
    `margin` shrinks the active zone so you don't need to reach frame edges.
    """
    rx = max(0.0, min(1.0, (nx - margin) / (1.0 - 2 * margin)))
    ry = max(0.0, min(1.0, (ny - margin) / (1.0 - 2 * margin)))
    return rx * sw, ry * sh


def pinch_distance(landmarks):
    """Euclidean distance between thumb-tip (4) and index-tip (8), normalised."""
    t, i = landmarks[4], landmarks[8]
    return math.sqrt((t.x - i.x)**2 + (t.y - i.y)**2 + (t.z - i.z)**2)


# ─── Controller ──────────────────────────────────────────────────────────────────

class MouseController:
    """
    Mobile-style mouse controller.

    Pinch = touch screen with finger:
      • Pinch start  → mouse button DOWN  (tap / start drag)
      • Pinch held   → dragging           (move while holding)
      • Pinch release → mouse button UP   (lift finger)

    Quick pinch+release = normal click.
    Hold pinch + move  = drag (files, scroll bars, text selection, etc.)
    """

    def __init__(self):
        self.screen_w, self.screen_h = get_screen_size()
        self.enabled = True

        # Smoothing state
        self._sx = 0.0
        self._sy = 0.0
        self._initialised = False

        # Pinch state (hysteresis: enter < exit to avoid flicker)
        self._pinch_enter = 0.040
        self._pinch_exit  = 0.060
        self._is_pinching = False
        self._mouse_down  = False   # is left button currently held?
        self._pinch_start = 0.0     # when pinch began

    # ── public ───────────────────────────────────────────────────────────

    def update(self, landmarks):
        """
        Process one frame.  Returns diagnostics dict:
            screen_pos, pinching, pinch_dist, action
            action: "press" | "drag" | "release" | "move"
        """
        idx_tip = landmarks[8]
        raw_x, raw_y = map_to_screen(
            idx_tip.x, idx_tip.y, self.screen_w, self.screen_h
        )

        # Adaptive smoothing: fast motion → responsive, slow → stable
        if not self._initialised:
            self._sx, self._sy = raw_x, raw_y
            self._initialised = True
        else:
            speed = math.hypot(raw_x - self._sx, raw_y - self._sy)
            alpha = min(0.75, max(0.18, speed / 120.0))
            self._sx += alpha * (raw_x - self._sx)
            self._sy += alpha * (raw_y - self._sy)

        sx, sy = int(self._sx), int(self._sy)

        # Move cursor
        if self.enabled:
            abs_x = int(sx * 65535 / self.screen_w)
            abs_y = int(sy * 65535 / self.screen_h)
            _mouse_event(abs_x, abs_y, _MOUSEEVENTF_MOVE | _MOUSEEVENTF_ABSOLUTE)

        # Pinch detection with hysteresis
        dist = pinch_distance(landmarks)
        was_pinching = self._is_pinching

        if not self._is_pinching and dist < self._pinch_enter:
            self._is_pinching = True
        elif self._is_pinching and dist > self._pinch_exit:
            self._is_pinching = False

        # ── Mobile-style press / drag / release ──────────────────────
        action = "move"
        now = time.time()

        if self._is_pinching and not was_pinching:
            # Finger just touched down → PRESS
            if self.enabled and not self._mouse_down:
                _mouse_event(0, 0, _MOUSEEVENTF_LEFTDOWN)
                self._mouse_down = True
                self._pinch_start = now
            action = "press"

        elif self._is_pinching and was_pinching and self._mouse_down:
            # Finger still held → DRAG
            action = "drag"

        elif not self._is_pinching and was_pinching:
            # Finger lifted → RELEASE
            if self.enabled and self._mouse_down:
                _mouse_event(0, 0, _MOUSEEVENTF_LEFTUP)
                self._mouse_down = False
            action = "release"

        return {
            "screen_pos":  (sx, sy),
            "pinching":    self._is_pinching,
            "pinch_dist":  dist,
            "action":      action,
            "holding":     self._mouse_down,
            "hold_time":   (now - self._pinch_start) if self._mouse_down else 0.0,
        }

    def reset(self):
        """Call when hand disappears — release button if held."""
        if self._mouse_down:
            _mouse_event(0, 0, _MOUSEEVENTF_LEFTUP)
            self._mouse_down = False
        self._initialised = False
        self._is_pinching = False
