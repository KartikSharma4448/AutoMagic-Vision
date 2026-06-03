"""
Complete Hand Gestures with Smart Mouse Control
=================================================
All-in-one standalone hand gesture recognition + smart mouse controller.
No fancy effects — clean, professional, fast.

Features:
  • Move cursor with index finger (adaptive smoothing)
  • Pinch (thumb + index) to click / drag (mobile-style)
  • Quick pinch+release = click  |  Hold pinch + move = drag
  • All 5 finger states tracked (UP / DN)
  • Finger count display
  • Clean skeleton + joint visualization
  • Real-time FPS, cursor position, action state

Keys:  C = toggle mouse  |  Q = quit
"""

import cv2
import mediapipe as mp
import numpy as np
import math
import time
import ctypes
import ctypes.wintypes
import os, sys
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

# ═════════════════════════════════════════════════════════════════════════════════
#  Constants
# ═════════════════════════════════════════════════════════════════════════════════

TIP  = [4, 8, 12, 16, 20]
PIP  = [3, 6, 10, 14, 18]
NAMES = ["Thumb", "Index", "Middle", "Ring", "Pinky"]

SKELETON = [
    (0,1),(1,2),(2,3),(3,4),  (0,5),(5,6),(6,7),(7,8),
    (0,9),(9,10),(10,11),(11,12), (0,13),(13,14),(14,15),(15,16),
    (0,17),(17,18),(18,19),(19,20), (5,9),(9,13),(13,17),
]

# Colours (BGR)
C_BG    = (30, 30, 30)
C_WHITE = (255, 255, 255)
C_GRAY  = (160, 160, 160)
C_GREEN = (0, 220, 100)
C_RED   = (50, 50, 255)
C_CYAN  = (220, 200, 0)
C_BONE  = (160, 220, 160)
C_WRIST = (255, 150, 50)
FTIP_C  = [(0,160,255),(0,220,100),(220,200,0),(180,105,255),(50,50,255)]


# ═════════════════════════════════════════════════════════════════════════════════
#  Win32 Mouse Control (direct SendInput — no pyautogui needed)
# ═════════════════════════════════════════════════════════════════════════════════

_MOUSEEVENTF_MOVE     = 0x0001
_MOUSEEVENTF_ABSOLUTE = 0x8000
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP   = 0x0004
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


def get_screen_size():
    u32 = ctypes.windll.user32
    u32.SetProcessDPIAware()
    return u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)


def map_to_screen(nx, ny, sw, sh, margin=0.15):
    rx = max(0.0, min(1.0, (nx - margin) / (1.0 - 2 * margin)))
    ry = max(0.0, min(1.0, (ny - margin) / (1.0 - 2 * margin)))
    return rx * sw, ry * sh


def pinch_distance(landmarks):
    t, i = landmarks[4], landmarks[8]
    return math.sqrt((t.x-i.x)**2 + (t.y-i.y)**2 + (t.z-i.z)**2)


# ═════════════════════════════════════════════════════════════════════════════════
#  Mouse Controller
# ═════════════════════════════════════════════════════════════════════════════════

class MouseController:
    """
    Mobile-style mouse controller.
    Pinch = touch:  start → mouse DOWN | held → DRAG | release → mouse UP
    Quick pinch+release = normal click.
    """

    def __init__(self):
        self.screen_w, self.screen_h = get_screen_size()
        self.enabled = True
        self._sx = self._sy = 0.0
        self._init = False
        self._pinch_enter = 0.040
        self._pinch_exit  = 0.060
        self._is_pinching = False
        self._mouse_down  = False
        self._pinch_start = 0.0

    def update(self, landmarks):
        idx_tip = landmarks[8]
        raw_x, raw_y = map_to_screen(idx_tip.x, idx_tip.y, self.screen_w, self.screen_h)

        if not self._init:
            self._sx, self._sy = raw_x, raw_y
            self._init = True
        else:
            speed = math.hypot(raw_x - self._sx, raw_y - self._sy)
            alpha = min(0.75, max(0.18, speed / 120.0))
            self._sx += alpha * (raw_x - self._sx)
            self._sy += alpha * (raw_y - self._sy)

        sx, sy = int(self._sx), int(self._sy)

        if self.enabled:
            abs_x = int(sx * 65535 / self.screen_w)
            abs_y = int(sy * 65535 / self.screen_h)
            _mouse_event(abs_x, abs_y, _MOUSEEVENTF_MOVE | _MOUSEEVENTF_ABSOLUTE)

        dist = pinch_distance(landmarks)
        was = self._is_pinching
        if not self._is_pinching and dist < self._pinch_enter:
            self._is_pinching = True
        elif self._is_pinching and dist > self._pinch_exit:
            self._is_pinching = False

        action = "move"
        now = time.time()

        if self._is_pinching and not was:
            self._pinch_start = now
            self._pinch_handled = False
            action = "press"
        elif self._is_pinching and was:
            if not getattr(self, '_pinch_handled', False) and (now - self._pinch_start) > 5.0:
                if self.enabled and not self._mouse_down:
                    _mouse_event(0, 0, _MOUSEEVENTF_LEFTDOWN)
                    self._mouse_down = True
                self._pinch_handled = True
            
            if self._mouse_down:
                action = "drag"
            else:
                action = "wait..."
        elif not self._is_pinching and was:
            if not getattr(self, '_pinch_handled', False):
                # Quick tap (< 5.0s) -> Click!
                if self.enabled:
                    _mouse_event(0, 0, _MOUSEEVENTF_LEFTDOWN)
                    _mouse_event(0, 0, _MOUSEEVENTF_LEFTUP)
                action = "tap"
            else:
                # Release after drag
                if self.enabled and self._mouse_down:
                    _mouse_event(0, 0, _MOUSEEVENTF_LEFTUP)
                    self._mouse_down = False
                action = "release"

        return {
            "screen_pos": (sx, sy),
            "pinching":   self._is_pinching,
            "pinch_dist": dist,
            "action":     action,
            "holding":    self._mouse_down,
            "hold_time":  (now - self._pinch_start) if self._mouse_down else 0.0,
        }

    def reset(self):
        if self._mouse_down:
            _mouse_event(0, 0, _MOUSEEVENTF_LEFTUP)
            self._mouse_down = False
        self._init = False
        self._is_pinching = False


# ═════════════════════════════════════════════════════════════════════════════════
#  Drawing Helpers
# ═════════════════════════════════════════════════════════════════════════════════

def overlay_rect(img, x1, y1, x2, y2, color=C_BG, alpha=0.72):
    roi = img[y1:y2, x1:x2]
    fill = np.full_like(roi, color, dtype=np.uint8)
    cv2.addWeighted(fill, alpha, roi, 1-alpha, 0, roi)
    img[y1:y2, x1:x2] = roi


def draw_skeleton(frame, lms, w, h):
    pts = [(int(l.x*w), int(l.y*h)) for l in lms]
    for a, b in SKELETON:
        cv2.line(frame, pts[a], pts[b], C_BONE, 2, cv2.LINE_AA)
    for i, (cx, cy) in enumerate(pts):
        if i == 0:
            cv2.circle(frame, (cx,cy), 7, C_WRIST, -1, cv2.LINE_AA)
        elif i in TIP:
            c = FTIP_C[TIP.index(i)]
            cv2.circle(frame, (cx,cy), 10, c, 2, cv2.LINE_AA)
            cv2.circle(frame, (cx,cy), 5, c, -1, cv2.LINE_AA)
        else:
            cv2.circle(frame, (cx,cy), 3, C_GRAY, -1, cv2.LINE_AA)


def draw_pinch_line(frame, lms, w, h, pinching, dist):
    tx, ty = int(lms[4].x*w), int(lms[4].y*h)
    ix, iy = int(lms[8].x*w), int(lms[8].y*h)
    if pinching:
        col, thick = C_RED, 3
        mx, my = (tx+ix)//2, (ty+iy)//2
        cv2.circle(frame, (mx,my), 14, C_RED, 2, cv2.LINE_AA)
    else:
        t = max(0.0, min(1.0, 1-dist/0.09))
        col = (0, int(220*(1-t)), int(255*t))
        thick = 2
    cv2.line(frame, (tx,ty), (ix,iy), col, thick, cv2.LINE_AA)


def finger_up(lms, idx, label):
    tip, pip = lms[TIP[idx]], lms[PIP[idx]]
    if idx == 0:
        return (tip.x < pip.x) if label == "Right" else (tip.x > pip.x)
    return tip.y < pip.y


def draw_hand_panel(frame, lms, label, slot, fw, fh):
    pw, ph = 200, 165
    m = 10
    ox = m if slot == 0 else fw - pw - m
    oy = m
    overlay_rect(frame, ox, oy, ox+pw, oy+ph)
    cv2.putText(frame, f"{label} Hand", (ox+8, oy+22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, C_CYAN, 2)
    cv2.line(frame, (ox+8, oy+30), (ox+pw-8, oy+30), C_GRAY, 1)
    ups = 0
    for i, name in enumerate(NAMES):
        ry = oy + 50 + i*22
        up = finger_up(lms, i, label)
        ups += up
        sc = C_GREEN if up else C_RED
        cv2.circle(frame, (ox+14, ry-3), 4, sc, -1)
        cv2.putText(frame, name, (ox+26, ry), cv2.FONT_HERSHEY_SIMPLEX, 0.40, C_WHITE, 1)
        cv2.putText(frame, "UP" if up else "DN", (ox+100, ry), cv2.FONT_HERSHEY_SIMPLEX, 0.38, sc, 1)
    cv2.putText(frame, f"Count: {ups}", (ox+8, oy+ph-8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, C_GREEN, 1)


def draw_status_bar(frame, fw, fh, mouse, diag, fps):
    bar_h = 36
    oy = fh - bar_h
    overlay_rect(frame, 0, oy, fw, fh, alpha=0.78)

    # FPS
    fc = C_GREEN if fps >= 20 else C_RED
    cv2.putText(frame, f"FPS {fps:.0f}", (10, oy+24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, fc, 1)

    # Mouse state
    tag = "MOUSE ON" if mouse.enabled else "MOUSE OFF"
    tc = C_GREEN if mouse.enabled else C_RED
    cv2.putText(frame, tag, (110, oy+24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, tc, 2)

    # Cursor pos + action
    if diag:
        sx, sy = diag["screen_pos"]
        cv2.putText(frame, f"({sx},{sy})", (280, oy+24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, C_GRAY, 1)
        act = diag.get("action", "move")
        if act == "press":
            cv2.putText(frame, "TAP", (400, oy+24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0,180,255), 2)
        elif act == "drag":
            ht = diag.get("hold_time", 0)
            cv2.putText(frame, f"DRAG {ht:.1f}s", (400, oy+24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0,100,255), 2)
        elif act == "release":
            cv2.putText(frame, "RELEASED", (400, oy+24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.50, C_GREEN, 2)

    cv2.putText(frame, "[C] toggle  [Q] quit", (fw-210, oy+24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, C_GRAY, 1)


# ═════════════════════════════════════════════════════════════════════════════════
#  Main
# ═════════════════════════════════════════════════════════════════════════════════

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    model = os.path.join(here, "hand_landmarker.task")
    if not os.path.exists(model):
        print("[ERROR] hand_landmarker.task not found in", here)
        sys.exit(1)

    landmarker = vision.HandLandmarker.create_from_options(
        vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=model),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.65,
            min_hand_presence_confidence=0.55,
            min_tracking_confidence=0.55,
        )
    )

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened(): cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Cannot open webcam."); sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)

    mouse = MouseController()
    mouse.enabled = False
    diag = {}
    prev_t = time.perf_counter()
    fps = 0.0
    ts_ms = 0

    print(f"[*] Smart Mouse -- Camera {int(cap.get(3))}x{int(cap.get(4))}")
    print(f"   Screen: {mouse.screen_w}x{mouse.screen_h}")
    print("   C = toggle mouse | Q = quit")
    print("   Mouse is OFF by default. Press C to activate.")

    try:
        while True:
            ok, frame = cap.read()
            if not ok: break
            frame = cv2.flip(frame, 1)
            fh, fw = frame.shape[:2]

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            ts_ms += 33
            result = landmarker.detect_for_video(
                mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts_ms)

            if result.hand_landmarks:
                for idx, (lms, hd) in enumerate(
                    zip(result.hand_landmarks, result.handedness)):
                    label = hd[0].category_name
                    label = ("Left" if label == "Right" else "Right")

                    draw_skeleton(frame, lms, fw, fh)
                    draw_hand_panel(frame, lms, label, idx, fw, fh)

                    if idx == 0:
                        diag = mouse.update(lms)
                        draw_pinch_line(frame, lms, fw, fh,
                                        diag["pinching"], diag["pinch_dist"])
            else:
                msg = "Show your hand to control"
                sz = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 0.75, 2)[0]
                tx = (fw-sz[0])//2
                overlay_rect(frame, tx-16, fh//2-28, tx+sz[0]+16, fh//2+10)
                cv2.putText(frame, msg, (tx, fh//2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.75, C_GRAY, 2, cv2.LINE_AA)
                mouse.reset()
                diag = {}

            # FPS
            now = time.perf_counter()
            fps = 0.9*fps + 0.1/max(now-prev_t, 1e-6)
            prev_t = now

            draw_status_bar(frame, fw, fh, mouse, diag, fps)

            cv2.imshow("Smart Mouse Control", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"): break
            elif key == ord("c"):
                mouse.enabled = not mouse.enabled
                print(f"  Mouse {'ON' if mouse.enabled else 'OFF'}")
    finally:
        cap.release()
        landmarker.close()
        cv2.destroyAllWindows()
        print("Stopped.")


if __name__ == "__main__":
    main()
