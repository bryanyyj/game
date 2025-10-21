import sys
import time
import random
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

try:
    import tkinter as tk
except Exception as e:
    print("Tkinter is required to run this game.")
    raise


Vec2 = Tuple[int, int]


# --- Config ---
GRID_W = 20
GRID_H = 15
TILE = 32
HUD_H = 120
CANVAS_W = GRID_W * TILE
CANVAS_H = GRID_H * TILE + HUD_H

ROUND_SECONDS = 120  # 2:00 minutes


class TileType:
    EMPTY = "empty"
    ROAD = "road"
    BUILDING = "building"
    PARK = "park"
    GREEN = "green"  # planted during play


@dataclass
class Tile:
    kind: str
    upgraded: bool = False      # for roads (bike/pedestrian)
    has_solar: bool = False     # for buildings
    green_type: Optional[str] = None  # 'flowers' | 'trees' | 'garden'


@dataclass
class Player:
    pos: Vec2 = (1, 1)


@dataclass
class Citizen:
    pos: List[float]
    mood: float = 0.4  # 0..1
    dir: Vec2 = field(default_factory=lambda: random.choice([(1,0),(-1,0),(0,1),(0,-1)]))

    def step(self, grid_w: int, grid_h: int):
        # Random walk with occasional direction change
        if random.random() < 0.05:
            self.dir = random.choice([(1,0),(-1,0),(0,1),(0,-1)])
        self.pos[0] = max(0, min(grid_w - 1, self.pos[0] + self.dir[0] * 0.1))
        self.pos[1] = max(0, min(grid_h - 1, self.pos[1] + self.dir[1] * 0.1))


class Game:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("EcoDistrict: Game 3 Prototype (Python/Tkinter)")
        self.canvas = tk.Canvas(root, width=CANVAS_W, height=CANVAS_H, bg="#1e1e1e")
        self.canvas.pack()

        # World state
        self.grid: List[List[Tile]] = self._generate_world()
        self.player = Player(pos=(GRID_W // 2, GRID_H // 2))
        self.citizens: List[Citizen] = [Citizen([random.uniform(0, GRID_W-1), random.uniform(0, GRID_H-1)]) for _ in range(18)]

        # Metrics (0..100)
        self.start_carbon = 62
        self.carbon = float(self.start_carbon)
        self.happiness = 38.0
        self.renewables = 0
        self.green_spaces = 0
        self.energy = 0  # collected scraps to feed buildings

        # Round
        self.round_seconds = ROUND_SECONDS
        self.round_start = time.time()
        self.round_active = True

        # Mini-challenge: reduce carbon by 10%
        self.challenge_target = max(0, self.start_carbon - int(self.start_carbon * 0.10))

        # Feedback state
        self.flash_text: Optional[Tuple[str, float]] = None
        self.compi_phase = 0.0

        # Help overlay
        self.show_help = True
        # Simulated NFC scan / student identity
        self.student_id: str = "Guest"
        self.awaiting_nfc: bool = True
        self.nfc_prompt_start = time.time()

        # Bindings
        self.root.bind("<KeyPress>", self.on_key)

        # Main loop
        self._tick()
        # Spawn collectibles after grid exists
        self.scraps: List[Vec2] = self._spawn_scraps(10)

    # --- World generation ---
    def _generate_world(self) -> List[List[Tile]]:
        grid: List[List[Tile]] = []
        for y in range(GRID_H):
            row: List[Tile] = []
            for x in range(GRID_W):
                # Simple lanes of roads + clusters of buildings and parks
                if y in (5, 9) or x in (3, 10, 16):
                    row.append(Tile(TileType.ROAD))
                else:
                    r = random.random()
                    if r < 0.20:
                        row.append(Tile(TileType.BUILDING))
                    elif r < 0.30:
                        row.append(Tile(TileType.PARK))
                    else:
                        row.append(Tile(TileType.EMPTY))
            grid.append(row)
        return grid

    def _spawn_scraps(self, count: int) -> List[Tuple[int, int]]:
        spots: List[Tuple[int, int]] = []
        attempts = 0
        while len(spots) < count and attempts < 600:
            attempts += 1
            x = random.randrange(0, GRID_W)
            y = random.randrange(0, GRID_H)
            tile = self.grid[y][x]
            if tile.kind in (TileType.EMPTY, TileType.PARK) and (x, y) not in spots:
                spots.append((x, y))
        return spots

    # --- Input ---
    def on_key(self, e: tk.Event):
        # Simulate NFC card scan and optional ID entry before round starts
        if getattr(self, 'awaiting_nfc', False):
            if e.keysym == "Return":
                self.awaiting_nfc = False
                self.round_start = time.time()
                return
            if e.keysym == "BackSpace":
                if self.student_id != "Guest" and len(self.student_id) > 0:
                    self.student_id = self.student_id[:-1]
                return
            if len(e.char) == 1 and e.char.isprintable():
                if self.student_id == "Guest":
                    self.student_id = e.char
                else:
                    self.student_id += e.char
                return

        if not self.round_active:
            if e.keysym.lower() in ("space", "return"):
                self._reset_round()
            return

        px, py = self.player.pos
        moved = False
        if e.keysym in ("Left", "a"):
            px = max(0, px - 1); moved = True
        elif e.keysym in ("Right", "d"):
            px = min(GRID_W - 1, px + 1); moved = True
        elif e.keysym in ("Up", "w"):
            py = max(0, py - 1); moved = True
        elif e.keysym in ("Down", "s"):
            py = min(GRID_H - 1, py + 1); moved = True
        elif e.keysym == "1":
            self._action_place_solar()
        elif e.keysym == "2":
            self._action_add_green()
        elif e.keysym == "3":
            self._action_upgrade_road()
        elif e.keysym.lower() == "f":
            self._action_feed_building()
        elif e.keysym.lower() == "h":
            self.show_help = not self.show_help

        if moved:
            self.player.pos = (px, py)
            # Pickup scraps if stepping onto one
            if hasattr(self, 'scraps') and self.player.pos in self.scraps:
                self.scraps.remove(self.player.pos)
                self.energy += 1
                self._flash("Collected scrap: +1 Energy")

    # --- Actions ---
    def _action_place_solar(self):
        x, y = self.player.pos
        t = self.grid[y][x]
        if t.kind == TileType.BUILDING and not t.has_solar:
            t.has_solar = True
            self.renewables += 1
            self._apply_effects(carbon_delta=-3.0, happy_delta=+1.0)
            self._flash("Solar installed: cleaner energy!")
        else:
            self._flash("Find a building to place solar (1)")

    def _action_add_green(self):
        x, y = self.player.pos
        t = self.grid[y][x]
        if t.kind in (TileType.EMPTY, TileType.PARK):
            if t.kind != TileType.GREEN:
                t.kind = TileType.GREEN
                self.green_spaces += 1
                t.green_type = random.choice(["flowers", "trees", "garden"])
                self._apply_effects(carbon_delta=-2.0, happy_delta=+2.0)
                self._flash("Green space added: cleaner air!")
            else:
                self._flash("This spot is already green")
        else:
            self._flash("Add green on empty/park tiles (2)")

    def _action_upgrade_road(self):
        x, y = self.player.pos
        t = self.grid[y][x]
        if t.kind == TileType.ROAD and not t.upgraded:
            t.upgraded = True
            self._apply_effects(carbon_delta=-2.0, happy_delta=+1.0)
            self._flash("Road upgraded: bike/pedestrian friendly!")
        elif t.kind == TileType.ROAD:
            self._flash("Road already upgraded")
        else:
            self._flash("Upgrade roads into bike/ped paths (3)")

    def _action_feed_building(self):
        x, y = self.player.pos
        t = self.grid[y][x]
        if t.kind == TileType.BUILDING and self.energy > 0:
            self.energy -= 1
            extra = -3.0 if t.has_solar else -1.5
            self._apply_effects(carbon_delta=extra, happy_delta=+0.5)
            self._flash("Fed building with energy!")
        elif t.kind != TileType.BUILDING:
            self._flash("Stand on a building to feed (F)")
        else:
            self._flash("No energy. Collect scraps first.")

    def _apply_effects(self, carbon_delta: float, happy_delta: float):
        self.carbon = max(0.0, min(100.0, self.carbon + carbon_delta))
        self.happiness = max(0.0, min(100.0, self.happiness + happy_delta))

    def _flash(self, msg: str, seconds: float = 1.8):
        self.flash_text = (msg, time.time() + seconds)

    # --- Loop ---
    def _tick(self):
        now = time.time()
        if getattr(self, 'awaiting_nfc', False):
            # Waiting for simulated NFC scan; do not start timer
            pass
        elif self.round_active:
            remaining = max(0, self.round_seconds - int(now - self.round_start))
            if remaining == 0:
                self.round_active = False
                self.round_end_time = now
                self.end_carbon = int(self.carbon)
                self.end_happiness = int(self.happiness)
            self._update_citizens()

        self._draw()
        self.root.after(33, self._tick)  # ~30 FPS

    def _update_citizens(self):
        # Mood trends towards global happiness
        target = self.happiness / 100.0
        for c in self.citizens:
            c.mood += (target - c.mood) * 0.02
            c.step(GRID_W, GRID_H)

    # --- Drawing ---
    def _draw(self):
        self.canvas.delete("all")
        self._draw_grid()
        self._draw_smog_layer()
        self._draw_scraps()
        self._draw_citizens()
        self._draw_player()
        self._draw_compi()
        self._draw_hud2()
        if self.show_help:
            self._draw_help()
        self._draw_overlays()
        if not self.round_active:
            self._draw_end_screen2()

    def _tile_color(self, t: Tile) -> str:
        # Base colors per type
        base = {
            TileType.EMPTY: (40, 40, 45),
            TileType.ROAD: (70, 70, 80),
            TileType.BUILDING: (90, 90, 110),
            TileType.PARK: (35, 80, 40),
            TileType.GREEN: (30, 120, 45),
        }[t.kind]
        # Smog darkens when carbon is high
        smog = self.carbon / 100.0  # 0 clear, 1 dark
        # If upgraded/solar, slightly brighten
        brighten = 0
        if t.kind == TileType.ROAD and t.upgraded:
            brighten += 15
        if t.kind == TileType.BUILDING and t.has_solar:
            brighten += 15
        r, g, b = base
        r = max(0, min(255, int(r * (0.7 + 0.3 * (1 - smog))) + brighten))
        g = max(0, min(255, int(g * (0.7 + 0.3 * (1 - smog))) + brighten))
        b = max(0, min(255, int(b * (0.7 + 0.3 * (1 - smog))) + brighten))
        return f"#{r:02x}{g:02x}{b:02x}"

    def _draw_grid(self):
        for y in range(GRID_H):
            for x in range(GRID_W):
                t = self.grid[y][x]
                x0, y0 = x * TILE, y * TILE
                x1, y1 = x0 + TILE, y0 + TILE
                color = self._tile_color(t)
                self.canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="#2a2a2a")
                # Details
                if t.kind == TileType.ROAD:
                    line_color = "#c6ff9e" if t.upgraded else "#cccccc"
                    self.canvas.create_line(x0+4, (y0+y1)//2, x1-4, (y0+y1)//2, fill=line_color)
                elif t.kind == TileType.BUILDING:
                    self.canvas.create_rectangle(x0+6, y0+6, x1-6, y1-6, outline="#191919")
                    if t.has_solar:
                        self.canvas.create_rectangle(x0+8, y0+8, x0+18, y0+14, fill="#2ad4ff", outline="")
                elif t.kind in (TileType.PARK, TileType.GREEN):
                    gtype = t.green_type or ("trees" if t.kind == TileType.PARK else random.choice(["flowers","trees"]))
                    if gtype == "trees":
                        for i in range(2):
                            cx = x0 + 8 + i * 14
                            cy = y0 + 10 + i * 6
                            self.canvas.create_oval(cx, cy, cx+10, cy+10, fill="#2ecc71", outline="")
                    elif gtype == "flowers":
                        colors = ["#f87171", "#fbbf24", "#60a5fa", "#34d399"]
                        for i in range(3):
                            cx = x0 + 6 + i * 9
                            cy = y0 + 18
                            self.canvas.create_oval(cx, cy, cx+6, cy+6, fill=random.choice(colors), outline="")
                    elif gtype == "garden":
                        self.canvas.create_rectangle(x0+6, y0+6, x1-6, y1-6, outline="#14532d")
                        for i in range(3):
                            cx = x0 + 10 + i * 8
                            cy = y0 + 12 + (i%2)*6
                            self.canvas.create_line(cx, cy, cx, cy+8, fill="#16a34a", width=2)

    def _draw_player(self):
        x, y = self.player.pos
        x0, y0 = x * TILE, y * TILE
        self.canvas.create_rectangle(x0+8, y0+8, x0+TILE-8, y0+TILE-8, fill="#ffd166", outline="#000000")

    def _draw_citizens(self):
        for c in self.citizens:
            x0 = int(c.pos[0] * TILE) + 8
            y0 = int(c.pos[1] * TILE) + 8
            mood = max(0, min(1, c.mood))
            # Red -> Yellow -> Green
            r = int(255 * (1 - mood))
            g = int(200 * mood + 55)
            b = 60
            self.canvas.create_oval(x0, y0, x0+12, y0+12, fill=f"#{r:02x}{g:02x}{b:02x}", outline="")

    def _draw_compi(self):
        # Friendly creature reacting to improvements
        self.compi_phase += 0.15 + (100 - self.carbon) * 0.0005
        base_x = 32
        base_y = GRID_H * TILE + 70
        jump = int(8 * abs(random.random() * 0.4 + 0.6) * (1 - self.carbon/100.0))
        size = 18 + int((100 - self.carbon) * 0.05)
        self.canvas.create_oval(base_x, base_y - jump, base_x + size, base_y - jump + size,
                                 fill="#7bdff2", outline="#075985")
        self.canvas.create_text(base_x + size//2, base_y - jump - 10, text="Compi", fill="#cce9ff", font=("Segoe UI", 9))

        # Mini-creatures appear as ecosystem thrives
        if self.green_spaces > 0:
            for i in range(min(12, 2 + self.green_spaces)):
                bx = 100 + (i * 18) % (CANVAS_W - 160)
                by = GRID_H * TILE + 70 + int(6 * math.sin(time.time()*2 + i))
                color = "#fde68a" if i % 2 == 0 else "#bfdbfe"
                self.canvas.create_oval(bx, by, bx+4, by+4, fill=color, outline="")

    def _draw_bar(self, x: int, y: int, w: int, h: int, pct: float, fg: str, bg: str, frame: str, label: str):
        self.canvas.create_rectangle(x, y, x+w, y+h, fill=bg, outline=frame)
        fill_w = int(w * max(0.0, min(1.0, pct)))
        self.canvas.create_rectangle(x, y, x+fill_w, y+h, fill=fg, outline="")
        self.canvas.create_text(x+w//2, y+h//2, text=label, fill="#111111" if pct > 0.5 else "#f0f0f0", font=("Segoe UI", 10, "bold"))

    def _tile_improvement_influence(self, x: int, y: int) -> float:
        radius = 3
        influence = 0.0
        for dy in range(-radius, radius+1):
            for dx in range(-radius, radius+1):
                nx, ny = x+dx, y+dy
                if nx < 0 or ny < 0 or nx >= GRID_W or ny >= GRID_H:
                    continue
                t = self.grid[ny][nx]
                dist = abs(dx) + abs(dy)
                if dist == 0:
                    dist = 1
                weight = 1.0 / dist
                if t.kind == TileType.GREEN:
                    influence += 0.6 * weight
                if t.kind == TileType.ROAD and t.upgraded:
                    influence += 0.4 * weight
                if t.kind == TileType.BUILDING and t.has_solar:
                    influence += 0.5 * weight
        return min(2.5, influence)

    def _draw_smog_layer(self):
        base = self.carbon / 100.0
        for y in range(GRID_H):
            for x in range(GRID_W):
                influence = self._tile_improvement_influence(x, y)
                local = max(0.0, base - 0.12 * influence)
                if local <= 0.05:
                    continue
                x0, y0 = x * TILE, y * TILE
                x1, y1 = x0 + TILE, y0 + TILE
                if local > 0.66:
                    stip = 'gray75'
                elif local > 0.33:
                    stip = 'gray50'
                else:
                    stip = 'gray25'
                self.canvas.create_rectangle(x0, y0, x1, y1, fill="#000000", outline="", stipple=stip)

    def _draw_scraps(self):
        for (x, y) in getattr(self, 'scraps', []):
            x0, y0 = x * TILE + 12, y * TILE + 12
            self.canvas.create_rectangle(x0, y0, x0+8, y0+8, fill="#9ca3af", outline="#4b5563")

    def _world_health_score(self) -> float:
        carbon_score = max(0.0, min(100.0, 100.0 - self.carbon))
        green_score = max(0.0, min(100.0, self.green_spaces * 12.5))
        happy_score = max(0.0, min(100.0, self.happiness))
        renew_score = max(0.0, min(100.0, self.renewables * 12.5))
        eco_score = max(0.0, min(100.0, (2 + self.green_spaces) * 8.0))
        return (carbon_score * 0.30 + green_score * 0.25 + happy_score * 0.20 + renew_score * 0.15 + eco_score * 0.10)

    def _draw_overlays(self):
        # NFC prompt overlay
        if getattr(self, 'awaiting_nfc', False):
            w, h = 520, 180
            x0, y0 = (CANVAS_W - w)//2, (CANVAS_H - h)//2 - 30
            self.canvas.create_rectangle(x0, y0, x0+w, y0+h, fill="#0b1220", outline="#334155")
            self.canvas.create_text(x0+w//2, y0+26, text="Scan NFC to load avatar", fill="#e2e8f0", font=("Segoe UI", 16, "bold"))
            self.canvas.create_text(x0+w//2, y0+60, text="Type your Student ID and press Enter", fill="#cbd5e1", font=("Segoe UI", 11))
            self.canvas.create_text(x0+w//2, y0+92, text=f"ID: {self.student_id}", fill="#93c5fd", font=("Consolas", 12, "bold"))
            return

        # Quick Overview 0:00–0:15
        elapsed = time.time() - self.round_start
        if 0 <= elapsed <= 15:
            w, h = 640, 160
            x0, y0 = (CANVAS_W - w)//2, 18
            self.canvas.create_rectangle(x0, y0, x0+w, y0+h, fill="#111827", outline="#334155")
            tip = (
                "Welcome! Your city's air quality is low.\n"
                "Collect scraps, add green spaces, and feed energy to buildings."
            )
            self.canvas.create_text(x0+14, y0+16, anchor="nw", text=tip, fill="#e5e7eb", font=("Segoe UI", 12))

    def _draw_hud2(self):
        y0 = GRID_H * TILE
        self.canvas.create_rectangle(0, y0, CANVAS_W, CANVAS_H, fill="#0f172a", outline="")

        # Timer
        if self.round_active:
            remaining = max(0, self.round_seconds - int(time.time() - self.round_start))
        else:
            remaining = 0
        mm, ss = divmod(remaining, 60)
        self.canvas.create_text(CANVAS_W - 80, y0 + 24, text=f"{mm:01d}:{ss:02d}", fill="#e2e8f0", font=("Segoe UI", 20, "bold"))
        self.canvas.create_text(CANVAS_W - 80, y0 + 44, text="Timer", fill="#94a3b8", font=("Segoe UI", 9))

        # Bars
        carbon_pct = self.carbon / 100.0
        carbon_color = "#16a34a" if carbon_pct < 0.33 else ("#f59e0b" if carbon_pct < 0.66 else "#ef4444")
        self._draw_bar(120, y0+16, 220, 18, 1 - carbon_pct, fg=carbon_color, bg="#111827", frame="#374151", label="Air Quality")
        self._draw_bar(120, y0+42, 220, 18, self.happiness/100.0, fg="#22c55e", bg="#111827", frame="#374151", label="Citizen Happiness")

        # Counts
        self.canvas.create_text(370, y0+25, text=f"Solar: {self.renewables}", fill="#93c5fd", font=("Segoe UI", 10))
        self.canvas.create_text(370, y0+45, text=f"Green: {self.green_spaces}", fill="#86efac", font=("Segoe UI", 10))
        self.canvas.create_text(450, y0+25, text=f"Energy: {self.energy}", fill="#fde68a", font=("Segoe UI", 10))

        # Challenge progress
        target = self.challenge_target
        achieved = self.carbon <= target
        ch_color = "#22c55e" if achieved else "#f59e0b"
        self.canvas.create_text(540, y0+24, text=f"Goal: carbon <= {target}", fill=ch_color, font=("Segoe UI", 11, "bold"))

    def _draw_hud(self):
        y0 = GRID_H * TILE
        self.canvas.create_rectangle(0, y0, CANVAS_W, CANVAS_H, fill="#0f172a", outline="")

        # Timer
        if self.round_active:
            remaining = max(0, self.round_seconds - int(time.time() - self.round_start))
        else:
            remaining = 0
        mm, ss = divmod(remaining, 60)
        self.canvas.create_text(CANVAS_W - 80, y0 + 24, text=f"{mm:01d}:{ss:02d}", fill="#e2e8f0", font=("Segoe UI", 20, "bold"))
        self.canvas.create_text(CANVAS_W - 80, y0 + 44, text="Timer", fill="#94a3b8", font=("Segoe UI", 9))

        # Bars
        carbon_pct = self.carbon / 100.0
        # Color from green->red
        carbon_color = "#16a34a" if carbon_pct < 0.33 else ("#f59e0b" if carbon_pct < 0.66 else "#ef4444")
        self._draw_bar(120, y0+16, 220, 18, 1 - carbon_pct, fg=carbon_color, bg="#111827", frame="#374151", label="Air Quality")
        self._draw_bar(120, y0+42, 220, 18, self.happiness/100.0, fg="#22c55e", bg="#111827", frame="#374151", label="Citizen Happiness")

        # Counts
        self.canvas.create_text(370, y0+25, text=f"Solar: {self.renewables}", fill="#93c5fd", font=("Segoe UI", 10))
        self.canvas.create_text(370, y0+45, text=f"Green: {self.green_spaces}", fill="#86efac", font=("Segoe UI", 10))
        self.canvas.create_text(450, y0+25, text=f"Energy: {self.energy}", fill="#fde68a", font=("Segoe UI", 10))

        # Challenge progress
        target = self.challenge_target
        achieved = self.carbon <= target
        ch_color = "#22c55e" if achieved else "#f59e0b"
        self.canvas.create_text(540, y0+24, text=f"Goal: carbon ≤ {target}", fill=ch_color, font=("Segoe UI", 11, "bold"))

        # Flash feedback
        if self.flash_text is not None:
            msg, until = self.flash_text
            if time.time() > until:
                self.flash_text = None
            else:
                self.canvas.create_text(CANVAS_W//2, y0+80, text=msg, fill="#eab308", font=("Segoe UI", 12, "bold"))

    def _draw_help(self):
        pad = 10
        lines = [
            "Welcome! Reduce carbon by upgrading your district.",
            "Move: Arrow keys / WASD",
            "1: Place Solar (on buildings)",
            "2: Add Green Space (on empty/park)",
            "3: Upgrade Road (bike/pedestrian)",
            "F: Feed Building (use Energy)",
            "H: Toggle Help",
        ]
        text = "\n".join(lines)
        w = 360
        h = 110
        self.canvas.create_rectangle(pad, pad, pad+w, pad+h, fill="#111827", outline="#334155")
        self.canvas.create_text(pad+8, pad+8, anchor="nw", text=text, fill="#e5e7eb", font=("Segoe UI", 10))

    def _draw_end_screen(self):
        # Overlay
        self.canvas.create_rectangle(0, 0, CANVAS_W, CANVAS_H, fill="", outline="#94a3b8")
        box_w = 520
        box_h = 220
        x0 = (CANVAS_W - box_w)//2
        y0 = (CANVAS_H - box_h)//2 - 30
        self.canvas.create_rectangle(x0, y0, x0+box_w, y0+box_h, fill="#0b1220", outline="#334155")
        self.canvas.create_text(x0+box_w//2, y0+24, text="Round Complete", fill="#e2e8f0", font=("Segoe UI", 16, "bold"))

        # Before/after
        self.canvas.create_text(x0+120, y0+70, text=f"Carbon: {self.start_carbon} → {int(self.carbon)}", fill="#93c5fd", font=("Segoe UI", 12))
        self.canvas.create_text(x0+120, y0+92, text=f"Happiness: 38 → {int(self.happiness)}", fill="#86efac", font=("Segoe UI", 12))
        self.canvas.create_text(x0+120, y0+114, text=f"Solar: {self.renewables}", fill="#d1fae5", font=("Segoe UI", 11))
        self.canvas.create_text(x0+120, y0+134, text=f"Green Spaces: {self.green_spaces}", fill="#d1fae5", font=("Segoe UI", 11))

        # Narrative feedback
        reduction = self.start_carbon - int(self.carbon)
        msg = f"You reduced carbon by {reduction}%! Citizens are happier."
        self.canvas.create_text(x0+310, y0+90, text=msg, fill="#fef08a", font=("Segoe UI", 11))

        achieved = int(self.carbon) <= self.challenge_target
        goal_text = "Goal met!" if achieved else "Goal not met yet."
        goal_color = "#22c55e" if achieved else "#ef4444"
        self.canvas.create_text(x0+310, y0+116, text=goal_text, fill=goal_color, font=("Segoe UI", 12, "bold"))

        self.canvas.create_text(x0+box_w//2, y0+box_h-26, text="Press Space/Enter to play again", fill="#cbd5e1", font=("Segoe UI", 10))

    def _draw_end_screen2(self):
        # Overlay
        self.canvas.create_rectangle(0, 0, CANVAS_W, CANVAS_H, fill="", outline="#94a3b8")
        box_w = 520
        box_h = 240
        x0 = (CANVAS_W - box_w)//2
        y0 = (CANVAS_H - box_h)//2 - 30
        self.canvas.create_rectangle(x0, y0, x0+box_w, y0+box_h, fill="#0b1220", outline="#334155")
        self.canvas.create_text(x0+box_w//2, y0+24, text="Round Complete", fill="#e2e8f0", font=("Segoe UI", 16, "bold"))

        # Before/after
        self.canvas.create_text(x0+120, y0+70, text=f"Carbon: {self.start_carbon} -> {int(self.carbon)}", fill="#93c5fd", font=("Segoe UI", 12))
        self.canvas.create_text(x0+120, y0+92, text=f"Happiness: 38 -> {int(self.happiness)}", fill="#86efac", font=("Segoe UI", 12))
        self.canvas.create_text(x0+120, y0+114, text=f"Solar: {self.renewables}", fill="#d1fae5", font=("Segoe UI", 11))
        self.canvas.create_text(x0+120, y0+134, text=f"Green Spaces: {self.green_spaces}", fill="#d1fae5", font=("Segoe UI", 11))

        # Narrative feedback
        reduction = self.start_carbon - int(self.carbon)
        msg = f"You reduced carbon by {reduction}%! Citizens are happier."
        self.canvas.create_text(x0+310, y0+90, text=msg, fill="#fef08a", font=("Segoe UI", 11))
        self.canvas.create_text(x0+310, y0+110, text="Adding green space helped absorb carbon. Well done!", fill="#e5e7eb", font=("Segoe UI", 9))

        achieved = int(self.carbon) <= self.challenge_target
        goal_text = "Goal met!" if achieved else "Goal not met yet."
        goal_color = "#22c55e" if achieved else "#ef4444"
        self.canvas.create_text(x0+310, y0+128, text=goal_text, fill=goal_color, font=("Segoe UI", 12, "bold"))

        # World Health summary
        world_health = int(self._world_health_score())
        self.canvas.create_text(x0+box_w//2, y0+box_h-46, text=f"World Health: {world_health}%", fill="#93c5fd", font=("Segoe UI", 12, "bold"))
        self.canvas.create_text(x0+box_w//2, y0+box_h-26, text="Press Space/Enter to play again", fill="#cbd5e1", font=("Segoe UI", 10))

    def _reset_round(self):
        self.round_active = True
        self.round_start = time.time()
        self.carbon = float(self.start_carbon)
        self.happiness = 38.0
        self.renewables = 0
        self.green_spaces = 0
        self.energy = 0
        self.flash_text = None
        # Reset map upgrades
        for row in self.grid:
            for t in row:
                t.has_solar = False
                t.upgraded = False
                if t.kind == TileType.GREEN:
                    t.kind = TileType.EMPTY
                t.green_type = None
        # Respawn scraps
        self.scraps = self._spawn_scraps(10)


def main():
    root = tk.Tk()
    Game(root)
    root.mainloop()


if __name__ == "__main__":
    main()
