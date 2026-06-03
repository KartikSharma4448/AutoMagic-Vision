"""
Hand-Controlled Mouse + Iron Man Effects
==========================================
Point with your index finger to move the cursor.
Pinch (thumb + index) to click / drag (mobile-style).

Keys: C = mouse | E = effects | Q = quit
"""

import cv2
import mediapipe as mp
import numpy as np
import time
import os
import sys

from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
from mouse_control import MouseController
from handgestures import EffectsEngine

# ─── Landmark IDs ────────────────────────────────────────────────────────────────
TIP  = [4, 8, 12, 16, 20]
PIP  = [3, 6, 10, 14, 18]
NAMES = ["Thumb", "Index", "Middle", "Ring", "Pinky"]

SKELETON = [
    (0,1),(1,2),(2,3),(3,4),  (0,5),(5,6),(6,7),(7,8),
    (0,9),(9,10),(10,11),(11,12), (0,13),(13,14),(14,15),(15,16),
    (0,17),(17,18),(18,19),(19,20), (5,9),(9,13),(13,17),
]

# ─── Colours (BGR) ───────────────────────────────────────────────────────────────
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
#  Drawing helpers — each does one job, no unnecessary copies
# ═════════════════════════════════════════════════════════════════════════════════

def overlay_rect(img, x1, y1, x2, y2, color=C_BG, alpha=0.72):
    """Draw translucent rectangle directly onto img (single ROI copy)."""
    roi = img[y1:y2, x1:x2]
    fill = np.full_like(roi, color, dtype=np.uint8)
    cv2.addWeighted(fill, alpha, roi, 1 - alpha, 0, roi)
    img[y1:y2, x1:x2] = roi


def draw_skeleton(frame, lms, w, h):
    """Draw hand skeleton with styled joints."""
    pts = [(int(l.x * w), int(l.y * h)) for l in lms]

    # Bones
    for a, b in SKELETON:
        cv2.line(frame, pts[a], pts[b], C_BONE, 2, cv2.LINE_AA)

    # Joints
    for i, (cx, cy) in enumerate(pts):
        if i == 0:
            cv2.circle(frame, (cx, cy), 7, C_WRIST, -1, cv2.LINE_AA)
        elif i in TIP:
            c = FTIP_C[TIP.index(i)]
            cv2.circle(frame, (cx, cy), 10, c, 2, cv2.LINE_AA)
            cv2.circle(frame, (cx, cy), 5,  c, -1, cv2.LINE_AA)
        else:
            cv2.circle(frame, (cx, cy), 3, C_GRAY, -1, cv2.LINE_AA)


def draw_pinch_line(frame, lms, w, h, pinching, dist):
    """Visualise pinch: line between thumb and index, colour = proximity."""
    tx, ty = int(lms[4].x * w), int(lms[4].y * h)
    ix, iy = int(lms[8].x * w), int(lms[8].y * h)

    if pinching:
        col, thick = C_RED, 3
        mx, my = (tx+ix)//2, (ty+iy)//2
        cv2.circle(frame, (mx, my), 14, C_RED, 2, cv2.LINE_AA)
    else:
        t = max(0.0, min(1.0, 1.0 - dist / 0.09))
        col = (0, int(220*(1-t)), int(255*t))
        thick = 2

    cv2.line(frame, (tx, ty), (ix, iy), col, thick, cv2.LINE_AA)


def finger_up(lms, idx, hand_label):
    """Is finger `idx` extended?"""
    tip, pip = lms[TIP[idx]], lms[PIP[idx]]
    if idx == 0:
        return (tip.x < pip.x) if hand_label == "Right" else (tip.x > pip.x)
    return tip.y < pip.y


def draw_hand_panel(frame, lms, hand_label, slot, fw, fh):
    """Compact finger-status panel."""
    pw, ph = 200, 165
    m = 10
    ox = m if slot == 0 else fw - pw - m
    oy = m

    overlay_rect(frame, ox, oy, ox + pw, oy + ph)

    cv2.putText(frame, f"{hand_label} Hand", (ox+8, oy+22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, C_CYAN, 2)
    cv2.line(frame, (ox+8, oy+30), (ox+pw-8, oy+30), C_GRAY, 1)

    ups = 0
    for i, name in enumerate(NAMES):
        ry = oy + 50 + i * 22
        up = finger_up(lms, i, hand_label)
        ups += up
        sc = C_GREEN if up else C_RED
        cv2.circle(frame, (ox+14, ry-3), 4, sc, -1)
        cv2.putText(frame, name, (ox+26, ry),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, C_WHITE, 1)
        cv2.putText(frame, "UP" if up else "DN", (ox+100, ry),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, sc, 1)

    cv2.putText(frame, f"Count: {ups}", (ox+8, oy+ph-8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, C_GREEN, 1)


def draw_status_bar(frame, fw, fh, mouse, diag, fps):
    """Single bottom bar: FPS + mouse status + pinch."""
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

    # Cursor pos
    if diag:
        sx, sy = diag["screen_pos"]
        cv2.putText(frame, f"({sx},{sy})", (280, oy+24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, C_GRAY, 1)

        # Action state
        act = diag.get("action", "move")
        if act == "press":
            cv2.putText(frame, "TAP", (400, oy+24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 180, 255), 2)
        elif act == "drag":
            hold_t = diag.get("hold_time", 0)
            cv2.putText(frame, f"DRAG {hold_t:.1f}s", (400, oy+24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 100, 255), 2)
        elif act == "release":
            cv2.putText(frame, "RELEASED", (400, oy+24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.50, C_GREEN, 2)

    # Hint
    cv2.putText(frame, "[C] toggle  [Q] quit", (fw-210, oy+24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, C_GRAY, 1)


def draw_idle(frame, fw, fh):
    """Centred prompt when no hand is visible."""
    msg = "Show your hand to start"
    sz = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 0.75, 2)[0]
    tx = (fw - sz[0]) // 2
    ty = fh // 2
    overlay_rect(frame, tx-16, ty-28, tx+sz[0]+16, ty+10)
    cv2.putText(frame, msg, (tx, ty),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, C_GRAY, 2, cv2.LINE_AA)


# ═════════════════════════════════════════════════════════════════════════════════
#  Main
# ═════════════════════════════════════════════════════════════════════════════════

def main():
    # ── Model ────────────────────────────────────────────────────────────
    here = os.path.dirname(os.path.abspath(__file__))
    model = os.path.join(here, "hand_landmarker.task")
    if not os.path.exists(model):
        print("[ERROR] hand_landmarker.task not found in", here)
        print("Download: https://storage.googleapis.com/mediapipe-models/"
              "hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task")
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

    # ── Camera ───────────────────────────────────────────────────────────
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)  # DirectShow = faster init on Windows
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)  # fallback
    if not cap.isOpened():
        print("[ERROR] Cannot open webcam.")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)

    # ── State ────────────────────────────────────────────────────────────
    mouse = MouseController()
    mouse.enabled = False       # safe default — press 'c'
    fx = EffectsEngine()
    fx_on = True                # effects ON by default
    diag = {}
    prev_t = time.perf_counter()
    fps = 0.0
    ts_ms = 0
    win = "Iron Hand"

    print(f"Ready.  Camera {int(cap.get(3))}x{int(cap.get(4))}")
    print("  C = mouse | E = effects | Q = quit")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            frame = cv2.flip(frame, 1)          # mirror
            fh, fw = frame.shape[:2]

            # Detect
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            ts_ms += 33
            result = landmarker.detect_for_video(
                mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts_ms
            )

            if result.hand_landmarks:
                all_hand_lms = []
                for idx, (lms, hd) in enumerate(
                    zip(result.hand_landmarks, result.handedness)
                ):
                    label = hd[0].category_name
                    label = ("Left" if label == "Right" else "Right")  # mirror flip

                    draw_skeleton(frame, lms, fw, fh)
                    draw_hand_panel(frame, lms, label, idx, fw, fh)
                    all_hand_lms.append(lms)

                    if idx == 0:
                        diag = mouse.update(lms)
                        draw_pinch_line(frame, lms, fw, fh,
                                        diag["pinching"], diag["pinch_dist"])

                        # Iron Man / Magic effects
                        if fx_on:
                            fx.render(frame, lms, fw, fh,
                                      pinching=diag["pinching"])
                            if diag.get("action") == "press":
                                pcx = int(sum(lms[i].x for i in [0,5,9,13,17]) / 5 * fw)
                                pcy = int(sum(lms[i].y for i in [0,5,9,13,17]) / 5 * fh)
                                fx.trigger_shockwave(pcx, pcy)

                # ── Finger-to-finger connections + sparks ──
                if fx_on and len(all_hand_lms) == 2:
                    fx.render_finger_connections(
                        frame, all_hand_lms[0], all_hand_lms[1], fw, fh
                    )
            else:
                draw_idle(frame, fw, fh)
                mouse.reset()
                fx.reset()
                diag = {}

            # ── Iron Man Helmet on face ──
            if fx_on:
                fx.render_helmet(frame, fw, fh)

            # FPS
            now = time.perf_counter()
            fps = 0.9 * fps + 0.1 / max(now - prev_t, 1e-6)
            prev_t = now

            draw_status_bar(frame, fw, fh, mouse, diag, fps)

            cv2.imshow(win, frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("c"):
                mouse.enabled = not mouse.enabled
                print(f"  Mouse {'ON' if mouse.enabled else 'OFF'}")
            elif key == ord("e"):
                fx_on = not fx_on
                print(f"  Effects {'ON' if fx_on else 'OFF'}")

    finally:
        cap.release()
        landmarker.close()
        cv2.destroyAllWindows()
        print("Stopped.")


if __name__ == "__main__":
    main()
