"""
================================================================================
  GRAVITY SLINGSHOT - A Celeste-inspired Space Physics Game
================================================================================
  Built with Pygame | Internal resolution: 320x180 (upscaled 4x to 1280x720)
  
  PHYSICS OVERVIEW:
  ─────────────────
  Gravitational acceleration from body i onto the ship:
  
      a⃗ᵢ = G·mᵢ / |r⃗ᵢ|² · r̂ᵢ
  
  where:
      G   = gravitational constant (scaled for gameplay)
      mᵢ  = mass of celestial body i (in gameplay units)
      r⃗ᵢ  = vector from ship to body i
      r̂ᵢ  = unit vector in direction of r⃗ᵢ
      |r⃗ᵢ| = distance from ship to body i
  
  Total acceleration:
      a⃗ = Σ aᵢ for all bodies in level
  
  Integration method: Symplectic Euler (velocity-Verlet step)
      v⃗(t+dt) = v⃗(t) + a⃗(t)·dt
      x⃗(t+dt) = x⃗(t) + v⃗(t+dt)·dt
  
  STRUCTURE:
  ─────────
  - Constants & palette
  - CelestialBody definitions (real objects with real masses)
  - Sprite rendering (hand-crafted pixel art for each object)
  - LevelGenerator (backwards-path construction for solvability)
  - GameState (physics loop, input, rendering)
  - Screens: MainMenu, ShipSelect, ViewObjects, HowToPlay, PhysicsScreen
================================================================================
"""

import pygame
import math
import random
import sys
import copy

# ─────────────────────────────────────────────────────────────────────────────
#  INIT
# ─────────────────────────────────────────────────────────────────────────────
pygame.init()
pygame.display.set_caption("GRAVITY SLINGSHOT")

WINDOW_W, WINDOW_H = 1280, 720
RENDER_W, RENDER_H = 320, 180   # Internal Celeste-style low-res buffer
SCALE = 4                        # 320*4=1280, 180*4=720

screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
render_surface = pygame.Surface((RENDER_W, RENDER_H))
clock = pygame.time.Clock()
FPS = 60

# ─────────────────────────────────────────────────────────────────────────────
#  CELESTE-INSPIRED PALETTE  (limited, chunky, high-contrast)
# ─────────────────────────────────────────────────────────────────────────────
C_BLACK      = (  0,   0,   0)
C_DARK_SPACE = (  7,   9,  23)   # Deep dark blue background
C_SPACE2     = ( 12,  15,  40)   # Slightly lighter space
C_SPACE3     = ( 18,  22,  56)   # Panel/UI bg
C_STAR1      = (255, 255, 255)
C_STAR2      = (180, 200, 255)
C_STAR3      = (100, 130, 220)
C_GALAXY     = ( 80,  60, 140)
C_WHITE      = (255, 255, 255)
C_YELLOW     = (255, 230,  50)
C_ORANGE     = (255, 130,  30)
C_RED        = (220,  40,  40)
C_GREEN      = ( 50, 220,  80)
C_CYAN       = ( 80, 220, 255)
C_PURPLE     = (140,  60, 200)
C_PINK       = (255, 100, 180)
C_TRAJ       = (255, 230,  50)   # Trajectory arrow colour
C_UI_BG      = ( 10,  12,  32)
C_UI_BORDER  = ( 40,  50, 120)
C_UI_TEXT    = (200, 210, 255)
C_UI_BRIGHT  = (255, 255, 255)
C_SLINGSHOT  = (160, 120,  60)
C_EXPLOSION1 = (255, 200,  50)
C_EXPLOSION2 = (255,  80,  20)
C_EXPLOSION3 = (200,  20,  10)

# ─────────────────────────────────────────────────────────────────────────────
#  PHYSICS CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
# Gameplay-scaled gravitational constant.
# Real G = 6.674e-11 N m²/kg², but we use game units where distances are
# in pixels and masses are relative gameplay values. Tuned so that a
# Jupiter-mass object at ~60px pulls a ship into orbit in ~3 seconds.
G_CONSTANT = 800.0

# Softening factor ε to prevent singularities when ship is very close:
#   a = G*m / (r² + ε²)   (prevents division by near-zero)
SOFTENING_SQ = 25.0

# Time step (seconds per physics tick at 60fps)
PHYS_DT = 1.0 / 60.0

# Max simulation steps for trajectory preview (360 = ~6 s of flight at 60 fps)
TRAJ_STEPS = 360

# How far the visual rocky fringe juts into the corridor (render pixels).
# Collision is triggered when the ship enters this zone, matching the visual wall.
FRINGE_COLLISION = 5   # pixels fringe juts into corridor; collision matches this exactly
SHIP_RADIUS      = 4   # collision radius added on top of fringe so ship sprite never visually enters rocks

# Inventory bar height (in render pixels)
INVENTORY_H = 40

# HUD bar height at top of play area (in render pixels)
HUD_H = 18

# ─────────────────────────────────────────────────────────────────────────────
#  SPACESHIPS
# ─────────────────────────────────────────────────────────────────────────────
# Each ship has a real mass (kg), a name, and a pixel colour scheme.
# Mass affects how strongly gravitational bodies pull on it
# (all bodies pull equally regardless of ship mass in Newtonian gravity,
#  but we keep mass for flavour / display).
SHIPS = [
    {
        "name": "VOYAGER 1",
        "mass_kg": 825.5,
        "mass_label": "~10^2 kg",
        "color": (200, 210, 255),
        "accent": (80, 180, 255),
        "desc": "NASA deep space probe. Lightest & nimblest.",
        "facts": ["Launched 1977", "Now in interstellar space", "Most distant human object"],
    },
    {
        "name": "HUBBLE",
        "mass_kg": 11110.0,
        "mass_label": "~10^4 kg",
        "color": (180, 200, 180),
        "accent": (100, 220, 120),
        "desc": "Space telescope. Sturdy mid-weight craft.",
        "facts": ["Launched 1990", "Orbits at 547 km", "2.4 m primary mirror"],
    },
    {
        "name": "ISS MODULE",
        "mass_kg": 419700.0,
        "mass_label": "~10^5 kg",
        "color": (220, 220, 180),
        "accent": (255, 200, 60),
        "desc": "Station segment. Heavy but iconic shape.",
        "facts": ["Assembled 1998-2011", "Orbits at 408 km", "Crew of up to 7"],
    },
    {
        "name": "APOLLO CM",
        "mass_kg": 5809.0,
        "mass_label": "~10^3 kg",
        "color": (220, 180, 140),
        "accent": (255, 140, 60),
        "desc": "Command module. Classic cone silhouette.",
        "facts": ["Moon landings 1969-72", "3-astronaut crew", "Ocean splashdown"],
    },
    {
        "name": "STARSHIP",
        "mass_kg": 100000.0,
        "mass_label": "~10^5 kg",
        "color": (200, 200, 220),
        "accent": (160, 160, 255),
        "desc": "SpaceX mega-rocket. Big & bold.",
        "facts": ["Fully reusable", "100+ tonne payload", "Mars mission target"],
    },
]

# ─────────────────────────────────────────────────────────────────────────────
#  CELESTIAL OBJECTS  (placeable + obstacles + targets)
# ─────────────────────────────────────────────────────────────────────────────
# mass_kg:      Real mass in kilograms (for display)
# mass_game:    Gameplay gravitational mass (tuned relative values)
# radius:       Collision/display radius in render pixels
# is_large:     True=planet/star sprite (16px), False=small body (8px)
# color:        Primary pixel art colour
# ring_color:   If not None, draw Saturn-style ring
# order_mag:    Order of magnitude in kg (for display label)

CELESTIAL_OBJECTS = [
    # ── SUN (placeable; not used as a random level target) ────────────────
    {
        "id": "sun",
        "name": "SUN",
        "short": "SUN",
        "type": "star",
        "mass_kg": 1.989e30,
        "mass_game": 200.0,
        "order_mag": "~10^30 kg",
        "radius": 8,
        "is_large": True,
        "color": (255, 250, 220),
        "color2": (255, 210,  80),
        "band_color": (255, 130,  35),
        "ring_color": None,
        "desc": "Our star. Strongest pull in the set — place with care.",
        "facts": ["Core fusion", "~8 light-minutes from Earth", "Drives the solar system"],
    },
    # ── PLANETS / LARGE BODIES ──────────────────────────────────────────────
    {
        "id": "jupiter",
        "name": "JUPITER",
        "short": "JUPITER",
        "type": "planet",
        "mass_kg": 1.898e27,
        "mass_game": 120.0,
        "order_mag": "~10^27 kg",
        "radius": 7,
        "is_large": True,
        "color": (210, 170, 110),
        "color2": (190, 130,  80),
        "band_color": (160,  90,  50),
        "ring_color": None,
        "desc": "Largest planet. Strongest pull.",
        "facts": ["Gas giant", "79 known moons", "Great Red Spot storm"],
    },
    {
        "id": "saturn",
        "name": "SATURN",
        "short": "SATURN",
        "type": "planet",
        "mass_kg": 5.683e26,
        "mass_game": 85.0,
        "order_mag": "~10^26 kg",
        "radius": 6,
        "is_large": True,
        "color": (220, 195, 140),
        "color2": (190, 160, 100),
        "band_color": (170, 130,  70),
        "ring_color": (200, 180, 120),
        "desc": "Ringed giant. Strong pull.",
        "facts": ["Iconic ring system", "Density less than water", "146 known moons"],
    },
    {
        "id": "neptune",
        "name": "NEPTUNE",
        "short": "NEPTUNE",
        "type": "planet",
        "mass_kg": 1.024e26,
        "mass_game": 60.0,
        "order_mag": "~10^26 kg",
        "radius": 5,
        "is_large": True,
        "color": ( 50, 100, 200),
        "color2": ( 30,  70, 170),
        "band_color": ( 20,  50, 140),
        "ring_color": None,
        "desc": "Ice giant. Deep blue, strong pull.",
        "facts": ["Furthest from Sun", "Supersonic winds", "Faint ring system"],
    },
    {
        "id": "earth",
        "name": "EARTH",
        "short": "EARTH",
        "type": "planet",
        "mass_kg": 5.972e24,
        "mass_game": 30.0,
        "order_mag": "~10^24 kg",
        "radius": 5,
        "is_large": True,
        "color": ( 60, 130, 220),
        "color2": ( 50, 170,  80),
        "band_color": (100, 200, 100),
        "ring_color": None,
        "desc": "Home. Moderate pull.",
        "facts": ["Only known life", "Liquid water oceans", "1 large moon"],
    },
    {
        "id": "mars",
        "name": "MARS",
        "short": "MARS",
        "type": "planet",
        "mass_kg": 6.390e23,
        "mass_game": 18.0,
        "order_mag": "~10^23 kg",
        "radius": 4,
        "is_large": True,
        "color": (200,  80,  40),
        "color2": (160,  50,  20),
        "band_color": (120,  40,  20),
        "ring_color": None,
        "desc": "Red planet. Gentle pull.",
        "facts": ["Red from iron oxide", "Tallest volcano (Olympus)", "2 small moons"],
    },
    {
        "id": "kepler442b",
        "name": "KEPLER-442b",
        "short": "KPL-442b",
        "type": "exoplanet",
        "mass_kg": 2.3e25,
        "mass_game": 40.0,
        "order_mag": "~10^25 kg",
        "radius": 5,
        "is_large": True,
        "color": ( 80, 180, 140),
        "color2": ( 50, 140, 100),
        "band_color": ( 30, 100,  70),
        "ring_color": None,
        "desc": "Super-Earth exoplanet. Good pull.",
        "facts": ["1200 light years away", "In habitable zone", "1.34x Earth radius"],
    },
    {
        "id": "55cancrie",
        "name": "55 CNCE",
        "short": "55 CNC e",
        "type": "exoplanet",
        "mass_kg": 4.48e25,
        "mass_game": 50.0,
        "order_mag": "~10^25 kg",
        "radius": 5,
        "is_large": True,
        "color": (220, 140,  40),
        "color2": (180, 100,  20),
        "band_color": (140,  70,  10),
        "ring_color": None,
        "desc": "Lava world. Diamond core. Hot pull.",
        "facts": ["41 light years away", "Possible diamond mantle", "Year = 18 Earth days"],
    },
    # ── MOONS (half sprite size) ─────────────────────────────────────────────
    {
        "id": "europa",
        "name": "EUROPA",
        "short": "EUROPA",
        "type": "moon",
        "mass_kg": 4.80e22,
        "mass_game": 12.0,
        "order_mag": "~10^22 kg",
        "radius": 5,
        "is_large": False,
        "color": (225, 215, 200),
        "color2": (170, 140, 110),
        "band_color": (130, 100,  80),
        "ring_color": None,
        "desc": "Jupiter's icy moon. Moderate pull.",
        "facts": ["Global subsurface ocean", "Possible microbial life", "Smoothest body in solar system"],
    },
    {
        "id": "titan",
        "name": "TITAN",
        "short": "TITAN",
        "type": "moon",
        "mass_kg": 1.35e23,
        "mass_game": 16.0,
        "order_mag": "~10^23 kg",
        "radius": 5,
        "is_large": False,
        "color": (210, 145,  65),
        "color2": (160,  95,  35),
        "band_color": (120,  65,  20),
        "ring_color": None,
        "desc": "Saturn's largest moon. Good pull.",
        "facts": ["Dense nitrogen atmosphere", "Lakes of liquid methane", "Larger than Mercury"],
    },
    {
        "id": "ganymede",
        "name": "GANYMEDE",
        "short": "GANYMEDE",
        "type": "moon",
        "mass_kg": 1.48e23,
        "mass_game": 18.0,
        "order_mag": "~10^23 kg",
        "radius": 5,
        "is_large": False,
        "color": (155, 148, 138),
        "color2": (105,  98,  88),
        "band_color": ( 70,  65,  55),
        "ring_color": None,
        "desc": "Largest moon in solar system. Good pull.",
        "facts": ["Larger than Mercury", "Has own magnetosphere", "Icy & rocky terrain"],
    },
]

# Build lookup dict
OBJ_BY_ID = {o["id"]: o for o in CELESTIAL_OBJECTS}

# ─────────────────────────────────────────────────────────────────────────────
#  PIXEL ART SPRITE RENDERING
# ─────────────────────────────────────────────────────────────────────────────
# Sprites are drawn programmatically as pixel art onto small surfaces.
# Large bodies: 18x18 px canvas (radius ~9)
# Sun:          20x20 canvas (slightly larger than other large sprites at 14px)
# Small bodies:  9x9 px canvas (radius ~4)

def draw_sun_sprite(obj, size=16):
    """Bright stellar disk with hot core, granulation, and a soft corona ring."""
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx, cy = size // 2, size // 2
    r = size // 2 - 1
    core = obj["color"]
    mid = obj["color2"]
    limb = obj["band_color"]

    for px in range(size):
        for py in range(size):
            dx = px - cx
            dy = py - cy
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= r:
                t = dist / max(r, 1)
                # Hot bright centre → gold mid → orange limb
                if t < 0.45:
                    u = t / 0.45
                    col = tuple(int(core[i] * (1 - u) + mid[i] * u) for i in range(3))
                else:
                    u = (t - 0.45) / 0.55
                    col = tuple(int(mid[i] * (1 - u) + limb[i] * u) for i in range(3))
                # Surface granulation
                g = math.sin(dx * 2.7 + dy * 2.1) * math.cos(dx * 1.3 - dy * 2.4)
                if g > 0.55:
                    col = tuple(min(255, c + 14) for c in col)
                elif g < -0.55:
                    col = tuple(max(0, c - 22) for c in col)
                # Centre blow-out
                if dist < r * 0.35:
                    col = tuple(min(255, int(c * 1.08 + 12)) for c in col)
                surf.set_at((px, py), col + (255,))
            elif dist <= r + 2:
                # Faint corona pixels
                a = int(120 * (1.0 - (dist - r) / 2.0))
                if a > 8 and (px + py * 3) % 2 == 0:
                    cc = tuple(min(255, int(limb[i] * 0.85 + core[i] * 0.15)) for i in range(3))
                    surf.set_at((px, py), cc + (a,))

    hx, hy = cx - 2, cy - 2
    for ddx in (-1, 0, 1):
        for ddy in (-1, 0, 1):
            nx, ny = hx + ddx, hy + ddy
            if 0 <= nx < size and 0 <= ny < size:
                ex = surf.get_at((nx, ny))
                if ex[3] > 0:
                    surf.set_at((nx, ny), tuple(min(255, int(ex[i] * 1.15 + 28)) for i in range(3)) + (255,))
    return surf


def draw_planet_sprite(obj, size=18):
    """
    Draw a pixel-art planet sprite for 'obj' onto a new Surface of 'size'×'size'.
    Uses obj's color, color2, band_color, and ring_color.
    """
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx, cy = size // 2, size // 2
    r = size // 2 - 1

    c1 = obj["color"]
    c2 = obj["color2"]
    bc = obj["band_color"]

    # Draw base circle
    for px in range(size):
        for py in range(size):
            dx = px - cx
            dy = py - cy
            dist = math.sqrt(dx*dx + dy*dy)
            if dist <= r:
                # Latitude-based band colouring
                norm_y = dy / r   # -1 (top) to +1 (bottom)
                # Blend between c1 and c2 based on latitude
                t = (norm_y + 1) / 2
                base = tuple(int(c1[i]*(1-t) + c2[i]*t) for i in range(3))
                # Add band stripes (sin-wave pattern)
                band = math.sin(norm_y * math.pi * 3)
                if band > 0.4:
                    base = tuple(int(base[i]*0.6 + bc[i]*0.4) for i in range(3))
                # Lighting: top-left lighter
                light = 1.0 - 0.3 * (dx/r + 0.3) - 0.2 * (dy/r + 0.3)
                light = max(0.5, min(1.2, light))
                col = tuple(min(255, int(base[i] * light)) for i in range(3))
                surf.set_at((px, py), col + (255,))

    # Highlight (top-left specular)
    hx, hy = cx - r//3, cy - r//3
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            nx, ny = hx+dx, hy+dy
            if 0 <= nx < size and 0 <= ny < size:
                existing = surf.get_at((nx, ny))
                if existing[3] > 0:
                    bright = tuple(min(255, int(existing[i]*1.4 + 30)) for i in range(3))
                    surf.set_at((nx, ny), bright + (255,))

    # Saturn rings
    if obj.get("ring_color"):
        rc = obj["ring_color"]
        for angle in range(0, 360, 3):
            rad = math.radians(angle)
            for rr in range(r+2, r+6):
                rx = int(cx + rr * math.cos(rad))
                ry = int(cy + rr * math.sin(rad) * 0.35)   # flatten to ellipse
                if 0 <= rx < size and 0 <= ry < size:
                    alpha = 180 if rr < r+4 else 100
                    surf.set_at((rx, ry), rc + (alpha,))

    return surf


def draw_small_body_sprite(obj, size=11):
    """
    Draw a pixel-art moon sprite.  Each moon has a distinctive surface style:
      Europa   – icy white sphere criss-crossed with reddish-brown crack lines
      Titan    – orange-brown with subtle atmospheric banding and a hazy limb
      Ganymede – two-toned grey: bright icy patches over dark rocky terrain with craters
      (generic) – smooth sphere with subtle surface markings
    All moons use upper-left lighting for a consistent 3-D feel.
    """
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx, cy = size // 2, size // 2
    r = size // 2 - 1
    c1  = obj["color"]
    c2  = obj["color2"]
    bc  = obj["band_color"]
    oid = obj["id"]

    for px in range(size):
        for py in range(size):
            dx   = px - cx
            dy   = py - cy
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > r:
                continue
            norm_x = dx / max(r, 1)
            norm_y = dy / max(r, 1)
            t = dist / max(r, 1)

            if oid == "europa":
                # ── Europa: bright ice with reddish fracture lines ───────────
                # Base: slightly warmer toward the edge
                col = tuple(int(c1[i] * (1 - t * 0.35) + c2[i] * t * 0.35)
                            for i in range(3))
                # Crack network – two crossing sine waves produce a fracture pattern
                crack = (math.sin(dx * 3.8 + dy * 1.6) *
                         math.cos(dx * 0.9 - dy * 2.7))
                if crack > 0.50:
                    # Reddish-brown crack colour
                    col = (max(0, col[0] - 30), max(0, col[1] - 55),
                           max(0, col[2] - 60))
                # Thin secondary cracks
                crack2 = math.sin(dx * 1.4 - dy * 3.1 + 1.2)
                if crack2 > 0.80:
                    col = (max(0, col[0] - 15), max(0, col[1] - 25),
                           max(0, col[2] - 25))

            elif oid == "titan":
                # ── Titan: orange haze with latitudinal bands ────────────────
                col = tuple(int(c1[i] * (1 - t * 0.5) + c2[i] * t * 0.5)
                            for i in range(3))
                # Subtle horizontal banding
                band = math.sin(norm_y * math.pi * 2.8)
                if band > 0.25:
                    col = tuple(int(col[i] * 0.72 + bc[i] * 0.28) for i in range(3))
                # Hazy limb brightening – atmosphere scatters light at the edge
                if t > 0.75:
                    blend = (t - 0.75) / 0.25
                    haze  = tuple(min(255, int(c1[i] * 1.25)) for i in range(3))
                    col   = tuple(int(col[i] * (1 - blend) + haze[i] * blend)
                                  for i in range(3))

            elif oid == "ganymede":
                # ── Ganymede: bright icy grooved terrain over dark rock ──────
                col = tuple(int(c1[i] * (1 - t * 0.45) + c2[i] * t * 0.45)
                            for i in range(3))
                # Two-toned terrain patches (Perlin-like via two sines)
                terrain = (math.sin(dx * 2.3 + 1.1) *
                           math.cos(dy * 2.9 - 0.4))
                if terrain > 0.28:
                    # Dark rocky region
                    col = tuple(int(col[i] * 0.50 + bc[i] * 0.50) for i in range(3))
                # Grooved texture lines in the bright regions
                groove = math.sin(dx * 1.5 - dy * 0.8 + 0.7)
                if terrain <= 0.28 and groove > 0.65:
                    col = tuple(min(255, c + 18) for c in col)
                # Small crater depressions
                if (px * 7 + py * 13) % 17 == 0 and dist < r - 1:
                    col = tuple(max(0, c - 30) for c in col)

            else:
                # ── Generic moon: smooth sphere with faint markings ──────────
                col = tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))
                if math.sin(dx * 2.1 + dy * 1.3 + 0.5) > 0.70:
                    col = tuple(max(0, c - 18) for c in col)

            # Upper-left lighting (shared by all moons)
            light = 1.0 + 0.35 * (-norm_x * 0.6 - norm_y * 0.4)
            light = max(0.5, min(1.4, light))
            col   = tuple(min(255, int(c * light)) for c in col)
            surf.set_at((px, py), col + (255,))

    # Specular highlight – small bright patch at upper-left
    hx, hy = cx - max(1, r // 3), cy - max(1, r // 3)
    for ddx in range(-1, 2):
        for ddy in range(-1, 2):
            nx, ny = hx + ddx, hy + ddy
            if 0 <= nx < size and 0 <= ny < size:
                ex = surf.get_at((nx, ny))
                if ex[3] > 0:
                    bright = tuple(min(255, int(ex[i] * 1.35 + 25)) for i in range(3))
                    surf.set_at((nx, ny), bright + (255,))

    return surf


def draw_ship_sprite(ship, size=7):
    """
    Draw a pixel-art spaceship sprite. Each ship has a unique silhouette.
    size: pixel height of the sprite
    """
    surf = pygame.Surface((size*2, size*2), pygame.SRCALPHA)
    c = ship["color"]
    ac = ship["accent"]
    cx, cy = size, size

    name = ship["name"]

    if "VOYAGER" in name:
        # Probe body: small box + dish + long antenna
        # Body
        for px in range(cx-2, cx+3):
            for py in range(cy-1, cy+2):
                surf.set_at((px, py), c+(255,))
        # Dish (circle above)
        surf.set_at((cx, cy-3), ac+(255,))
        surf.set_at((cx-1, cy-2), ac+(255,))
        surf.set_at((cx+1, cy-2), ac+(255,))
        # Antenna arm
        surf.set_at((cx-3, cy), ac+(255,))
        surf.set_at((cx+3, cy), ac+(255,))

    elif "HUBBLE" in name:
        # Telescope: long cylinder with solar panels
        for px in range(cx-3, cx+4):
            surf.set_at((px, cy), c+(255,))
            surf.set_at((px, cy-1), c+(255,))
        # Solar panels
        for py in range(cy-3, cy+4):
            surf.set_at((cx-4, py), ac+(255,))
            surf.set_at((cx+4, py), ac+(255,))
        # Lens
        surf.set_at((cx+3, cy), (200,200,255,255))

    elif "ISS" in name:
        # Station: cross shape with multiple modules
        for px in range(cx-4, cx+5):
            surf.set_at((px, cy), c+(255,))
        for py in range(cy-2, cy+3):
            surf.set_at((cx, py), c+(255,))
        # Panels
        surf.set_at((cx-4, cy-1), ac+(255,))
        surf.set_at((cx-4, cy+1), ac+(255,))
        surf.set_at((cx+4, cy-1), ac+(255,))
        surf.set_at((cx+4, cy+1), ac+(255,))

    elif "APOLLO" in name:
        # Cone capsule
        surf.set_at((cx, cy-3), c+(255,))
        for px in range(cx-1, cx+2):
            surf.set_at((px, cy-2), c+(255,))
            surf.set_at((px, cy-1), c+(255,))
        for px in range(cx-2, cx+3):
            surf.set_at((px, cy), c+(255,))
            surf.set_at((px, cy+1), c+(255,))
        # Engine nozzle
        surf.set_at((cx, cy+2), ac+(255,))
        surf.set_at((cx-1, cy+3), ac+(255,))
        surf.set_at((cx+1, cy+3), ac+(255,))

    else:  # STARSHIP
        # Tall rocket with fins
        for px in range(cx-2, cx+3):
            for py in range(cy-4, cy+3):
                surf.set_at((px, py), c+(255,))
        # Nose cone
        surf.set_at((cx, cy-5), c+(255,))
        surf.set_at((cx-1, cy-4), c+(255,))
        surf.set_at((cx+1, cy-4), c+(255,))
        # Fins
        for py in range(cy+1, cy+4):
            surf.set_at((cx-3, py), ac+(255,))
            surf.set_at((cx+3, py), ac+(255,))
        # Flame
        surf.set_at((cx, cy+3), (255, 180, 50, 255))
        surf.set_at((cx-1, cy+4), (255, 100, 20, 200))
        surf.set_at((cx+1, cy+4), (255, 100, 20, 200))

    return surf


# Pre-render all celestial body sprites
PLANET_SPRITES = {}
for obj in CELESTIAL_OBJECTS:
    if obj["id"] == "sun":
        PLANET_SPRITES[obj["id"]] = draw_sun_sprite(obj, size=16)
    elif obj["is_large"]:
        PLANET_SPRITES[obj["id"]] = draw_planet_sprite(obj, size=14)
    else:
        PLANET_SPRITES[obj["id"]] = draw_small_body_sprite(obj, size=11)

# Pre-render ship sprites
SHIP_SPRITES = {}
for ship in SHIPS:
    SHIP_SPRITES[ship["name"]] = draw_ship_sprite(ship, size=7)

# ─────────────────────────────────────────────────────────────────────────────
#  STAR FIELD
# ─────────────────────────────────────────────────────────────────────────────

def generate_starfield(world_height, seed=42, world_width=None):
    """
    Generate a list of star/galaxy positions for a scrollable world.
    Each star: (x, y, size, base_color, twinkle_phase, twinkle_speed)
    world_width defaults to RENDER_W (used by menus).
    For game levels pass world_width explicitly.
    """
    if world_width is None:
        world_width = RENDER_W
    rng = random.Random(seed)
    stars = []
    count = int(world_width * world_height / 400)
    for _ in range(count):
        x = rng.randint(0, world_width - 1)
        y = rng.randint(0, world_height - 1)
        twinkle_phase = rng.uniform(0, math.pi * 2)
        twinkle_speed = rng.uniform(0.01, 0.04)
        r = rng.random()
        if r < 0.6:
            stars.append((x, y, 1, C_STAR3, twinkle_phase, twinkle_speed))
        elif r < 0.85:
            stars.append((x, y, 1, C_STAR2, twinkle_phase, twinkle_speed))
        elif r < 0.97:
            stars.append((x, y, 1, C_STAR1, twinkle_phase, twinkle_speed))
        else:
            stars.append((x, y, rng.randint(2, 4), C_GALAXY, 0.0, 0.0))
    return stars


# Global frame counter for twinkle animation (incremented in run loop)
_frame_tick = 0


def draw_starfield(surface, stars, camera_x, camera_y, cam_zoom=1.0):
    """
    Draw visible stars in world space → screen (camera + optional zoom).
    Menus pass (0, 0, 1.0).
    """
    z = max(0.35, min(float(cam_zoom), 2.8))
    for (x, y, size, col, phase, speed) in stars:
        sx = (x - camera_x) / z
        sy = (y - camera_y) / z
        if -size <= sx <= RENDER_W and -size <= sy <= RENDER_H:
            if size == 1:
                # Twinkle: brightness oscillates ±40 around base
                if speed > 0:
                    brightness = 0.6 + 0.4 * math.sin(phase + _frame_tick * speed)
                else:
                    brightness = 1.0
                tcol = tuple(min(255, int(c * brightness)) for c in col)
                surface.set_at((int(sx), int(sy)), tcol)
            else:
                # Galaxy smudge — static, no twinkle
                pygame.draw.circle(surface, col, (int(sx), int(sy)), size)
                clight = tuple(min(255, c+40) for c in col)
                pygame.draw.circle(surface, clight, (int(sx), int(sy)), max(1, size-1))

# ─────────────────────────────────────────────────────────────────────────────
#  PIXEL FONT HELPERS
# ─────────────────────────────────────────────────────────────────────────────
# The render surface is 320×180, upscaled 4× to 1280×720.
# Text rendered at size N on the 320×180 buffer appears as N*4 pixels on screen.
# e.g. size=8 → 32px on screen, size=16 → 64px on screen.
#
# Font priority list — picked for clean, sharp rendering at small sizes on the
# 320×180 render canvas.  Monaco/Menlo look crisp and slightly retro; the list
# falls back through common cross-platform options to pygame's built-in.
_FONT_NAMES = "monaco,menlo,lucidaconsole,couriernew,courier,consolas"

_font_cache = {}

def get_font(size=8):
    if size not in _font_cache:
        _font_cache[size] = pygame.font.SysFont(_FONT_NAMES, max(8, size))
    return _font_cache[size], size


def draw_text(surface, text, x, y, color=C_UI_TEXT, size=8, shadow=True, center=False):
    """
    Draw text at logical pixel size 'size' onto the render surface.
    antialiasing=False keeps edges sharp for the 4× pixel-art upscale.
    center=True: x is the horizontal centre.
    Returns rendered width in render pixels.
    """
    font, _ = get_font(size)
    t_surf = font.render(text, False, color)   # False = no antialiasing
    w, h = t_surf.get_size()
    draw_x = x - w // 2 if center else x
    if shadow:
        s_surf = font.render(text, False, C_BLACK)
        surface.blit(s_surf, (draw_x + 1, y + 1))
    surface.blit(t_surf, (draw_x, y))
    return w


def text_width(text, size=8):
    font, _ = get_font(size)
    w, _ = font.size(text)
    return w

# ─────────────────────────────────────────────────────────────────────────────
#  LEVEL GENERATOR
# ─────────────────────────────────────────────────────────────────────────────
# Strategy: "backwards construction" for guaranteed solvability.
# 
# 1. Pick a start (slingshot) at top of world, target near bottom.
# 2. Trace a "guide path" — a gentle S-curve or arc between them.
# 3. Place required inventory objects near the guide path such that
#    they nudge a ship launched in the guide direction onto the path.
# 4. Place obstacles (asteroid belts, large rock obstacles) away from
#    the guide path (with clearance check).
# 5. Verify: simulate 12 random perturbations; at least one must reach
#    within target_radius of target. If not, regenerate.

class PlacedBody:
    """A celestial body placed in the world."""
    __slots__ = ["obj_id", "x", "y", "is_obstacle"]
    def __init__(self, obj_id, x, y, is_obstacle=False):
        self.obj_id = obj_id
        self.x = float(x)
        self.y = float(y)
        self.is_obstacle = is_obstacle

    @property
    def obj(self):
        return OBJ_BY_ID[self.obj_id]

    @property
    def mass(self):
        return self.obj["mass_game"]

    @property
    def radius(self):
        return self.obj["radius"]


class OrbitObstaclePair:
    """
    Fixed planet at (cx, cy) plus a moon on a circular path (same idea as the
    physics mini lab). Positions are written into the two PlacedBody instances.
    `tick` matches gameplay: one tick per frame / preview substep / sim step.
    """
    __slots__ = ("planet", "moon", "cx", "cy", "orbit_r", "omega", "phase0")

    def __init__(self, planet, moon, cx, cy, orbit_r, omega, phase0=0.0):
        self.planet = planet
        self.moon = moon
        self.cx = float(cx)
        self.cy = float(cy)
        self.orbit_r = float(orbit_r)
        self.omega = float(omega)
        self.phase0 = float(phase0)

    def sync(self, tick):
        """Set planet and moon world positions for orbit phase `tick`."""
        self.planet.x = self.cx
        self.planet.y = self.cy
        ang = self.phase0 - tick * self.omega
        self.moon.x = self.cx + self.orbit_r * math.cos(ang)
        self.moon.y = self.cy + self.orbit_r * math.sin(ang)


class BinaryStarPair:
    """
    Two equal-mass bodies (e.g. both sun) in circular orbit around their
    barycenter at (cx, cy). Each star stays on opposite sides of the center.
    """
    __slots__ = ("star_a", "star_b", "cx", "cy", "sep", "omega", "phase0")

    def __init__(self, star_a, star_b, cx, cy, separation, omega, phase0=0.0):
        self.star_a = star_a
        self.star_b = star_b
        self.cx = float(cx)
        self.cy = float(cy)
        self.sep = float(separation)
        self.omega = float(omega)
        self.phase0 = float(phase0)

    def sync(self, tick):
        ang = self.phase0 - tick * self.omega
        r = self.sep * 0.5
        self.star_a.x = self.cx + r * math.cos(ang)
        self.star_a.y = self.cy + r * math.sin(ang)
        self.star_b.x = self.cx - r * math.cos(ang)
        self.star_b.y = self.cy - r * math.sin(ang)


def _merge_intervals_open(intervals):
    """Merge (lo, hi) corridor interiors; lo < hi in world y."""
    if not intervals:
        return []
    iv = sorted((min(a, b), max(a, b)) for a, b in intervals)
    out = [list(iv[0])]
    for lo, hi in iv[1:]:
        if lo <= out[-1][1]:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return out


def _merged_safe_intervals_at_column(top_arr, bot_arr, xi, corridor_bands):
    """Merged navigable (top, bot) y-intervals at integer column index xi."""
    xi = int(max(0, min(len(top_arr) - 1, xi)))
    safe = []
    if corridor_bands:
        for band in corridor_bands:
            t = band["top"][xi]
            b = band["bot"][xi]
            if b > t:
                safe.append((t, b))
    else:
        t, b = top_arr[xi], bot_arr[xi]
        if b > t:
            safe.append((t, b))
    return _merge_intervals_open(safe)


def _rock_vertical_spans_for_column(top_arr, bot_arr, xi, world_h, corridor_bands):
    """
    Return list of (y0, y1) half-open rock spans in world y for this column,
    i.e. complement of union of corridor interiors.
    """
    merged = _merged_safe_intervals_at_column(top_arr, bot_arr, xi, corridor_bands)
    rocks = []
    y0 = 0.0
    for lo, hi in merged:
        if y0 < lo:
            rocks.append((y0, lo))
        y0 = max(y0, hi)
    if y0 < world_h:
        rocks.append((y0, world_h))
    return rocks


def simulate_ship(start_x, start_y, vx, vy, placed_bodies, world_width,
                  belt_top_edge=None, belt_bot_edge=None,
                  max_steps=2400, target=None, target_radius=12,
                  orbit_pairs=None, binary_star_pairs=None,
                  world_height=None, corridor_bands=None):
    """
    Symplectic-Euler simulation for level-solvability verification.
    belt_top_edge / belt_bot_edge are per-x float arrays (irregular walls).
    Falls back to full-screen bounds if not provided.
    orbit_pairs: optional list of OrbitObstaclePair; synced with sim step index.
    binary_star_pairs: optional list of BinaryStarPair; synced each step.
    world_height: vertical OOB limit (defaults from belt or RENDER_H).
    corridor_bands: optional list of dicts with top/bot arrays (multi-corridor).
    Returns ("target"|"oob"|"obstacle"|"timeout", steps, path).
    """
    n_edge = len(belt_top_edge) if belt_top_edge else 0
    _def_wh = float(RENDER_H - INVENTORY_H)
    wh = float(world_height if world_height is not None
               else (_def_wh if belt_bot_edge else float(RENDER_H)))
    sx, sy = float(start_x), float(start_y)
    path   = [(sx, sy)]

    for step in range(max_steps):
        if orbit_pairs:
            for op in orbit_pairs:
                op.sync(step)
        if binary_star_pairs:
            for bp in binary_star_pairs:
                bp.sync(step)
        ax, ay = 0.0, 0.0
        for body in placed_bodies:
            rx = body.x - sx
            ry = body.y - sy
            dist_sq = rx*rx + ry*ry + SOFTENING_SQ
            dist    = math.sqrt(dist_sq)
            a_mag   = G_CONSTANT * body.mass / dist_sq
            ax += a_mag * rx / dist
            ay += a_mag * ry / dist

        vx += ax * PHYS_DT
        vy += ay * PHYS_DT
        sx += vx * PHYS_DT
        sy += vy * PHYS_DT
        path.append((sx, sy))

        # Belt / world-edge collision (per-x; multi-corridor = union of safe strips)
        xi = int(max(0, min(n_edge - 1, sx))) if n_edge else 0
        fr = FRINGE_COLLISION + SHIP_RADIUS
        if n_edge and (belt_top_edge and belt_bot_edge):
            ok = False
            if corridor_bands:
                for band in corridor_bands:
                    t = band["top"][xi]
                    b = band["bot"][xi]
                    if t + fr < sy < b - fr:
                        ok = True
                        break
            else:
                t, b = belt_top_edge[xi], belt_bot_edge[xi]
                ok = (t + fr < sy < b - fr)
            if (sx < -20 or sx > world_width + 20 or sy < -20 or sy > wh + 20
                    or not ok):
                return ("oob", step, path)
        elif sx < -20 or sx > world_width + 20 or sy < -20 or sy > wh + 20:
            return ("oob", step, path)

        # Body collision
        for body in placed_bodies:
            dx = sx - body.x
            dy = sy - body.y
            if dx*dx + dy*dy < (body.radius + 2)**2:
                if (not body.is_obstacle and target
                        and body.obj_id == target.obj_id
                        and abs(body.x - target.x) < 1):
                    return ("target", step, path)
                return ("obstacle", step, path)

        # Explicit target check
        if target:
            dx = sx - target.x
            dy = sy - target.y
            if dx*dx + dy*dy < (target.radius + 3)**2:
                return ("target", step, path)

    return ("timeout", max_steps, path)


class Level:
    """
    A generated level — navigation is LEFT → RIGHT.

    Belt walls are IRREGULAR (sine-wave edges):
      belt_top_edge[x]  = y of the corridor's top wall at world-x
      belt_bot_edge[x]  = y of the corridor's bottom wall at world-x
    Flying into a wall (above top or below bot) = explosion.
    belt_dots = list of (world_x, world_y, size) for visual rocks.
    """
    def __init__(self, world_width, world_height, slingshot_pos, target,
                 obstacles, inventory, inv_bodies,
                 starfield, solution_vx, solution_vy,
                 belt_top_edge, belt_bot_edge, belt_dots,
                 orbit_pairs=None, corridor_bands=None, binary_star_pairs=None):
        self.world_width    = world_width
        self.world_height   = world_height     # world y extent (may exceed view height)
        self.belt_top_edge  = belt_top_edge    # list[float], length = world_width
        self.belt_bot_edge  = belt_bot_edge    # list[float], length = world_width
        self.belt_dots      = belt_dots
        self.slingshot_pos  = slingshot_pos
        self.target         = target
        self.obstacles      = obstacles
        self.inventory      = inventory
        self.inv_bodies     = inv_bodies
        self.starfield      = starfield
        self.solution_vx    = solution_vx
        self.solution_vy    = solution_vy
        self.orbit_pairs    = orbit_pairs or []
        self.corridor_bands = corridor_bands   # None = single belt_top/bot; else list of dicts
        self.binary_star_pairs = binary_star_pairs or []
        self.attempt        = 0

    def sync_orbits(self, tick):
        for op in self.orbit_pairs:
            op.sync(tick)
        for bp in self.binary_star_pairs:
            bp.sync(tick)

    def ship_in_corridor(self, sx, sy):
        """True if (sx,sy) lies inside any navigable corridor strip (with fringe margin)."""
        fr = FRINGE_COLLISION + SHIP_RADIUS
        xi = int(max(0, min(self.world_width - 1, sx)))
        if self.corridor_bands:
            for band in self.corridor_bands:
                t = band["top"][xi]
                b = band["bot"][xi]
                if t + fr < sy < b - fr:
                    return True
            return False
        t = self.belt_top_edge[xi]
        b = self.belt_bot_edge[xi]
        return t + fr < sy < b - fr

    def belt_top_at(self, x):
        """Return top-belt edge y at world-x (clamped to array bounds)."""
        xi = int(max(0, min(len(self.belt_top_edge) - 1, x)))
        return self.belt_top_edge[xi]

    def belt_bot_at(self, x):
        """Return bottom-belt edge y at world-x (clamped to array bounds)."""
        xi = int(max(0, min(len(self.belt_bot_edge) - 1, x)))
        return self.belt_bot_edge[xi]


# level_num (0-based) → layout variant for orbit obstacle showcase levels
_ORBIT_SHOWCASE_LEVELS = frozenset({3, 12, 21})
_BINARY_SUN_LEVELS = frozenset({5, 18})
_DUAL_CORRIDOR_LEVELS = frozenset({6, 20})
_CORNER_CLIMB_LEVELS = frozenset({7, 19})


def _offset_corridor_band(top_arr, bot_arr, dy, world_h, min_corridor=30.0):
    """Shift a (top, bot) corridor vertically; clamp to HUD and world floor."""
    out_t, out_b = [], []
    for t, b in zip(top_arr, bot_arr):
        t2 = float(t) + dy
        b2 = float(b) + dy
        t2 = max(float(HUD_H + 3), t2)
        b2 = min(float(world_h - 4), b2)
        if b2 - t2 < min_corridor:
            mid = (t2 + b2) * 0.5
            half = min_corridor * 0.5
            t2 = max(float(HUD_H + 3), mid - half)
            b2 = min(float(world_h - 4), mid + half)
        out_t.append(t2)
        out_b.append(b2)
    return out_t, out_b


def _promote_level_dual_corridors(level, rng, lower_off, upper_off):
    """
    Stack two parallel corridors from the same wall template (different vertical offsets).
    Primary gameplay stays in the lower corridor; upper is an alternate survivable lane.
    """
    play_h = float(RENDER_H - INVENTORY_H)
    world_h = float(int(lower_off + play_h + 24))
    loff = float(lower_off)
    uoff = float(upper_off)
    lo_t, lo_b = _offset_corridor_band(level.belt_top_edge, level.belt_bot_edge, loff, world_h)
    hi_t, hi_b = _offset_corridor_band(level.belt_top_edge, level.belt_bot_edge, uoff, world_h)
    sx, sy = level.slingshot_pos
    tx, ty = level.target.x, level.target.y
    sling = (float(sx), float(sy) + loff)
    target = PlacedBody(level.target.obj_id, float(tx), float(ty) + loff, is_obstacle=False)
    inv_bodies = []
    for b in level.inv_bodies:
        inv_bodies.append(PlacedBody(b.obj_id, b.x, b.y + loff, b.is_obstacle))
    obstacles = []
    for b in level.obstacles:
        obstacles.append(PlacedBody(b.obj_id, b.x, b.y + loff, b.is_obstacle))
    orbit_pairs = []
    for op in level.orbit_pairs:
        p = PlacedBody(op.planet.obj_id, op.planet.x, op.planet.y + loff, True)
        m = PlacedBody(op.moon.obj_id, op.moon.x, op.moon.y + loff, True)
        orbit_pairs.append(
            OrbitObstaclePair(p, m, op.cx, op.cy + loff, op.orbit_r, op.omega, op.phase0))
    for op in orbit_pairs:
        op.sync(0.0)
    binary_pairs = []
    for bp in level.binary_star_pairs:
        a = PlacedBody(bp.star_a.obj_id, bp.star_a.x, bp.star_a.y + loff, True)
        b = PlacedBody(bp.star_b.obj_id, bp.star_b.x, bp.star_b.y + loff, True)
        binary_pairs.append(
            BinaryStarPair(a, b, bp.cx, bp.cy + loff, bp.sep, bp.omega, bp.phase0))
    for bp in binary_pairs:
        bp.sync(0.0)
    belt_dots = []
    for (bx, by, bsz) in level.belt_dots:
        belt_dots.append((bx, by + loff, bsz))
    starfield = generate_starfield(
        int(world_h), seed=rng.randint(0, 1_000_000), world_width=level.world_width)
    return Level(
        world_width=level.world_width,
        world_height=int(world_h),
        slingshot_pos=sling,
        target=target,
        obstacles=obstacles,
        inventory=list(level.inventory),
        inv_bodies=inv_bodies,
        starfield=starfield,
        solution_vx=level.solution_vx,
        solution_vy=level.solution_vy,
        belt_top_edge=lo_t,
        belt_bot_edge=lo_b,
        belt_dots=belt_dots,
        orbit_pairs=orbit_pairs,
        corridor_bands=[{"top": lo_t, "bot": lo_b}, {"top": hi_t, "bot": hi_b}],
        binary_star_pairs=binary_pairs,
    )


def _dual_level_passes_verify(lvl):
    """Solution + bare checks with multi-corridor collision."""
    sx, sy = lvl.slingshot_pos
    all_b = lvl.inv_bodies + lvl.obstacles + [lvl.target]
    res, _, _ = simulate_ship(
        sx, sy, lvl.solution_vx, lvl.solution_vy, all_b, lvl.world_width,
        belt_top_edge=lvl.belt_top_edge, belt_bot_edge=lvl.belt_bot_edge,
        max_steps=4200, target=lvl.target, target_radius=14,
        orbit_pairs=lvl.orbit_pairs, binary_star_pairs=lvl.binary_star_pairs,
        world_height=float(lvl.world_height), corridor_bands=lvl.corridor_bands,
    )
    if res != "target":
        return False
    bare = [lvl.target] + lvl.obstacles
    BARE_ANGLES = 40
    BARE_SPEEDS = [35, 60, 85, 110, 135, 160, 185, 200]
    for ai in range(BARE_ANGLES):
        ang = -math.pi / 2.0 + math.pi * ai / max(1, BARE_ANGLES - 1)
        for spd in BARE_SPEEDS:
            r, _, _ = simulate_ship(
                sx, sy, spd * math.cos(ang), spd * math.sin(ang), bare, lvl.world_width,
                belt_top_edge=lvl.belt_top_edge, belt_bot_edge=lvl.belt_bot_edge,
                max_steps=4200, target=lvl.target, target_radius=14,
                orbit_pairs=lvl.orbit_pairs, binary_star_pairs=lvl.binary_star_pairs,
                world_height=float(lvl.world_height), corridor_bands=lvl.corridor_bands,
            )
            if r == "target":
                return False
    # Upper lane alone: no obstacles — quick clearance sample
    fr = FRINGE_COLLISION + SHIP_RADIUS
    hi = lvl.corridor_bands[1]
    for xi in range(0, lvl.world_width, max(1, lvl.world_width // 24)):
        if hi["top"][xi] + fr >= hi["bot"][xi] - fr:
            return False
    return True


def _build_binary_sun_level(level_num):
    """Two sun sprites in mutual circular orbit; solvable with inventory only."""
    play_h = float(RENDER_H - INVENTORY_H)
    world_width = int(RENDER_W * 1.55)
    for seed in range(200):
        rng = random.Random(level_num * 7103 + seed * 97)
        belt_top_edge, belt_bot_edge = _make_belt_edges(
            world_width, base_top=28, base_bot=108, amplitude=8, rng=rng,
            min_corridor=72,
        )

        def mid_y(wx):
            xi = int(max(0, min(world_width - 1, int(wx))))
            return (belt_top_edge[xi] + belt_bot_edge[xi]) * 0.5

        sx = 22.0
        sy = mid_y(sx) + rng.uniform(-6.0, 6.0)
        sy = max(HUD_H + 18.0, min(play_h - 18.0, sy))
        tx = float(world_width - 24)
        ty = mid_y(tx) + rng.uniform(-10.0, 10.0)
        ty = max(HUD_H + 18.0, min(play_h - 18.0, ty))
        target = PlacedBody("earth", tx, ty, is_obstacle=False)

        cx = sx + (tx - sx) * rng.uniform(0.38, 0.62)
        cy = mid_y(cx) + rng.uniform(-8.0, 8.0)
        cy = max(HUD_H + 36.0, min(play_h - 36.0, cy))
        sep = 26.0 + rng.uniform(0.0, 6.0)
        omega = 0.055 + rng.uniform(0.0, 0.022)
        phase0 = rng.uniform(0.0, math.pi * 2.0)
        sun_a = PlacedBody("sun", cx, cy, is_obstacle=True)
        sun_b = PlacedBody("sun", cx, cy, is_obstacle=True)
        bpair = BinaryStarPair(sun_a, sun_b, cx, cy, sep, omega, phase0)
        bpair.sync(0.0)
        obstacles = [sun_a, sun_b]

        inv_pool = [o for o in CELESTIAL_OBJECTS if o["mass_game"] >= 10 and o["id"] != "sun"]
        inv_objs = rng.sample(inv_pool, min(3, len(inv_pool)))
        inventory = [o["id"] for o in inv_objs]
        used_xy = [(sx, sy), (tx, ty), (cx, cy)]
        inv_bodies = []
        for i, obj in enumerate(inv_objs):
            placed = False
            for _ in range(55):
                t_frac = (i + 1) / (len(inv_objs) + 1)
                bx = sx + (tx - sx) * t_frac + rng.uniform(-44.0, 44.0)
                bx = max(48.0, min(world_width - 48.0, bx))
                by = (sy + ty) * 0.5 + rng.uniform(-36.0, 36.0)
                by = max(HUD_H + 22.0, min(play_h - 22.0, by))
                if all(math.hypot(bx - px, by - py) > 30 for px, py in used_xy):
                    if math.hypot(bx - cx, by - cy) < sep * 0.5 + 36:
                        continue
                    inv_bodies.append(PlacedBody(obj["id"], bx, by, is_obstacle=False))
                    used_xy.append((bx, by))
                    placed = True
                    break
            if not placed:
                inv_bodies = None
                break
        if not inv_bodies:
            continue

        all_sim = inv_bodies + obstacles + [target]
        SPEED_VALS = [45, 65, 85, 105, 125, 150, 175, 200]
        sol_vx = sol_vy = None
        for ai in range(56):
            ang = -math.pi / 2.0 + math.pi * ai / 55.0
            for spd in SPEED_VALS:
                vx = spd * math.cos(ang)
                vy = spd * math.sin(ang)
                res, _, _ = simulate_ship(
                    sx, sy, vx, vy, all_sim, world_width,
                    belt_top_edge=belt_top_edge, belt_bot_edge=belt_bot_edge,
                    max_steps=4400, target=target, target_radius=14,
                    binary_star_pairs=[bpair], world_height=play_h,
                )
                if res == "target":
                    sol_vx, sol_vy = vx, vy
                    break
            if sol_vx is not None:
                break
        if sol_vx is None:
            continue

        bare_ok = False
        for ai in range(36):
            ang = -math.pi / 2.0 + math.pi * ai / 35.0
            for spd in SPEED_VALS:
                vx = spd * math.cos(ang)
                vy = spd * math.sin(ang)
                res, _, _ = simulate_ship(
                    sx, sy, vx, vy, obstacles + [target], world_width,
                    belt_top_edge=belt_top_edge, belt_bot_edge=belt_bot_edge,
                    max_steps=4400, target=target, target_radius=14,
                    binary_star_pairs=[bpair], world_height=play_h,
                )
                if res == "target":
                    bare_ok = True
                    break
            if bare_ok:
                break
        if bare_ok:
            continue

        belt_rng = random.Random(level_num * 4441 + seed)
        belt_dots = []
        for _ in range(int(world_width * 0.62)):
            bx = belt_rng.randint(0, world_width - 1)
            xi = min(bx, world_width - 1)
            top_h = belt_top_edge[xi]
            bot_h = play_h - belt_bot_edge[xi]
            total = top_h + bot_h
            if total < 2:
                continue
            if belt_rng.random() < top_h / total and top_h > 1:
                by = belt_rng.randint(0, max(1, int(top_h) - 1))
            elif bot_h > 1:
                by = belt_rng.randint(int(belt_bot_edge[xi]) + 1, int(play_h) - 1)
            else:
                continue
            belt_dots.append((bx, by, belt_rng.randint(1, 2)))

        starfield = generate_starfield(int(play_h), seed=level_num * 1009 + seed,
                                       world_width=world_width)
        bpair.sync(0.0)
        return Level(
            world_width=world_width,
            world_height=int(play_h),
            slingshot_pos=(sx, sy),
            target=target,
            obstacles=obstacles,
            inventory=inventory,
            inv_bodies=inv_bodies,
            starfield=starfield,
            solution_vx=sol_vx,
            solution_vy=sol_vy,
            belt_top_edge=belt_top_edge,
            belt_bot_edge=belt_bot_edge,
            belt_dots=belt_dots,
            orbit_pairs=[],
            corridor_bands=None,
            binary_star_pairs=[bpair],
        )
    return None


def _build_corner_climb_level(level_num):
    """
    Tall world: target above start with ≥0.4 screen horizontal separation.
    """
    play_h = float(RENDER_H - INVENTORY_H)
    world_h = int(play_h * 2.35)
    world_width = int(RENDER_W * 2.0)
    min_dx = 0.42 * float(RENDER_W)
    rng = random.Random(level_num * 5021 + 17)

    for seed in range(120):
        rng2 = random.Random(level_num * 8803 + seed * 131)
        belt_top_edge, belt_bot_edge = _make_belt_edges(
            world_width, base_top=HUD_H + 14, base_bot=float(world_h) - 18.0,
            amplitude=10 + rng2.uniform(0, 5), rng=rng2, drift=rng2.uniform(-0.04, 0.04),
            min_corridor=58, world_h=float(world_h),
        )

        sx = 26.0
        sy = float(world_h) - 52.0 - rng2.uniform(0, 18)
        tx = sx + min_dx + rng2.uniform(0.0, float(world_width) * 0.35)
        tx = min(float(world_width - 22), max(sx + min_dx, tx))
        ty = HUD_H + 36.0 + rng2.uniform(0, 28)
        if ty >= sy - 24:
            continue
        if abs(tx - sx) < min_dx - 1:
            continue
        target = PlacedBody("earth", tx, ty, is_obstacle=False)

        inv_pool = [o for o in CELESTIAL_OBJECTS if o["mass_game"] >= 10]
        inv_objs = rng2.sample(inv_pool, min(3, len(inv_pool)))
        inventory = [o["id"] for o in inv_objs]
        used_xy = [(sx, sy), (tx, ty)]
        inv_bodies = []
        for i, obj in enumerate(inv_objs):
            placed = False
            for _ in range(50):
                t_frac = (i + 1) / (len(inv_objs) + 1)
                bx = sx + (tx - sx) * t_frac + rng2.uniform(-55.0, 55.0)
                bx = max(40.0, min(world_width - 40.0, bx))
                by = sy + (ty - sy) * t_frac + rng2.uniform(-40.0, 40.0)
                by = max(HUD_H + 20.0, min(world_h - 24.0, by))
                if all(math.hypot(bx - px, by - py) > 26 for px, py in used_xy):
                    inv_bodies.append(PlacedBody(obj["id"], bx, by, is_obstacle=False))
                    used_xy.append((bx, by))
                    placed = True
                    break
            if not placed:
                inv_bodies = None
                break
        if not inv_bodies:
            continue

        all_sim = inv_bodies + [target]
        SPEED_VALS = [45, 65, 85, 105, 125, 150, 175, 200]
        sol_vx = sol_vy = None
        for ai in range(64):
            ang = -math.pi * 0.65 + math.pi * 1.3 * ai / 63.0
            for spd in SPEED_VALS:
                vx = spd * math.cos(ang)
                vy = spd * math.sin(ang)
                res, _, path = simulate_ship(
                    sx, sy, vx, vy, all_sim, world_width,
                    belt_top_edge=belt_top_edge, belt_bot_edge=belt_bot_edge,
                    max_steps=5200, target=target, target_radius=14,
                    world_height=float(world_h),
                )
                if res == "target" and len(path) > 2:
                    ok_y = True
                    for _, py in path:
                        if py < HUD_H + 8 or py > float(world_h) - 10:
                            ok_y = False
                            break
                    if ok_y:
                        sol_vx, sol_vy = vx, vy
                        break
            if sol_vx is not None:
                break
        if sol_vx is None:
            continue

        bare_solved = False
        for ai in range(40):
            ang = -math.pi / 2.0 + math.pi * ai / 39.0
            for spd in SPEED_VALS:
                res, _, _ = simulate_ship(
                    sx, sy, spd * math.cos(ang), spd * math.sin(ang),
                    [target], world_width,
                    belt_top_edge=belt_top_edge, belt_bot_edge=belt_bot_edge,
                    max_steps=5200, target=target, target_radius=14,
                    world_height=float(world_h),
                )
                if res == "target":
                    bare_solved = True
                    break
            if bare_solved:
                break
        if bare_solved:
            continue

        belt_rng = random.Random(level_num * 3331 + seed)
        belt_dots = []
        for _ in range(int(world_width * 0.55)):
            bx = belt_rng.randint(0, world_width - 1)
            xi = min(bx, world_width - 1)
            t = belt_top_edge[xi]
            b = belt_bot_edge[xi]
            if b - t < 8:
                continue
            if belt_rng.random() < 0.5:
                by = belt_rng.uniform(t + 2, t + (b - t) * 0.35)
            else:
                by = belt_rng.uniform(b - (b - t) * 0.35, b - 2)
            belt_dots.append((bx, by, belt_rng.randint(1, 2)))

        starfield = generate_starfield(world_h, seed=level_num * 1003 + seed,
                                       world_width=world_width)
        return Level(
            world_width=world_width,
            world_height=world_h,
            slingshot_pos=(sx, sy),
            target=target,
            obstacles=[],
            inventory=inventory,
            inv_bodies=inv_bodies,
            starfield=starfield,
            solution_vx=sol_vx,
            solution_vy=sol_vy,
            belt_top_edge=belt_top_edge,
            belt_bot_edge=belt_bot_edge,
            belt_dots=belt_dots,
            orbit_pairs=[],
            corridor_bands=None,
            binary_star_pairs=[],
        )
    return None


def _orbit_showcase_variant(level_num):
    """Map level index to one of three planet+moon pair presets."""
    if level_num not in _ORBIT_SHOWCASE_LEVELS:
        return None
    return sorted(_ORBIT_SHOWCASE_LEVELS).index(level_num)


def _build_orbit_showcase_level(level_num, variant):
    """
    Hand-tuned levels with a moving moon obstacle (same motion model as the physics lab).
    Solvable only when inventory bodies are used (no bare-shot win).
    """
    play_h = RENDER_H - INVENTORY_H
    world_width = int(RENDER_W * 1.58)

    presets = [
        ("jupiter", "europa", 15.0, 0.072),
        ("saturn", "titan", 14.0, 0.066),
        ("neptune", "ganymede", 16.0, 0.068),
    ]
    pid, mid, base_r, omega = presets[variant % len(presets)]

    for seed in range(160):
        rng = random.Random(level_num * 9001 + seed * 131)
        belt_top_edge, belt_bot_edge = _make_belt_edges(
            world_width, base_top=26, base_bot=110, amplitude=7, rng=rng,
            min_corridor=78,
        )

        def corridor_mid(wx):
            xi = int(max(0, min(world_width - 1, int(wx))))
            return (belt_top_edge[xi] + belt_bot_edge[xi]) * 0.5

        sx = 22.0
        sy = corridor_mid(sx) + rng.uniform(-8.0, 8.0)
        sy = max(HUD_H + 18.0, min(play_h - 18.0, sy))
        tx = float(world_width - 22)
        ty = corridor_mid(tx) + rng.uniform(-14.0, 14.0)
        ty = max(HUD_H + 18.0, min(play_h - 18.0, ty))

        target = PlacedBody("earth", tx, ty, is_obstacle=False)

        cx_frac = rng.uniform(0.42, 0.58)
        cx = sx + (tx - sx) * cx_frac
        cy = corridor_mid(cx) + rng.uniform(-10.0, 10.0)
        cy = max(HUD_H + 28.0, min(play_h - 28.0, cy))
        orbit_r = base_r + rng.uniform(-1.5, 1.5)
        orbit_r = max(11.0, min(20.0, orbit_r))
        phase0 = rng.uniform(0.0, math.pi * 2.0)

        planet = PlacedBody(pid, cx, cy, is_obstacle=True)
        moon = PlacedBody(mid, cx + orbit_r, cy, is_obstacle=True)
        pair = OrbitObstaclePair(planet, moon, cx, cy, orbit_r, omega, phase0)
        pair.sync(0)
        obstacles = [planet, moon]

        inv_pool = [o for o in CELESTIAL_OBJECTS if o["mass_game"] >= 10]
        inv_objs = rng.sample(inv_pool, min(3, len(inv_pool)))
        inventory = [o["id"] for o in inv_objs]
        n_inv = len(inv_objs)
        used_xy = [(sx, sy), (tx, ty), (cx, cy)]
        inv_bodies = []
        jitter_x = 48.0
        jitter_y = 40.0
        for i, obj in enumerate(inv_objs):
            placed = False
            for _ in range(50):
                t_frac = (i + 1) / (n_inv + 1)
                bx = sx + (tx - sx) * t_frac + rng.uniform(-jitter_x, jitter_x)
                bx = max(50.0, min(world_width - 50.0, bx))
                by = (sy + ty) * 0.5 + rng.uniform(-jitter_y, jitter_y)
                by = max(HUD_H + 20.0, min(play_h - 20.0, by))
                if all(math.hypot(bx - px, by - py) > 28 for px, py in used_xy):
                    if math.hypot(bx - cx, by - cy) < orbit_r + 22:
                        continue
                    inv_bodies.append(PlacedBody(obj["id"], bx, by, is_obstacle=False))
                    used_xy.append((bx, by))
                    placed = True
                    break
            if not placed:
                inv_bodies = None
                break
        if not inv_bodies or len(inv_bodies) != n_inv:
            continue

        all_sim = inv_bodies + obstacles + [target]
        N_ANGLES = 64
        SPEED_VALS = [45, 65, 85, 105, 125, 150, 175, 200]
        a_min = -math.pi / 2.0
        a_max = math.pi / 2.0
        sol_vx = sol_vy = None
        for ai in range(N_ANGLES):
            ang = a_min + (a_max - a_min) * ai / (N_ANGLES - 1)
            for spd in SPEED_VALS:
                vx = spd * math.cos(ang)
                vy = spd * math.sin(ang)
                res, _, _ = simulate_ship(
                    sx, sy, vx, vy, all_sim, world_width,
                    belt_top_edge=belt_top_edge, belt_bot_edge=belt_bot_edge,
                    max_steps=4200, target=target, target_radius=14,
                    orbit_pairs=[pair],
                    world_height=play_h,
                )
                if res == "target":
                    sol_vx, sol_vy = vx, vy
                    break
            if sol_vx is not None:
                break
        if sol_vx is None:
            continue

        bare_solved = False
        for ai in range(40):
            ang = a_min + (a_max - a_min) * ai / 39.0
            for spd in SPEED_VALS:
                vx = spd * math.cos(ang)
                vy = spd * math.sin(ang)
                res, _, _ = simulate_ship(
                    sx, sy, vx, vy, obstacles + [target], world_width,
                    belt_top_edge=belt_top_edge, belt_bot_edge=belt_bot_edge,
                    max_steps=4200, target=target, target_radius=14,
                    orbit_pairs=[pair],
                    world_height=play_h,
                )
                if res == "target":
                    bare_solved = True
                    break
            if bare_solved:
                break
        if bare_solved:
            continue

        belt_rng = random.Random(level_num * 777 + seed)
        belt_dots = []
        for _ in range(int(world_width * 0.65)):
            bx = belt_rng.randint(0, world_width - 1)
            xi = min(bx, world_width - 1)
            top_h = belt_top_edge[xi]
            bot_h = play_h - belt_bot_edge[xi]
            total = top_h + bot_h
            if total < 2:
                continue
            if belt_rng.random() < top_h / total and top_h > 1:
                by = belt_rng.randint(0, max(1, int(top_h) - 1))
            elif bot_h > 1:
                by = belt_rng.randint(int(belt_bot_edge[xi]) + 1, play_h - 1)
            else:
                continue
            belt_dots.append((bx, by, belt_rng.randint(1, 2)))

        edge_w = min(72, max(24, world_width // 5))
        for _ in range(max(16, edge_w)):
            if belt_rng.random() < 0.5:
                bx = belt_rng.randint(0, min(edge_w - 1, world_width - 1))
            else:
                lo = max(0, world_width - edge_w)
                bx = belt_rng.randint(lo, world_width - 1)
            xi = min(bx, world_width - 1)
            top_h = belt_top_edge[xi]
            bot_h = play_h - belt_bot_edge[xi]
            total = top_h + bot_h
            if total < 2:
                continue
            if belt_rng.random() < top_h / total and top_h > 1:
                by = belt_rng.randint(0, max(1, int(top_h) - 1))
            elif bot_h > 1:
                by = belt_rng.randint(int(belt_bot_edge[xi]) + 1, play_h - 1)
            else:
                continue
            belt_dots.append((bx, by, belt_rng.randint(1, 2)))

        starfield = generate_starfield(play_h, seed=level_num * 1000 + seed,
                                       world_width=world_width)
        pair.sync(0)
        return Level(
            world_width=world_width,
            world_height=play_h,
            slingshot_pos=(sx, sy),
            target=target,
            obstacles=obstacles,
            inventory=inventory,
            inv_bodies=inv_bodies,
            starfield=starfield,
            solution_vx=sol_vx,
            solution_vy=sol_vy,
            belt_top_edge=belt_top_edge,
            belt_bot_edge=belt_bot_edge,
            belt_dots=belt_dots,
            orbit_pairs=[pair],
            corridor_bands=None,
            binary_star_pairs=[],
        )
    return None


def generate_level(level_num, rng=None):
    """
    Build a guaranteed-solvable horizontal level.
    Retries up to 25 times; falls back to a trivial level.
    """
    v = _orbit_showcase_variant(level_num)
    if v is not None:
        orbit_lvl = _build_orbit_showcase_level(level_num, v)
        if orbit_lvl is not None:
            return orbit_lvl

    if level_num in _BINARY_SUN_LEVELS:
        bl = _build_binary_sun_level(level_num)
        if bl is not None:
            return bl

    if level_num in _CORNER_CLIMB_LEVELS:
        cl = _build_corner_climb_level(level_num)
        if cl is not None:
            return cl

    if rng is None:
        rng = random.Random(level_num * 137 + 29)

    for attempt in range(25):
        result = _try_generate(level_num, rng, attempt)
        if result is not None:
            if level_num in _DUAL_CORRIDOR_LEVELS:
                loff = 88.0 + rng.uniform(0.0, 18.0)
                uoff = 10.0 + rng.uniform(0.0, 14.0)
                cand = _promote_level_dual_corridors(result, rng, loff, uoff)
                if _dual_level_passes_verify(cand):
                    return cand
            return result
    return _fallback_level(level_num)


def _make_belt_edges(world_width, base_top, base_bot, amplitude, rng,
                     drift=0.0, pinches=None, min_corridor=None, world_h=None):
    """
    Build irregular top/bottom belt edges.

    drift   – total vertical drift applied linearly left-to-right (positive = corridor
              slides downward; negative = upward).  Both edges shift together, so the
              corridor itself tilts but doesn't narrow from the drift alone.

    pinches – list of (cx, half_width, shift, side) tuples:
                cx         : world-x centre of the pinch
                half_width : half the x-extent over which the pinch spreads
                shift      : max pixels one wall juts into the corridor
                side       : -1 = top wall juts down, +1 = bottom wall juts up

    min_corridor – if set, overrides default minimum clear corridor height (pixels).

    Guarantees:
      - top edge stays below HUD_H + 3
      - bottom edge stays above world floor (default play_h − 4)
      - corridor is always at least min_corridor (or 55) pixels tall
    """
    play_h       = RENDER_H - INVENTORY_H
    wh           = float(world_h if world_h is not None else play_h)
    min_c        = 55 if min_corridor is None else int(min_corridor)

    def wave_params():
        return [
            (rng.uniform(0.012, 0.030), rng.uniform(0, math.pi * 2)),
            (rng.uniform(0.055, 0.110), rng.uniform(0, math.pi * 2)),
            (rng.uniform(0.160, 0.280), rng.uniform(0, math.pi * 2)),
        ]

    top_waves = wave_params()
    bot_waves = wave_params()

    top_edge = []
    bot_edge = []
    for x in range(world_width):
        t = x / max(world_width - 1, 1)   # 0 → 1 across level

        # Overlapping sine waves (independent for top and bottom)
        def wave(params):
            (f0, p0), (f1, p1), (f2, p2) = params
            return (amplitude * 0.55 * math.sin(f0*x + p0) +
                    amplitude * 0.30 * math.sin(f1*x + p1) +
                    amplitude * 0.15 * math.sin(f2*x + p2))

        # Shared tilt: both edges shift together proportionally
        tilt = drift * t

        ty = base_top  + wave(top_waves) + tilt
        by = base_bot  + wave(bot_waves) + tilt

        # Apply pinch zones
        if pinches:
            for (cx, hw, shift, side) in pinches:
                dx_pin = x - cx
                if abs(dx_pin) < hw:
                    # Smooth cosine falloff: 1 at centre, 0 at edges
                    env = 0.5 * (1.0 + math.cos(math.pi * dx_pin / hw))
                    if side == -1:
                        ty += shift * env   # top wall juts down
                    else:
                        by -= shift * env   # bottom wall juts up

        # Edge-weighted grit so far left/right stay jagged (not a smooth wash)
        de = float(min(x, world_width - 1 - x))
        edge_band = max(24.0, min(72.0, world_width * 0.22))
        edge_boost = 1.0 + 1.35 * max(0.0, 1.0 - de / edge_band) ** 1.4
        chip = ((((x * 1103515245) + 12345) >> 3) & 0xFFFF) / 32768.0 - 1.0
        ty += chip * 2.1 * edge_boost
        by -= chip * 0.75 * edge_boost

        # Clamp to world vertical extent
        ty = max(float(HUD_H + 3), ty)
        by = min(wh - 4.0, by)

        # Enforce minimum corridor
        if by - ty < min_c:
            deficit = min_c - (by - ty)
            ty -= deficit * 0.5
            by += deficit * 0.5
            ty = max(float(HUD_H + 3), ty)
            by = min(wh - 4.0, by)

        top_edge.append(ty)
        bot_edge.append(by)

    return top_edge, bot_edge


def _try_generate(level_num, rng, attempt_num):
    """
    Path-first generation with progressive difficulty.

    Two-tier difficulty:
      d in [0, 1]  — first 8 levels  (tier 1: easy → hard)
      d in [1, 2]  — levels 9 – 32   (tier 2: hard → brutal)
      d in [2, 3]  — levels 33+       (tier 3: brutal → merciless)

    Controlled by a square-root curve so early levels feel the ramp most.
    """
    play_h = RENDER_H - INVENTORY_H

    # ── Difficulty factor ──────────────────────────────────────────────────
    # Uncapped: d=1 at level 3, d=2 at level 12, d=3 at level 27.
    d = math.sqrt(level_num / 3.0)

    def lerp(a, b, t):
        return a + (b - a) * t

    def ramp(a, b, c, e, t):
        """Piecewise lerp through 4 waypoints at t = 0, 1, 2, 3."""
        if t <= 1.0:
            return lerp(a, b, t)
        elif t <= 2.0:
            return lerp(b, c, t - 1.0)
        else:
            return lerp(c, e, min(1.0, t - 2.0))

    # ── 1. World width scales with difficulty ──────────────────────────────
    # Tier 1: 1.0–1.1×  →  1.5–2.0×
    # Tier 2: 1.5–2.0×  →  2.2–3.0×
    # Tier 3: 2.2–3.0×  →  2.8–3.8×
    width_min = ramp(1.00, 1.50, 2.20, 2.80, d)
    width_max = ramp(1.10, 2.00, 3.00, 3.80, d)
    world_width = int(rng.uniform(width_min, width_max) * RENDER_W)

    # ── 2. Slingshot and target ────────────────────────────────────────────
    # Vertical jitter grows with difficulty (harder to line up a straight shot)
    vert_jitter = ramp(18, 30, 40, 52, d)
    sx = 22
    sy = play_h / 2.0 + rng.uniform(-vert_jitter, vert_jitter)
    sy = max(HUD_H + 16, min(play_h - 16, sy))

    tx = world_width - 22
    ty = play_h / 2.0 + rng.uniform(-vert_jitter, vert_jitter)
    ty = max(HUD_H + 16, min(play_h - 16, ty))

    target_pool = [o for o in CELESTIAL_OBJECTS if o["is_large"] and o["id"] != "sun"]
    t_obj  = rng.choice(target_pool)
    target = PlacedBody(t_obj["id"], tx, ty, is_obstacle=False)

    # ── 3. Randomly place inventory bodies ────────────────────────────────
    # Body count: tier 1 → 1-4, tier 2+ stays at 4 (placement gets much harder)
    max_inv = min(4, 2 + int(d * 2))  # 2 at d=0, 4 at d=1+
    inv_pool = [o for o in CELESTIAL_OBJECTS if o["mass_game"] >= 10]
    n_inv    = rng.randint(1, max_inv)
    inv_objs = rng.sample(inv_pool, min(n_inv, len(inv_pool)))
    inventory = [o["id"] for o in inv_objs]

    # Placement jitter grows — in hard tiers objects are spread further apart
    jitter_x = ramp(25, 45, 65, 80, d)
    jitter_y = ramp(28, 45, 58, 70, d)

    used_xy    = [(sx, sy), (tx, ty)]
    inv_bodies = []
    for i, obj in enumerate(inv_objs):
        placed = False
        for _ in range(40):
            t_frac = (i + 1) / (n_inv + 1)
            bx = sx + (tx - sx) * t_frac + rng.uniform(-jitter_x, jitter_x)
            bx = max(45, min(world_width - 45, bx))
            by = (sy + ty) / 2.0 + rng.uniform(-jitter_y, jitter_y)
            by = max(HUD_H + 16, min(play_h - 16, by))
            if all(math.sqrt((bx - px)**2 + (by - py)**2) > 24 for px, py in used_xy):
                inv_bodies.append(PlacedBody(obj["id"], bx, by, is_obstacle=False))
                used_xy.append((bx, by))
                placed = True
                break
        if not placed:
            return None

    # ── 4. Find a solution trajectory using those bodies ──────────────────
    # Search free-space (no belt yet) — belt is built from the winner.
    all_sim    = inv_bodies + [target]
    N_ANGLES   = 60
    SPEED_VALS = [45, 65, 85, 105, 125, 150, 175, 200]

    sol_vx = sol_vy = None
    sol_path = None

    for ai in range(N_ANGLES):
        ang = -math.pi / 2.0 + math.pi * ai / (N_ANGLES - 1)
        for spd in SPEED_VALS:
            vx = spd * math.cos(ang)
            vy = spd * math.sin(ang)
            res, _, path = simulate_ship(
                sx, sy, vx, vy, all_sim, world_width,
                max_steps=3600, target=target, target_radius=14,
            )
            if res == "target" and len(path) > 2:
                # Discard paths that wander outside the visible play area
                if all(HUD_H <= py <= play_h for _, py in path):
                    sol_vx, sol_vy = vx, vy
                    sol_path = path
                    break
        if sol_vx is not None:
            break

    if sol_path is None:
        return None

    # ── 5. Build belt walls tightly around the solution path ──────────────
    # Accumulate the min and max y reached at each x column.
    path_min_y = [None] * world_width
    path_max_y = [None] * world_width
    for (px, py) in sol_path:
        xi = int(max(0, min(world_width - 1, px)))
        if path_min_y[xi] is None:
            path_min_y[xi] = py
            path_max_y[xi] = py
        else:
            path_min_y[xi] = min(path_min_y[xi], py)
            path_max_y[xi] = max(path_max_y[xi], py)

    # Force slingshot and target endpoints into the arrays
    for fx, fy in [(sx, sy), (tx, ty)]:
        xi = int(max(0, min(world_width - 1, fx)))
        if path_min_y[xi] is None:
            path_min_y[xi] = fy
            path_max_y[xi] = fy
        else:
            path_min_y[xi] = min(path_min_y[xi], fy)
            path_max_y[xi] = max(path_max_y[xi], fy)

    # Linear interpolation for columns not visited by the path
    def _fill(arr, default):
        result = list(arr)
        known  = [i for i, v in enumerate(result) if v is not None]
        if not known:
            return [default] * len(result)
        for i in range(known[0]):
            result[i] = result[known[0]]
        for i in range(known[-1] + 1, len(result)):
            result[i] = result[known[-1]]
        for k in range(len(known) - 1):
            x0, x1 = known[k], known[k + 1]
            y0, y1 = result[x0], result[x1]
            for x in range(x0 + 1, x1):
                t = (x - x0) / (x1 - x0)
                result[x] = y0 + (y1 - y0) * t
        return result

    pmin = _fill(path_min_y, play_h / 2.0)
    pmax = _fill(path_max_y, play_h / 2.0)

    # Belt walls = path extents ± margin + layered noise for a jagged, rocky look
    # Margin shrinks hard through all tiers
    margin_lo = ramp(24, 14,  8,  5, d)
    margin_hi = ramp(34, 22, 13,  9, d)
    MARGIN = rng.uniform(margin_lo, margin_hi)

    # Sine wave amplitudes grow in harder tiers, making walls more jagged/unpredictable
    wave_amp_lo = ramp( 9.0,  9.0, 13.0, 18.0, d)
    wave_amp_mi = ramp( 6.0,  6.0,  9.0, 13.0, d)
    wave_amp_hi = ramp( 4.0,  4.0,  6.0,  9.0, d)

    # Three overlapping sine waves per edge (low, mid, high frequency)
    tw = [(rng.uniform(0.010, 0.025), rng.uniform(0, math.pi * 2), wave_amp_lo),
          (rng.uniform(0.055, 0.110), rng.uniform(0, math.pi * 2), wave_amp_mi),
          (rng.uniform(0.180, 0.340), rng.uniform(0, math.pi * 2), wave_amp_hi)]
    bw = [(rng.uniform(0.010, 0.025), rng.uniform(0, math.pi * 2), wave_amp_lo),
          (rng.uniform(0.055, 0.110), rng.uniform(0, math.pi * 2), wave_amp_mi),
          (rng.uniform(0.180, 0.340), rng.uniform(0, math.pi * 2), wave_amp_hi)]

    # Minimum corridor shrinks across all tiers — never below 26px (survivable but brutal)
    min_corridor = int(ramp(62, 38, 30, 26, d)) + 2 * (FRINGE_COLLISION + SHIP_RADIUS)

    # Value noise amplitude also grows, adding organic spikes to the wall
    vnoise_amp = ramp(6.0, 6.0, 9.0, 12.0, d)
    _ns = 10   # one control point every 10 pixels
    _np = world_width // _ns + 2
    tn_pts = [rng.uniform(-vnoise_amp, vnoise_amp) for _ in range(_np)]
    bn_pts = [rng.uniform(-vnoise_amp, vnoise_amp) for _ in range(_np)]

    def _vnoise(pts, x):
        ni  = x / _ns
        i0  = int(ni)
        i1  = min(i0 + 1, len(pts) - 1)
        nt  = ni - i0
        return pts[i0] * (1 - nt) + pts[i1] * nt

    belt_top_edge = []
    belt_bot_edge = []
    edge_band = max(28.0, min(80.0, world_width * 0.24))
    for x in range(world_width):
        top_wave = sum(amp * math.sin(f * x + ph) for f, ph, amp in tw)
        bot_wave = sum(amp * math.sin(f * x + ph) for f, ph, amp in bw)
        top = pmin[x] - MARGIN + top_wave + _vnoise(tn_pts, x)
        bot = pmax[x] + MARGIN + bot_wave + _vnoise(bn_pts, x)
        # Stronger grit near world x≈0 and x≈max so scrolling edges stay rocky
        de = float(min(x, world_width - 1 - x))
        edge_boost = 1.0 + 1.45 * max(0.0, 1.0 - de / edge_band) ** 1.45
        h = (x * 1664525 + attempt_num * 719393 + level_num * 1013904223) & 0xFFFFFF
        chip_t = (h % 5001) / 2500.0 - 1.0
        chip_b = ((h >> 11) % 5001) / 2500.0 - 1.0
        top += chip_t * 3.0 * edge_boost
        bot += chip_b * 2.4 * edge_boost
        top = max(float(HUD_H + 3), top)
        bot = min(float(play_h - 4), bot)
        if bot - top < min_corridor:
            mid = (top + bot) / 2.0
            half = min_corridor / 2.0
            top = max(float(HUD_H + 3), mid - half)
            bot = min(float(play_h - 4), mid + half)
        belt_top_edge.append(top)
        belt_bot_edge.append(bot)

    # ── 6. Bare check: level must be impossible without any placed body ────
    bare_sim    = [target]
    BARE_ANGLES = 48
    BARE_SPEEDS = [35, 60, 85, 110, 135, 160, 185, 200]
    a_min = -math.pi / 2.0
    a_max =  math.pi / 2.0

    bare_solved = False
    for ai in range(BARE_ANGLES):
        ang = a_min + (a_max - a_min) * ai / (BARE_ANGLES - 1)
        for spd in BARE_SPEEDS:
            res, _, _ = simulate_ship(
                sx, sy, spd * math.cos(ang), spd * math.sin(ang),
                bare_sim, world_width,
                belt_top_edge=belt_top_edge, belt_bot_edge=belt_bot_edge,
                max_steps=3600, target=target, target_radius=14,
                world_height=play_h,
            )
            if res == "target":
                bare_solved = True
                break
        if bare_solved:
            break

    if bare_solved:
        return None

    # ── 7. Belt visual dots ────────────────────────────────────────────────
    belt_rng  = random.Random(level_num * 777 + attempt_num)
    belt_dots = []
    for _ in range(int(world_width * 0.7)):
        bx  = belt_rng.randint(0, world_width - 1)
        xi  = min(bx, world_width - 1)
        top_h = belt_top_edge[xi]
        bot_h = play_h - belt_bot_edge[xi]
        total = top_h + bot_h
        if total < 2:
            continue
        if belt_rng.random() < top_h / total and top_h > 1:
            by = belt_rng.randint(0, max(1, int(top_h) - 1))
        elif bot_h > 1:
            by = belt_rng.randint(int(belt_bot_edge[xi]) + 1, play_h - 1)
        else:
            continue
        belt_dots.append((bx, by, belt_rng.randint(1, 2)))

    # Extra rocks hugging world edges (visible when camera is at scroll limits)
    edge_w = min(72, max(24, world_width // 5))
    for _ in range(max(18, edge_w)):
        if belt_rng.random() < 0.5:
            bx = belt_rng.randint(0, min(edge_w - 1, world_width - 1))
        else:
            lo = max(0, world_width - edge_w)
            bx = belt_rng.randint(lo, world_width - 1)
        xi = min(bx, world_width - 1)
        top_h = belt_top_edge[xi]
        bot_h = play_h - belt_bot_edge[xi]
        total = top_h + bot_h
        if total < 2:
            continue
        if belt_rng.random() < top_h / total and top_h > 1:
            by = belt_rng.randint(0, max(1, int(top_h) - 1))
        elif bot_h > 1:
            by = belt_rng.randint(int(belt_bot_edge[xi]) + 1, play_h - 1)
        else:
            continue
        belt_dots.append((bx, by, belt_rng.randint(1, 2)))

    # ── 8. Build level ─────────────────────────────────────────────────────
    starfield = generate_starfield(play_h, seed=level_num * 1000 + attempt_num,
                                   world_width=world_width)
    return Level(
        world_width=world_width,
        world_height=play_h,
        slingshot_pos=(sx, sy),
        target=target,
        obstacles=[],
        inventory=inventory,
        inv_bodies=inv_bodies,
        starfield=starfield,
        solution_vx=sol_vx,
        solution_vy=sol_vy,
        belt_top_edge=belt_top_edge,
        belt_bot_edge=belt_bot_edge,
        belt_dots=belt_dots,
        orbit_pairs=[],
        corridor_bands=None,
        binary_star_pairs=[],
    )


def _fallback_level(level_num):
    """Guaranteed trivial level when generation keeps failing."""
    play_h      = RENDER_H - INVENTORY_H
    world_width = RENDER_W
    rng_fb      = random.Random(level_num + 1)
    belt_top_edge, belt_bot_edge = _make_belt_edges(
        world_width, base_top=32, base_bot=102, amplitude=8, rng=rng_fb
    )
    cy = (belt_top_edge[22] + belt_bot_edge[22]) / 2
    starfield = generate_starfield(play_h, seed=level_num, world_width=world_width)
    target    = PlacedBody("earth", world_width - 22, cy)
    helper    = PlacedBody("jupiter", world_width // 2, cy - 18)
    belt_rng  = random.Random(level_num * 31)
    belt_dots = []
    for _ in range(60):
        bx = belt_rng.randint(0, world_width - 1)
        xi = min(bx, world_width - 1)
        if belt_top_edge[xi] > 2:
            by = belt_rng.randint(0, max(1, int(belt_top_edge[xi]) - 1))
            belt_dots.append((bx, by, belt_rng.randint(1, 2)))
    edge_w = min(48, world_width // 3)
    for _ in range(24):
        bx = belt_rng.randint(0, edge_w - 1) if belt_rng.random() < 0.5 else belt_rng.randint(
            max(0, world_width - edge_w), world_width - 1)
        xi = min(bx, world_width - 1)
        if belt_top_edge[xi] > 2:
            by = belt_rng.randint(0, max(1, int(belt_top_edge[xi]) - 1))
            belt_dots.append((bx, by, belt_rng.randint(1, 2)))
    return Level(
        world_width=world_width,
        world_height=play_h,
        slingshot_pos=(22, cy),
        target=target,
        obstacles=[],
        inventory=["jupiter"],
        inv_bodies=[helper],
        starfield=starfield,
        solution_vx=80.0,
        solution_vy=0.0,
        belt_top_edge=belt_top_edge,
        belt_bot_edge=belt_bot_edge,
        belt_dots=belt_dots,
        orbit_pairs=[],
        corridor_bands=None,
        binary_star_pairs=[],
    )

# ─────────────────────────────────────────────────────────────────────────────
#  EXPLOSION PARTICLE SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

class Particle:
    __slots__ = ["x","y","vx","vy","life","max_life","color","size"]
    def __init__(self, x, y, vx, vy, life, color, size=1):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.life = life
        self.max_life = life
        self.color = color
        self.size = size

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.05   # slight gravity on particles
        self.life -= 1
        return self.life > 0

    def draw(self, surface, camera_x=0.0, camera_y=0.0, cam_zoom=1.0):
        z = max(0.35, min(cam_zoom, 2.8))
        sx = (self.x - camera_x) / z
        sy = (self.y - camera_y) / z
        if 0 <= sx <= RENDER_W and 0 <= sy <= RENDER_H:
            if self.size == 1:
                surface.set_at((int(sx), int(sy)), self.color)
            else:
                pygame.draw.circle(surface, self.color, (int(sx), int(sy)), self.size)


def spawn_explosion(x, y):
    particles = []
    colors = [C_EXPLOSION1, C_EXPLOSION2, C_EXPLOSION3, C_YELLOW, C_WHITE]
    for _ in range(40):
        angle = random.uniform(0, math.pi*2)
        speed = random.uniform(0.5, 3.5)
        vx = math.cos(angle) * speed
        vy = math.sin(angle) * speed
        life = random.randint(15, 35)
        color = random.choice(colors)
        size = random.randint(1, 2)
        particles.append(Particle(x, y, vx, vy, life, color, size))
    return particles

# ─────────────────────────────────────────────────────────────────────────────
#  LANDING FLASH EFFECT
# ─────────────────────────────────────────────────────────────────────────────

class LandingFlash:
    def __init__(self):
        self.active = False
        self.timer = 0
        self.duration = 90   # frames

    def trigger(self):
        self.active = True
        self.timer = self.duration

    def update(self):
        if self.active:
            self.timer -= 1
            if self.timer <= 0:
                self.active = False

    def draw(self, surface):
        if not self.active:
            return
        t = self.timer / self.duration
        phase = self.duration - self.timer

        # Flash white
        if phase < 10:
            alpha = int(255 * (1 - phase/10))
            flash = pygame.Surface((RENDER_W, RENDER_H))
            flash.fill(C_WHITE)
            flash.set_alpha(alpha)
            surface.blit(flash, (0,0))

        # Sparkle burst after flash — WIN text is shown by GameState render
        if 10 <= phase < 40:
            for i in range(6):
                angle = math.pi * 2 * i / 6 + phase * 0.1
                px = int(RENDER_W // 2 + math.cos(angle) * (phase - 10))
                py = int((RENDER_H - INVENTORY_H) // 2 + math.sin(angle) * (phase - 10) * 0.5)
                if 0 <= px < RENDER_W and 0 <= py < RENDER_H:
                    pygame.draw.circle(surface, C_YELLOW, (px, py), 2)

# ─────────────────────────────────────────────────────────────────────────────
#  MAIN GAME STATE
# ─────────────────────────────────────────────────────────────────────────────

class GameState:
    """
    Core gameplay screen.
    States: "aim" → "flying" → "exploding" → "aim"
                                           → "landed" → next level
    """
    def __init__(self, ship_idx=0):
        self.ship_idx = ship_idx
        self.ship = SHIPS[ship_idx]
        self.ship_sprite = SHIP_SPRITES[self.ship["name"]]

        self.level_num = 0
        self.level = generate_level(self.level_num)

        # Reset per-level state
        self._reset_level()

    def _reset_level(self):
        lvl = self.level
        self.placed_bodies = []          # bodies placed by player this attempt
        self.inv_remaining = list(lvl.inventory)   # obj_ids left in inventory

        # Ship state
        self.ship_x = float(lvl.slingshot_pos[0])
        self.ship_y = float(lvl.slingshot_pos[1])
        self.ship_vx = 0.0
        self.ship_vy = 0.0

        # Camera (world scroll); cam_zoom > 1 = zoom out (more world in view)
        self.cam_zoom = 1.0
        self.dragging_cam = False
        self._cam_drag_mx = 0.0
        self._cam_drag_my = 0.0
        self._cam_drag_start_x = 0.0
        self._cam_drag_start_y = 0.0
        play_h = float(RENDER_H - INVENTORY_H)
        z = self._cam_z()
        max_cx = max(0.0, float(lvl.world_width) - RENDER_W / z)
        self.camera_x = max(0.0, min(max_cx,
                                     float(lvl.slingshot_pos[0]) - 0.5 * RENDER_W * z))
        self.camera_y = max(0.0, min(float(lvl.world_height) - play_h / z,
                                       float(lvl.slingshot_pos[1]) - 0.5 * play_h / z))

        # State machine
        self.state = "aim"   # "aim" | "flying" | "exploding" | "landed" | "won"

        # Aim / power controls — default to pointing at target on a fresh level
        lvl = self.level
        dx0 = lvl.target.x - lvl.slingshot_pos[0]
        dy0 = lvl.target.y - lvl.slingshot_pos[1]
        self.aim_angle    = math.atan2(dy0, dx0)
        self.launch_power = 0.5
        self._last_aim_angle    = self.aim_angle    # persisted across attempts
        self._last_launch_power = self.launch_power
        self.dragging_aim   = False
        self.dragging_power = False
        self.power_drag_start_x   = 0.0
        self.power_drag_start_val = 0.5

        # Inventory drag (placing a new body)
        self.dragging_inv = False
        self.drag_inv_idx = None
        self.drag_x = 0.0
        self.drag_y = 0.0

        # Placed-body drag (repositioning or returning an already-placed body)
        self.dragging_placed     = False
        self.drag_placed_idx     = None    # index into self.placed_bodies
        self.drag_placed_x       = 0.0    # current world-x while dragging
        self.drag_placed_y       = 0.0    # current world-y while dragging

        # Trajectory preview cache (always computed in aim state)
        self.traj_points = []

        # Particles
        self.particles = []

        # Landing effect
        self.landing_flash = LandingFlash()

        # Orbit phase (float tick); moon/planet positions = f(orbit_t) like the physics lab
        self.orbit_t = 0.0
        if self.level.orbit_pairs or self.level.binary_star_pairs:
            self.level.sync_orbits(self.orbit_t)

        # Attempts counter
        self.level.attempt += 1

    @staticmethod
    def _inv_remaining_for_placed(lvl_inventory, placed_bodies):
        """Which inventory slots are still in the bar after bodies are on the field."""
        placed_n = {}
        for b in placed_bodies:
            placed_n[b.obj_id] = placed_n.get(b.obj_id, 0) + 1
        used = {k: 0 for k in placed_n}
        out = []
        for oid in lvl_inventory:
            if used.get(oid, 0) < placed_n.get(oid, 0):
                used[oid] = used.get(oid, 0) + 1
            else:
                out.append(oid)
        return out

    def _reset_attempt(self, clear_placements=False):
        """Keep level + attempt count; reset ship. Planets stay put unless clear_placements."""
        lvl = self.level
        if clear_placements:
            self.placed_bodies = []
            self.inv_remaining = list(lvl.inventory)
        else:
            self.inv_remaining = self._inv_remaining_for_placed(lvl.inventory,
                                                                 self.placed_bodies)
        self.ship_x = float(lvl.slingshot_pos[0])
        self.ship_y = float(lvl.slingshot_pos[1])
        self.ship_vx = 0.0
        self.ship_vy = 0.0
        play_h = float(RENDER_H - INVENTORY_H)
        z = self._cam_z()
        max_cx = max(0.0, float(lvl.world_width) - RENDER_W / z)
        self.camera_x = max(0.0, min(max_cx,
                                     float(lvl.slingshot_pos[0]) - 0.5 * RENDER_W * z))
        self.camera_y = max(0.0, min(float(lvl.world_height) - play_h / z,
                                     float(lvl.slingshot_pos[1]) - 0.5 * play_h / z))
        self.state = "aim"
        # Restore the aim/power settings from the last launched attempt
        self.aim_angle    = self._last_aim_angle
        self.launch_power = self._last_launch_power
        self.dragging_aim    = False
        self.dragging_power  = False
        self.dragging_inv    = False
        self.drag_inv_idx    = None
        self.dragging_placed = False
        self.drag_placed_idx = None
        self.traj_points = []
        self.particles = []
        self.level.attempt += 1

    def _all_bodies(self):
        """Return all active bodies: placed by player + obstacles + target."""
        return self.placed_bodies + self.level.obstacles + [self.level.target]

    def _bodies_for_trajectory_preview(self):
        """
        Bodies used for the aim dotted-line preview. While dragging a placed body
        or a new body from inventory, includes the ghost at the cursor so the
        trajectory updates live.
        """
        placed = []
        for i, b in enumerate(self.placed_bodies):
            if self.dragging_placed and self.drag_placed_idx == i:
                wx, wy = self._screen_to_world(self.drag_placed_x, self.drag_placed_y)
                placed.append(PlacedBody(b.obj_id, wx, wy, b.is_obstacle))
            else:
                placed.append(b)
        out = placed + self.level.obstacles + [self.level.target]
        if (self.dragging_inv and self.drag_inv_idx is not None
                and self.drag_inv_idx < len(self.inv_remaining)):
            if self.drag_y < RENDER_H - INVENTORY_H - 5:
                oid = self.inv_remaining[self.drag_inv_idx]
                wx, wy = self._screen_to_world(self.drag_x, self.drag_y)
                out = placed + [PlacedBody(oid, wx, wy, is_obstacle=False)]
                out += self.level.obstacles + [self.level.target]
        return out

    # ── Physics ─────────────────────────────────────────────────────────────
    def _compute_accel(self, sx, sy):
        """
        Compute total gravitational acceleration on ship at (sx,sy).
        
        a⃗ = Σᵢ G·mᵢ·r̂ᵢ / (|r⃗ᵢ|² + ε²)
        
        where ε² = SOFTENING_SQ prevents singularity at r→0.
        """
        ax, ay = 0.0, 0.0
        for body in self._all_bodies():
            rx = body.x - sx
            ry = body.y - sy
            dist_sq = rx*rx + ry*ry + SOFTENING_SQ
            dist = math.sqrt(dist_sq)
            a_mag = G_CONSTANT * body.mass / dist_sq
            ax += a_mag * rx / dist
            ay += a_mag * ry / dist
        return ax, ay

    # ── Input ────────────────────────────────────────────────────────────────
    def handle_event(self, event, mouse_render):
        """
        mouse_render: mouse pos in render-space coordinates.

        Aim control layout (in aim state):
          • Drag the YELLOW AIM HANDLE (circle at arrow tip) → rotate aim angle.
          • Drag the POWER SLIDER (vertical bar right of slingshot) → set power.
          • Click slingshot body OR press SPACE → fire.
          • Drag from inventory slot onto level → place gravity body.
          • Mouse wheel / ← → arrows → manual horizontal scroll.
        """
        mx, my = mouse_render

        # ── Win screen ────────────────────────────────────────────────────
        if self.state == "won":
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
                self._next_level()
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.state != "aim":
                return

            # ── 1. Placed-body drag (reposition or return to hand) ────────
            placed_hit = self._get_placed_body_at(mx, my)
            if placed_hit is not None and my < RENDER_H - INVENTORY_H:
                self.dragging_placed = True
                self.drag_placed_idx = placed_hit
                body = self.placed_bodies[placed_hit]
                self.drag_placed_x, self.drag_placed_y = self._world_to_screen(body.x, body.y)
                return

            # ── 2. Inventory-slot drag (place new body) ───────────────────
            inv_slot = self._get_inv_slot_at(mx, my)
            if inv_slot is not None:
                self.dragging_inv   = True
                self.drag_inv_idx   = inv_slot
                self.drag_x, self.drag_y = mx, my
                return

            # ── 3. Power slider handle (small, check before open-field aim) ──
            phx, phy = self._power_handle_screen()
            if math.sqrt((mx - phx)**2 + (my - phy)**2) < 12:
                self.dragging_power       = True
                self.power_drag_start_x   = mx
                self.power_drag_start_val = self.launch_power
                return

            # ── 4. Click slingshot body → fire ─────────────────────────────
            ssx_f, ssy_f = self._sling_screen()
            if math.sqrt((mx - ssx_f)**2 + (my - ssy_f)**2) < 10:
                self._launch_ship()
                return

            # ── 5. Click anywhere in play area → start aim drag ────────────
            # Do NOT snap the angle on click — only update on mouse movement,
            # so grabbing the arrow mid-shaft doesn't teleport it.
            play_h = RENDER_H - INVENTORY_H
            if my < play_h:
                self.dragging_aim = True

        elif event.type == pygame.MOUSEMOTION:
            if self.dragging_cam and self.state == "aim":
                z = self._cam_z()
                play_h = float(RENDER_H - INVENTORY_H)
                dx = (self._cam_drag_mx - mx) * z
                dy = (self._cam_drag_my - my) * z
                max_cx = max(0.0, float(self.level.world_width) - RENDER_W / z)
                max_cy = max(0.0, float(self.level.world_height) - play_h / z)
                self.camera_x = max(0.0, min(max_cx, self._cam_drag_start_x + dx))
                self.camera_y = max(0.0, min(max_cy, self._cam_drag_start_y + dy))
                self.traj_points = []

            elif self.dragging_placed:
                # Track cursor in screen space; commit to world on release
                self.drag_placed_x = mx
                self.drag_placed_y = my

            elif self.dragging_aim:
                ssx, ssy = self._sling_screen()
                dx, dy = mx - ssx, my - ssy
                if dx*dx + dy*dy > 4:
                    self.aim_angle = math.atan2(dy, dx)
                self.traj_points = []

            elif self.dragging_power:
                delta = mx - self.power_drag_start_x
                # Map drag distance to bar width for natural feel
                self.launch_power = max(0.0, min(1.0,
                    self.power_drag_start_val + delta / self.POWER_BAR_W))
                self.traj_points = []

            elif self.dragging_inv:
                self.drag_x, self.drag_y = mx, my

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging_aim   = False
            self.dragging_power = False

            if self.dragging_placed and self.drag_placed_idx is not None:
                self.dragging_placed = False
                idx = self.drag_placed_idx
                self.drag_placed_idx = None
                if my >= RENDER_H - INVENTORY_H:
                    # Dropped into inventory bar → return to hand
                    obj_id = self.placed_bodies[idx].obj_id
                    self.placed_bodies.pop(idx)
                    self.inv_remaining.append(obj_id)
                else:
                    # Dropped in play area → update world position
                    drop_x, drop_y = self._screen_to_world(mx, my)
                    self.placed_bodies[idx].x = drop_x
                    self.placed_bodies[idx].y = drop_y
                self.traj_points = []

            elif self.dragging_inv and self.drag_inv_idx is not None:
                self.dragging_inv = False
                if my < RENDER_H - INVENTORY_H - 5:
                    obj_id = self.inv_remaining[self.drag_inv_idx]
                    drop_x, drop_y = self._screen_to_world(mx, my)
                    self.placed_bodies.append(
                        PlacedBody(obj_id, drop_x, drop_y, is_obstacle=False)
                    )
                    self.inv_remaining.pop(self.drag_inv_idx)
                    self.traj_points = []
                self.drag_inv_idx = None
                self.dragging_inv = False

        elif event.type == pygame.MOUSEWHEEL:
            if self.state == "aim" and not self.dragging_inv:
                z = self._cam_z()
                play_h = float(RENDER_H - INVENTORY_H)
                scroll_amt = -event.y * 14
                keys = pygame.key.get_pressed()
                if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                    max_cy = max(0.0, self.level.world_height - play_h / z)
                    self.camera_y = max(0.0, min(max_cy, self.camera_y + scroll_amt))
                else:
                    max_cam = max(0.0, float(self.level.world_width - RENDER_W / z))
                    self.camera_x = max(0.0, min(max_cam, self.camera_x + scroll_amt))
                self.traj_points = []

        elif getattr(pygame, "MULTIGESTURE", None) is not None and event.type == pygame.MULTIGESTURE:
            if self.state == "aim" and my < RENDER_H - INVENTORY_H:
                dd = float(getattr(event, "dDist", 0.0) or 0.0)
                if abs(dd) > 0.0002:
                    self.cam_zoom = max(0.35, min(2.8, self.cam_zoom * (1.0 + dd)))
                    self.traj_points = []

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 2:
            if self.state == "aim" and my < RENDER_H - INVENTORY_H:
                self.dragging_cam = True
                self._cam_drag_mx = float(mx)
                self._cam_drag_my = float(my)
                self._cam_drag_start_x = self.camera_x
                self._cam_drag_start_y = self.camera_y

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 2:
            self.dragging_cam = False

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_c and self.state == "aim":
                self.cam_zoom = 1.0
                self.traj_points = []
            if event.key == pygame.K_r and self.state == "aim":
                self._reset_attempt(clear_placements=True)
            if event.key == pygame.K_s:
                self._next_level()
            if event.key == pygame.K_SPACE and self.state == "aim":
                self._launch_ship()
            # UP/DOWN adjust power by 1% per tap (held-down handled in update)
            if self.state == "aim":
                if event.key == pygame.K_UP:
                    self.launch_power = min(1.0, self.launch_power + 0.01)
                    self.traj_points = []
                elif event.key == pygame.K_DOWN:
                    self.launch_power = max(0.0, self.launch_power - 0.01)
                    self.traj_points = []

    def _get_inv_slot_at(self, mx, my):
        """Return index into inv_remaining if click is on an inventory slot, else None."""
        if my < RENDER_H - INVENTORY_H:
            return None
        slot_w  = 56
        start_x = 5
        for i, obj_id in enumerate(self.inv_remaining):
            sx = start_x + i * slot_w
            if sx <= mx <= sx + slot_w - 4:
                return i
        return None

    def _cam_z(self):
        return max(0.35, min(self.cam_zoom, 2.8))

    def _get_placed_body_at(self, mx, my):
        """
        Return index into self.placed_bodies whose sprite is near screen pos (mx,my),
        or None. Only checked while in aim state (before launch).
        """
        world_x, world_y = self._screen_to_world(mx, my)
        for i, body in enumerate(self.placed_bodies):
            r = body.radius + 5   # generous hit radius
            if (world_x - body.x)**2 + (world_y - body.y)**2 < r * r:
                return i
        return None

    def _world_to_screen(self, wx, wy):
        """World → render-surface coords (accounts for camera + zoom)."""
        z = self._cam_z()
        return ((wx - self.camera_x) / z, (wy - self.camera_y) / z)

    def _screen_to_world(self, sx, sy):
        z = self._cam_z()
        return (sx * z + self.camera_x, sy * z + self.camera_y)

    # ── Launch speed constants ────────────────────────────────────────────────
    LAUNCH_MIN_SPEED = 35.0
    LAUNCH_MAX_SPEED = 200.0
    AIM_ARROW_LEN    = 35   # screen pixels for the aim-direction arrow
    POWER_BAR_W      = 50   # width  of power slider (horizontal bar below slingshot)
    POWER_BAR_H      = 8    # height of power slider

    def _launch_speed(self):
        return (self.LAUNCH_MIN_SPEED
                + self.launch_power * (self.LAUNCH_MAX_SPEED - self.LAUNCH_MIN_SPEED))

    def _launch_ship(self):
        """Fire using current aim_angle + launch_power. Remember settings for next attempt."""
        # Persist so the next attempt starts with the same aim/power
        self._last_aim_angle    = self.aim_angle
        self._last_launch_power = self.launch_power
        spd = self._launch_speed()
        self.ship_vx = spd * math.cos(self.aim_angle)
        self.ship_vy = spd * math.sin(self.aim_angle)
        self.ship_x  = float(self.level.slingshot_pos[0])
        self.ship_y  = float(self.level.slingshot_pos[1])
        self.state   = "flying"
        self.traj_points = []

    def _update_trajectory_preview(self):
        """
        Simulate TRAJ_STEPS of ship trajectory using aim_angle + launch_power.
        Uses same Symplectic-Euler physics as actual flight.
        """
        spd = self._launch_speed()
        pvx = spd * math.cos(self.aim_angle)
        pvy = spd * math.sin(self.aim_angle)

        all_bodies = self._bodies_for_trajectory_preview()
        sx = float(self.level.slingshot_pos[0])
        sy = float(self.level.slingshot_pos[1])
        self.traj_points = []
        wh = float(self.level.world_height)
        base_t = self.orbit_t
        try:
            for i in range(TRAJ_STEPS):
                if self.level.orbit_pairs or self.level.binary_star_pairs:
                    # Mid-frame sample so preview matches multi-substep flight
                    self.level.sync_orbits(base_t + i + 0.5)
                ax, ay = 0.0, 0.0
                for body in all_bodies:
                    rx = body.x - sx
                    ry = body.y - sy
                    dist_sq = rx*rx + ry*ry + SOFTENING_SQ
                    dist    = math.sqrt(dist_sq)
                    a_mag   = G_CONSTANT * body.mass / dist_sq
                    ax += a_mag * rx / dist
                    ay += a_mag * ry / dist
                pvx += ax * PHYS_DT
                pvy += ay * PHYS_DT
                sx  += pvx * PHYS_DT
                sy  += pvy * PHYS_DT
                self.traj_points.append((sx, sy))
                if (sx < -30 or sx > self.level.world_width + 30
                        or sy < -30 or sy > wh + 30
                        or not self.level.ship_in_corridor(sx, sy)):
                    break
        finally:
            if self.level.orbit_pairs or self.level.binary_star_pairs:
                self.level.sync_orbits(base_t)

    def _sling_screen(self):
        """Screen coords of the slingshot."""
        return self._world_to_screen(self.level.slingshot_pos[0],
                                     self.level.slingshot_pos[1])

    def _aim_tip_screen(self):
        """Screen coords of the draggable aim handle."""
        ssx, ssy = self._sling_screen()
        return (ssx + self.AIM_ARROW_LEN * math.cos(self.aim_angle),
                ssy + self.AIM_ARROW_LEN * math.sin(self.aim_angle))

    POWER_BAR_OFFSET = -8   # bar starts this many px left of slingshot centre

    def _power_handle_screen(self):
        """Screen coords of the power-slider drag handle (horizontal bar below slingshot)."""
        ssx, ssy = self._sling_screen()
        bar_left = max(2, int(ssx) + self.POWER_BAR_OFFSET)
        bar_mid_y = ssy + 16 + self.POWER_BAR_H // 2
        return (bar_left + self.launch_power * self.POWER_BAR_W,
                bar_mid_y)

    # ── Update ───────────────────────────────────────────────────────────────
    def update(self):
        if self.state == "won":
            return

        # Sync moving obstacles for aim (flying updates moon inside the physics substeps)
        if (self.level.orbit_pairs or self.level.binary_star_pairs) and self.state == "aim":
            self.level.sync_orbits(self.orbit_t)

        # Arrow-key hold behaviour (only in aim state)
        if self.state == "aim" and not self.dragging_inv:
            keys = pygame.key.get_pressed()
            z = self._cam_z()
            play_h = float(RENDER_H - INVENTORY_H)
            max_cam = max(0.0, float(self.level.world_width) - RENDER_W / z)
            max_cy = max(0.0, float(self.level.world_height) - play_h / z)
            # LEFT / RIGHT → scroll camera
            if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                if keys[pygame.K_LEFT]:
                    self.camera_x = max(0.0, self.camera_x - 8)
                elif keys[pygame.K_RIGHT]:
                    self.camera_x = min(max_cam, self.camera_x + 8)
                if keys[pygame.K_UP]:
                    self.camera_y = max(0.0, self.camera_y - 8)
                elif keys[pygame.K_DOWN]:
                    self.camera_y = min(max_cy, self.camera_y + 8)
            else:
                if keys[pygame.K_LEFT]:
                    self.camera_x = max(0.0, self.camera_x - 8)
                elif keys[pygame.K_RIGHT]:
                    self.camera_x = min(max_cam, self.camera_x + 8)
            if keys[pygame.K_z]:
                self.cam_zoom = max(0.35, self.cam_zoom / (1.0 + 0.028))
                self.traj_points = []
            if keys[pygame.K_x]:
                self.cam_zoom = min(2.8, self.cam_zoom * (1.0 + 0.028))
                self.traj_points = []
            # UP / DOWN → nudge power by 0.5 %/frame while held (not while shift-panning)
            if not (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]):
                if keys[pygame.K_UP]:
                    old = self.launch_power
                    self.launch_power = min(1.0, self.launch_power + 0.005)
                    if self.launch_power != old:
                        self.traj_points = []
                elif keys[pygame.K_DOWN]:
                    old = self.launch_power
                    self.launch_power = max(0.0, self.launch_power - 0.005)
                    if self.launch_power != old:
                        self.traj_points = []

        # Trajectory preview: rebuild every frame when moon moves, or while dragging
        # bodies so the dotted line follows ghost positions in real time.
        if self.state == "aim" and (
                not self.traj_points
                or self.level.orbit_pairs
                or self.level.binary_star_pairs
                or self.dragging_placed
                or self.dragging_inv):
            self._update_trajectory_preview()

        if self.state == "flying":
            wh = float(self.level.world_height)
            play_h_f = float(RENDER_H - INVENTORY_H)
            zf = self._cam_z()

            def _belt_hit(sx, sy):
                return not self.level.ship_in_corridor(sx, sy)

            def _oob(sx, sy):
                return (sx < -30 or sx > self.level.world_width + 30
                        or sy < -30 or sy > wh + 30)

            def _body_collision(sx, sy):
                for body in self._all_bodies():
                    dx = sx - body.x
                    dy = sy - body.y
                    if dx * dx + dy * dy < (body.radius + 2) ** 2:
                        return body
                return None

            moving = self.level.orbit_pairs or self.level.binary_star_pairs
            if moving:
                SUB = 5
                dt = PHYS_DT / SUB
                t0 = self.orbit_t
                for k in range(SUB):
                    self.level.sync_orbits(t0 + (k + 1) / SUB)
                    ax, ay = self._compute_accel(self.ship_x, self.ship_y)
                    self.ship_vx += ax * dt
                    self.ship_vy += ay * dt
                    self.ship_x += self.ship_vx * dt
                    self.ship_y += self.ship_vy * dt
                    if _belt_hit(self.ship_x, self.ship_y) or _oob(self.ship_x, self.ship_y):
                        self.particles += spawn_explosion(self.ship_x, self.ship_y)
                        self.state = "exploding"
                        return
                    hit = _body_collision(self.ship_x, self.ship_y)
                    if hit is not None:
                        if (not hit.is_obstacle and hit.obj_id == self.level.target.obj_id
                                and abs(hit.x - self.level.target.x) < 1):
                            self.state = "landed"
                            self.landing_flash.trigger()
                        else:
                            self.particles += spawn_explosion(self.ship_x, self.ship_y)
                            self.state = "exploding"
                        return
            else:
                ax, ay = self._compute_accel(self.ship_x, self.ship_y)
                self.ship_vx += ax * PHYS_DT
                self.ship_vy += ay * PHYS_DT
                self.ship_x += self.ship_vx * PHYS_DT
                self.ship_y += self.ship_vy * PHYS_DT

                if _belt_hit(self.ship_x, self.ship_y) or _oob(self.ship_x, self.ship_y):
                    self.particles += spawn_explosion(self.ship_x, self.ship_y)
                    self.state = "exploding"
                    return

                hit = _body_collision(self.ship_x, self.ship_y)
                if hit is not None:
                    if (not hit.is_obstacle and hit.obj_id == self.level.target.obj_id
                            and abs(hit.x - self.level.target.x) < 1):
                        self.state = "landed"
                        self.landing_flash.trigger()
                    else:
                        self.particles += spawn_explosion(self.ship_x, self.ship_y)
                        self.state = "exploding"
                    return

            max_cam = max(0.0, float(self.level.world_width) - RENDER_W / zf)
            max_cy = max(0.0, wh - play_h_f / zf)
            target_cx = self.ship_x - 0.5 * RENDER_W * zf
            target_cx = max(0.0, min(target_cx, max_cam))
            target_cy = self.ship_y - 0.5 * play_h_f / zf
            target_cy = max(0.0, min(target_cy, max_cy))
            self.camera_x += (target_cx - self.camera_x) * 0.12
            self.camera_y += (target_cy - self.camera_y) * 0.12

        if ((self.level.orbit_pairs or self.level.binary_star_pairs)
                and self.state in ("aim", "flying")):
            self.orbit_t += 1.0
            self.level.sync_orbits(self.orbit_t)

        elif self.state == "exploding":
            self.particles = [p for p in self.particles if p.update()]
            if not self.particles:
                self._reset_attempt()

        elif self.state == "landed":
            self.landing_flash.update()
            if not self.landing_flash.active:
                # Flash done → show WIN screen, wait for click
                self.state = "won"

        # Always tick particles
        self.particles = [p for p in self.particles if p.update()]

    def _next_level(self):
        self.level_num += 1
        self.level = generate_level(self.level_num)
        self._reset_level()

    # ── Render ───────────────────────────────────────────────────────────────
    def render(self, surface):
        """Render everything to the 320×180 render surface."""
        play_h    = RENDER_H - INVENTORY_H
        # belt_top / belt_bot are now per-x arrays; only used locally below

        # ── Background ────────────────────────────────────────────────────
        pygame.draw.rect(surface, C_DARK_SPACE, (0, 0, RENDER_W, play_h))

        # ── Asteroid belt (rock = complement of navigable corridors in world space) ──
        z = self._cam_z()
        cam_x = self.camera_x
        cam_y = self.camera_y
        wh = float(self.level.world_height)
        top_arr = self.level.belt_top_edge
        bot_arr = self.level.belt_bot_edge
        bands = self.level.corridor_bands
        BELT_COLOR = (22, 16, 38)
        # Rocky fringe — matches legacy look; layer 0 depth = FRINGE_COLLISION (collision margin)
        FRINGE_PAL = [
            (95, 80, 62),
            (68, 56, 44),
            (45, 38, 30),
        ]
        prev_top_sy = None
        prev_bot_sy = None

        for sx_col in range(RENDER_W):
            wx = cam_x + sx_col * z
            xi = int(max(0, min(len(top_arr) - 1, wx)))
            spans = _rock_vertical_spans_for_column(top_arr, bot_arr, xi, wh, bands)
            for (ry0, ry1) in spans:
                sy0 = (ry0 - cam_y) / z
                sy1 = (ry1 - cam_y) / z
                if sy1 <= 0 or sy0 >= play_h:
                    continue
                sy0c = max(0.0, sy0)
                sy1c = min(float(play_h), sy1)
                if sy1c <= sy0c:
                    continue
                wmid = (ry0 + ry1) * 0.5
                tint = 0.78 + 0.22 * (((int(wx) * 3 + int(wmid) * 5) & 255) / 255.0)
                bc = (int(BELT_COLOR[0] * tint), int(BELT_COLOR[1] * tint),
                      int(BELT_COLOR[2] * tint))
                y0i, y1i = int(sy0c), int(math.ceil(sy1c)) - 1
                if y1i >= y0i:
                    pygame.draw.line(surface, bc, (sx_col, y0i), (sx_col, y1i))

            # Edge fringe at every rock ↔ navigable boundary (world y → screen)
            seed = (int(wx) * 1664525 + 1013904223) & 0xFFFFFF
            fringe_t = (seed >> 8) & 0xF
            for (ry0, ry1) in spans:
                if ry1 < wh:
                    s_edge = int((ry1 - cam_y) / z)
                    for layer, fc in enumerate(FRINGE_PAL):
                        if layer == 0:
                            thick = FRINGE_COLLISION
                        else:
                            thick = max(1, FRINGE_COLLISION - layer -
                                        (0 if fringe_t < 6 else 1 if fringe_t < 12 else 2))
                        for fy in range(s_edge, min(play_h, s_edge + thick)):
                            if 0 <= fy < play_h:
                                surface.set_at((sx_col, fy), fc)
                if ry0 > 0:
                    s_edge = int((ry0 - cam_y) / z)
                    for layer, fc in enumerate(FRINGE_PAL):
                        if layer == 0:
                            thick = FRINGE_COLLISION
                        else:
                            thick = max(1, FRINGE_COLLISION - layer -
                                        (0 if fringe_t < 6 else 1 if fringe_t < 12 else 2))
                        for fy in range(max(0, s_edge - thick), s_edge):
                            if 0 <= fy < play_h:
                                surface.set_at((sx_col, fy), fc)

            # Connect outer corridor edges across columns (bright fringe seam)
            merged = _merged_safe_intervals_at_column(top_arr, bot_arr, xi, bands)
            if merged:
                lo0 = merged[0][0]
                hi1 = merged[-1][1]
                te = int((lo0 - cam_y) / z)
                be = int((hi1 - cam_y) / z)
                if prev_top_sy is not None and sx_col > 0:
                    pygame.draw.line(surface, FRINGE_PAL[0],
                                       (sx_col - 1, prev_top_sy), (sx_col, te))
                    pygame.draw.line(surface, FRINGE_PAL[0],
                                       (sx_col - 1, prev_bot_sy), (sx_col, be))
                prev_top_sy, prev_bot_sy = te, be
            else:
                prev_top_sy = prev_bot_sy = None

        # Stars drawn ON TOP of belt — they show through the rocky walls
        draw_starfield(surface, self.level.starfield, self.camera_x, self.camera_y,
                       self.cam_zoom)

        # Scanline overlay (Celeste feel)
        for scan_y in range(0, play_h, 2):
            pygame.draw.line(surface, (0, 0, 0, 18), (0, scan_y), (RENDER_W, scan_y))

        # Belt rock dots (on top of stars for depth)
        for (bx, by, bsz) in self.level.belt_dots:
            dot_sx = (bx - self.camera_x) / z
            dot_sy = (by - self.camera_y) / z
            if (-2 <= dot_sx <= RENDER_W + 2 and -2 <= dot_sy <= play_h + 2
                    and not self.level.ship_in_corridor(bx, by)):
                col = (60, 52, 44) if (int(bx) ^ int(by)) % 3 != 0 else (82, 70, 58)
                pygame.draw.circle(surface, col, (int(dot_sx), int(dot_sy)), bsz)

        # Moon orbit guide (same visual language as the physics mini lab)
        for op in self.level.orbit_pairs:
            gx, gy = self._world_to_screen(op.cx, op.cy)
            if -60 <= gx <= RENDER_W + 60 and -60 <= gy <= play_h + 60:
                rr = max(2, int(op.orbit_r / z))
                pygame.draw.circle(surface, (46, 50, 72),
                                   (int(gx), int(gy)), rr, 1)

        for bp in self.level.binary_star_pairs:
            gx, gy = self._world_to_screen(bp.cx, bp.cy)
            if -80 <= gx <= RENDER_W + 80 and -80 <= gy <= play_h + 80:
                rr = max(3, int((bp.sep * 0.5) / z))
                pygame.draw.circle(surface, (72, 58, 38), (int(gx), int(gy)), rr, 1)

        # ── Celestial bodies ─────────────────────────────────────────────
        # Identify which placed body (if any) is being dragged
        drag_pi = self.drag_placed_idx if self.dragging_placed else None

        # Compute cursor world pos for hover detection on placed bodies
        mx_raw, my_raw = pygame.mouse.get_pos()
        cursor_sx = mx_raw // SCALE
        cursor_sy = my_raw // SCALE
        cursor_wx, cursor_wy = self._screen_to_world(float(cursor_sx), float(cursor_sy))

        for idx, body in enumerate(self.placed_bodies):
            if idx == drag_pi:
                continue   # drawn separately at cursor position
            sx, sy = self._world_to_screen(body.x, body.y)
            if -20 <= sx <= RENDER_W + 20 and -20 <= sy <= play_h + 20:
                sprite = PLANET_SPRITES.get(body.obj_id)
                if sprite:
                    sw, sh = sprite.get_size()
                    surface.blit(sprite, (int(sx - sw//2), int(sy - sh//2)))
                # Hover / draggable highlight (in aim state only)
                if self.state == "aim":
                    dist2 = (cursor_wx - body.x)**2 + (cursor_wy - body.y)**2
                    hover_r = body.radius + 5
                    if dist2 < hover_r * hover_r:
                        pygame.draw.circle(surface, (220, 220, 100),
                                           (int(sx), int(sy)), body.radius + 4, 1)
                        draw_text(surface, "DRAG", int(sx) - 10, int(sy) - body.radius - 10,
                                  (220, 220, 100), 7)
                        om = body.obj.get("order_mag", "")
                        line2 = f"m {int(body.mass)}"
                        sz = 7
                        w1 = text_width(om, sz) if om else 0
                        w2 = text_width(line2, sz)
                        bw = max(w1, w2, 34) + 4
                        bh = 22 if om else 12
                        bx = int(sx - bw // 2)
                        by = int(sy - body.radius - 10 - bh)
                        if by < 2:
                            by = int(sy + body.radius + 8)
                        tip = pygame.Surface((bw, bh), pygame.SRCALPHA)
                        tip.fill((22, 26, 42, 238))
                        surface.blit(tip, (bx, by))
                        pygame.draw.rect(surface, (90, 100, 140), (bx, by, bw, bh), 1)
                        yy = by + 2
                        if om:
                            draw_text(surface, om, bx + 2, yy, C_UI_BRIGHT, sz,
                                      shadow=False, center=False)
                            yy += 10
                        draw_text(surface, line2, bx + 2, yy, (210, 210, 225), sz,
                                  shadow=False, center=False)

        for body in self.level.obstacles + [self.level.target]:
            sx, sy = self._world_to_screen(body.x, body.y)
            if -20 <= sx <= RENDER_W + 20 and -20 <= sy <= play_h + 20:
                sprite = PLANET_SPRITES.get(body.obj_id)
                if sprite:
                    sw, sh = sprite.get_size()
                    surface.blit(sprite, (int(sx - sw//2), int(sy - sh//2)))
                    # Pulsing highlight on target
                    if (not body.is_obstacle and body.obj_id == self.level.target.obj_id
                            and abs(body.x - self.level.target.x) < 1):
                        pulse = int(abs(math.sin(pygame.time.get_ticks() * 0.003)) * 3)
                        pygame.draw.circle(surface, C_YELLOW,
                                           (int(sx), int(sy)), body.radius + 3 + pulse, 1)
                    if body.is_obstacle:
                        pygame.draw.circle(surface, C_RED,
                                           (int(sx), int(sy - body.radius - 2)), 1)

        # ── Slingshot + aim/power controls ────────────────────────────────
        ssx, ssy = self._sling_screen()
        if -50 <= ssx <= RENDER_W + 50:
            self._draw_slingshot(surface, int(ssx), int(ssy))
            if self.state == "aim":
                self._draw_aim_controls(surface, ssx, ssy)

        # ── Trajectory preview (always shown in aim state) ─────────────────
        if self.state == "aim" and self.traj_points:
            self._draw_trajectory(surface)

        # ── Ship ──────────────────────────────────────────────────────────
        if self.state in ("aim", "flying"):
            ship_sx, ship_sy = self._world_to_screen(self.ship_x, self.ship_y)
            if -10 <= ship_sx <= RENDER_W + 10 and -10 <= ship_sy <= play_h + 10:
                sw, sh = self.ship_sprite.get_size()
                surface.blit(self.ship_sprite,
                             (int(ship_sx - sw//2), int(ship_sy - sh//2)))

        # ── Explosion particles ────────────────────────────────────────────
        for p in self.particles:
            p.draw(surface, self.camera_x, self.camera_y, self.cam_zoom)

        # ── Landing flash ─────────────────────────────────────────────────
        self.landing_flash.draw(surface)

        # ── WIN overlay ───────────────────────────────────────────────────
        if self.state == "won":
            overlay = pygame.Surface((RENDER_W, play_h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 130))
            surface.blit(overlay, (0, 0))
            t_ms = pygame.time.get_ticks()
            pulse = int(abs(math.sin(t_ms * 0.0025)) * 25)
            win_color = (255, min(255, 200 + pulse), 30)
            draw_text(surface, "WIN!", RENDER_W // 2, play_h // 2 - 24,
                      win_color, 40, shadow=True, center=True)
            draw_text(surface, "CLICK OR PRESS ANY KEY",
                      RENDER_W // 2, play_h // 2 + 20,
                      C_UI_TEXT, 12, shadow=True, center=True)

        # ── Dragged object follows cursor ──────────────────────────────────
        if self.dragging_inv and self.drag_inv_idx is not None:
            obj_id = self.inv_remaining[self.drag_inv_idx]
            sprite = PLANET_SPRITES.get(obj_id)
            if sprite:
                sw, sh = sprite.get_size()
                surface.blit(sprite,
                             (int(self.drag_x - sw//2), int(self.drag_y - sh//2)))

        if self.dragging_placed and self.drag_placed_idx is not None:
            body   = self.placed_bodies[self.drag_placed_idx]
            sprite = PLANET_SPRITES.get(body.obj_id)
            if sprite:
                sw, sh = sprite.get_size()
                surface.blit(sprite,
                             (int(self.drag_placed_x - sw//2),
                              int(self.drag_placed_y - sh//2)))
            # "Release in inventory bar to return" hint
            draw_text(surface, "DROP IN BAR TO RETURN",
                      RENDER_W // 2, RENDER_H - INVENTORY_H - 14,
                      (200, 200, 100), 8, center=True)

        # ── HUD ───────────────────────────────────────────────────────────
        self._draw_hud(surface)

        # ── Inventory bar ─────────────────────────────────────────────────
        self._draw_inventory(surface)

    def _draw_slingshot(self, surface, sx, sy):
        """Draw a Y-shaped slingshot at screen position (sx, sy)."""
        col = C_SLINGSHOT
        pygame.draw.line(surface, col, (sx, sy), (sx, sy + 8), 1)
        pygame.draw.line(surface, col, (sx, sy), (sx - 4, sy - 6), 1)
        pygame.draw.line(surface, col, (sx, sy), (sx + 4, sy - 6), 1)
        pygame.draw.circle(surface, col, (sx - 4, sy - 6), 1)
        pygame.draw.circle(surface, col, (sx + 4, sy - 6), 1)

    def _draw_aim_controls(self, surface, ssx, ssy):
        """
        Draw aim arrow (draggable tip) + horizontal power slider below slingshot.
        Aim  : yellow circle at arrow tip — drag to change angle.
        Power: horizontal bar centred below slingshot — drag left/right.
        No text labels; controls are self-explanatory from the visuals.
        """
        ssx, ssy = int(ssx), int(ssy)

        # ── Aim arrow ─────────────────────────────────────────────────────
        tip_x = int(ssx + self.AIM_ARROW_LEN * math.cos(self.aim_angle))
        tip_y = int(ssy + self.AIM_ARROW_LEN * math.sin(self.aim_angle))
        pygame.draw.line(surface, C_TRAJ, (ssx, ssy), (tip_x, tip_y), 2)
        dx = math.cos(self.aim_angle)
        dy = math.sin(self.aim_angle)
        pygame.draw.line(surface, C_TRAJ,
                         (tip_x, tip_y),
                         (int(tip_x - dx*5 - dy*3), int(tip_y - dy*5 + dx*3)), 1)
        pygame.draw.line(surface, C_TRAJ,
                         (tip_x, tip_y),
                         (int(tip_x - dx*5 + dy*3), int(tip_y - dy*5 - dx*3)), 1)

        # ── Horizontal power slider (below slingshot) ──────────────────────
        bar_left = max(2, ssx + self.POWER_BAR_OFFSET)
        bar_top  = ssy + 14
        bw, bh   = self.POWER_BAR_W, self.POWER_BAR_H

        # Track
        pygame.draw.rect(surface, (20, 18, 38), (bar_left, bar_top, bw, bh))
        pygame.draw.rect(surface, (60, 58, 80), (bar_left, bar_top, bw, bh), 1)

        # Gradient fill: green (left/low) → yellow → red (right/high)
        fill_w = max(1, int(self.launch_power * bw))
        for fx in range(fill_w):
            tc = fx / max(bw - 1, 1)           # 0 at left edge, 1 at full power
            r  = int(40  + tc * 215)
            g  = int(210 - tc * 160)
            b  = int(40  - tc * 30)
            pygame.draw.line(surface, (r, g, b),
                             (bar_left + 1 + fx, bar_top + 1),
                             (bar_left + 1 + fx, bar_top + bh - 2))

        # Handle — vertical tab at the fill edge
        hx = bar_left + fill_w
        handle_col2 = C_WHITE if not self.dragging_power else C_YELLOW
        pygame.draw.rect(surface, handle_col2, (hx - 2, bar_top - 2, 4, bh + 4))

    def _draw_trajectory(self, surface):
        """Draw dashed yellow arrow showing predicted trajectory."""
        pts = self.traj_points
        screen_pts = [self._world_to_screen(px, py) for (px, py) in pts]
        # Draw dashed line (every other segment)
        dash_on = True
        for i in range(0, len(screen_pts)-1, 2):
            p1 = screen_pts[i]
            p2 = screen_pts[i+1] if i+1 < len(screen_pts) else p1
            if dash_on:
                pygame.draw.line(surface, C_TRAJ,
                                 (int(p1[0]), int(p1[1])),
                                 (int(p2[0]), int(p2[1])), 1)
            dash_on = not dash_on
        # Arrow head at end of trajectory
        if len(screen_pts) >= 3:
            ex, ey = screen_pts[-1]
            dx = screen_pts[-1][0] - screen_pts[-3][0]
            dy = screen_pts[-1][1] - screen_pts[-3][1]
            length = math.sqrt(dx*dx + dy*dy) + 1e-9
            nx, ny = dx/length, dy/length
            # Arrow head
            pygame.draw.line(surface, C_TRAJ,
                             (int(ex), int(ey)),
                             (int(ex - nx*4 - ny*2), int(ey - ny*4 + nx*2)), 1)
            pygame.draw.line(surface, C_TRAJ,
                             (int(ex), int(ey)),
                             (int(ex - nx*4 + ny*2), int(ey - ny*4 - nx*2)), 1)

    def _draw_hud(self, surface):
        """Draw top HUD: level number, attempts, ship name, skip button."""
        play_h = RENDER_H - INVENTORY_H

        # Top bar — 18 px tall
        pygame.draw.rect(surface, C_UI_BG, (0, 0, RENDER_W, HUD_H))
        pygame.draw.line(surface, C_UI_BORDER, (0, HUD_H - 1), (RENDER_W, HUD_H - 1), 1)

        draw_text(surface, f"LVL {self.level_num+1}", 4, 2, C_UI_BRIGHT, 14)
        draw_text(surface, f"ATTEMPTS: {self.level.attempt}",
                  RENDER_W//2, 2, C_UI_TEXT, 14, center=True)
        ship_name = self.ship["name"]
        ship_w = text_width(ship_name, 14)
        draw_text(surface, ship_name, RENDER_W - 4 - ship_w, 2,
                  self.ship["color"], 14)

        # Skip button — bottom-right of play area
        skip_x = RENDER_W - 62
        skip_y = play_h - 18
        pygame.draw.rect(surface, C_UI_BG,     (skip_x-2, skip_y-2, 64, 16))
        pygame.draw.rect(surface, C_UI_BORDER, (skip_x-2, skip_y-2, 64, 16), 1)
        draw_text(surface, "[S] SKIP", skip_x, skip_y, C_UI_TEXT, 12)

        # Launch hint
        if self.state == "aim":
            draw_text(surface, "AIM  |  POWER  |  SPC=FIRE  |  Z/X ZOOM  |  C RESET",
                      RENDER_W//2, play_h - 20, C_UI_BRIGHT, 9, center=True)

    def _draw_inventory(self, surface):
        """Draw inventory bar at bottom of screen."""
        play_h = RENDER_H - INVENTORY_H
        inv_y  = play_h

        # Background
        pygame.draw.rect(surface, C_UI_BG, (0, inv_y, RENDER_W, INVENTORY_H))
        pygame.draw.line(surface, C_UI_BORDER, (0, inv_y), (RENDER_W, inv_y), 1)

        slot_w  = 64          # wide enough for 8-char names
        slot_h  = INVENTORY_H - 4
        start_x = 5

        # Get mouse in render coords for hover detection
        mx_raw, my_raw = pygame.mouse.get_pos()
        mx = mx_raw * RENDER_W // max(1, WINDOW_W) if SCALE == 1 else mx_raw // SCALE
        my = my_raw * RENDER_H // max(1, WINDOW_H) if SCALE == 1 else my_raw // SCALE
        hover_idx = None

        for i, obj_id in enumerate(self.inv_remaining):
            obj = OBJ_BY_ID[obj_id]
            sx = start_x + i * slot_w
            sy = inv_y + 2

            # Check if mouse is over this slot
            if sx <= mx <= sx + slot_w - 4 and inv_y <= my <= RENDER_H:
                hover_idx = i

            # Slot background
            pygame.draw.rect(surface, C_SPACE3,    (sx, sy, slot_w-4, slot_h))
            pygame.draw.rect(surface, C_UI_BORDER, (sx, sy, slot_w-4, slot_h), 1)

            # Planet sprite centred in upper part of slot
            sprite = PLANET_SPRITES.get(obj_id)
            if sprite:
                sw, sh = sprite.get_size()
                blit_x = sx + (slot_w-4)//2 - sw//2
                surface.blit(sprite, (blit_x, sy + 3))

            # Name label — use the pre-defined short display name
            draw_text(surface, obj["short"],
                      sx + 2, inv_y + slot_h - 11, C_UI_TEXT, 11)

        # ── Hover mass popup ──────────────────────────────────────────────────
        if hover_idx is not None:
            obj_id   = self.inv_remaining[hover_idx]
            obj      = OBJ_BY_ID[obj_id]
            mass_txt = obj["order_mag"]
            pw = text_width(mass_txt, 14) + 10
            ph = 20
            px = start_x + hover_idx * slot_w
            px = max(2, min(RENDER_W - pw - 2, px))
            py = inv_y - ph - 3
            pygame.draw.rect(surface, C_UI_BG,  (px, py, pw, ph))
            pygame.draw.rect(surface, C_YELLOW, (px, py, pw, ph), 1)
            draw_text(surface, mass_txt, px + 5, py + 3, C_YELLOW, 14)

        # ── Placed bodies (greyed out, skip the one being dragged) ──────────
        drag_pi      = self.drag_placed_idx if self.dragging_placed else None
        placed_start = start_x + len(self.inv_remaining) * slot_w
        slot_col = 0
        for j, body in enumerate(self.placed_bodies):
            if j == drag_pi:
                continue   # being dragged — don't show grayed-out slot
            obj = OBJ_BY_ID[body.obj_id]
            sx  = placed_start + slot_col * slot_w
            sy  = inv_y + 2
            slot_col += 1
            pygame.draw.rect(surface, (20, 20, 40), (sx, sy, slot_w-4, slot_h))
            pygame.draw.rect(surface, (30, 30, 60), (sx, sy, slot_w-4, slot_h), 1)
            sprite = PLANET_SPRITES.get(body.obj_id)
            if sprite:
                grey = sprite.copy()
                grey.fill((80, 80, 80, 0), special_flags=pygame.BLEND_RGBA_MULT)
                sw, sh = grey.get_size()
                surface.blit(grey, (sx + (slot_w-4)//2 - sw//2, sy + 3))
            draw_text(surface, obj["short"],
                      sx + 2, inv_y + slot_h - 11, (80, 80, 110), 11)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN MENU
# ─────────────────────────────────────────────────────────────────────────────

class MainMenu:
    # Option IDs — "FULLSCREEN" is handled specially (toggles, shows state)
    BASE_OPTIONS = ["PLAY", "VIEW OBJECTS", "HOW TO PLAY", "THE PHYSICS!", "FULLSCREEN"]
    # Layout tuned for 320×180 — wide enough for "FULLSCREEN: ON", tall enough for font
    BTN_W, BTN_H, BTN_Y0, BTN_STEP = 214, 18, 54, 18
    MENU_FONT = 12

    def __init__(self):
        self.options  = list(self.BASE_OPTIONS)
        self.selected = 0
        self.stars = generate_starfield(RENDER_H * 3, seed=999)
        self.t = 0

    def _btn_rect(self, i):
        bx = RENDER_W // 2 - self.BTN_W // 2
        oy = self.BTN_Y0 + i * self.BTN_STEP
        return pygame.Rect(bx, oy, self.BTN_W, self.BTN_H)

    def handle_event(self, event, mouse_render):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_UP:
                self.selected = (self.selected - 1) % len(self.options)
            elif event.key == pygame.K_DOWN:
                self.selected = (self.selected + 1) % len(self.options)
            elif event.key in (pygame.K_RETURN, pygame.K_z, pygame.K_SPACE):
                return self.options[self.selected]
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = mouse_render
            for i, opt in enumerate(self.options):
                if self._btn_rect(i).collidepoint(mx, my):
                    if i == self.selected:
                        return opt
                    self.selected = i
                    break
        return None

    def render(self, surface, fullscreen=False):
        self.t += 1
        surface.fill(C_DARK_SPACE)
        draw_starfield(surface, self.stars, 0, 0)

        pulse = int(abs(math.sin(self.t * 0.04)) * 15)
        draw_text(surface, "GRAVITY", RENDER_W//2, 2,
                  (180+pulse, 180+pulse, 255), 17, shadow=True, center=True)
        draw_text(surface, "SLINGSHOT", RENDER_W//2, 21,
                  (100+pulse, 160+pulse, 255), 17, shadow=True, center=True)

        draw_text(surface, "A SPACE PHYSICS PUZZLE",
                  RENDER_W//2, 40, C_UI_TEXT, 10, center=True)

        sz = self.MENU_FONT
        for i, opt in enumerate(self.options):
            r = self._btn_rect(i)
            bx, oy = r.x, r.y
            # Fullscreen button shows current state
            label = opt
            if opt == "FULLSCREEN":
                label = "FULLSCREEN: ON" if fullscreen else "FULLSCREEN: OFF"
            if i == self.selected:
                pygame.draw.rect(surface, C_SPACE3, r)
                pygame.draw.rect(surface, C_YELLOW, r, 1)
                draw_text(surface, f"> {label} <", RENDER_W//2, oy + 3,
                          C_YELLOW, sz, center=True)
            else:
                draw_text(surface, label, RENDER_W//2, oy + 3,
                          C_UI_TEXT, sz, center=True)


# ─────────────────────────────────────────────────────────────────────────────
#  SHIP SELECT SCREEN
# ─────────────────────────────────────────────────────────────────────────────

class ShipSelectScreen:
    SLOT_H = 54   # pixels per ship row on the 320×180 buffer

    def __init__(self, current_ship_idx=0):
        self.selected = current_ship_idx
        self.scroll   = 0
        self.stars    = generate_starfield(RENDER_H * 4, seed=777)
        self.t        = 0
        # Content starts at y=24 (below header); scrolls if ships overflow
        self._content_top = 24
        self._content_bot = RENDER_H - 18
        visible_h = self._content_bot - self._content_top
        self.max_scroll = max(0, len(SHIPS) * self.SLOT_H - visible_h)

    def _clamp_scroll(self):
        self.scroll = max(0, min(self.max_scroll, self.scroll))

    def handle_event(self, event, mouse_render):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_UP:
                self.selected = max(0, self.selected - 1)
                # Auto-scroll to keep selection visible
                slot_top = self._content_top + self.selected * self.SLOT_H
                if slot_top < self._content_top + self.scroll:
                    self.scroll = max(0, self.selected * self.SLOT_H)
            elif event.key == pygame.K_DOWN:
                self.selected = min(len(SHIPS)-1, self.selected+1)
                slot_bot = self._content_top + (self.selected+1) * self.SLOT_H
                visible_bot = self._content_top + self.scroll + (self._content_bot - self._content_top)
                if slot_bot > visible_bot:
                    self.scroll = (self.selected+1)*self.SLOT_H - (self._content_bot - self._content_top)
                self._clamp_scroll()
            elif event.key in (pygame.K_RETURN, pygame.K_z, pygame.K_SPACE):
                return ("select", self.selected)
            elif event.key == pygame.K_ESCAPE:
                return ("back", self.selected)
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(self.max_scroll, self.scroll - event.y * self.SLOT_H))
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = mouse_render
            for i in range(len(SHIPS)):
                sy = self._content_top + i * self.SLOT_H - self.scroll
                if sy <= my <= sy + self.SLOT_H - 3 and 8 <= mx <= RENDER_W - 8:
                    if i == self.selected:
                        return ("select", self.selected)   # second click = confirm
                    self.selected = i                       # first click = highlight
        return None

    def render(self, surface):
        self.t += 1
        surface.fill(C_DARK_SPACE)
        draw_starfield(surface, self.stars, 0, 0)

        draw_text(surface, "SELECT SHIP", RENDER_W//2, 4,
                  C_YELLOW, 13, shadow=True, center=True)

        surface.set_clip(pygame.Rect(0, self._content_top,
                                     RENDER_W,
                                     self._content_bot - self._content_top))

        slot_h = self.SLOT_H
        for i, ship in enumerate(SHIPS):
            sy = self._content_top + i * slot_h - self.scroll
            if sy + slot_h < self._content_top or sy > self._content_bot:
                continue
            selected = (i == self.selected)

            bg_col     = C_SPACE3     if selected else C_UI_BG
            border_col = C_YELLOW     if selected else C_UI_BORDER
            pygame.draw.rect(surface, bg_col,     (8, sy, RENDER_W-16, slot_h-3))
            pygame.draw.rect(surface, border_col, (8, sy, RENDER_W-16, slot_h-3), 1)

            sprite = SHIP_SPRITES.get(ship["name"])
            if sprite:
                sw, sh = sprite.get_size()
                surface.blit(sprite, (16, sy + (slot_h-3)//2 - sh//2))

            name_col = C_YELLOW if selected else C_UI_BRIGHT
            # Left: name + mass
            draw_text(surface, ship["name"],       36, sy + 4,  name_col,  13)
            draw_text(surface, ship["mass_label"], 36, sy + 20, C_UI_TEXT, 10)
            # Divider
            div_x = RENDER_W // 2
            pygame.draw.line(surface, C_UI_BORDER, (div_x, sy + 4), (div_x, sy + slot_h - 8))
            # Right: bullet facts
            rx = div_x + 6
            for fi, fact in enumerate(ship.get("facts", [])):
                draw_text(surface, "· " + fact, rx, sy + 5 + fi * 11, (130, 155, 190), 7)

        surface.set_clip(None)

        # Draw bottom bar AFTER clearing clip so it's never masked
        draw_text(surface, "ENTER = SELECT", 6, RENDER_H - 13, C_UI_BORDER, 11)
        esc_w = text_width("ESC = BACK", 11)
        draw_text(surface, "ESC = BACK", RENDER_W - 6 - esc_w, RENDER_H - 13, C_UI_BORDER, 11)

# ─────────────────────────────────────────────────────────────────────────────
#  VIEW OBJECTS SCREEN
# ─────────────────────────────────────────────────────────────────────────────

class ViewObjectsScreen:
    ROW_H = 54

    def __init__(self):
        self.scroll = 0
        self.stars  = generate_starfield(RENDER_H * 6, seed=888)
        self.t      = 0
        self._content_top = 26
        self._content_bot = RENDER_H - 18
        visible_h = self._content_bot - self._content_top
        self.max_scroll = max(0, len(CELESTIAL_OBJECTS) * self.ROW_H - visible_h)

    def handle_event(self, event, mouse_render):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_UP:
                self.scroll = max(0, self.scroll - self.ROW_H)
            elif event.key == pygame.K_DOWN:
                self.scroll = min(self.max_scroll, self.scroll + self.ROW_H)
            elif event.key == pygame.K_ESCAPE:
                return "back"
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(self.max_scroll,
                                     self.scroll - event.y * self.ROW_H))
        return None

    def render(self, surface):
        self.t += 1
        surface.fill(C_DARK_SPACE)
        draw_starfield(surface, self.stars, 0, 0)

        draw_text(surface, "OBJECT CATALOGUE", RENDER_W//2, 4,
                  C_CYAN, 13, shadow=True, center=True)

        surface.set_clip(pygame.Rect(0, self._content_top,
                                     RENDER_W,
                                     self._content_bot - self._content_top))

        for i, obj in enumerate(CELESTIAL_OBJECTS):
            ry = self._content_top + i * self.ROW_H - self.scroll
            if ry + self.ROW_H < self._content_top or ry > self._content_bot:
                continue

            pygame.draw.rect(surface, C_UI_BG,
                             (5, ry, RENDER_W-10, self.ROW_H-3))
            pygame.draw.rect(surface, C_UI_BORDER,
                             (5, ry, RENDER_W-10, self.ROW_H-3), 1)

            sprite = PLANET_SPRITES.get(obj["id"])
            if sprite:
                sw, sh = sprite.get_size()
                surface.blit(sprite, (11, ry + (self.ROW_H-3)//2 - sh//2))

            name_col = C_YELLOW if obj["is_large"] else C_CYAN
            # Left: name + mass
            draw_text(surface, obj["name"],      32, ry + 3,  name_col,  13)
            draw_text(surface, obj["order_mag"], 32, ry + 20, C_UI_TEXT, 10)
            # Divider
            div_x = RENDER_W // 2
            pygame.draw.line(surface, C_UI_BORDER, (div_x, ry + 4), (div_x, ry + self.ROW_H - 8))
            # Right: bullet facts
            rx = div_x + 6
            for fi, fact in enumerate(obj.get("facts", [])):
                draw_text(surface, "· " + fact, rx, ry + 5 + fi * 11, (130, 155, 190), 7)

        surface.set_clip(None)

        # Draw bottom bar AFTER clearing clip so it's never masked
        draw_text(surface, "SCROLL / WHEEL", 6, RENDER_H - 13, C_UI_BORDER, 11)
        esc_w = text_width("ESC = BACK", 11)
        draw_text(surface, "ESC = BACK", RENDER_W - 6 - esc_w, RENDER_H - 13, C_UI_BORDER, 11)

# ─────────────────────────────────────────────────────────────────────────────
#  HOW TO PLAY SCREEN
# ─────────────────────────────────────────────────────────────────────────────

class HowToPlayScreen:
    # Each entry: (text, size, color, indent_px)
    LINE_H  = 19   # pixels per text line  (size 16 body needs ~19px)
    BLANK_H = 10   # pixels for blank separator rows

    def __init__(self):
        self.stars = generate_starfield(RENDER_H * 3, seed=555)
        self.t = 0
        self.scroll = 0

        self.lines = [
            # ── Objective ───────────────────────────────────────
            ("OBJECTIVE", 15, C_YELLOW, 0),
            ("Get your ship to the target planet.", 11, C_UI_BRIGHT, 8),
            ("Drag planets/moons from the bar below", 11, C_UI_TEXT, 8),
            ("onto the level to bend your path.", 11, C_UI_TEXT, 8),
            ("Every level needs at least one body.", 11, C_UI_TEXT, 8),
            ("", 0, C_UI_TEXT, 0),
            # ── Controls ────────────────────────────────────────
            ("CONTROLS", 15, C_YELLOW, 0),
            ("SPACE / click slingshot  fire", 11, C_CYAN, 8),
            ("drag arrow              aim angle", 11, C_CYAN, 8),
            ("drag power bar L/R      speed", 11, C_CYAN, 8),
            ("up / down               power +-1%", 11, C_CYAN, 8),
            ("left / right            scroll", 11, C_CYAN, 8),
            ("mouse wheel             scroll", 11, C_CYAN, 8),
            ("R                       reset", 11, C_CYAN, 8),
            ("S                       skip level", 11, C_CYAN, 8),
            ("F / F11                 fullscreen", 11, C_CYAN, 8),
            ("ESC                     menu", 11, C_CYAN, 8),
        ]

        total_h = sum(self.LINE_H if ln[0] else self.BLANK_H for ln in self.lines)
        self.visible_h = RENDER_H - 44
        self.max_scroll = max(0, total_h - self.visible_h)

    def handle_event(self, event, mouse_render):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_UP:
                self.scroll = max(0, self.scroll - 14)
            elif event.key == pygame.K_DOWN:
                self.scroll = min(self.max_scroll, self.scroll + 14)
            elif event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                return "back"
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(self.max_scroll,
                                     self.scroll - event.y * 14))
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = mouse_render
            btn_x = RENDER_W // 2 - 50
            btn_y = RENDER_H - 20
            if btn_x <= mx <= btn_x + 100 and btn_y <= my <= btn_y + 16:
                return "back"
        return None

    def render(self, surface):
        self.t += 1
        surface.fill(C_DARK_SPACE)
        draw_starfield(surface, self.stars, 0, 0)

        # Header
        draw_text(surface, "HOW TO PLAY", RENDER_W // 2, 5,
                  C_CYAN, 13, shadow=True, center=True)
        pygame.draw.line(surface, C_UI_BORDER, (8, 22), (RENDER_W - 8, 22), 1)

        # Scrollable content region
        content_top = 24
        content_bot = RENDER_H - 22
        surface.set_clip(pygame.Rect(0, content_top, RENDER_W,
                                     content_bot - content_top))

        cy = content_top - self.scroll
        for text, size, color, indent in self.lines:
            if not text:
                cy += self.BLANK_H
                continue
            # Only draw if visible
            if content_top - self.LINE_H <= cy <= content_bot:
                draw_text(surface, text, 10 + indent, cy, color, size)
            cy += self.LINE_H

        surface.set_clip(None)

        # Scroll indicator bar on the right edge
        if self.max_scroll > 0:
            bar_h = content_bot - content_top
            thumb_h = max(10, int(bar_h * self.visible_h /
                                  (self.visible_h + self.max_scroll)))
            thumb_y = content_top + int(
                (bar_h - thumb_h) * self.scroll / self.max_scroll
            )
            pygame.draw.rect(surface, C_UI_BORDER,
                             (RENDER_W - 4, content_top, 3, bar_h))
            pygame.draw.rect(surface, C_YELLOW,
                             (RENDER_W - 4, thumb_y, 3, thumb_h))

        # Back button
        btn_x = RENDER_W // 2 - 50
        btn_y = RENDER_H - 20
        pygame.draw.rect(surface, C_SPACE3,    (btn_x, btn_y, 100, 16))
        pygame.draw.rect(surface, C_UI_BORDER, (btn_x, btn_y, 100, 16), 1)
        draw_text(surface, "ESC / BACK", RENDER_W // 2, btn_y + 2,
                  C_UI_TEXT, 12, center=True)


# ─────────────────────────────────────────────────────────────────────────────
#  THE PHYSICS!  (science explainer + interactive gravity lab)
# ─────────────────────────────────────────────────────────────────────────────

class PhysicsScreen:
    """
    Late middle-school / early high-school explainer for the game's gravity model,
    plus a draggable mini-lab. Big ideas first, plain language, and hands-on
    investigation of the same math the flight simulation uses.
    """
    # One calm palette for headings / body (fewer competing hues)
    PHY_H = (220, 224, 240)
    PHY_P = (168, 178, 202)
    # Tight left margin so lines use more of the 320px buffer (scrollbar is 3px on right)
    TEXT_X = 3
    # Fixed header band (px): title + subtitle must sit fully ABOVE divider_y
    HEADER_TITLE_Y   = 4
    HEADER_TITLE_SZ  = 13
    HEADER_SUB_Y     = 21
    HEADER_SUB_SZ    = 9
    HEADER_DIVIDER_Y = 34
    HEADER_CONTENT_Y = 36   # scroll clip starts here (below divider + gap)
    LAB_H    = 60
    BACK_ROW = 18
    HEAD_H   = 20
    BODY_H   = 14
    GAP_H    = 16

    def __init__(self):
        self.stars = generate_starfield(RENDER_H * 4, seed=4242)
        self.t = 0
        self.scroll = 0
        H, P = self.PHY_H, self.PHY_P
        sz_h, sz_p = 12, 9
        # Scrollable blocks: ("h", title, color, size) | ("p", text, color, size) | ("g",)
        self.blocks = [
            ("h", "LOOKING UNDER THE HOOD", H, sz_h),
            ("p", "Start with a simple question: what is really", P, sz_p),
            ("p", "going on? This page pulls back the curtain on", P, sz_p),
            ("p", "curtain on the gravity model in the game -", P, sz_p),
            ("p", "the same big ideas astronomers use when they", P, sz_p),
            ("p", "predict how objects move under each other's", P, sz_p),
            ("p", "pull, just tuned so it is fun on a screen.", P, sz_p),
            ("g",), ("g",),
            ("h", "BIG IDEA: EVERY MASS TUGS ON EVERY MASS", H, sz_h),
            ("p", "Centuries ago, scientists worked out a simple", P, sz_p),
            ("p", "rule: anything with mass attracts everything", P, sz_p),
            ("p", "else with mass. You do not notice a pencil", P, sz_p),
            ("p", "pulling you because both pulls are small.", P, sz_p),
            ("p", "Planets and moons are enormous, so their", P, sz_p),
            ("p", "tugs matter. Here each body has a mass", P, sz_p),
            ("p", "number; larger mass means a stronger pull at", P, sz_p),
            ("p", "the same separation.", P, sz_p),
            ("g",), ("g",),
            ("h", "PATTERN SPOTTERS: THE INVERSE-SQUARE LAW", H, sz_h),
            ("p", "Scientists love patterns. With Newton-style", P, sz_p),
            ("p", "gravity, doubling the distance cuts the pull", P, sz_p),
            ("p", "to about one fourth. Tripling cuts it to", P, sz_p),
            ("p", "about one ninth. We say the strength falls", P, sz_p),
            ("p", "off like one over r squared, where r is the", P, sz_p),
            ("p", "center-to-center gap. That is how gravity", P, sz_p),
            ("p", "weakens as you move away in space.", P, sz_p),
            ("g",), ("g",),
            ("p", "Scroll to the grey box and drag the ship. A", P, sz_p),
            ("p", "small dot orbits the big body - it is a real", P, sz_p),
            ("p", "second mass in the math. One red arrow shows", P, sz_p),
            ("p", "total pull; length jumps as you move closer", P, sz_p),
            ("p", "and shifts as the moon swings around.", P, sz_p),
            ("lab",),
            ("g",), ("g",),
            ("h", "OUR COMPUTER MODEL (WHAT WE CALCULATE)", H, sz_h),
            ("p", "Models are tools. For each body we measure", P, sz_p),
            ("p", "how far the ship is, then add a tug along", P, sz_p),
            ("p", "that line. The tug's strength follows", P, sz_p),
            ("p", "a = G * m / (r^2 + e^2).", P, sz_p),
            ("p", f"G is a gameplay constant ({G_CONSTANT}); m is", P, sz_p),
            ("p", "mass; r is distance in pixels. The e^2 bit", P, sz_p),
            ("p", "keeps the model well-behaved up close.", P, sz_p),
            ("g",), ("g",),
            ("h", "MANY TUGS AT ONCE (VECTOR SUM)", H, sz_h),
            ("p", "In the real universe many objects pull at the", P, sz_p),
            ("p", "same time. We draw one arrow per tug, then", P, sz_p),
            ("p", "add them as vectors - tip to tail, just like", P, sz_p),
            ("p", "in a classroom force diagram. The ship only", P, sz_p),
            ("p", "feels the single combined result each step.", P, sz_p),
            ("g",), ("g",),
            ("h", "WHY WE ADD A TINY e^2 (STABILITY)", H, sz_h),
            ("p", "If r could hit zero, dividing by r squared", P, sz_p),
            ("p", "would send accelerations toward infinity and", P, sz_p),
            ("p", "the program would break. A small e^2 in the", P, sz_p),
            ("p", "denominator is a stabilizer - a trick modelers", P, sz_p),
            ("p", "use so close passes stay smooth. Far away,", P, sz_p),
            ("p", "r is large and you hardly notice e at all.", P, sz_p),
            ("g",), ("g",),
            ("h", "TIME IN CHUNKS (SYMPLECTIC EULER)", H, sz_h),
            ("p", "Nature is continuous; computers work in ticks.", P, sz_p),
            ("p", "This game takes sixty ticks per second (each", P, sz_p),
            ("p", "tick is one sixtieth of a second). Each tick:", P, sz_p),
            ("p", "update velocity from acceleration, then move", P, sz_p),
            ("p", "the ship using the new velocity. That order", P, sz_p),
            ("p", "helps long flights stay honest instead of", P, sz_p),
            ("p", "gaining fake energy and drifting wrong.", P, sz_p),
            ("g",), ("g",),
            ("h", "REAL-WORLD SCALE VS PLAY SCALE", H, sz_h),
            ("p", "The object catalogue keeps real masses in kg,", P, sz_p),
            ("p", "but the playfield scales them so you can see", P, sz_p),
            ("p", "and steer. The story of the science -", P, sz_p),
            ("p", "inverse-square pulls, vector sums, careful", P, sz_p),
            ("p", "time steps - stays the same. That is the same", P, sz_p),
            ("p", "cycle many scientists use: observe, build a", P, sz_p),
            ("p", "model, test it, and refine what you think.", P, sz_p),
        ]
        self._lab_drag = False
        self.lab_lx = 34.0
        self.lab_ly = self.LAB_H / 2.0
        self._rebuild_layout()

    def _block_height(self, b):
        if b[0] == "h":
            return self.HEAD_H
        if b[0] == "p":
            return self.BODY_H
        if b[0] == "lab":
            return self.LAB_H
        if b[0] == "g":
            return self.GAP_H
        return self.GAP_H

    def _rebuild_layout(self):
        self.content_h = sum(self._block_height(b) for b in self.blocks)
        self.content_top = PhysicsScreen.HEADER_CONTENT_Y
        self.content_bot = RENDER_H - self.BACK_ROW - 2
        self.visible_h = self.content_bot - self.content_top
        self.max_scroll = max(0, self.content_h - self.visible_h)
        # Y-offset of the lab block from top of scrollable content (for hit-testing)
        self.lab_content_y = 0
        for b in self.blocks:
            if b[0] == "lab":
                break
            self.lab_content_y += self._block_height(b)

    def _lab_rect_screen(self):
        ly = self.content_top - self.scroll + self.lab_content_y
        m = self.TEXT_X
        return pygame.Rect(m, int(ly), RENDER_W - 2 * m, self.LAB_H)

    def handle_event(self, event, mouse_render):
        lab_rect = self._lab_rect_screen()
        btn_y = RENDER_H - self.BACK_ROW
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_UP:
                self.scroll = max(0, self.scroll - 16)
            elif event.key == pygame.K_DOWN:
                self.scroll = min(self.max_scroll, self.scroll + 16)
            elif event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                return "back"
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(self.max_scroll,
                                     self.scroll - event.y * 16))
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = mouse_render
            if my >= btn_y:
                return "back"
            if lab_rect.collidepoint(mx, my):
                self._lab_drag = True
                self._lab_set_probe(mx, my, lab_rect)
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._lab_drag = False
        if event.type == pygame.MOUSEMOTION and self._lab_drag:
            mx, my = mouse_render
            self._lab_set_probe(mx, my, lab_rect)
        return None

    def _lab_set_probe(self, mx, my, lab_rect):
        """Store probe in lab-local coords so scrolling does not yank the ship."""
        m = 10.0
        lx = float(mx - lab_rect.left)
        ly = float(my - lab_rect.top)
        self.lab_lx = max(m, min(float(lab_rect.width) - m, lx))
        self.lab_ly = max(m, min(float(lab_rect.height) - m, ly))

    @staticmethod
    def _draw_narrow_arrow(surface, x0, y0, nx, ny, length, color, head_back=5.0, half_width=2.0, line_w=1):
        """Single thin shaft + tight isosceles head (diagram style, not chunky)."""
        if length < 1.0:
            return
        L = float(length)
        tip_x = x0 + nx * L
        tip_y = y0 + ny * L
        hb = min(head_back, L * 0.35)
        bx = tip_x - nx * hb
        by = tip_y - ny * hb
        px, py = -ny, nx
        p1 = (int(bx + px * half_width), int(by + py * half_width))
        p2 = (int(bx - px * half_width), int(by - py * half_width))
        pygame.draw.line(surface, color, (int(x0), int(y0)), (int(bx), int(by)), line_w)
        pygame.draw.line(surface, color, (int(tip_x), int(tip_y)), p1, line_w)
        pygame.draw.line(surface, color, (int(tip_x), int(tip_y)), p2, line_w)
        pygame.draw.line(surface, color, p1, p2, line_w)

    def _draw_gravity_lab(self, surface, lab_rect):
        """Net force only: true vector sum of pulls, arrow length uses exp(k|a|) so
        shrinking r (and thus growing |a| ~ 1/r^2) feels dramatically obvious."""
        ship_x = lab_rect.left + self.lab_lx
        ship_y = lab_rect.top + self.lab_ly
        # Planet + moon system sit on the left third of the lab (room for ship + arrow right)
        px = lab_rect.left + max(44, int(lab_rect.width * 0.30))
        py = lab_rect.centery

        # Second mass orbits the planet (drawn below) so net pull varies with time.
        sx2 = px + int(15 * math.cos(-self.t * 0.07))
        sy2 = py + int(15 * math.sin(-self.t * 0.07))

        def acc_toward(sx, sy, bx, by, mass):
            rx, ry = bx - sx, by - sy
            dsq = rx * rx + ry * ry + SOFTENING_SQ
            d = math.sqrt(dsq)
            am = G_CONSTANT * mass / dsq
            return am * rx / d, am * ry / d

        ax, ay = acc_toward(ship_x, ship_y, px, py, 25.0)
        ax2, ay2 = acc_toward(ship_x, ship_y, sx2, sy2, 4.0)
        ax += ax2
        ay += ay2
        mag_tot = math.sqrt(ax * ax + ay * ay)
        if mag_tot < 1e-8:
            nx, ny = 1.0, 0.0
        else:
            nx, ny = ax / mag_tot, ay / mag_tot

        dx, dy = px - ship_x, py - ship_y
        dist = math.sqrt(dx * dx + dy * dy + SOFTENING_SQ)

        # Arrow length: exponential in |a_net| (steep near close approach).
        L_cap = min(62.0, float(lab_rect.width) * 0.92)
        k_exp = 0.16
        mag_cap = 22.0
        denom = math.exp(k_exp * mag_cap) - 1.0
        tnorm = min(1.0, (math.exp(k_exp * mag_tot) - 1.0) / max(1e-9, denom))
        arrow_len = 5.0 + (L_cap - 5.0) * tnorm

        bg = (18, 20, 34)
        edge = (55, 62, 95)
        pygame.draw.rect(surface, bg, lab_rect)
        pygame.draw.rect(surface, edge, lab_rect, 1)
        draw_text(surface, "MINI LAB: dot = moon, arrow = net pull", lab_rect.x + 5,
                  lab_rect.y + 2, self.PHY_P, 8)

        pygame.draw.circle(surface, (78, 82, 105), (px, py), 8)
        pygame.draw.circle(surface, (115, 120, 145), (px - 2, py - 2), 2)
        # Faint orbit guide so the moving moon is easy to spot
        pygame.draw.circle(surface, (45, 48, 68), (px, py), 15, 1)
        pygame.draw.circle(surface, (155, 160, 185), (sx2, sy2), 3)
        pygame.draw.circle(surface, (95, 100, 125), (sx2, sy2), 3, 1)
        pygame.draw.circle(surface, (210, 215, 230), (int(ship_x), int(ship_y)), 3)
        pygame.draw.circle(surface, edge, (int(ship_x), int(ship_y)), 3, 1)

        RED = (224, 52, 62)
        self._draw_narrow_arrow(surface, ship_x, ship_y, nx, ny, arrow_len, RED,
                                head_back=4.5, half_width=1.5, line_w=1)

        draw_text(surface, f"r~{dist:.0f} |a|~{mag_tot:.1f}", lab_rect.x + 5,
                  lab_rect.bottom - 10, self.PHY_P, 8)
        bar_w = 68
        bar_x = lab_rect.right - bar_w - 5
        pull = tnorm
        pygame.draw.rect(surface, (32, 34, 52), (bar_x, lab_rect.bottom - 11, bar_w, 7))
        pygame.draw.rect(surface, (120, 48, 58),
                         (bar_x + 1, lab_rect.bottom - 10, int((bar_w - 2) * pull), 5))
        draw_text(surface, "|a|", bar_x - 22, lab_rect.bottom - 10, self.PHY_P, 8)

    def render(self, surface):
        self.t += 1
        surface.fill(C_DARK_SPACE)
        draw_starfield(surface, self.stars, 0, 0)

        draw_text(surface, "THE PHYSICS!", RENDER_W // 2, self.HEADER_TITLE_Y,
                  self.PHY_H, self.HEADER_TITLE_SZ, shadow=True, center=True)
        draw_text(surface, "Investigate the gravity model",
                  RENDER_W // 2, self.HEADER_SUB_Y, self.PHY_P, self.HEADER_SUB_SZ,
                  center=True)
        pygame.draw.line(surface, C_UI_BORDER,
                         (self.TEXT_X, self.HEADER_DIVIDER_Y),
                         (RENDER_W - self.TEXT_X, self.HEADER_DIVIDER_Y), 1)

        # Demo orbit (lab-local) when not dragging — uses same box size as real lab
        if not self._lab_drag:
            wf = float(RENDER_W - 2 * self.TEXT_X)
            hf = float(self.LAB_H)
            ang = self.t * 0.045
            self.lab_lx = max(10.0, min(wf - 10.0, wf * 0.62 + 26.0 * math.cos(ang)))
            self.lab_ly = max(10.0, min(hf - 10.0, hf * 0.5 + 12.0 * math.sin(ang)))

        surface.set_clip(pygame.Rect(0, self.content_top, RENDER_W,
                                     self.content_bot - self.content_top))
        cy = self.content_top - self.scroll
        for b in self.blocks:
            if b[0] == "h":
                _, title, col, sz = b
                if self.content_top - self.HEAD_H <= cy <= self.content_bot:
                    draw_text(surface, title, self.TEXT_X, cy, col, sz)
                cy += self.HEAD_H
            elif b[0] == "p":
                _, txt, col, sz = b
                if self.content_top - self.BODY_H <= cy <= self.content_bot:
                    draw_text(surface, txt, self.TEXT_X, cy, col, sz)
                cy += self.BODY_H
            elif b[0] == "lab":
                m = self.TEXT_X
                lab_rect = pygame.Rect(m, cy, RENDER_W - 2 * m, self.LAB_H)
                if cy + self.LAB_H >= self.content_top and cy <= self.content_bot:
                    self._draw_gravity_lab(surface, lab_rect)
                cy += self.LAB_H
            elif b[0] == "g":
                cy += self.GAP_H
            else:
                cy += self.GAP_H
        surface.set_clip(None)

        if self.max_scroll > 0:
            bar_top, bar_bot = self.content_top, self.content_bot
            bar_h = bar_bot - bar_top
            thumb_h = max(8, int(bar_h * self.visible_h /
                                 (self.visible_h + self.max_scroll)))
            thumb_y = bar_top + int((bar_h - thumb_h) * self.scroll / self.max_scroll)
            pygame.draw.rect(surface, (45, 50, 75), (RENDER_W - 4, bar_top, 3, bar_h))
            pygame.draw.rect(surface, (110, 118, 150), (RENDER_W - 4, thumb_y, 3, thumb_h))

        btn_y = RENDER_H - self.BACK_ROW
        pygame.draw.rect(surface, C_SPACE3,    (0, btn_y, RENDER_W, self.BACK_ROW))
        pygame.draw.line(surface, C_UI_BORDER, (0, btn_y), (RENDER_W, btn_y), 1)
        draw_text(surface, "ESC  SPACE  OR  CLICK = BACK",
                  RENDER_W // 2, btn_y + 4, C_UI_TEXT, 10, center=True)


# ─────────────────────────────────────────────────────────────────────────────
#  APPLICATION LOOP
# ─────────────────────────────────────────────────────────────────────────────

def run():
    global screen, SCALE, WINDOW_W, WINDOW_H

    current_ship_idx = 0
    state = "menu"   # "menu" | "game" | "ship_select" | "view_objects" | "how_to_play" | "physics"
    fullscreen = False

    def toggle_fullscreen():
        nonlocal fullscreen
        global screen, SCALE, WINDOW_W, WINDOW_H
        fullscreen = not fullscreen
        if fullscreen:
            # Use the desktop resolution; get actual size from the surface itself
            # because display.Info() may not reflect the new mode yet on macOS.
            screen   = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            WINDOW_W, WINDOW_H = screen.get_size()
            SCALE    = 1   # unused; mouse mapped proportionally below
        else:
            SCALE    = 4
            WINDOW_W = RENDER_W * 4   # 1280
            WINDOW_H = RENDER_H * 4   # 720
            screen   = pygame.display.set_mode((WINDOW_W, WINDOW_H))

    menu = MainMenu()
    game = None
    ship_select = None
    view_objects = None
    how_to_play = None
    physics_screen = None

    running = True
    while running:
        # ── Scale mouse to render coords ──────────────────────────────────
        mx_win, my_win = pygame.mouse.get_pos()
        if fullscreen:
            # Map proportionally from the actual screen size → 320×180 logical coords
            mouse_render = (mx_win * RENDER_W // max(1, WINDOW_W),
                            my_win * RENDER_H // max(1, WINDOW_H))
        else:
            mouse_render = (mx_win // SCALE, my_win // SCALE)

        # ── Events ────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            # F or F11 toggles fullscreen from anywhere
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_f, pygame.K_F11):
                toggle_fullscreen()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                # ESC navigates menus only — fullscreen is F/F11 exclusively
                if state == "game":
                    state = "menu"
                    menu = MainMenu()
                elif state in ("ship_select", "view_objects", "how_to_play", "physics"):
                    state = "menu"
                    ship_select = None
                    physics_screen = None

            if state == "menu":
                result = menu.handle_event(event, mouse_render)
                if result == "PLAY":
                    # Go to ship select first, then launch the game
                    ship_select = ShipSelectScreen(current_ship_idx)
                    state = "ship_select"
                elif result == "VIEW OBJECTS":
                    view_objects = ViewObjectsScreen()
                    state = "view_objects"
                elif result == "HOW TO PLAY":
                    how_to_play = HowToPlayScreen()
                    state = "how_to_play"
                elif result == "THE PHYSICS!":
                    physics_screen = PhysicsScreen()
                    state = "physics"
                elif result == "FULLSCREEN":
                    toggle_fullscreen()

            elif state == "game" and game:
                game.handle_event(event, mouse_render)

            elif state == "ship_select" and ship_select:
                result = ship_select.handle_event(event, mouse_render)
                if result:
                    action, idx = result
                    current_ship_idx = idx
                    if action == "select":
                        # Launch the game with the chosen ship
                        game = GameState(current_ship_idx)
                        state = "game"
                    else:
                        # "back" — return to menu without starting
                        state = "menu"

            elif state == "view_objects" and view_objects:
                result = view_objects.handle_event(event, mouse_render)
                if result == "back":
                    state = "menu"

            elif state == "how_to_play" and how_to_play:
                result = how_to_play.handle_event(event, mouse_render)
                if result == "back":
                    state = "menu"

            elif state == "physics" and physics_screen:
                result = physics_screen.handle_event(event, mouse_render)
                if result == "back":
                    state = "menu"
                    physics_screen = None

        # ── Update ────────────────────────────────────────────────────────
        if state == "game" and game:
            game.update()

        # ── Render to low-res buffer ──────────────────────────────────────
        render_surface.fill(C_DARK_SPACE)

        if state == "menu":
            menu.render(render_surface, fullscreen=fullscreen)
        elif state == "game" and game:
            game.render(render_surface)
        elif state == "ship_select" and ship_select:
            ship_select.render(render_surface)
        elif state == "view_objects" and view_objects:
            view_objects.render(render_surface)
        elif state == "how_to_play" and how_to_play:
            how_to_play.render(render_surface)
        elif state == "physics" and physics_screen:
            physics_screen.render(render_surface)

        # ── Upscale to window ─────────────────────────────────────────────
        # In fullscreen WINDOW_W/H == actual display size; stretch to fill it.
        pygame.transform.scale(render_surface, (WINDOW_W, WINDOW_H), screen)

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    run()
