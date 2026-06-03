"""
Hand Gesture Visual Effects — Iron Man + Doctor Strange
=========================================================
Cinematic visual effects for hand landmarks:
  • Palm repulsor glow (Iron Man blast charge)
  • Fingertip energy particles with trails
  • Rotating magic circle (Doctor Strange portal)
  • Electric arcs between fingers
  • HUD targeting reticle
  • Pulse shockwave on pinch
  • Finger-to-finger magic connections (both hands)
  • Falling lightning sparks (bijli) from connected fingers
  • Iron Man helmet HUD on face

Import and call `EffectsEngine.render(frame, landmarks, ...)` each frame.
"""

import cv2
import numpy as np
import math
import time
import random
from collections import deque

# ─── Colour palette ──────────────────────────────────────────────────────────────
REPULSOR_CORE   = (200, 230, 255)    # white-blue core
REPULSOR_GLOW   = (255, 180, 50)     # warm orange-gold outer
REPULSOR_RING   = (0, 180, 255)      # cyan ring
MAGIC_CYAN      = (255, 220, 0)      # bright cyan
MAGIC_GOLD      = (0, 200, 255)      # gold
ELECTRIC_BLUE   = (255, 140, 0)      # electric blue
PARTICLE_COLORS = [
    (0, 200, 255),    # gold
    (0, 180, 255),    # orange
    (200, 230, 255),  # white-blue
    (255, 220, 0),    # cyan
    (100, 255, 255),  # yellow
]
HUD_CYAN = (255, 200, 0)
HUD_DIM  = (180, 140, 0)

# Finger connection + sparks
CONNECT_GLOW    = (255, 180, 0)      # blue glow for connections
CONNECT_CORE    = (255, 240, 200)    # bright white-blue core
SPARK_COLORS    = [
    (255, 220, 50),   # bright cyan
    (255, 180, 0),    # blue
    (200, 230, 255),  # white-blue
    (0, 200, 255),    # gold spark
    (255, 255, 200),  # white
]

# Iron Man helmet
HELMET_GOLD     = (0, 180, 255)      # gold outline
HELMET_RED      = (0, 30, 180)       # dark red
HELMET_CYAN     = (255, 220, 0)      # HUD cyan
HELMET_EYE      = (255, 255, 220)    # bright eye glow
HELMET_DIM      = (0, 90, 130)       # dim gold


# ═════════════════════════════════════════════════════════════════════════════════
#  Particle System
# ═════════════════════════════════════════════════════════════════════════════════

class Particle:
    __slots__ = ('x', 'y', 'vx', 'vy', 'life', 'max_life', 'size', 'color',
                 'gravity')

    def __init__(self, x, y, vx, vy, life, size, color, gravity=15):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life
        self.max_life = life
        self.size = size
        self.color = color
        self.gravity = gravity

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += self.gravity * dt
        self.life -= dt
        return self.life > 0

    @property
    def alpha(self):
        return max(0.0, self.life / self.max_life)


class ParticleSystem:
    """Lightweight particle pool — manages spawn, update, draw."""

    def __init__(self, max_particles=200):
        self.particles = []
        self.max = max_particles

    def emit(self, x, y, count=3, speed=80, life=0.6, size=3):
        """Spawn particles at (x, y) with random velocity."""
        for _ in range(count):
            angle = random.uniform(0, 2 * math.pi)
            spd = random.uniform(speed * 0.3, speed)
            vx = math.cos(angle) * spd
            vy = math.sin(angle) * spd
            s = random.randint(max(1, size - 1), size + 1)
            c = random.choice(PARTICLE_COLORS)
            self.particles.append(Particle(x, y, vx, vy, life, s, c))

        # cap
        if len(self.particles) > self.max:
            self.particles = self.particles[-self.max:]

    def emit_directional(self, x, y, angle, spread=0.5, count=2, speed=120, life=0.5):
        """Emit particles in a specific direction (for repulsor beam)."""
        for _ in range(count):
            a = angle + random.uniform(-spread, spread)
            spd = random.uniform(speed * 0.5, speed)
            vx = math.cos(a) * spd
            vy = math.sin(a) * spd
            s = random.randint(2, 4)
            c = random.choice(PARTICLE_COLORS[:3])
            self.particles.append(Particle(x, y, vx, vy, life, s, c))

        if len(self.particles) > self.max:
            self.particles = self.particles[-self.max:]

    def emit_sparks(self, x, y, count=5, speed=40, life=0.8, size=2):
        """Emit falling lightning sparks (bijli) — heavy gravity, downward bias."""
        for _ in range(count):
            angle = random.uniform(-math.pi * 0.3, math.pi * 0.3) + math.pi / 2
            spd = random.uniform(speed * 0.2, speed)
            vx = math.cos(angle) * spd + random.uniform(-20, 20)
            vy = math.sin(angle) * spd * 0.5  # mostly downward
            s = random.randint(max(1, size - 1), size + 1)
            c = random.choice(SPARK_COLORS)
            self.particles.append(
                Particle(x, y, vx, vy,
                         random.uniform(life * 0.5, life),
                         s, c, gravity=250)  # heavy gravity = falling fast
            )

        if len(self.particles) > self.max:
            self.particles = self.particles[-self.max:]

    def update_and_draw(self, frame, dt):
        alive = []
        for p in self.particles:
            if p.update(dt):
                alive.append(p)
                a = p.alpha
                r = max(1, int(p.size * a))
                # Glow layer
                if r > 2:
                    gc = tuple(int(c * 0.4 * a) for c in p.color)
                    cv2.circle(frame, (int(p.x), int(p.y)), r + 3, gc, -1, cv2.LINE_AA)
                # Core
                c = tuple(int(c * a) for c in p.color)
                cv2.circle(frame, (int(p.x), int(p.y)), r, c, -1, cv2.LINE_AA)
        self.particles = alive


# ═════════════════════════════════════════════════════════════════════════════════
#  Trail System
# ═════════════════════════════════════════════════════════════════════════════════

class TrailSystem:
    """Stores recent positions of fingertips and draws fading trails."""

    def __init__(self, max_len=18):
        # one deque per fingertip (5 fingers)
        self.trails = [deque(maxlen=max_len) for _ in range(5)]

    def update(self, tips):
        """tips = list of 5 (x, y) tuples for each fingertip."""
        for i, (x, y) in enumerate(tips):
            self.trails[i].append((x, y, time.time()))

    def draw(self, frame):
        colors = [
            (0, 160, 255),   # thumb  - orange
            (0, 220, 100),   # index  - green
            (255, 200, 0),   # middle - cyan
            (180, 105, 255), # ring   - pink
            (100, 100, 255), # pinky  - red-ish
        ]
        now = time.time()
        for i, trail in enumerate(self.trails):
            pts = list(trail)
            if len(pts) < 2:
                continue
            for j in range(1, len(pts)):
                age = now - pts[j][2]
                alpha = max(0.0, 1.0 - age / 0.4)  # fade over 0.4s
                if alpha < 0.05:
                    continue
                thick = max(1, int(3 * alpha))
                c = tuple(int(v * alpha) for v in colors[i])
                cv2.line(frame,
                         (int(pts[j-1][0]), int(pts[j-1][1])),
                         (int(pts[j][0]), int(pts[j][1])),
                         c, thick, cv2.LINE_AA)

    def clear(self):
        for t in self.trails:
            t.clear()


# ═════════════════════════════════════════════════════════════════════════════════
#  Effects Engine — the main class
# ═════════════════════════════════════════════════════════════════════════════════

class EffectsEngine:
    """
    Call `render(frame, landmarks, fw, fh)` every frame to draw all effects.
    Landmarks = list of MediaPipe NormalizedLandmark for one hand.
    """

    def __init__(self):
        self.particles = ParticleSystem(max_particles=400)
        self.trails = TrailSystem(max_len=20)
        self._t0 = time.time()
        self._prev_time = time.time()
        self._shockwaves = []    # list of (cx, cy, start_time)
        self._prev_palm = None
        # Face detection for helmet
        self._face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        self._last_face = None        # cached face rect
        self._face_detect_skip = 0    # detect every N frames for perf
        self._portal_bursts = []      # list of (cx, cy, start_time) for finger-touch portals

    def elapsed(self):
        return time.time() - self._t0

    def trigger_shockwave(self, cx, cy):
        """Call on pinch to create an expanding ring effect."""
        self._shockwaves.append((cx, cy, time.time()))

    def render(self, frame, landmarks, fw, fh, pinching=False):
        """
        Main render call — draws all Iron Man + Magic effects.

        Args:
            frame: BGR image (modified in place)
            landmarks: list of 21 NormalizedLandmark
            fw, fh: frame width, height
            pinching: whether pinch gesture is active
        """
        now = time.time()
        dt = max(now - self._prev_time, 0.001)
        self._prev_time = now
        t = self.elapsed()

        # Convert landmarks to pixel coords
        pts = [(int(l.x * fw), int(l.y * fh)) for l in landmarks]
        tips = [pts[4], pts[8], pts[12], pts[16], pts[20]]

        # Palm center (average of wrist + MCP joints)
        palm_ids = [0, 5, 9, 13, 17]
        pcx = sum(pts[i][0] for i in palm_ids) // len(palm_ids)
        pcy = sum(pts[i][1] for i in palm_ids) // len(palm_ids)

        # Palm size (for scaling effects)
        wrist = pts[0]
        mid_mcp = pts[9]
        palm_r = int(math.hypot(wrist[0]-mid_mcp[0], wrist[1]-mid_mcp[1]) * 0.6)
        palm_r = max(30, palm_r)

        # ── 1. Magic Circle (rotating rune) ──────────────────────────
        self._draw_magic_circle(frame, pcx, pcy, palm_r, t)

        # ── 2. Palm Repulsor Glow ────────────────────────────────────
        self._draw_repulsor(frame, pcx, pcy, palm_r, t, pinching)

        # ── 3. Electric Arcs between fingertips ──────────────────────
        self._draw_electric_arcs(frame, tips, t)

        # ── 4. Fingertip Energy ──────────────────────────────────────
        for i, (tx, ty) in enumerate(tips):
            self._draw_fingertip_energy(frame, tx, ty, t, i)
            # Emit particles from fingertips
            if random.random() < 0.35:
                self.particles.emit(tx, ty, count=1, speed=50, life=0.45, size=2)

        # ── 5. Trails ────────────────────────────────────────────────
        self.trails.update(tips)
        self.trails.draw(frame)

        # ── 6. HUD Reticle ───────────────────────────────────────────
        self._draw_hud(frame, pcx, pcy, palm_r, t, pinching)

        # ── 7. Shockwave on pinch ────────────────────────────────────
        if pinching and self._prev_palm and not hasattr(self, '_was_pinching'):
            self.trigger_shockwave(pcx, pcy)
        self._was_pinching = pinching
        # Reset shockwave trigger when pinch releases
        if not pinching and hasattr(self, '_was_pinching'):
            del self._was_pinching

        self._draw_shockwaves(frame, now)

        # ── 8. Repulsor particles ────────────────────────────────────
        if pinching:
            # Burst particles from palm
            self.particles.emit(pcx, pcy, count=5, speed=100, life=0.5, size=3)

        # ── 9. Portal bursts (from finger connections) ───────────────
        self._draw_portal_bursts(frame, now)

        # ── Update particles ─────────────────────────────────────────
        self.particles.update_and_draw(frame, dt)

        self._prev_palm = (pcx, pcy)

    def reset(self):
        """Call when hand disappears."""
        self.trails.clear()
        self._prev_palm = None
        if hasattr(self, '_was_pinching'):
            del self._was_pinching

    # ── Private drawing methods ──────────────────────────────────────────

    def _draw_magic_circle(self, frame, cx, cy, r, t):
        """Rotating geometric magic circle (Doctor Strange style)."""
        r_outer = int(r * 1.8)
        r_inner = int(r * 1.2)

        # Outer rotating ring
        angle = t * 45  # degrees per second
        n_segments = 6
        for i in range(n_segments):
            a1 = math.radians(angle + i * 360 / n_segments)
            a2 = math.radians(angle + (i + 0.7) * 360 / n_segments)
            p1 = (int(cx + r_outer * math.cos(a1)), int(cy + r_outer * math.sin(a1)))
            p2 = (int(cx + r_outer * math.cos(a2)), int(cy + r_outer * math.sin(a2)))
            cv2.line(frame, p1, p2, MAGIC_CYAN, 1, cv2.LINE_AA)

        # Inner counter-rotating ring
        angle2 = -t * 60
        for i in range(8):
            a = math.radians(angle2 + i * 45)
            p1 = (int(cx + r_inner * math.cos(a)), int(cy + r_inner * math.sin(a)))
            p2 = (int(cx + (r_inner + 8) * math.cos(a)), int(cy + (r_inner + 8) * math.sin(a)))
            cv2.line(frame, p1, p2, MAGIC_GOLD, 1, cv2.LINE_AA)

        # Rotating triangle
        angle3 = t * 30
        tri_r = int(r * 1.5)
        tri_pts = []
        for i in range(3):
            a = math.radians(angle3 + i * 120)
            tri_pts.append((int(cx + tri_r * math.cos(a)), int(cy + tri_r * math.sin(a))))
        for i in range(3):
            cv2.line(frame, tri_pts[i], tri_pts[(i+1) % 3], HUD_DIM, 1, cv2.LINE_AA)

        # Pulsing outer circle
        pulse = 0.8 + 0.2 * math.sin(t * 4)
        pr = int(r_outer * pulse)
        cv2.ellipse(frame, (cx, cy), (pr, pr), 0, 0, 360, MAGIC_CYAN, 1, cv2.LINE_AA)

    def _draw_repulsor(self, frame, cx, cy, r, t, pinching):
        """Iron Man palm repulsor — pulsing glow at palm center."""
        pulse = 0.7 + 0.3 * math.sin(t * 6)
        base_r = int(r * 0.35)

        if pinching:
            # Intense blast mode
            pulse = 1.0
            base_r = int(r * 0.5)

        # Outer glow (additive look via overlay)
        overlay = frame.copy()
        glow_r = int(base_r * 2.0 * pulse)
        cv2.circle(overlay, (cx, cy), glow_r, REPULSOR_GLOW, -1, cv2.LINE_AA)
        cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)

        # Mid ring
        mid_r = int(base_r * 1.3 * pulse)
        cv2.circle(frame, (cx, cy), mid_r, REPULSOR_RING, 1, cv2.LINE_AA)

        # Inner core
        core_r = int(base_r * 0.6 * pulse)
        cv2.circle(frame, (cx, cy), core_r + 3, REPULSOR_RING, -1, cv2.LINE_AA)
        cv2.circle(frame, (cx, cy), core_r, REPULSOR_CORE, -1, cv2.LINE_AA)

    def _draw_fingertip_energy(self, frame, x, y, t, finger_idx):
        """Small pulsing energy orb at each fingertip."""
        pulse = 0.6 + 0.4 * math.sin(t * 8 + finger_idx * 1.2)
        r = int(6 * pulse)

        # Glow
        gc = tuple(int(v * 0.3 * pulse) for v in PARTICLE_COLORS[finger_idx])
        cv2.circle(frame, (x, y), r + 5, gc, -1, cv2.LINE_AA)
        # Core
        c = tuple(int(v * pulse) for v in PARTICLE_COLORS[finger_idx])
        cv2.circle(frame, (x, y), r, c, -1, cv2.LINE_AA)
        # White center
        wr = max(1, int(r * 0.4))
        cv2.circle(frame, (x, y), wr, (255, 255, 255), -1, cv2.LINE_AA)

    def _draw_electric_arcs(self, frame, tips, t):
        """Jagged electric arcs between adjacent fingertips."""
        pairs = [(0, 1), (1, 2), (2, 3), (3, 4)]  # thumb-index, index-middle, etc.
        for a, b in pairs:
            x1, y1 = tips[a]
            x2, y2 = tips[b]
            dist = math.hypot(x2-x1, y2-y1)

            if dist > 200:  # too far apart, skip
                continue

            # Generate jagged path
            segments = max(4, int(dist / 15))
            points = []
            for i in range(segments + 1):
                frac = i / segments
                mx = x1 + (x2 - x1) * frac
                my = y1 + (y2 - y1) * frac
                if 0 < i < segments:
                    # Random perpendicular offset for lightning look
                    jitter = random.uniform(-8, 8) * (1.0 - abs(frac - 0.5) * 2)
                    nx = -(y2 - y1) / max(dist, 1)
                    ny = (x2 - x1) / max(dist, 1)
                    mx += nx * jitter
                    my += ny * jitter
                points.append((int(mx), int(my)))

            # Draw the arc
            alpha = max(0.3, 0.7 - dist / 300)
            c = tuple(int(v * alpha) for v in ELECTRIC_BLUE)
            for i in range(len(points) - 1):
                cv2.line(frame, points[i], points[i+1], c, 1, cv2.LINE_AA)

    def _draw_hud(self, frame, cx, cy, r, t, pinching):
        """HUD targeting brackets around the hand."""
        # Corner brackets
        br = int(r * 2.2)
        blen = 15
        corners = [
            (cx - br, cy - br),  # top-left
            (cx + br, cy - br),  # top-right
            (cx + br, cy + br),  # bottom-right
            (cx - br, cy + br),  # bottom-left
        ]
        dirs = [(1, 1), (-1, 1), (-1, -1), (1, -1)]

        for (x, y), (dx, dy) in zip(corners, dirs):
            cv2.line(frame, (x, y), (x + blen * dx, y), HUD_CYAN, 1, cv2.LINE_AA)
            cv2.line(frame, (x, y), (x, y + blen * dy), HUD_CYAN, 1, cv2.LINE_AA)

        # Scanning line
        scan_y = cy - br + int((2 * br) * ((t * 0.5) % 1.0))
        cv2.line(frame, (cx - br, scan_y), (cx + br, scan_y), HUD_DIM, 1, cv2.LINE_AA)

        # Status text
        status = "LOCKED" if pinching else "TRACKING"
        sc = (0, 0, 255) if pinching else HUD_CYAN
        cv2.putText(frame, status, (cx - br, cy - br - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, sc, 1, cv2.LINE_AA)

        # Coordinates
        cv2.putText(frame, f"X:{cx} Y:{cy}", (cx - br, cy + br + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.32, HUD_DIM, 1, cv2.LINE_AA)

    def _draw_shockwaves(self, frame, now):
        """Expanding ring shockwave on pinch."""
        alive = []
        for cx, cy, start in self._shockwaves:
            age = now - start
            if age > 0.6:
                continue
            alive.append((cx, cy, start))

            progress = age / 0.6
            radius = int(30 + 150 * progress)
            alpha = 1.0 - progress
            thick = max(1, int(3 * alpha))

            c = tuple(int(v * alpha) for v in REPULSOR_RING)
            cv2.circle(frame, (cx, cy), radius, c, thick, cv2.LINE_AA)

            # Second ring (delayed)
            if age > 0.1:
                p2 = (age - 0.1) / 0.5
                r2 = int(20 + 120 * p2)
                a2 = max(0, 1.0 - p2)
                c2 = tuple(int(v * a2 * 0.6) for v in MAGIC_GOLD)
                cv2.circle(frame, (cx, cy), r2, c2, max(1, int(2 * a2)), cv2.LINE_AA)

        self._shockwaves = alive

    def _draw_portal_bursts(self, frame, now):
        """Doctor Strange expanding portal rings from finger-touch points."""
        alive = []
        for cx, cy, start in self._portal_bursts:
            age = now - start
            if age > 1.0:
                continue
            alive.append((cx, cy, start))

            progress = age / 1.0
            alpha = 1.0 - progress

            # Outer golden ring
            r1 = int(15 + 80 * progress)
            c1 = tuple(int(v * alpha) for v in MAGIC_GOLD)
            cv2.circle(frame, (cx, cy), r1, c1, max(1, int(2 * alpha)), cv2.LINE_AA)

            # Inner cyan ring (delayed)
            if age > 0.05:
                p2 = (age - 0.05) / 0.95
                r2 = int(10 + 60 * p2)
                a2 = max(0, 1.0 - p2)
                c2 = tuple(int(v * a2) for v in MAGIC_CYAN)
                cv2.circle(frame, (cx, cy), r2, c2, max(1, int(2 * a2)), cv2.LINE_AA)

            # Rotating arc segments
            n_arcs = 4
            for i in range(n_arcs):
                a_start = int((now * 200 + i * 90) % 360)
                r3 = int(10 + 100 * progress)
                c3 = tuple(int(v * alpha * 0.5) for v in MAGIC_CYAN)
                cv2.ellipse(frame, (cx, cy), (r3, r3),
                            0, a_start, a_start + 40, c3,
                            max(1, int(2 * alpha)), cv2.LINE_AA)

        self._portal_bursts = alive

    # ── Finger-to-Finger Connections (Both Hands) ────────────────────────

    def render_finger_connections(self, frame, lms1, lms2, fw, fh):
        """
        Draw magic connections between matching fingertips of two hands.
        When fingers touch → lightning sparks rain down + portal burst.
        lms1, lms2 = landmark lists for hand 1 and hand 2.
        """
        t = self.elapsed()
        tip_ids = [4, 8, 12, 16, 20]   # thumb, index, middle, ring, pinky

        tips1 = [(int(lms1[i].x * fw), int(lms1[i].y * fh)) for i in tip_ids]
        tips2 = [(int(lms2[i].x * fw), int(lms2[i].y * fh)) for i in tip_ids]

        finger_names = ["Thumb", "Index", "Middle", "Ring", "Pinky"]
        connect_threshold = 80   # pixels — fingers "close" enough
        touch_threshold   = 35   # pixels — fingers actually touching

        any_connected = False

        for i in range(5):
            x1, y1 = tips1[i]
            x2, y2 = tips2[i]
            dist = math.hypot(x2 - x1, y2 - y1)

            if dist > connect_threshold:
                continue

            any_connected = True
            # Midpoint
            mx, my = (x1 + x2) // 2, (y1 + y2) // 2

            # ── Proximity factor (1.0 = touching, 0.0 = at threshold) ──
            prox = max(0.0, 1.0 - dist / connect_threshold)
            touching = dist < touch_threshold

            # ── 1. Glowing connection line ──
            pulse = 0.6 + 0.4 * math.sin(t * 8 + i * 1.5)
            line_alpha = prox * pulse

            # Outer glow
            glow_thick = max(1, int(14 * line_alpha))
            gc = tuple(int(v * line_alpha * 0.3) for v in CONNECT_GLOW)
            cv2.line(frame, (x1, y1), (x2, y2), gc, glow_thick, cv2.LINE_AA)

            # Core line
            core_thick = max(1, int(3 * line_alpha))
            cc = tuple(int(v * line_alpha) for v in CONNECT_CORE)
            cv2.line(frame, (x1, y1), (x2, y2), cc, core_thick, cv2.LINE_AA)

            # ── 2. Lightning arc along connection ──
            if dist > 5:
                ndx = (x2 - x1) / dist
                ndy = (y2 - y1) / dist
                for arc in range(2):
                    segs = max(5, int(dist / 8))
                    points = []
                    for s in range(segs + 1):
                        frac = s / segs
                        px = x1 + (x2 - x1) * frac
                        py = y1 + (y2 - y1) * frac
                        if 0 < s < segs:
                            jit = random.uniform(-10, 10) * math.sin(frac * math.pi) * prox
                            px += -ndy * jit
                            py += ndx * jit
                        points.append((int(px), int(py)))

                    arc_alpha = 0.3 + 0.7 * math.sin(t * 15 + arc * 3 + i)
                    ac = tuple(int(v * arc_alpha * prox) for v in ELECTRIC_BLUE)
                    for j in range(len(points) - 1):
                        cv2.line(frame, points[j], points[j+1], ac, 1, cv2.LINE_AA)

            # ── 3. Connection midpoint orb ──
            orb_r = int(8 * prox * pulse)
            if orb_r > 1:
                cv2.circle(frame, (mx, my), orb_r + 4,
                           (180, 140, 0), -1, cv2.LINE_AA)
                cv2.circle(frame, (mx, my), orb_r,
                           CONNECT_CORE, -1, cv2.LINE_AA)
                cv2.circle(frame, (mx, my), max(1, orb_r // 2),
                           (255, 255, 255), -1, cv2.LINE_AA)

            # ── 4. TOUCHING → bijli / falling sparks! ──
            if touching:
                # Emit falling lightning sparks from the touch point
                self.particles.emit_sparks(
                    mx, my, count=4, speed=60, life=0.7, size=3
                )

                # Extra bright flash at touch point
                flash_r = int(16 * pulse)
                cv2.circle(frame, (mx, my), flash_r + 8,
                           (200, 160, 0), -1, cv2.LINE_AA)
                cv2.circle(frame, (mx, my), flash_r,
                           (255, 240, 180), -1, cv2.LINE_AA)
                cv2.circle(frame, (mx, my), int(flash_r * 0.3),
                           (255, 255, 255), -1, cv2.LINE_AA)

                # Mini portal burst (Doctor Strange style)
                if random.random() < 0.08:
                    self._portal_bursts.append((mx, my, time.time()))

                # Finger label
                cv2.putText(frame, finger_names[i],
                            (mx - 20, my - 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                            (255, 255, 255), 1, cv2.LINE_AA)

            # ── 5. Endpoint sparks on each fingertip ──
            if prox > 0.5:
                for (fx, fy) in [(x1, y1), (x2, y2)]:
                    er = int(6 * prox * pulse)
                    cv2.circle(frame, (fx, fy), er + 3,
                               CONNECT_GLOW, -1, cv2.LINE_AA)
                    cv2.circle(frame, (fx, fy), er,
                               (255, 255, 255), -1, cv2.LINE_AA)

        # ── 6. Grand portal when 3+ fingers touching ──
        touching_count = sum(
            1 for i in range(5)
            if math.hypot(tips2[i][0]-tips1[i][0], tips2[i][1]-tips1[i][1]) < touch_threshold
        )
        if touching_count >= 3:
            # Big Doctor Strange portal between the hands
            all_tips = tips1 + tips2
            portal_cx = sum(p[0] for p in all_tips) // len(all_tips)
            portal_cy = sum(p[1] for p in all_tips) // len(all_tips)
            self._draw_strange_portal(frame, portal_cx, portal_cy, t, touching_count)

    def _draw_strange_portal(self, frame, cx, cy, t, n_fingers):
        """Big rotating Doctor Strange portal when multiple fingers touch."""
        base_r = 40 + n_fingers * 15
        pulse = 0.8 + 0.2 * math.sin(t * 3)

        # Multiple rotating ring segments
        for ring in range(3):
            r = int((base_r + ring * 20) * pulse)
            angle_off = t * (60 + ring * 30) * (1 if ring % 2 == 0 else -1)
            n_arcs = 5 + ring
            arc_len = 360 // n_arcs - 10

            for i in range(n_arcs):
                a_start = int(angle_off + i * (360 // n_arcs)) % 360
                alpha = 0.5 + 0.5 * math.sin(t * 5 + ring + i)
                c = tuple(int(v * alpha) for v in MAGIC_CYAN)
                cv2.ellipse(frame, (cx, cy), (r, r),
                            0, a_start, a_start + arc_len,
                            c, max(1, int(2 * alpha)), cv2.LINE_AA)

        # Inner golden mandala
        r_inner = int(base_r * 0.6 * pulse)
        for i in range(6):
            a = math.radians(t * 40 + i * 60)
            p1 = (int(cx + r_inner * math.cos(a)),
                  int(cy + r_inner * math.sin(a)))
            a2 = math.radians(t * 40 + (i + 2) * 60)
            p2 = (int(cx + r_inner * math.cos(a2)),
                  int(cy + r_inner * math.sin(a2)))
            cv2.line(frame, p1, p2, MAGIC_GOLD, 1, cv2.LINE_AA)

        # Center glow
        cv2.circle(frame, (cx, cy), int(15 * pulse),
                   (200, 180, 50), -1, cv2.LINE_AA)
        cv2.circle(frame, (cx, cy), int(8 * pulse),
                   (255, 255, 200), -1, cv2.LINE_AA)

        # Emit sparks falling from the portal
        if random.random() < 0.6:
            sx = cx + random.randint(-base_r, base_r)
            sy = cy + random.randint(-10, 10)
            self.particles.emit_sparks(sx, sy, count=2, speed=50, life=0.9, size=2)

    # ── Iron Man Helmet HUD on Face ──────────────────────────────────────

    def render_helmet(self, frame, fw, fh):
        """
        Detect face and draw Iron Man helmet HUD overlay.
        Uses Haar cascade (built into OpenCV, no extra model needed).
        """
        t = self.elapsed()

        # Detect face (skip frames for performance)
        self._face_detect_skip += 1
        if self._face_detect_skip >= 3 or self._last_face is None:
            self._face_detect_skip = 0
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self._face_cascade.detectMultiScale(
                gray, scaleFactor=1.15, minNeighbors=5,
                minSize=(80, 80),
                flags=cv2.CASCADE_SCALE_IMAGE
            )
            if len(faces) > 0:
                # Pick largest face
                areas = [w * h for (x, y, w, h) in faces]
                best = int(np.argmax(areas))
                self._last_face = tuple(int(v) for v in faces[best])
            else:
                self._last_face = None

        if self._last_face is None:
            return

        fx, fy, fw_face, fh_face = self._last_face
        cx = fx + fw_face // 2
        cy = fy + fh_face // 2
        hw = fw_face // 2    # half width
        hh = fh_face // 2    # half height

        pulse = 0.8 + 0.2 * math.sin(t * 3)

        # ── 1. Outer helmet contour ──
        # Forehead arc
        cv2.ellipse(frame, (cx, fy + int(hh * 0.15)),
                    (int(hw * 1.15), int(hh * 0.55)),
                    0, 200, 340, HELMET_GOLD, 2, cv2.LINE_AA)

        # Side panels (left)
        pts_l = np.array([
            [fx - int(hw * 0.1), cy - int(hh * 0.3)],
            [fx - int(hw * 0.15), cy + int(hh * 0.2)],
            [fx + int(hw * 0.15), cy + int(hh * 0.6)],
            [fx + int(hw * 0.3), cy - int(hh * 0.1)],
        ], dtype=np.int32)
        cv2.polylines(frame, [pts_l], False, HELMET_GOLD, 1, cv2.LINE_AA)

        # Side panels (right)
        pts_r = np.array([
            [fx + fw_face + int(hw * 0.1), cy - int(hh * 0.3)],
            [fx + fw_face + int(hw * 0.15), cy + int(hh * 0.2)],
            [fx + fw_face - int(hw * 0.15), cy + int(hh * 0.6)],
            [fx + fw_face - int(hw * 0.3), cy - int(hh * 0.1)],
        ], dtype=np.int32)
        cv2.polylines(frame, [pts_r], False, HELMET_GOLD, 1, cv2.LINE_AA)

        # Chin piece
        chin_y = fy + fh_face
        cv2.line(frame,
                 (cx - int(hw * 0.5), chin_y),
                 (cx, chin_y + int(hh * 0.35)),
                 HELMET_GOLD, 2, cv2.LINE_AA)
        cv2.line(frame,
                 (cx + int(hw * 0.5), chin_y),
                 (cx, chin_y + int(hh * 0.35)),
                 HELMET_GOLD, 2, cv2.LINE_AA)

        # ── 2. Eye visors (glowing slits) ──
        eye_y = cy - int(hh * 0.05)
        eye_w = int(hw * 0.45)
        eye_h = int(hh * 0.18)
        eye_spacing = int(hw * 0.25)

        for side in [-1, 1]:  # left, right
            ex = cx + side * eye_spacing
            # Visor shape (trapezoid)
            eye_pts = np.array([
                [ex - eye_w, eye_y - eye_h // 3],
                [ex + eye_w * side, eye_y - eye_h],
                [ex + eye_w * side, eye_y + eye_h // 2],
                [ex - eye_w // 2, eye_y + eye_h // 2],
            ], dtype=np.int32)

            # Glow fill
            overlay = frame.copy()
            cv2.fillPoly(overlay, [eye_pts], HELMET_EYE)
            cv2.addWeighted(overlay, 0.25 * pulse, frame, 1.0 - 0.25 * pulse, 0, frame)

            # Outline
            cv2.polylines(frame, [eye_pts], True, HELMET_CYAN, 1, cv2.LINE_AA)

        # ── 3. Forehead arc reactor / emblem ──
        emblem_y = fy + int(hh * 0.25)
        emblem_r = int(hw * 0.15 * pulse)
        cv2.circle(frame, (cx, emblem_y), emblem_r + 3,
                   HELMET_DIM, 1, cv2.LINE_AA)
        cv2.circle(frame, (cx, emblem_y), emblem_r,
                   HELMET_CYAN, -1, cv2.LINE_AA)
        cv2.circle(frame, (cx, emblem_y), max(1, emblem_r // 2),
                   (255, 255, 255), -1, cv2.LINE_AA)

        # ── 4. Nose / mouth plate lines ──
        nose_top = cy + int(hh * 0.15)
        nose_bot = fy + fh_face - int(hh * 0.1)

        # Center line
        cv2.line(frame, (cx, nose_top), (cx, nose_bot),
                 HELMET_DIM, 1, cv2.LINE_AA)

        # Mouth vent lines
        vent_y = cy + int(hh * 0.45)
        for i in range(3):
            vy = vent_y + i * int(hh * 0.12)
            vw = int(hw * (0.5 - i * 0.1))
            cv2.line(frame, (cx - vw, vy), (cx + vw, vy),
                     HELMET_DIM, 1, cv2.LINE_AA)

        # ── 5. HUD data overlay ──
        # Targeting brackets
        br_size = 12
        for (bx, by) in [(fx, fy), (fx + fw_face, fy),
                          (fx, fy + fh_face), (fx + fw_face, fy + fh_face)]:
            dx = 1 if bx <= cx else -1
            dy = 1 if by <= cy else -1
            cv2.line(frame, (bx, by), (bx + br_size * dx, by),
                     HELMET_CYAN, 1, cv2.LINE_AA)
            cv2.line(frame, (bx, by), (bx, by + br_size * dy),
                     HELMET_CYAN, 1, cv2.LINE_AA)

        # HUD text
        cv2.putText(frame, "STARK INDUSTRIES",
                    (fx, fy - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, HELMET_CYAN, 1, cv2.LINE_AA)

        cv2.putText(frame, f"POWER: {int(pulse * 100)}%",
                    (fx + fw_face + 8, cy - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.30, HELMET_DIM, 1, cv2.LINE_AA)

        cv2.putText(frame, f"SYS: ONLINE",
                    (fx + fw_face + 8, cy + 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.30, HELMET_DIM, 1, cv2.LINE_AA)

        # Scanning line across face
        scan_y = fy + int(fh_face * ((t * 0.4) % 1.0))
        scan_alpha = 0.3
        sc = tuple(int(v * scan_alpha) for v in HELMET_CYAN)
        cv2.line(frame, (fx, scan_y), (fx + fw_face, scan_y),
                 sc, 1, cv2.LINE_AA)
