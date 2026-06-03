"""
Ultimate Hand Gesture Fruit Ninja
===================================
Play Fruit Ninja with your bare hands!
Uses real emojis as fruits and precise blade mechanics.

Features:
- Emoji-based fruits (🍉, 🍎, 🍊, 🥝, 🍍) and bombs (💣)
- Real image slicing (fruits literally cut in half)
- Smooth blade trail with dynamic thickness
- High-speed motion slicing detection

Keys: Q = quit
"""

import cv2
import mediapipe as mp
import numpy as np
import math
import time
import random
import os
import sys
from collections import deque
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
from PIL import Image, ImageDraw, ImageFont

# ═════════════════════════════════════════════════════════════════════════════════
#  Helper: Pre-render Emojis into OpenCV Images (BGRA)
# ═════════════════════════════════════════════════════════════════════════════════

def create_emoji_image(emoji_char, size=80):
    """Renders an emoji to a transparent numpy BGRA image."""
    font_path = "C:/Windows/Fonts/seguiemj.ttf"
    if not os.path.exists(font_path):
        font_path = "arial.ttf" # Fallback, though won't have color emojis

    # Create a transparent PIL image
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype(font_path, int(size * 0.7))
    except:
        font = ImageFont.load_default()

    # Center the emoji
    # getbbox might return None if font fails, but usually works
    bbox = draw.textbbox((0, 0), emoji_char, font=font)
    if bbox:
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (size - w) / 2 - bbox[0]
        y = (size - h) / 2 - bbox[1]
    else:
        x, y = 10, 10
        
    draw.text((x, y), emoji_char, font=font, embedded_color=True, fill=(255,255,255,255))
    
    # Convert PIL to cv2 BGRA
    open_cv_image = np.array(img)
    open_cv_image = cv2.cvtColor(open_cv_image, cv2.COLOR_RGBA2BGRA)
    return open_cv_image

def rotate_image(image, angle):
    """Rotates a BGRA image."""
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    # Use borderMode transparent
    rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0,0))
    return rotated

def overlay_image(bg, fg, x, y):
    """Fast alpha blending of a BGRA fg onto a BGR bg at center (x,y)."""
    h, w = fg.shape[:2]
    
    # Top-left coordinates
    tl_x = int(x - w / 2)
    tl_y = int(y - h / 2)
    
    # Bounds checking
    if tl_x >= bg.shape[1] or tl_y >= bg.shape[0] or tl_x + w <= 0 or tl_y + h <= 0:
        return bg

    # Calculate overlaps
    x1, x2 = max(0, tl_x), min(bg.shape[1], tl_x + w)
    y1, y2 = max(0, tl_y), min(bg.shape[0], tl_y + h)
    
    fg_x1, fg_x2 = max(0, -tl_x), min(w, bg.shape[1] - tl_x)
    fg_y1, fg_y2 = max(0, -tl_y), min(h, bg.shape[0] - tl_y)

    fg_crop = fg[fg_y1:fg_y2, fg_x1:fg_x2]
    bg_crop = bg[y1:y2, x1:x2]

    alpha = fg_crop[:, :, 3] / 255.0
    
    for c in range(3):
        bg_crop[:, :, c] = (alpha * fg_crop[:, :, c] + (1 - alpha) * bg_crop[:, :, c])
        
    return bg


# ═════════════════════════════════════════════════════════════════════════════════
#  Game Entities
# ═════════════════════════════════════════════════════════════════════════════════

class Fruit:
    def __init__(self, w, h, images):
        self.radius = 40
        self.x = random.randint(150, w - 150)
        self.y = h + self.radius
        
        target_x = random.randint(w // 3, 2 * w // 3)
        self.vy = random.uniform(-28, -20)  # Upward velocity
        self.vx = (target_x - self.x) / 35.0
        
        self.gravity = 0.6
        self.angle = random.randint(0, 360)
        self.spin = random.uniform(-4, 4)
        
        # 15% chance for a bomb
        self.is_bomb = random.random() < 0.15
        
        if self.is_bomb:
            self.image = images['bomb']
        else:
            self.image = random.choice(images['fruits'])
            
    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += self.gravity
        self.angle += self.spin

    def draw(self, frame):
        rotated = rotate_image(self.image, self.angle)
        overlay_image(frame, rotated, self.x, self.y)


class HalfFruit:
    def __init__(self, x, y, vx, vy, angle, image, is_left):
        self.x = x
        self.y = y
        self.vx = vx + (-6 if is_left else 6)
        self.vy = vy - 2
        self.gravity = 0.6
        self.angle = angle
        self.spin = -8 if is_left else 8
        self.image = image

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += self.gravity
        self.angle += self.spin

    def draw(self, frame):
        rotated = rotate_image(self.image, self.angle)
        overlay_image(frame, rotated, self.x, self.y)


# ═════════════════════════════════════════════════════════════════════════════════
#  Collision Math
# ═════════════════════════════════════════════════════════════════════════════════

def segment_intersects_circle(p1, p2, cx, cy, r):
    """Check if a line segment crosses a circle (swept area collision)."""
    x1, y1 = p1
    x2, y2 = p2
    
    # Distance from center to segment
    dx = x2 - x1
    dy = y2 - y1
    length_sq = dx*dx + dy*dy
    
    if length_sq == 0:
        return math.hypot(x1 - cx, y1 - cy) <= r
        
    # Projection
    t = max(0, min(1, ((cx - x1)*dx + (cy - y1)*dy) / length_sq))
    
    # Closest point on segment
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    
    dist = math.hypot(cx - proj_x, cy - proj_y)
    return dist <= r

# ═════════════════════════════════════════════════════════════════════════════════
#  Main Game Loop
# ═════════════════════════════════════════════════════════════════════════════════

def main():
    print("[*] Initializing Game and pre-rendering graphics...")
    
    # Pre-render images
    fruit_emojis = ["🍉", "🍎", "🍊", "🥝", "🍍"]
    images = {
        'fruits': [create_emoji_image(e, 90) for e in fruit_emojis],
        'bomb': create_emoji_image("💣", 90)
    }
    
    # Pre-split images for halves
    split_images = {}
    for i, img in enumerate(images['fruits']):
        h, w = img.shape[:2]
        left = img.copy()
        left[:, w//2:] = 0
        right = img.copy()
        right[:, :w//2] = 0
        split_images[i] = (left, right)

    here = os.path.dirname(os.path.abspath(__file__))
    model = os.path.join(here, "hand_landmarker.task")
    if not os.path.exists(model):
        print("[ERROR] hand_landmarker.task not found!")
        sys.exit(1)

    landmarker = vision.HandLandmarker.create_from_options(
        vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=model),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=0.6,
            min_hand_presence_confidence=0.6,
            min_tracking_confidence=0.6,
        )
    )

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened(): cap = cv2.VideoCapture(0)
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)

    score = 0
    lives = 3
    combo = 0
    combo_timer = 0
    
    fruits = []
    halves = []
    blade_trail = deque(maxlen=12)
    
    spawn_timer = 0
    spawn_interval = 45  # frames
    
    ts_ms = 0
    game_over = False
    game_over_timer = 0
    
    flash_alpha = 0.0

    print("[*] Game Ready! Show your hand to the camera to play.")
    
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

            # --- Game Logic ---
            if not game_over:
                # 1. Spawn fruits
                spawn_timer += 1
                if spawn_timer >= spawn_interval:
                    spawn_timer = 0
                    count = random.choices([1, 2, 3], weights=[0.6, 0.3, 0.1])[0]
                    for _ in range(count):
                        fruits.append(Fruit(fw, fh, images))
                    spawn_interval = max(25, spawn_interval - 1)

                # 2. Track finger (Blade)
                current_blade = None
                if result.hand_landmarks:
                    lms = result.hand_landmarks[0]
                    # Index tip
                    idx_tip = lms[8]
                    current_blade = (int(idx_tip.x * fw), int(idx_tip.y * fh))
                    blade_trail.append(current_blade)
                else:
                    if len(blade_trail) > 0:
                        blade_trail.popleft()

                # 3. Collision Detection (Swept Area)
                sliced_this_frame = 0
                if len(blade_trail) >= 2:
                    p1 = blade_trail[-2]
                    p2 = blade_trail[-1]
                    speed = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
                    
                    # Only slice if moving fast enough (stops accidental cuts when resting finger)
                    if speed > 15:
                        alive_fruits = []
                        for f in fruits:
                            if segment_intersects_circle(p1, p2, f.x, f.y, f.radius):
                                if f.is_bomb:
                                    lives -= 1
                                    flash_alpha = 1.0  # White screen flash
                                    combo = 0
                                    if lives <= 0:
                                        game_over = True
                                        game_over_timer = 150
                                else:
                                    sliced_this_frame += 1
                                    score += 10
                                    combo_timer = 30
                                    
                                    # Create halves based on which fruit it was
                                    try:
                                        idx = [np.array_equal(f.image, im) for im in images['fruits']].index(True)
                                        left_img, right_img = split_images[idx]
                                        halves.append(HalfFruit(f.x, f.y, f.vx, f.vy, f.angle, left_img, True))
                                        halves.append(HalfFruit(f.x, f.y, f.vx, f.vy, f.angle, right_img, False))
                                    except ValueError:
                                        pass
                            else:
                                alive_fruits.append(f)
                        fruits = alive_fruits
                
                # Combo system
                if sliced_this_frame > 0:
                    combo += sliced_this_frame
                    if combo >= 3:
                        score += combo * 5  # Bonus points
                
                if combo_timer > 0:
                    combo_timer -= 1
                else:
                    combo = 0

                # 4. Update & Draw Halves (Background)
                alive_halves = []
                for h in halves:
                    h.update()
                    h.draw(frame)
                    if h.y < fh + 100:
                        alive_halves.append(h)
                halves = alive_halves

                # 5. Update & Draw Fruits (Foreground)
                alive_fruits = []
                for f in fruits:
                    f.update()
                    f.draw(frame)
                    if f.y < fh + 100:
                        alive_fruits.append(f)
                    else:
                        if not f.is_bomb and f.vy > 0:
                            lives -= 1
                            flash_alpha = 0.5  # Red flash for drop
                            combo = 0
                            if lives <= 0:
                                game_over = True
                                game_over_timer = 150
                fruits = alive_fruits

                # 6. Draw Blade Slash
                if len(blade_trail) >= 2:
                    pts = list(blade_trail)
                    # Draw a fading polygon trail
                    overlay = frame.copy()
                    for i in range(1, len(pts)):
                        dist = math.hypot(pts[i][0]-pts[i-1][0], pts[i][1]-pts[i-1][1])
                        # Thickness depends on speed and position in trail
                        alpha = i / len(pts)
                        thick = max(1, int(max(2, min(25, dist * 0.3)) * alpha))
                        
                        # Outer cyan glow
                        cv2.line(overlay, pts[i-1], pts[i], (255, 200, 50), thick + 8, cv2.LINE_AA)
                        # Inner white core
                        cv2.line(overlay, pts[i-1], pts[i], (255, 255, 255), thick, cv2.LINE_AA)
                    
                    # Blend the slash smoothly
                    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

                # Flash effect (Bombs or drops)
                if flash_alpha > 0:
                    overlay = np.full_like(frame, (255, 255, 255) if lives > 0 else (0, 0, 255))
                    cv2.addWeighted(overlay, flash_alpha, frame, 1 - flash_alpha, 0, frame)
                    flash_alpha -= 0.05

            else:
                # GAME OVER STATE
                cv2.putText(frame, "GAME OVER", (fw//2 - 200, fh//2 - 50), 
                            cv2.FONT_HERSHEY_SIMPLEX, 2.5, (0, 0, 255), 5, cv2.LINE_AA)
                cv2.putText(frame, f"FINAL SCORE: {score}", (fw//2 - 150, fh//2 + 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3, cv2.LINE_AA)
                
                game_over_timer -= 1
                if game_over_timer <= 0:
                    score = 0
                    lives = 3
                    combo = 0
                    fruits.clear()
                    halves.clear()
                    blade_trail.clear()
                    spawn_interval = 45
                    game_over = False

            # --- UI Overlay ---
            # Score
            cv2.putText(frame, f"Score: {score}", (30, 60), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 255), 3, cv2.LINE_AA)
            
            # Combo
            if combo >= 3:
                cv2.putText(frame, f"{combo}x COMBO!", (30, 110), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 150, 255), 2, cv2.LINE_AA)
            
            # Lives (Hearts)
            for i in range(3):
                color = (0, 0, 255) if i < lives else (100, 100, 100)
                cv2.putText(frame, "X", (fw - 150 + i*40, 60), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1.5, color, 4, cv2.LINE_AA)
            
            cv2.imshow("Fruit Ninja - Ultimate", frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"): break

    finally:
        cap.release()
        landmarker.close()
        cv2.destroyAllWindows()
        print("[*] Game closed.")

if __name__ == "__main__":
    main()
