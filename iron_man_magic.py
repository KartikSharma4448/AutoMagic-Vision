"""
Iron Man + Doctor Strange — Magic Hand Effects
================================================
All-in-one standalone visual effects demo.
No mouse control — pure cinematic eye candy.

Show one hand  → repulsor glow, magic circle, electric arcs, particles
Show both hands → finger-to-finger connections, falling sparks, portals
Face detected  → Iron Man helmet HUD overlay

Keys:  E = toggle effects  |  Q = quit
"""

import cv2
import mediapipe as mp
import numpy as np
import math
import time
import random
import os, sys
from collections import deque
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

# ═════════════════════════════════════════════════════════════════════════════════
#  Constants
# ═════════════════════════════════════════════════════════════════════════════════

TIP = [4, 8, 12, 16, 20]
PIP = [3, 6, 10, 14, 18]
SKELETON = [
    (0,1),(1,2),(2,3),(3,4),  (0,5),(5,6),(6,7),(7,8),
    (0,9),(9,10),(10,11),(11,12), (0,13),(13,14),(14,15),(15,16),
    (0,17),(17,18),(18,19),(19,20), (5,9),(9,13),(13,17),
]

# Colours (BGR)
C_BG     = (30, 30, 30)
C_WHITE  = (255, 255, 255)
C_GRAY   = (160, 160, 160)
C_GREEN  = (0, 220, 100)
C_RED    = (50, 50, 255)
C_CYAN   = (220, 200, 0)
C_BONE   = (160, 220, 160)
C_WRIST  = (255, 150, 50)
FTIP_C   = [(0,160,255),(0,220,100),(220,200,0),(180,105,255),(50,50,255)]

# Effects palette
REPULSOR_CORE = (200, 230, 255)
REPULSOR_GLOW = (255, 180, 50)
REPULSOR_RING = (0, 180, 255)
MAGIC_CYAN    = (255, 220, 0)
MAGIC_GOLD    = (0, 200, 255)
ELECTRIC_BLUE = (255, 140, 0)
PARTICLE_COLORS = [
    (0, 200, 255), (0, 180, 255), (200, 230, 255),
    (255, 220, 0), (100, 255, 255),
]
HUD_CYAN = (255, 200, 0)
HUD_DIM  = (180, 140, 0)

# Finger connections
CONNECT_GLOW = (255, 180, 0)
CONNECT_CORE = (255, 240, 200)
SPARK_COLORS = [
    (255, 220, 50), (255, 180, 0), (200, 230, 255),
    (0, 200, 255), (255, 255, 200),
]

# Helmet
HELMET_GOLD = (0, 180, 255)
HELMET_RED  = (0, 30, 180)
HELMET_CYAN = (255, 220, 0)
HELMET_EYE  = (255, 255, 220)
HELMET_DIM  = (0, 90, 130)


# ═════════════════════════════════════════════════════════════════════════════════
#  Particle System
# ═════════════════════════════════════════════════════════════════════════════════

class Particle:
    __slots__ = ('x','y','vx','vy','life','max_life','size','color','gravity')

    def __init__(self, x, y, vx, vy, life, size, color, gravity=15):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.life = self.max_life = life
        self.size, self.color, self.gravity = size, color, gravity

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
    def __init__(self, cap=400):
        self.particles = []
        self.cap = cap

    def emit(self, x, y, count=3, speed=80, life=0.6, size=3):
        for _ in range(count):
            a = random.uniform(0, 2 * math.pi)
            s = random.uniform(speed * 0.3, speed)
            self.particles.append(Particle(
                x, y, math.cos(a)*s, math.sin(a)*s, life,
                random.randint(max(1,size-1), size+1),
                random.choice(PARTICLE_COLORS)))
        if len(self.particles) > self.cap:
            self.particles = self.particles[-self.cap:]

    def emit_sparks(self, x, y, count=5, speed=40, life=0.8, size=2):
        for _ in range(count):
            a = random.uniform(-math.pi*0.3, math.pi*0.3) + math.pi/2
            s = random.uniform(speed*0.2, speed)
            self.particles.append(Particle(
                x, y, math.cos(a)*s + random.uniform(-20,20),
                math.sin(a)*s*0.5,
                random.uniform(life*0.5, life),
                random.randint(max(1,size-1), size+1),
                random.choice(SPARK_COLORS), gravity=250))
        if len(self.particles) > self.cap:
            self.particles = self.particles[-self.cap:]

    def update_and_draw(self, frame, dt):
        alive = []
        for p in self.particles:
            if p.update(dt):
                alive.append(p)
                a = p.alpha
                r = max(1, int(p.size * a))
                px, py = int(p.x), int(p.y)
                if r > 2:
                    gc = tuple(int(c * 0.4 * a) for c in p.color)
                    cv2.circle(frame, (px, py), r+3, gc, -1, cv2.LINE_AA)
                c = tuple(int(c * a) for c in p.color)
                cv2.circle(frame, (px, py), r, c, -1, cv2.LINE_AA)
        self.particles = alive


# ═════════════════════════════════════════════════════════════════════════════════
#  Trail System
# ═════════════════════════════════════════════════════════════════════════════════

class TrailSystem:
    def __init__(self, max_len=20):
        self.trails = [deque(maxlen=max_len) for _ in range(5)]

    def update(self, tips):
        for i, (x, y) in enumerate(tips):
            self.trails[i].append((x, y, time.time()))

    def draw(self, frame):
        colors = [(0,160,255),(0,220,100),(255,200,0),(180,105,255),(100,100,255)]
        now = time.time()
        for i, trail in enumerate(self.trails):
            pts = list(trail)
            for j in range(1, len(pts)):
                a = max(0.0, 1.0 - (now - pts[j][2]) / 0.4)
                if a < 0.05: continue
                c = tuple(int(v*a) for v in colors[i])
                cv2.line(frame, (int(pts[j-1][0]),int(pts[j-1][1])),
                         (int(pts[j][0]),int(pts[j][1])), c, max(1,int(3*a)), cv2.LINE_AA)

    def clear(self):
        for t in self.trails: t.clear()


# ═════════════════════════════════════════════════════════════════════════════════
#  Drawing helpers
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


# ═════════════════════════════════════════════════════════════════════════════════
#  Effects Engine
# ═════════════════════════════════════════════════════════════════════════════════

class EffectsEngine:
    def __init__(self):
        self.particles = ParticleSystem(400)
        self.trails = TrailSystem(20)
        self._t0 = time.time()
        self._prev_time = time.time()
        self._shockwaves = []
        self._portal_bursts = []
        self._prev_palm = None
        self._face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self._last_face = None
        self._face_skip = 0

    def elapsed(self):
        return time.time() - self._t0

    def trigger_shockwave(self, cx, cy):
        self._shockwaves.append((cx, cy, time.time()))

    # ── Main single-hand render ──────────────────────────────────────────

    def render(self, frame, landmarks, fw, fh):
        now = time.time()
        dt = max(now - self._prev_time, 0.001)
        self._prev_time = now
        t = self.elapsed()

        pts = [(int(l.x*fw), int(l.y*fh)) for l in landmarks]
        tips = [pts[4], pts[8], pts[12], pts[16], pts[20]]
        palm_ids = [0,5,9,13,17]
        pcx = sum(pts[i][0] for i in palm_ids) // 5
        pcy = sum(pts[i][1] for i in palm_ids) // 5
        wrist, mid = pts[0], pts[9]
        palm_r = max(30, int(math.hypot(wrist[0]-mid[0], wrist[1]-mid[1]) * 0.6))

        # 1. Magic circle
        self._magic_circle(frame, pcx, pcy, palm_r, t)
        # 2. Repulsor glow
        self._repulsor(frame, pcx, pcy, palm_r, t)
        # 3. Electric arcs
        self._electric_arcs(frame, tips, t)
        # 4. Fingertip energy
        for i, (tx, ty) in enumerate(tips):
            self._fingertip_energy(frame, tx, ty, t, i)
            if random.random() < 0.35:
                self.particles.emit(tx, ty, count=1, speed=50, life=0.45, size=2)
        # 5. Trails
        self.trails.update(tips)
        self.trails.draw(frame)
        # 6. HUD
        self._hud(frame, pcx, pcy, palm_r, t)
        # 7. Shockwaves
        self._draw_shockwaves(frame, now)
        # 8. Portal bursts
        self._draw_portal_bursts(frame, now)
        # 9. Update particles
        self.particles.update_and_draw(frame, dt)

        self._prev_palm = (pcx, pcy)

    def reset(self):
        self.trails.clear()
        self._prev_palm = None

    # ── Private effects ──────────────────────────────────────────────────

    def _magic_circle(self, frame, cx, cy, r, t):
        r_o, r_i = int(r*1.8), int(r*1.2)
        ang = t * 45
        for i in range(6):
            a1 = math.radians(ang + i*60)
            a2 = math.radians(ang + (i+0.7)*60)
            p1 = (int(cx+r_o*math.cos(a1)), int(cy+r_o*math.sin(a1)))
            p2 = (int(cx+r_o*math.cos(a2)), int(cy+r_o*math.sin(a2)))
            cv2.line(frame, p1, p2, MAGIC_CYAN, 1, cv2.LINE_AA)
        ang2 = -t * 60
        for i in range(8):
            a = math.radians(ang2 + i*45)
            p1 = (int(cx+r_i*math.cos(a)), int(cy+r_i*math.sin(a)))
            p2 = (int(cx+(r_i+8)*math.cos(a)), int(cy+(r_i+8)*math.sin(a)))
            cv2.line(frame, p1, p2, MAGIC_GOLD, 1, cv2.LINE_AA)
        tri_r = int(r*1.5)
        tri = [(int(cx+tri_r*math.cos(math.radians(t*30+i*120))),
                int(cy+tri_r*math.sin(math.radians(t*30+i*120)))) for i in range(3)]
        for i in range(3):
            cv2.line(frame, tri[i], tri[(i+1)%3], HUD_DIM, 1, cv2.LINE_AA)
        pulse = 0.8 + 0.2*math.sin(t*4)
        pr = int(r_o * pulse)
        cv2.ellipse(frame, (cx,cy), (pr,pr), 0, 0, 360, MAGIC_CYAN, 1, cv2.LINE_AA)

    def _repulsor(self, frame, cx, cy, r, t):
        pulse = 0.7 + 0.3*math.sin(t*6)
        base = int(r*0.35)
        overlay = frame.copy()
        cv2.circle(overlay, (cx,cy), int(base*2*pulse), REPULSOR_GLOW, -1, cv2.LINE_AA)
        cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)
        cv2.circle(frame, (cx,cy), int(base*1.3*pulse), REPULSOR_RING, 1, cv2.LINE_AA)
        core = int(base*0.6*pulse)
        cv2.circle(frame, (cx,cy), core+3, REPULSOR_RING, -1, cv2.LINE_AA)
        cv2.circle(frame, (cx,cy), core, REPULSOR_CORE, -1, cv2.LINE_AA)

    def _fingertip_energy(self, frame, x, y, t, idx):
        pulse = 0.6 + 0.4*math.sin(t*8 + idx*1.2)
        r = int(6*pulse)
        gc = tuple(int(v*0.3*pulse) for v in PARTICLE_COLORS[idx])
        cv2.circle(frame, (x,y), r+5, gc, -1, cv2.LINE_AA)
        c = tuple(int(v*pulse) for v in PARTICLE_COLORS[idx])
        cv2.circle(frame, (x,y), r, c, -1, cv2.LINE_AA)
        cv2.circle(frame, (x,y), max(1,int(r*0.4)), C_WHITE, -1, cv2.LINE_AA)

    def _electric_arcs(self, frame, tips, t):
        for a, b in [(0,1),(1,2),(2,3),(3,4)]:
            x1,y1 = tips[a]; x2,y2 = tips[b]
            d = math.hypot(x2-x1, y2-y1)
            if d > 200: continue
            segs = max(4, int(d/15))
            pts = []
            for i in range(segs+1):
                f = i/segs
                mx, my = x1+(x2-x1)*f, y1+(y2-y1)*f
                if 0 < i < segs:
                    j = random.uniform(-8,8)*(1-abs(f-0.5)*2)
                    mx += -(y2-y1)/max(d,1)*j
                    my += (x2-x1)/max(d,1)*j
                pts.append((int(mx), int(my)))
            al = max(0.3, 0.7-d/300)
            c = tuple(int(v*al) for v in ELECTRIC_BLUE)
            for i in range(len(pts)-1):
                cv2.line(frame, pts[i], pts[i+1], c, 1, cv2.LINE_AA)

    def _hud(self, frame, cx, cy, r, t):
        br, blen = int(r*2.2), 15
        corners = [(cx-br,cy-br),(cx+br,cy-br),(cx+br,cy+br),(cx-br,cy+br)]
        dirs = [(1,1),(-1,1),(-1,-1),(1,-1)]
        for (x,y),(dx,dy) in zip(corners, dirs):
            cv2.line(frame, (x,y), (x+blen*dx,y), HUD_CYAN, 1, cv2.LINE_AA)
            cv2.line(frame, (x,y), (x,y+blen*dy), HUD_CYAN, 1, cv2.LINE_AA)
        sy = cy-br + int(2*br*((t*0.5)%1.0))
        cv2.line(frame, (cx-br,sy), (cx+br,sy), HUD_DIM, 1, cv2.LINE_AA)
        cv2.putText(frame, "TRACKING", (cx-br,cy-br-8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, HUD_CYAN, 1, cv2.LINE_AA)

    def _draw_shockwaves(self, frame, now):
        alive = []
        for cx, cy, start in self._shockwaves:
            age = now - start
            if age > 0.6: continue
            alive.append((cx,cy,start))
            p = age/0.6; a = 1-p
            c = tuple(int(v*a) for v in REPULSOR_RING)
            cv2.circle(frame, (cx,cy), int(30+150*p), c, max(1,int(3*a)), cv2.LINE_AA)
            if age > 0.1:
                p2 = (age-0.1)/0.5; a2 = max(0,1-p2)
                c2 = tuple(int(v*a2*0.6) for v in MAGIC_GOLD)
                cv2.circle(frame, (cx,cy), int(20+120*p2), c2, max(1,int(2*a2)), cv2.LINE_AA)
        self._shockwaves = alive

    def _draw_portal_bursts(self, frame, now):
        alive = []
        for cx, cy, start in self._portal_bursts:
            age = now - start
            if age > 1.0: continue
            alive.append((cx,cy,start))
            p = age/1.0; a = 1-p
            c1 = tuple(int(v*a) for v in MAGIC_GOLD)
            cv2.circle(frame, (cx,cy), int(15+80*p), c1, max(1,int(2*a)), cv2.LINE_AA)
            if age > 0.05:
                p2 = (age-0.05)/0.95; a2 = max(0,1-p2)
                c2 = tuple(int(v*a2) for v in MAGIC_CYAN)
                cv2.circle(frame, (cx,cy), int(10+60*p2), c2, max(1,int(2*a2)), cv2.LINE_AA)
            for i in range(4):
                sa = int((now*200+i*90)%360)
                r3 = int(10+100*p)
                c3 = tuple(int(v*a*0.5) for v in MAGIC_CYAN)
                cv2.ellipse(frame, (cx,cy), (r3,r3), 0, sa, sa+40, c3, max(1,int(2*a)), cv2.LINE_AA)
        self._portal_bursts = alive

    # ── Finger-to-finger connections ─────────────────────────────────────

    def render_finger_connections(self, frame, lms1, lms2, fw, fh):
        t = self.elapsed()
        tip_ids = [4, 8, 12, 16, 20]
        names = ["Thumb","Index","Middle","Ring","Pinky"]
        tips1 = [(int(lms1[i].x*fw), int(lms1[i].y*fh)) for i in tip_ids]
        tips2 = [(int(lms2[i].x*fw), int(lms2[i].y*fh)) for i in tip_ids]

        touch_thr, conn_thr = 35, 80
        touching_count = 0

        for i in range(5):
            x1,y1 = tips1[i]; x2,y2 = tips2[i]
            d = math.hypot(x2-x1, y2-y1)
            if d > conn_thr: continue

            prox = max(0, 1-d/conn_thr)
            touching = d < touch_thr
            if touching: touching_count += 1
            pulse = 0.6 + 0.4*math.sin(t*8+i*1.5)
            la = prox * pulse
            mx, my = (x1+x2)//2, (y1+y2)//2

            # Glow line
            gc = tuple(int(v*la*0.3) for v in CONNECT_GLOW)
            cv2.line(frame, (x1,y1), (x2,y2), gc, max(1,int(14*la)), cv2.LINE_AA)
            cc = tuple(int(v*la) for v in CONNECT_CORE)
            cv2.line(frame, (x1,y1), (x2,y2), cc, max(1,int(3*la)), cv2.LINE_AA)

            # Lightning arcs
            if d > 5:
                ndx, ndy = (x2-x1)/d, (y2-y1)/d
                for arc in range(2):
                    segs = max(5, int(d/8))
                    pts = []
                    for s in range(segs+1):
                        f = s/segs
                        px, py = x1+(x2-x1)*f, y1+(y2-y1)*f
                        if 0 < s < segs:
                            j = random.uniform(-10,10)*math.sin(f*math.pi)*prox
                            px += -ndy*j; py += ndx*j
                        pts.append((int(px), int(py)))
                    aa = 0.3+0.7*math.sin(t*15+arc*3+i)
                    ac = tuple(int(v*aa*prox) for v in ELECTRIC_BLUE)
                    for j in range(len(pts)-1):
                        cv2.line(frame, pts[j], pts[j+1], ac, 1, cv2.LINE_AA)

            # Midpoint orb
            orb_r = int(8*prox*pulse)
            if orb_r > 1:
                cv2.circle(frame, (mx,my), orb_r+4, (180,140,0), -1, cv2.LINE_AA)
                cv2.circle(frame, (mx,my), orb_r, CONNECT_CORE, -1, cv2.LINE_AA)
                cv2.circle(frame, (mx,my), max(1,orb_r//2), C_WHITE, -1, cv2.LINE_AA)

            # Touching → sparks!
            if touching:
                self.particles.emit_sparks(mx, my, count=4, speed=60, life=0.7, size=3)
                fr = int(16*pulse)
                cv2.circle(frame, (mx,my), fr+8, (200,160,0), -1, cv2.LINE_AA)
                cv2.circle(frame, (mx,my), fr, (255,240,180), -1, cv2.LINE_AA)
                cv2.circle(frame, (mx,my), int(fr*0.3), C_WHITE, -1, cv2.LINE_AA)
                if random.random() < 0.08:
                    self._portal_bursts.append((mx, my, time.time()))
                cv2.putText(frame, names[i], (mx-20,my-20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, C_WHITE, 1, cv2.LINE_AA)

            # Endpoint sparks
            if prox > 0.5:
                for fx2,fy2 in [(x1,y1),(x2,y2)]:
                    er = int(6*prox*pulse)
                    cv2.circle(frame, (fx2,fy2), er+3, CONNECT_GLOW, -1, cv2.LINE_AA)
                    cv2.circle(frame, (fx2,fy2), er, C_WHITE, -1, cv2.LINE_AA)

        # Grand portal
        if touching_count >= 3:
            all_t = tips1 + tips2
            px2 = sum(p[0] for p in all_t) // len(all_t)
            py2 = sum(p[1] for p in all_t) // len(all_t)
            self._strange_portal(frame, px2, py2, t, touching_count)

    def _strange_portal(self, frame, cx, cy, t, n):
        base_r = 40 + n*15
        pulse = 0.8+0.2*math.sin(t*3)
        for ring in range(3):
            r = int((base_r+ring*20)*pulse)
            ao = t*(60+ring*30)*(1 if ring%2==0 else -1)
            na = 5+ring; al2 = 360//na-10
            for i in range(na):
                sa = int(ao+i*(360//na))%360
                a = 0.5+0.5*math.sin(t*5+ring+i)
                c = tuple(int(v*a) for v in MAGIC_CYAN)
                cv2.ellipse(frame, (cx,cy), (r,r), 0, sa, sa+al2, c, max(1,int(2*a)), cv2.LINE_AA)
        ri = int(base_r*0.6*pulse)
        for i in range(6):
            a1 = math.radians(t*40+i*60)
            a2 = math.radians(t*40+(i+2)*60)
            cv2.line(frame, (int(cx+ri*math.cos(a1)),int(cy+ri*math.sin(a1))),
                     (int(cx+ri*math.cos(a2)),int(cy+ri*math.sin(a2))), MAGIC_GOLD, 1, cv2.LINE_AA)
        cv2.circle(frame, (cx,cy), int(15*pulse), (200,180,50), -1, cv2.LINE_AA)
        cv2.circle(frame, (cx,cy), int(8*pulse), (255,255,200), -1, cv2.LINE_AA)
        if random.random() < 0.6:
            self.particles.emit_sparks(cx+random.randint(-base_r,base_r), cy, 2, 50, 0.9, 2)

    # ── Iron Man Helmet ──────────────────────────────────────────────────

    def render_helmet(self, frame, fw, fh):
        t = self.elapsed()
        self._face_skip += 1
        if self._face_skip >= 3 or self._last_face is None:
            self._face_skip = 0
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self._face_cascade.detectMultiScale(gray, 1.15, 5, minSize=(80,80))
            if len(faces) > 0:
                areas = [w*h for (x,y,w,h) in faces]
                self._last_face = tuple(int(v) for v in faces[int(np.argmax(areas))])
            else:
                self._last_face = None

        if self._last_face is None: return
        fx2, fy2, wf, hf = self._last_face
        cx, cy = fx2+wf//2, fy2+hf//2
        hw, hh = wf//2, hf//2
        pulse = 0.8+0.2*math.sin(t*3)

        # Forehead arc
        cv2.ellipse(frame, (cx, fy2+int(hh*0.15)), (int(hw*1.15), int(hh*0.55)),
                    0, 200, 340, HELMET_GOLD, 2, cv2.LINE_AA)
        # Side panels
        for side, sign in [(-1, 1), (1, -1)]:
            bx = fx2 if side == -1 else fx2+wf
            pts = np.array([
                [bx+side*int(hw*0.1)*(-1), cy-int(hh*0.3)],
                [bx+side*int(hw*0.15)*(-1), cy+int(hh*0.2)],
                [bx-side*int(hw*0.15), cy+int(hh*0.6)],
                [bx-side*int(hw*0.3), cy-int(hh*0.1)],
            ], dtype=np.int32)
            cv2.polylines(frame, [pts], False, HELMET_GOLD, 1, cv2.LINE_AA)
        # Chin
        chin_y = fy2 + hf
        cv2.line(frame, (cx-int(hw*0.5), chin_y), (cx, chin_y+int(hh*0.35)), HELMET_GOLD, 2, cv2.LINE_AA)
        cv2.line(frame, (cx+int(hw*0.5), chin_y), (cx, chin_y+int(hh*0.35)), HELMET_GOLD, 2, cv2.LINE_AA)
        # Eye visors
        ey = cy - int(hh*0.05)
        ew, eh = int(hw*0.45), int(hh*0.18)
        esp = int(hw*0.25)
        for s in [-1, 1]:
            ex = cx + s*esp
            ep = np.array([[ex-ew,ey-eh//3],[ex+ew*s,ey-eh],[ex+ew*s,ey+eh//2],[ex-ew//2,ey+eh//2]], np.int32)
            ov = frame.copy()
            cv2.fillPoly(ov, [ep], HELMET_EYE)
            cv2.addWeighted(ov, 0.25*pulse, frame, 1-0.25*pulse, 0, frame)
            cv2.polylines(frame, [ep], True, HELMET_CYAN, 1, cv2.LINE_AA)
        # Forehead emblem
        ey2 = fy2+int(hh*0.25)
        er = int(hw*0.15*pulse)
        cv2.circle(frame, (cx,ey2), er+3, HELMET_DIM, 1, cv2.LINE_AA)
        cv2.circle(frame, (cx,ey2), er, HELMET_CYAN, -1, cv2.LINE_AA)
        cv2.circle(frame, (cx,ey2), max(1,er//2), C_WHITE, -1, cv2.LINE_AA)
        # Nose/mouth
        nt = cy+int(hh*0.15); nb = fy2+hf-int(hh*0.1)
        cv2.line(frame, (cx,nt), (cx,nb), HELMET_DIM, 1, cv2.LINE_AA)
        vy = cy+int(hh*0.45)
        for i in range(3):
            vyi = vy+i*int(hh*0.12); vw = int(hw*(0.5-i*0.1))
            cv2.line(frame, (cx-vw,vyi), (cx+vw,vyi), HELMET_DIM, 1, cv2.LINE_AA)
        # Targeting brackets
        for (bx,by) in [(fx2,fy2),(fx2+wf,fy2),(fx2,fy2+hf),(fx2+wf,fy2+hf)]:
            dx2 = 1 if bx <= cx else -1; dy2 = 1 if by <= cy else -1
            cv2.line(frame, (bx,by), (bx+12*dx2,by), HELMET_CYAN, 1, cv2.LINE_AA)
            cv2.line(frame, (bx,by), (bx,by+12*dy2), HELMET_CYAN, 1, cv2.LINE_AA)
        cv2.putText(frame, "STARK INDUSTRIES", (fx2,fy2-12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, HELMET_CYAN, 1, cv2.LINE_AA)
        cv2.putText(frame, f"POWER: {int(pulse*100)}%", (fx2+wf+8,cy-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.30, HELMET_DIM, 1, cv2.LINE_AA)
        sy = fy2+int(hf*((t*0.4)%1.0))
        cv2.line(frame, (fx2,sy), (fx2+wf,sy), tuple(int(v*0.3) for v in HELMET_CYAN), 1, cv2.LINE_AA)


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

    fx = EffectsEngine()
    fx_on = True
    prev_t = time.perf_counter()
    fps = 0.0
    ts_ms = 0

    print(f"[*] Iron Man Magic -- Camera {int(cap.get(3))}x{int(cap.get(4))}")
    print("  E = toggle effects | Q = quit")

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
                all_lms = []
                for idx, (lms, hd) in enumerate(
                    zip(result.hand_landmarks, result.handedness)):
                    draw_skeleton(frame, lms, fw, fh)
                    all_lms.append(lms)

                    if fx_on:
                        fx.render(frame, lms, fw, fh)

                # Finger connections between both hands
                if fx_on and len(all_lms) == 2:
                    fx.render_finger_connections(frame, all_lms[0], all_lms[1], fw, fh)
            else:
                msg = "Show your hand to begin the magic"
                sz = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 0.75, 2)[0]
                tx = (fw-sz[0])//2
                overlay_rect(frame, tx-16, fh//2-28, tx+sz[0]+16, fh//2+10)
                cv2.putText(frame, msg, (tx, fh//2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.75, C_GRAY, 2, cv2.LINE_AA)
                fx.reset()

            # Helmet on face
            if fx_on:
                fx.render_helmet(frame, fw, fh)

            # FPS
            now = time.perf_counter()
            fps = 0.9*fps + 0.1/max(now-prev_t, 1e-6)
            prev_t = now
            fc = C_GREEN if fps >= 20 else C_RED
            bar_h = 30
            overlay_rect(frame, 0, fh-bar_h, fw, fh, alpha=0.7)
            cv2.putText(frame, f"FPS {fps:.0f}", (10, fh-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, fc, 1)
            cv2.putText(frame, "IRON MAN MAGIC", (fw//2-80, fh-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, HUD_CYAN, 2)
            cv2.putText(frame, "[E] effects  [Q] quit", (fw-230, fh-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, C_GRAY, 1)

            cv2.imshow("Iron Man Magic", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"): break
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
