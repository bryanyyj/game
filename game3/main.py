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
# Changed to vertical mobile-friendly dimensions
GRID_W = 10
GRID_H = 16
TILE = 40
HUD_H = 160
CANVAS_W = GRID_W * TILE  # 400
CANVAS_H = GRID_H * TILE + HUD_H  # 880

ROUND_SECONDS = 120  # 2:00 minutes


class TileType:
    EMPTY = "empty"
    ROAD = "road"
    BUILDING = "building"
    PARK = "park"
    GREEN = "green"  # planted during play
    POLLUTION = "pollution"  # pollution/rubbish
    RUBBISH_BIN = "rubbish_bin"  # placed by player


@dataclass
class Tile:
    kind: str
    upgraded: bool = False      # for roads (bike/pedestrian)
    has_solar: bool = False     # for buildings
    green_type: Optional[str] = None  # 'flowers' | 'trees' | 'garden'
    pollution_amount: int = 0   # for pollution tiles, amount of pollution
    is_cleaned: bool = False    # for pollution tiles that have been cleaned


@dataclass
class Player:
    pos: Vec2 = (1, 1)
    money: int = 50  # Starting money to buy items
    solar_panels_available: int = 3  # Number of solar panels available to place
    green_spaces_available: int = 3  # Number of green spaces available to place


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
        self.citizens: List[Citizen] = [Citizen([random.uniform(0, GRID_W-1), random.uniform(0, GRID_H-1)]) for _ in range(20)]

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

        # Daily missions system
        self.daily_missions = [
            {"id": 1, "title": "Clean 3 pollution spots", "completed": False, "target": 3, "current": 0, "type": "clean_pollution"},
            {"id": 2, "title": "Install 2 solar panels", "completed": False, "target": 2, "current": 0, "type": "install_solar"},
            {"id": 3, "title": "Plant 4 green spaces", "completed": False, "target": 4, "current": 0, "type": "plant_green"},
            {"id": 4, "title": "Reduce carbon by 8%", "completed": False, "target": 8, "current": 0, "type": "reduce_carbon"}
        ]
        self.missions_visible = False  # To toggle missions display

        # Feedback state
        self.flash_text: Optional[Tuple[str, float]] = None
        self.compi_phase = 0.0

        # Tutorial system - Track tutorial progress
        self.tutorial_step = 0  # 0 = not started, 1-6 = tutorial steps
        self.tutorial_messages = [
            "Welcome! Your city needs your help to become more eco-friendly.",
            "First, let's learn to move around. Use ARROW KEYS or WASD to move your character.",
            "Great! Now try to collect some energy scraps (gray circles) by walking over them.",
            "You can reduce carbon by adding green spaces! Press '2' to plant on empty areas.",
            "Now try installing solar panels on buildings. Press '1' on a building to install.",
            "You can buy more items with money! Press 'M' to see your missions and goals.",
            "Tutorial complete! Explore all features and complete your daily missions.",
        ]
        
        # Track tutorial actions to determine when to progress
        self.tutorial_actions_completed = {
            'moved': False,
            'collected_scrap': False,
            'placed_green': False,
            'placed_solar': False,
            'viewed_missions': False
        }
        
        # Help overlay starts as false since we'll have tutorials instead
        self.show_help = False
        self.show_tutorial = True  # Show tutorial instead of help at start
        
        # Ensure player has some resources for tutorial
        self.player.solar_panels_available = max(self.player.solar_panels_available, 1)  # At least 1 solar panel for tutorial
        self.player.green_spaces_available = max(self.player.green_spaces_available, 1)   # At least 1 green space for tutorial
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
                # Adapt road layout for vertical game with more vertical flow
                if y in (4, 9, 14) or x in (3, 7):  # Horizontal roads for vertical layout
                    row.append(Tile(TileType.ROAD))
                else:
                    r = random.random()
                    # Increase building density for vertical layout
                    if r < 0.25:
                        row.append(Tile(TileType.BUILDING))
                    elif r < 0.35:  # Add pollution spots
                        pollution_amount = random.randint(1, 3)  # Different levels of pollution
                        row.append(Tile(TileType.POLLUTION, pollution_amount=pollution_amount))
                    elif r < 0.50:
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
        
        # Handle tutorial progression - advance from initial message when any action occurs during step 0
        if self.show_tutorial and self.tutorial_step == 0:
            self.tutorial_step = 1

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
        elif e.keysym.lower() == "m":
            # Check tutorial progress
            if self.show_tutorial and not self.tutorial_actions_completed['viewed_missions'] and self.tutorial_step == 5:
                self.tutorial_actions_completed['viewed_missions'] = True
                self._check_tutorial_progress()
            
            self.missions_visible = not self.missions_visible  # Always toggle missions display
        elif e.keysym.lower() == "c":
            self._action_clean_pollution()  # Clean pollution
        elif e.keysym.lower() == "5":
            self._action_buy_solar()  # Buy solar panels
        elif e.keysym.lower() == "6":
            self._action_buy_green()  # Buy green spaces
        elif e.keysym.lower() == "b":
            self._action_place_bin()  # Place a rubbish bin

        if moved:
            self.player.pos = (px, py)
            # Check if we need to progress the tutorial
            if self.show_tutorial and not self.tutorial_actions_completed['moved'] and self.tutorial_step == 1:
                self.tutorial_actions_completed['moved'] = True
                self._check_tutorial_progress()
                
            # Pickup scraps if stepping onto one
            if hasattr(self, 'scraps') and self.player.pos in self.scraps:
                self.scraps.remove(self.player.pos)
                self.energy += 1
                self._flash("Collected scrap: +1 Energy")
                
                # Check if we collected enough to progress tutorial
                if self.show_tutorial and not self.tutorial_actions_completed['collected_scrap'] and self.tutorial_step == 2:
                    self.tutorial_actions_completed['collected_scrap'] = True
                    self._check_tutorial_progress()

    # --- Actions ---
    def _action_place_solar(self):
        x, y = self.player.pos
        t = self.grid[y][x]
        if t.kind == TileType.BUILDING and not t.has_solar:
            if self.player.solar_panels_available > 0:
                t.has_solar = True
                self.player.solar_panels_available -= 1
                self.renewables += 1
                self._apply_effects(carbon_delta=-3.0, happy_delta=+1.0)
                
                # Check daily mission
                for mission in self.daily_missions:
                    if mission["type"] == "install_solar" and not mission["completed"]:
                        mission["current"] += 1
                        if mission["current"] >= mission["target"]:
                            mission["completed"] = True
                            self.player.money += 10  # Reward for completing mission
                            self._flash(f"Mission completed: {mission['title']}! +10 money")
                
                # Check tutorial progress
                if self.show_tutorial and not self.tutorial_actions_completed['placed_solar'] and self.tutorial_step == 4:
                    self.tutorial_actions_completed['placed_solar'] = True
                    self._check_tutorial_progress()
                    self._flash("Solar panel installed! Great job! Now check your missions with 'M'.")
                
                self._flash("Solar installed: cleaner energy!")
            else:
                self._flash("No solar panels available. Buy more (key 5)")
        else:
            self._flash("Find a building to place solar (1)")

    def _action_add_green(self):
        x, y = self.player.pos
        t = self.grid[y][x]
        if t.kind in (TileType.EMPTY, TileType.PARK):
            if t.kind != TileType.GREEN:
                if self.player.green_spaces_available > 0:
                    t.kind = TileType.GREEN
                    self.player.green_spaces_available -= 1
                    self.green_spaces += 1
                    t.green_type = random.choice(["flowers", "trees", "garden"])
                    self._apply_effects(carbon_delta=-2.0, happy_delta=+2.0)
                    
                    # Check daily mission
                    for mission in self.daily_missions:
                        if mission["type"] == "plant_green" and not mission["completed"]:
                            mission["current"] += 1
                            if mission["current"] >= mission["target"]:
                                mission["completed"] = True
                                self.player.money += 10  # Reward for completing mission
                                self._flash(f"Mission completed: {mission['title']}! +10 money")
                    
                    # Check tutorial progress
                    if self.show_tutorial and not self.tutorial_actions_completed['placed_green'] and self.tutorial_step == 3:
                        self.tutorial_actions_completed['placed_green'] = True
                        self._check_tutorial_progress()
                        self._flash("Green space placed! Well done! Now install a solar panel with '1'.")
                    
                    self._flash("Green space added: cleaner air!")
                else:
                    self._flash("No green spaces available. Buy more (key 6)")
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

    def _action_clean_pollution(self):
        x, y = self.player.pos
        t = self.grid[y][x]
        if t.kind == TileType.POLLUTION and t.pollution_amount > 0:
            # Clean the pollution
            t.pollution_amount -= 1
            t.is_cleaned = True
            self._apply_effects(carbon_delta=-1.0, happy_delta=+0.5)
            self._flash("Pollution cleaned! +1 Happiness")
            
            # Check daily mission
            for mission in self.daily_missions:
                if mission["type"] == "clean_pollution" and not mission["completed"]:
                    mission["current"] += 1
                    if mission["current"] >= mission["target"]:
                        mission["completed"] = True
                        self.player.money += 10  # Reward for completing mission
                        self._flash(f"Mission completed: {mission['title']}! +10 money")
        else:
            self._flash("Clean pollution spots (C)")

    def _action_buy_solar(self):
        # Buy solar panels with money
        if self.player.money >= 15:
            self.player.money -= 15
            self.player.solar_panels_available += 1
            self._flash("Bought 1 solar panel! Use key 1 to place")
        else:
            self._flash("Need $15 to buy solar panel")

    def _action_buy_green(self):
        # Buy green spaces with money
        if self.player.money >= 10:
            self.player.money -= 10
            self.player.green_spaces_available += 1
            self._flash("Bought 1 green space! Use key 2 to place")
        else:
            self._flash("Need $10 to buy green space")

    def _action_place_bin(self):
        x, y = self.player.pos
        t = self.grid[y][x]
        if t.kind == TileType.EMPTY and self.player.money >= 5:
            self.player.money -= 5
            self.grid[y][x] = Tile(TileType.RUBBISH_BIN)
            self._apply_effects(carbon_delta=-0.5, happy_delta=+0.3)
            self._flash("Rubbish bin placed! Prevents pollution buildup")
        else:
            self._flash("Place bins on empty spaces. Cost: $5")

    def _apply_effects(self, carbon_delta: float, happy_delta: float):
        old_carbon = self.carbon
        self.carbon = max(0.0, min(100.0, self.carbon + carbon_delta))
        self.happiness = max(0.0, min(100.0, self.happiness + happy_delta))
        
        # Check daily mission for carbon reduction
        carbon_reduction = old_carbon - self.carbon
        if carbon_reduction > 0:
            for mission in self.daily_missions:
                if mission["type"] == "reduce_carbon" and not mission["completed"]:
                    mission["current"] = int(self.start_carbon - self.carbon)
                    if mission["current"] >= mission["target"]:
                        mission["completed"] = True
                        self.player.money += 15  # Bigger reward for carbon reduction
                        self._flash(f"Mission completed: {mission['title']}! +15 money")

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
        
        # Randomly increase pollution over time to add challenge
        if random.random() < 0.005:  # Small chance each frame
            # Find an empty tile to add pollution to
            empty_tiles = []
            for y in range(GRID_H):
                for x in range(GRID_W):
                    if self.grid[y][x].kind == TileType.EMPTY:
                        empty_tiles.append((x, y))
            
            if empty_tiles:
                x, y = random.choice(empty_tiles)
                # Convert empty tile to pollution with small amount
                self.grid[y][x] = Tile(TileType.POLLUTION, pollution_amount=1)
        
        # Citizens can also contribute to pollution occasionally
        if random.random() < 0.01:  # 1% chance each frame
            # Find a road tile near the citizen
            for c in random.sample(self.citizens, min(2, len(self.citizens))):  # Check 2 random citizens
                cx, cy = int(c.pos[0]), int(c.pos[1])
                # Look for nearby road to potentially add pollution
                for dy in [-1, 0, 1]:
                    for dx in [-1, 0, 1]:
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < GRID_W and 0 <= ny < GRID_H:
                            if self.grid[ny][nx].kind == TileType.ROAD and random.random() < 0.3:
                                # Create a pollution spot near the road
                                if self.grid[ny][nx].kind not in [TileType.POLLUTION, TileType.RUBBISH_BIN]:
                                    new_x, new_y = nx, ny
                                    # Try to find an adjacent empty space for the pollution
                                    for ady in [-1, 0, 1]:
                                        for adx in [-1, 0, 1]:
                                            ax, ay = new_x + adx, new_y + ady
                                            if (0 <= ax < GRID_W and 0 <= ay < GRID_H and 
                                                self.grid[ay][ax].kind == TileType.EMPTY):
                                                self.grid[ay][ax] = Tile(TileType.POLLUTION, pollution_amount=1)
                                                break

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
        if self.show_tutorial and self.tutorial_step < len(self.tutorial_messages):
            self._draw_tutorial()
        elif self.show_help:
            self._draw_help()
        elif self.missions_visible:  # Only show missions when help is not active
            self._draw_missions()
        self._draw_overlays()
        if not self.round_active:
            self._draw_end_screen2()

    def _tile_color(self, t: Tile) -> str:
        # Base colors per type with more realistic visual appeal
        base_colors = {
            TileType.EMPTY: (199, 210, 254),      # Light blue for empty spaces (like sky/plain)
            TileType.ROAD: (112, 128, 144),       # More realistic road gray
            TileType.BUILDING: (160, 174, 192),   # More building-like gray-blue
            TileType.PARK: (74, 161, 62),         # Rich green for parks
            TileType.GREEN: (46, 125, 50),        # Deep green for green spaces
            TileType.POLLUTION: (106, 76, 86),    # Brownish for pollution
            TileType.RUBBISH_BIN: (120, 119, 198) # Purple-gray for rubbish bins
        }
        
        if t.kind == TileType.POLLUTION:
            # Pollution color intensity based on pollution amount
            pollution_factor = min(1.0, t.pollution_amount / 3.0)  # 0-1 based on pollution level
            r, g, b = base_colors[TileType.POLLUTION]
            # Darker with more pollution
            r = int(r * (1 - 0.3 * pollution_factor))
            g = int(g * (1 - 0.2 * pollution_factor))
            b = int(b * (1 - 0.4 * pollution_factor))
        else:
            # Use base color for other tile types
            r, g, b = base_colors[t.kind]
        
        # Smog darkens when carbon is high
        smog = self.carbon / 100.0  # 0 clear, 1 dark
        
        # Calculate improvement bonus to enhance tile brightness
        brighten = 0
        if t.kind == TileType.ROAD and t.upgraded:
            brighten += 35  # More noticeable upgrade effect
        if t.kind == TileType.BUILDING and t.has_solar:
            brighten += 35  # More noticeable solar effect
        if t.kind == TileType.GREEN:
            brighten += 25  # Green spaces are naturally brighter
        if t.kind == TileType.POLLUTION and t.is_cleaned:
            brighten += 50  # Cleaned pollution gets extra brightness
        
        # Enhanced color calculation with better contrast and preservation of color tone
        factor = 0.5 + 0.5 * (1 - smog)  # Base contrast
        r = max(0, min(255, int(r * factor) + brighten))
        g = max(0, min(255, int(g * factor) + brighten))
        b = max(0, min(255, int(b * factor) + brighten))
        
        return f"#{r:02x}{g:02x}{b:02x}"

    def _draw_grid(self):
        for y in range(GRID_H):
            for x in range(GRID_W):
                t = self.grid[y][x]
                x0, y0 = x * TILE, y * TILE
                x1, y1 = x0 + TILE, y0 + TILE
                color = self._tile_color(t)
                
                # Draw tile with rounded corners effect
                self.canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="#2a2a2a", width=1)
                
                # Additional details based on tile type
                if t.kind == TileType.ROAD:
                    # Draw more realistic road markings
                    line_color = "#a8e6cf" if t.upgraded else "#e2e2e2"
                    # Center line
                    self.canvas.create_line(x0+TILE//4, (y0+y1)//2, x1-TILE//4, (y0+y1)//2, fill=line_color, width=2)
                    # Draw road lane dividers
                    if not t.upgraded:
                        for i in range(0, TILE, 12):
                            cx = x0 + i
                            if cx < x1 - 4:
                                self.canvas.create_rectangle(cx, (y0+y1)//2 - 1, cx + 6, (y0+y1)//2 + 1, fill=line_color)
                    else:
                        # Draw bicycle lane markers if upgraded
                        self.canvas.create_line(x0+2, (y0+y1)//2 - 8, x1-2, (y0+y1)//2 - 8, fill="#90be6d", width=2, dash=(5, 5))
                        self.canvas.create_line(x0+2, (y0+y1)//2 + 8, x1-2, (y0+y1)//2 + 8, fill="#90be6d", width=2, dash=(5, 5))
                        
                elif t.kind == TileType.BUILDING:
                    # Draw more detailed building with various styles
                    building_height = TILE - 4
                    building_width = TILE - 4
                    building_x = x0 + 2
                    building_y = y0 + 2
                    
                    # Draw building base structure
                    self.canvas.create_rectangle(building_x, building_y, building_x + building_width, building_y + building_height, 
                                               fill="#cbd5e1", outline="#94a3b8", width=1)
                    
                    # Draw windows in a grid pattern based on building size
                    window_size = 4
                    window_spacing = 8
                    start_x = building_x + 4
                    start_y = building_y + 4
                    
                    # Calculate number of windows based on TILE size
                    windows_per_row = (building_width - 8) // window_spacing
                    windows_per_col = (building_height - 8) // window_spacing
                    
                    for row in range(min(windows_per_col, 4)):  # Maximum 4 rows
                        for col in range(min(windows_per_row, 3)):  # Maximum 3 columns
                            wx = start_x + col * window_spacing
                            wy = start_y + row * window_spacing
                            # Randomly light some windows
                            if random.random() > 0.3:  # 70% of windows are lit
                                window_color = "#fef3c7" if t.has_solar else "#dbeafe"
                            else:
                                window_color = "#64748b"  # Dark windows
                            self.canvas.create_rectangle(wx, wy, wx + window_size, wy + window_size, 
                                                       fill=window_color, outline="#475569", width=1)
                    
                    # Draw door at bottom
                    door_x = building_x + building_width // 2 - 3
                    door_y = building_y + building_height - 10
                    self.canvas.create_rectangle(door_x, door_y, door_x + 6, door_y + 8, 
                                               fill="#78350f", outline="#581c87", width=1)
                    
                    # Draw solar panels on top of building if present
                    if t.has_solar:
                        # Draw solar panel array on roof
                        roof_y = building_y + 2
                        for i in range(2):
                            sx = building_x + 4 + i * 14
                            sy = roof_y
                            self.canvas.create_rectangle(sx, sy, sx + 12, sy + 8, fill="#f59e0b", outline="#d97706", width=1)
                            # Add solar panel grid details
                            self.canvas.create_line(sx + 3, sy, sx + 3, sy + 8, fill="#d97706", width=1)
                            self.canvas.create_line(sx + 6, sy, sx + 6, sy + 8, fill="#d97706", width=1)
                            self.canvas.create_line(sx + 9, sy, sx + 9, sy + 8, fill="#d97706", width=1)
                            
                elif t.kind in (TileType.PARK, TileType.GREEN):
                    # Determine green space type
                    gtype = t.green_type or ("trees" if t.kind == TileType.PARK else random.choice(["flowers", "trees", "garden"]))
                    
                    if gtype == "trees":
                        # Draw more realistic trees
                        for i in range(2):
                            # Tree trunk
                            tx = x0 + 10 + i * 18
                            ty = y0 + 22
                            self.canvas.create_rectangle(tx, ty, tx + 4, ty + 12, fill="#8b4513", outline="#5d4037", width=1)
                            # Tree foliage with more detail
                            self.canvas.create_oval(tx - 6, ty - 10, tx + 10, ty + 6, fill="#16a34a", outline="#14532d", width=1)
                            # Add some variation
                            self.canvas.create_oval(tx - 2, ty - 14, tx + 14, ty - 2, fill="#22c55e", outline="#166534", width=1)
                    elif gtype == "flowers":
                        # Draw more diverse flowers
                        colors = ["#f87171", "#fbbf24", "#60a5fa", "#34d399", "#f0abfc"]
                        for i in range(5):
                            cx = x0 + 6 + i * 7
                            cy = y0 + 28
                            # Draw flower stem
                            self.canvas.create_line(cx, cy, cx, cy - 12, fill="#16a34a", width=2)
                            # Draw flower head with more detail
                            flower_color = random.choice(colors)
                            self.canvas.create_oval(cx - 4, cy - 14, cx + 4, cy - 6, fill=flower_color, outline="#115e59", width=1)
                            # Draw center of flower
                            self.canvas.create_oval(cx - 1.5, cy - 11, cx + 1.5, cy - 8, fill="#fbbf24", outline="")
                    elif gtype == "garden":
                        # Draw garden plot with more detail
                        self.canvas.create_rectangle(x0 + 2, y0 + 2, x1 - 2, y1 - 2, fill="#d9f99d", outline="#65a30d", width=2)
                        # Draw garden plants with more variety
                        for i in range(4):
                            px = x0 + 6 + i * 8
                            py = y0 + 8
                            # Draw a small plant
                            self.canvas.create_line(px, py, px, py - 10, fill="#16a34a", width=2)
                            # Draw leaves
                            self.canvas.create_oval(px - 5, py - 10, px + 3, py - 6, fill="#86efac", outline="#16a34a", width=1)
                            self.canvas.create_oval(px - 2, py - 12, px + 6, py - 8, fill="#86efac", outline="#16a34a", width=1)
                elif t.kind == TileType.POLLUTION:
                    # Draw pollution with visual indicators based on pollution amount
                    # Draw scattered pollution items
                    for i in range(t.pollution_amount):
                        px = x0 + 6 + (i * 8) % (TILE - 10)
                        py = y0 + 8 + (i * 5) % (TILE - 15)
                        # Draw trash items
                        trash_type = random.choice(["bag", "bottle", "can"])
                        if trash_type == "bag":
                            self.canvas.create_oval(px, py, px + 6, py + 4, fill="#6b7280", outline="")
                        elif trash_type == "bottle":
                            self.canvas.create_rectangle(px + 1, py, px + 5, py + 7, fill="#1e40af", outline="")
                        else:  # can
                            self.canvas.create_oval(px, py, px + 5, py + 5, fill="#9ca3af", outline="")
                    
                    # Draw warning sign if pollution is high
                    if t.pollution_amount >= 2:
                        self.canvas.create_text(x0 + TILE//2, y0 + TILE//2, text="⚠️", font=("Arial", 12), fill="#ef4444")
                elif t.kind == TileType.RUBBISH_BIN:
                    # Draw rubbish bin
                    bin_x = x0 + TILE//3
                    bin_y = y0 + TILE//3
                    # Bin body
                    self.canvas.create_rectangle(bin_x, bin_y, bin_x + 15, bin_y + 20, fill="#4b5563", outline="#1f2937", width=2)
                    # Bin opening
                    self.canvas.create_arc(bin_x - 2, bin_y - 5, bin_x + 17, bin_y + 5, 
                                          start=0, extent=180, style="chord", fill="#374151", outline="#1f2937")
                    # Draw recycling symbol
                    self.canvas.create_text(bin_x + 7, bin_y + 10, text="♻️", font=("Arial", 10))

    def _draw_player(self):
        x, y = self.player.pos
        x0, y0 = x * TILE, y * TILE
        # Draw player as a more detailed and refined character
        center_x = x0 + TILE // 2
        center_y = y0 + TILE // 2
        
        # Draw body with more detail
        body_color = "#ffd166"  # Skin tone
        self.canvas.create_oval(center_x - 14, center_y - 14, center_x + 14, center_y + 14, 
                                fill=body_color, outline="#000000", width=2)
        
        # Draw clothing (a simple shirt)
        shirt_color = "#4f46e5"  # Blue
        self.canvas.create_rectangle(center_x - 12, center_y - 2, center_x + 12, center_y + 12, 
                                    fill=shirt_color, outline="#000000", width=1)
        
        # Draw face details
        # Eyes with more detail
        eye_size = 4
        self.canvas.create_oval(center_x - 6, center_y - 4, center_x - 6 + eye_size, center_y - 4 + eye_size, 
                                fill="#ffffff", outline="#000000", width=1)
        self.canvas.create_oval(center_x + 6 - eye_size, center_y - 4, center_x + 6, center_y - 4 + eye_size, 
                                fill="#ffffff", outline="#000000", width=1)
        
        # Add pupils
        self.canvas.create_oval(center_x - 5, center_y - 3, center_x - 4, center_y - 2, 
                                fill="#000000", outline="")
        self.canvas.create_oval(center_x + 4, center_y - 3, center_x + 5, center_y - 2, 
                                fill="#000000", outline="")
        
        # Add eyebrows
        self.canvas.create_arc(center_x - 6, center_y - 7, center_x - 2, center_y - 3, 
                               start=0, extent=180, style="arc", outline="#000000", width=1)
        self.canvas.create_arc(center_x + 2, center_y - 7, center_x + 6, center_y - 3, 
                               start=0, extent=180, style="arc", outline="#000000", width=1)
        
        # Smile with more expression
        self.canvas.create_arc(center_x - 6, center_y + 2, center_x + 6, center_y + 8, 
                               start=0, extent=-180, style="arc", outline="#000000", width=1)
        
        # Add a simple hat or hair element
        self.canvas.create_arc(center_x - 12, center_y - 14, center_x + 12, center_y - 6, 
                               start=0, extent=180, style="chord", fill="#78350f", outline="#000000", width=1)

    def _draw_citizens(self):
        for i, c in enumerate(self.citizens):
            x0 = int(c.pos[0] * TILE) + TILE // 4
            y0 = int(c.pos[1] * TILE) + TILE // 4
            mood = max(0, min(1, c.mood))
            
            # Calculate base color based on mood (Red -> Yellow -> Green)
            r = int(255 * (1 - mood))
            g = int(200 * mood + 55)
            b = 60
            
            # Draw citizen as a more detailed character with unique features
            center_x = x0 + TILE // 2
            center_y = y0 + TILE // 2
            
            # Create unique visual features for each citizen based on their index
            citizen_type = i % 4  # 4 different citizen types
            
            # Body with unique colors based on citizen type
            if citizen_type == 0:  # Reddish/pinkish
                fill_color = f"#{min(255, r+30):02x}{g:02x}{min(255, b+30):02x}"
            elif citizen_type == 1:  # Blueish
                fill_color = f"#{r//2:02x}{min(255, int(g//1.5)):02x}{min(255, b+100):02x}"
            elif citizen_type == 2:  # Greenish
                fill_color = f"#{min(255, int(r//1.5)):02x}{min(255, g+50):02x}{b:02x}"
            else:  # Mixed
                fill_color = f"#{min(255, int((r+128)//1.5)):02x}{g:02x}{min(255, int((b+150)//1.5)):02x}"
            
            # Body with outline
            body_size = 10
            self.canvas.create_oval(center_x - body_size, center_y - body_size, 
                                    center_x + body_size, center_y + body_size, 
                                    fill=fill_color, outline="#000000", width=1)
            
            # Different accessories based on citizen type
            if citizen_type == 0:  # Hat
                hat_color = "#fbbf24" if mood > 0.5 else "#64748b"
                self.canvas.create_arc(center_x - 12, center_y - 12, 
                                       center_x + 12, center_y - 2,
                                       start=0, extent=180, style="chord", 
                                       fill=hat_color, outline="#000000", width=1)
            elif citizen_type == 1:  # Glasses
                self.canvas.create_oval(center_x - 6, center_y - 3, 
                                        center_x - 1, center_y + 1, 
                                        fill="#cbd5e1", outline="#0f172a", width=1)
                self.canvas.create_oval(center_x + 1, center_y - 3, 
                                        center_x + 6, center_y + 1, 
                                        fill="#cbd5e1", outline="#0f172a", width=1)
                # Bridge of glasses
                self.canvas.create_line(center_x - 1, center_y - 1, 
                                        center_x + 1, center_y - 1, 
                                        fill="#0f172a", width=2)
            elif citizen_type == 2:  # Hair style
                # Draw simple hair on top
                self.canvas.create_arc(center_x - 10, center_y - 10, 
                                       center_x + 10, center_y + 6, 
                                       start=0, extent=180, style="chord", 
                                       fill="#78350f", outline="#000000", width=1)
            else:  # Different clothing
                # Draw simple shirt pattern
                self.canvas.create_rectangle(center_x - 8, center_y, 
                                             center_x + 8, center_y + 6, 
                                             fill="#a5b4fc", outline="#000000", width=1)
            
            # Face details change based on mood
            eye_color = "#ffffff" if mood > 0.6 else "#aaaaaa" if mood > 0.3 else "#777777"
            
            # Eyes - positioned based on mood
            eye_offset = 1 if mood < 0.4 else -1 if mood > 0.7 else 0  # Eyes look up when happy, down when sad
            # Left eye
            self.canvas.create_oval(center_x - 5 + eye_offset, center_y - 2, 
                                    center_x - 1 + eye_offset, center_y + 1, 
                                    fill=eye_color, outline="#000000", width=1)
            # Add pupils based on mood
            pupil_color = "#0f172a" if mood > 0.4 else "#575757"
            self.canvas.create_oval(center_x - 4 + eye_offset, center_y - 1, 
                                    center_x - 2 + eye_offset, center_y, 
                                    fill=pupil_color, outline="")
            
            # Right eye
            self.canvas.create_oval(center_x + 1 + eye_offset, center_y - 2, 
                                    center_x + 5 + eye_offset, center_y + 1, 
                                    fill=eye_color, outline="#000000", width=1)
            # Add pupils based on mood
            self.canvas.create_oval(center_x + 2 + eye_offset, center_y - 1, 
                                    center_x + 4 + eye_offset, center_y, 
                                    fill=pupil_color, outline="")
            
            # Mouth changes with mood
            mouth_y_offset = 2 if mood < 0.3 else -1 if mood > 0.7 else 0  # Mouth position changes with mood
            if mood < 0.3:  # Sad - frown
                self.canvas.create_arc(center_x - 4, center_y + 1 + mouth_y_offset, 
                                       center_x + 4, center_y + 5 + mouth_y_offset, 
                                       start=0, extent=180, style="arc", 
                                       outline="#000000", width=1)
            elif mood > 0.7:  # Happy - smile
                self.canvas.create_arc(center_x - 4, center_y - 1 + mouth_y_offset, 
                                       center_x + 4, center_y + 3 + mouth_y_offset, 
                                       start=0, extent=-180, style="arc", 
                                       outline="#000000", width=1)
            else:  # Neutral
                self.canvas.create_line(center_x - 3, center_y + mouth_y_offset, 
                                        center_x + 3, center_y + mouth_y_offset, 
                                        fill="#000000", width=1)

    def _draw_compi(self):
        # Friendly creature reacting to improvements with more detail
        self.compi_phase += 0.15 + (100 - self.carbon) * 0.0005
        base_x = CANVAS_W // 2  # Center horizontally
        base_y = GRID_H * TILE + 40  # Move up for better vertical layout
        jump = int(8 * abs(random.random() * 0.4 + 0.6) * (1 - self.carbon/100.0))
        size = 24 + int((100 - self.carbon) * 0.15)  # Slightly larger and more responsive
        
        # Draw Compi body with gradient effect
        compi_x = base_x - size//2
        compi_y = base_y - jump - size//2
        
        # Draw main body with more detail
        body_color = "#7bdff2" if self.carbon < 50 else "#a5f3fc"  # Color changes with carbon level
        self.canvas.create_oval(compi_x, compi_y, compi_x + size, compi_y + size,
                                 fill=body_color, outline="#075985", width=2)
        
        # Draw inner detail on body
        inner_size = size * 0.7
        inner_x = compi_x + (size - inner_size) // 2
        inner_y = compi_y + (size - inner_size) // 2
        self.canvas.create_oval(inner_x, inner_y, inner_x + inner_size, inner_y + inner_size,
                                 fill="#bae6fd", outline="", stipple="gray25")
        
        # Draw eyes with more detail
        eye_size = size // 4
        # Left eye with highlight
        self.canvas.create_oval(compi_x + size//5, compi_y + size//4, 
                                compi_x + size//5 + eye_size, compi_y + size//4 + eye_size,
                                fill="#ffffff", outline="#000000", width=1)
        # Eye highlight
        self.canvas.create_oval(compi_x + size//5 + eye_size//3, compi_y + size//4 + eye_size//4, 
                                compi_x + size//5 + 2*eye_size//3, compi_y + size//4 + eye_size//2,
                                fill="#000000", outline="")
        
        # Right eye with highlight
        self.canvas.create_oval(compi_x + 3*size//5 - eye_size, compi_y + size//4,
                                compi_x + 3*size//5, compi_y + size//4 + eye_size,
                                fill="#ffffff", outline="#000000", width=1)
        # Eye highlight
        self.canvas.create_oval(compi_x + 3*size//5 - 2*eye_size//3, compi_y + size//4 + eye_size//4, 
                                compi_x + 3*size//5 - eye_size//3, compi_y + size//4 + eye_size//2,
                                fill="#000000", outline="")
        
        # Draw mouth that changes with carbon level and mood
        mouth_y = compi_y + size * 0.6
        mouth_width = size * 0.6
        
        if self.carbon > 70:  # Sad when carbon is high
            # Draw sad mouth with tear
            self.canvas.create_arc(compi_x + size//5, mouth_y, compi_x + 4*size//5, mouth_y + size//4,
                                   start=0, extent=180, style="arc", outline="#000000", width=2)
            # Draw a tear drop
            tear_x = compi_x + size//4
            tear_y = compi_y + size//2.5
            self.canvas.create_oval(tear_x - 2, tear_y, tear_x + 2, tear_y + 4, fill="#ffffff", outline="#000000", width=1)
        elif self.carbon < 30:  # Happy when carbon is low
            # Draw big happy smile
            self.canvas.create_arc(compi_x + size//5, mouth_y, compi_x + 4*size//5, mouth_y + size//3,
                                   start=0, extent=-180, style="arc", outline="#000000", width=2)
            # Draw rosy cheeks
            self.canvas.create_oval(compi_x + size//8, compi_y + size//2, 
                                    compi_x + size//8 + size//6, compi_y + size//2 + size//6,
                                    fill="#fda4af", outline="", stipple="gray25")
            self.canvas.create_oval(compi_x + 5*size//8, compi_y + size//2, 
                                    compi_x + 5*size//8 + size//6, compi_y + size//2 + size//6,
                                    fill="#fda4af", outline="", stipple="gray25")
        else:  # Neutral when in middle
            self.canvas.create_line(compi_x + size//4, mouth_y + size//5, 
                                    compi_x + 3*size//4, mouth_y + size//5,
                                    fill="#000000", width=2)
        
        # Draw name tag with more styling
        self.canvas.create_rectangle(base_x - 30, base_y - jump - size - 20, base_x + 30, base_y - jump - size - 5,
                                     fill="#0f172a", outline="#64748b", width=1)
        self.canvas.create_text(base_x, base_y - jump - size - 12, text="Compi", 
                                fill="#cce9ff", font=("Segoe UI", 10, "bold"))

        # Mini-creatures appear as ecosystem thrives - arranged in a more pleasing pattern
        if self.green_spaces > 0:
            for i in range(min(15, 2 + self.green_spaces)):
                # Position in an arc around the bottom of the screen
                angle = (i / max(15, 2 + self.green_spaces)) * 2 * math.pi
                offset_x = (CANVAS_W * 0.4) * math.cos(angle)
                offset_y = 25 * math.sin(time.time()*2 + i)
                bx = base_x + offset_x
                by = GRID_H * TILE + HUD_H - 35 + offset_y
                color = "#fde68a" if i % 2 == 0 else "#bfdbfe"
                
                # Draw mini-creatures with more details
                # Main body
                self.canvas.create_oval(bx - 5, by - 5, bx + 5, by + 5, fill=color, outline="#1e293b", width=1)
                # Eyes
                self.canvas.create_oval(bx - 2, by - 2, bx - 1, by - 1, fill="#000000", outline="")
                self.canvas.create_oval(bx + 1, by - 2, bx + 2, by - 1, fill="#000000", outline="")
                
                # Add small "wings" or details
                wing_color = "#fbbf24" if i % 2 == 0 else "#93c5fd"
                self.canvas.create_oval(bx - 7, by - 3, bx - 3, by + 1, fill=wing_color, outline="#000000", width=1)
                self.canvas.create_oval(bx + 3, by - 3, bx + 7, by + 1, fill=wing_color, outline="#000000", width=1)

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
                
                # Calculate smog color based on carbon level with more atmospheric colors
                # More realistic smog colors: grayish for low pollution, brownish for high pollution
                if local < 0.3:
                    # Light pollution - more gray/white
                    r, g, b = int(180 * local / 0.3), int(180 * local / 0.3), int(190 * local / 0.3)
                elif local < 0.7:
                    # Medium pollution - gray-brown
                    r = int(160 * local / 0.7)
                    g = int(120 * local / 0.7) 
                    b = int(80 * local / 0.7)
                else:
                    # High pollution - brown/orange
                    r = min(200, int(180 + 50 * (local - 0.7) / 0.3))
                    g = min(100, int(100 * (local - 0.5)))
                    b = 50
                
                smog_color = f"#{r:02x}{g:02x}{b:02x}"
                
                # Draw smog with gradient and transparency effects
                # Use multiple overlapping semi-transparent rectangles for a more atmospheric effect
                alpha_steps = 3
                for i in range(alpha_steps):
                    offset_x = (i - 1) * 0.5
                    offset_y = (i - 1) * 0.5
                    # Create a slightly offset and more transparent layer for atmospheric effect
                    self.canvas.create_rectangle(x0 + offset_x, y0 + offset_y, 
                                                x1 + offset_x, y1 + offset_y, 
                                                fill=smog_color, outline="", stipple="gray25" if local < 0.5 else "gray50")
                
                # Add animated atmospheric particles for more realistic fog/smog effect
                if local > 0.3:
                    # Add floating particles that move slowly
                    for _ in range(max(1, int(local * 4))):
                        # Use time-based positioning for animation
                        particle_x = x0 + (time.time() * 5 + x * 7 + y * 3) % TILE
                        particle_y = y0 + (time.time() * 3 + x * 5 + y * 7) % TILE
                        particle_size = 2 if local < 0.5 else 3
                        # Make particles more visible with the smog color
                        self.canvas.create_oval(particle_x, particle_y, 
                                               particle_x + particle_size, 
                                               particle_y + particle_size, 
                                               fill=smog_color, outline="")
                
                # Add a subtle haze effect around the edges of high pollution areas
                if local > 0.6:
                    # Draw a soft glow around polluted areas
                    self.canvas.create_rectangle(x0 - 1, y0 - 1, x1 + 1, y1 + 1, 
                                                fill=smog_color, outline="", stipple="gray12")

    def _draw_scraps(self):
        for (x, y) in getattr(self, 'scraps', []):
            x0, y0 = x * TILE + TILE//3, y * TILE + TILE//3
            # Draw energy scraps as more appealing energy crystals
            center_x = x0 + 4
            center_y = y0 + 4
            
            # Draw energy crystal with multiple layers
            # Outer glow
            self.canvas.create_oval(center_x - 6, center_y - 6, center_x + 6, center_y + 6, 
                                   fill="", outline="#d1d5db", width=1, stipple="gray25")
            # Main crystal
            self.canvas.create_oval(center_x - 5, center_y - 5, center_x + 5, center_y + 5, 
                                   fill="#9ca3af", outline="#4b5563", width=1)
            # Inner core with energy effect
            self.canvas.create_oval(center_x - 3, center_y - 3, center_x + 3, center_y + 3, 
                                   fill="#fbbf24", outline="#f59e0b", width=1)
            # Energy lines shooting out
            for angle in [0, 45, 90, 135]:
                rad = math.radians(angle)
                line_x = center_x + 8 * math.cos(rad)
                line_y = center_y + 8 * math.sin(rad)
                self.canvas.create_line(center_x, center_y, line_x, line_y, 
                                       fill="#fbbf24", width=1, dash=(2, 2))

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

        # Quick Overview 0:00–0:15 - More visual with arrow indicators
        elapsed = time.time() - self.round_start
        if 0 <= elapsed <= 15:
            # Full-width, top-centered overlay
            w, h = CANVAS_W - 40, 120
            x0, y0 = 20, 20
            self.canvas.create_rectangle(x0, y0, x0+w, y0+h, fill="#0f172a", outline="#334155", width=2)
            
            # Title
            self.canvas.create_text(x0+w//2, y0+20, text="Welcome to EcoDistrict!", 
                                    fill="#e2e8f0", font=("Segoe UI", 14, "bold"))
            
            # Brief description
            self.canvas.create_text(x0+w//2, y0+45, text="Improve your city by adding green spaces and clean energy!", 
                                    fill="#cbd5e1", font=("Segoe UI", 10))
            
            # Visual instruction with arrows
            self.canvas.create_text(x0+w//2, y0+75, text="Use ARROW KEYS to move around", 
                                    fill="#94a3b8", font=("Segoe UI", 10, "italic"))
            
            # Draw directional arrows
            center_x, center_y = x0+w//2, y0+100
            arrow_size = 8
            # Up arrow
            self.canvas.create_polygon(center_x, center_y-arrow_size, 
                                      center_x-arrow_size//2, center_y, 
                                      center_x+arrow_size//2, center_y, 
                                      fill="#e2e8f0", outline="#000000")
            # Down arrow
            self.canvas.create_polygon(center_x, center_y+arrow_size, 
                                      center_x-arrow_size//2, center_y, 
                                      center_x+arrow_size//2, center_y, 
                                      fill="#e2e8f0", outline="#000000")
            # Left arrow
            self.canvas.create_polygon(center_x-arrow_size, center_y, 
                                      center_x, center_y-arrow_size//2, 
                                      center_x, center_y+arrow_size//2, 
                                      fill="#e2e8f0", outline="#000000")
            # Right arrow
            self.canvas.create_polygon(center_x+arrow_size, center_y, 
                                      center_x, center_y-arrow_size//2, 
                                      center_x, center_y+arrow_size//2, 
                                      fill="#e2e8f0", outline="#000000")
        
        # Add a subtle visual guide for key actions when help is enabled
        elif self.show_help and not getattr(self, 'awaiting_nfc', False):
            # Draw visual indicators for game controls at the bottom
            self._draw_control_indicators()

    def _draw_control_indicators(self):
        # Draw visual control indicators at the bottom when help is enabled
        # Create visual buttons for each action
        y_pos = CANVAS_H - 80
        start_x = 40
        button_width = 60
        button_height = 60
        spacing = 15
        
        # Movement controls (arrows)
        # Up arrow (W)
        self.canvas.create_polygon(start_x + button_width//2, y_pos - 10,
                                  start_x, y_pos + 15,
                                  start_x + button_width, y_pos + 15,
                                  fill="#4f46e5", outline="#312e81", width=2)
        self.canvas.create_text(start_x + button_width//2, y_pos + 15, 
                                text="W", fill="#e2e8f0", font=("Segoe UI", 14, "bold"))
        
        # Left arrow (A)
        self.canvas.create_polygon(start_x - 10, y_pos + button_height//2,
                                  start_x + 25, y_pos,
                                  start_x + 25, y_pos + button_height,
                                  fill="#4f46e5", outline="#312e81", width=2)
        self.canvas.create_text(start_x + 15, y_pos + button_height//2, 
                                text="A", fill="#e2e8f0", font=("Segoe UI", 14, "bold"))
        
        # Down arrow (S)
        self.canvas.create_polygon(start_x + button_width//2, y_pos + button_height + 10,
                                  start_x, y_pos + 15,
                                  start_x + button_width, y_pos + 15,
                                  fill="#4f46e5", outline="#312e81", width=2)
        self.canvas.create_text(start_x + button_width//2, y_pos + 25, 
                                text="S", fill="#e2e8f0", font=("Segoe UI", 14, "bold"))
        
        # Right arrow (D)
        self.canvas.create_polygon(start_x + button_width + 10, y_pos + button_height//2,
                                  start_x + button_width - 25, y_pos,
                                  start_x + button_width - 25, y_pos + button_height,
                                  fill="#4f46e5", outline="#312e81", width=2)
        self.canvas.create_text(start_x + button_width - 15, y_pos + button_height//2, 
                                text="D", fill="#e2e8f0", font=("Segoe UI", 14, "bold"))
        
        # Action buttons (1, 2, 3, F)
        action_x = start_x + 2.5 * button_width + 2 * spacing
        action_labels = [
            ("1 ☀️", "Solar"),
            ("2 🌿", "Green"),
            ("3 🚲", "Road"),
            ("F ⚡", "Feed")
        ]
        
        for i, (key, label) in enumerate(action_labels):
            btn_x = action_x + i * (button_width + spacing)
            self.canvas.create_rectangle(btn_x, y_pos, btn_x + button_width, y_pos + button_height,
                                        fill="#1e293b", outline="#64748b", width=2)
            self.canvas.create_text(btn_x + button_width//2, y_pos + 15, 
                                    text=key, fill="#e2e8f0", font=("Segoe UI", 12, "bold"))
            self.canvas.create_text(btn_x + button_width//2, y_pos + 40, 
                                    text=label, fill="#94a3b8", font=("Segoe UI", 8))

        # Close help indicator
        close_x = CANVAS_W - 100
        self.canvas.create_oval(close_x, y_pos, close_x + 50, y_pos + 50, 
                                fill="#dc2626", outline="#991b1b", width=2)
        self.canvas.create_text(close_x + 25, y_pos + 25, 
                                text="H", fill="#f8fafc", font=("Segoe UI", 14, "bold"))
        self.canvas.create_text(close_x + 25, y_pos + 40, 
                                text="Hide", fill="#f1f5f9", font=("Segoe UI", 8))

    def _draw_hud2(self):
        y0 = GRID_H * TILE
        # Draw a more stylized HUD background
        self.canvas.create_rectangle(0, y0, CANVAS_W, CANVAS_H, fill="#0f172a", outline="#334155", width=2)

        # Timer - positioned at top right
        if self.round_active:
            remaining = max(0, self.round_seconds - int(time.time() - self.round_start))
        else:
            remaining = 0
        mm, ss = divmod(remaining, 60)
        self.canvas.create_text(CANVAS_W - 80, y0 + 30, text=f"{mm:01d}:{ss:02d}", fill="#e2e8f0", font=("Segoe UI", 20, "bold"))
        self.canvas.create_text(CANVAS_W - 80, y0 + 55, text="Time Left", fill="#94a3b8", font=("Segoe UI", 10))

        # Progress bars stacked vertically for better mobile layout
        carbon_pct = self.carbon / 100.0
        carbon_color = "#16a34a" if carbon_pct < 0.33 else ("#f59e0b" if carbon_pct < 0.66 else "#ef4444")
        
        # Air Quality bar
        self._draw_bar(20, y0+20, CANVAS_W - 160, 20, 1 - carbon_pct, 
                       fg=carbon_color, bg="#111827", frame="#374151", 
                       label=f"Air Quality ({int((1-carbon_pct)*100)})%")
        
        # Happiness bar
        self._draw_bar(20, y0+50, CANVAS_W - 160, 20, self.happiness/100.0, 
                       fg="#22c55e", bg="#111827", frame="#374151", 
                       label=f"Citizens ({int(self.happiness)}%)")

        # Stats - arranged in a grid for better mobile use
        stats_x = 20
        stats_y = y0 + 80
        self.canvas.create_text(stats_x, stats_y, text=f"💰 Money: ${self.player.money}", 
                                fill="#fde68a", font=("Segoe UI", 10), anchor="w")
        self.canvas.create_text(stats_x, stats_y + 20, text=f"☀️ Solar: {self.renewables} ({self.player.solar_panels_available} avl)", 
                                fill="#93c5fd", font=("Segoe UI", 10), anchor="w")
        self.canvas.create_text(stats_x, stats_y + 40, text=f"🌿 Green: {self.green_spaces} ({self.player.green_spaces_available} avl)", 
                                fill="#86efac", font=("Segoe UI", 10), anchor="w")
        self.canvas.create_text(stats_x, stats_y + 60, text=f"⚡ Energy: {self.energy}", 
                                fill="#fde68a", font=("Segoe UI", 10), anchor="w")

        # Challenge progress - moved to bottom
        target = self.challenge_target
        achieved = self.carbon <= target
        ch_color = "#22c55e" if achieved else "#f59e0b"
        self.canvas.create_text(CANVAS_W // 2, y0 + HUD_H - 20, 
                                text=f"Goal: carbon ≤ {target}", 
                                fill=ch_color, font=("Segoe UI", 11, "bold"))

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
        # Draw a cleaner, more mobile-friendly help overlay
        pad = 20
        box_width = CANVAS_W - 40  # Full width minus padding
        box_height = 250
        x0, y0 = pad, pad
        
        # Draw semi-transparent overlay
        self.canvas.create_rectangle(0, 0, CANVAS_W, CANVAS_H, fill="#000000", stipple="gray50")
        
        # Draw help box with refined styling
        self.canvas.create_rectangle(x0, y0, x0+box_width, y0+box_height, 
                                    fill="#0f172a", outline="#64748b", width=2)
        
        # Title with icon
        self.canvas.create_text(x0 + box_width//2, y0 + 25, 
                                text="🎮 How to Play", fill="#e2e8f0", 
                                font=("Segoe UI", 16, "bold"))
        
        # Instructions with better formatting
        instructions = [
            "Reduce carbon by upgrading your district 🌍",
            " ",  # Empty line for spacing
            " Movement: 🡅 🡇 🡄 🡆 / WASD",
            " Place Solar: 1 (on buildings ⬛) - Use available panels",
            " Add Green Space: 2 (on empty/grass 🟢) - Use available items",
            " Upgrade Roads: 3 (bike/pedestrian 🚴)",
            " Feed Building: F (use collected energy ⚡)",
            " Clean Pollution: C (stand on pollution 🗑️)",
            " Buy Solar: 5 ($15)",
            " Buy Green: 6 ($10)", 
            " Place Bin: B (on empty, $5)",
            " Toggle Missions: M",
            " Toggle Help: H"
        ]
        
        for i, line in enumerate(instructions):
            y_pos = y0 + 50 + i * 24
            self.canvas.create_text(x0 + 20, y_pos, text=line, 
                                    fill="#e5e7eb", font=("Segoe UI", 11), anchor="w")
        
        # Highlight the close instruction
        self.canvas.create_rectangle(x0 + box_width - 140, y0 + box_height - 35, 
                                    x0 + box_width - 20, y0 + box_height - 10,
                                    fill="#dc2626", outline="#991b1b", width=1)
        self.canvas.create_text(x0 + box_width - 80, y0 + box_height - 22, 
                                text="Press H to close", 
                                fill="#f8fafc", font=("Segoe UI", 10, "bold"))

    def _check_tutorial_progress(self):
        # Check which actions have been completed and advance tutorial accordingly
        # Only advance if we're currently on that step
        if self.tutorial_step == 1 and self.tutorial_actions_completed['moved']:
            self.tutorial_step = 2
            self._flash("Great! Now collect some energy scraps.")
        elif self.tutorial_step == 2 and self.tutorial_actions_completed['collected_scrap']:
            self.tutorial_step = 3
            self._flash("Excellent! Now place a green space using '2'.")
        elif self.tutorial_step == 3 and self.tutorial_actions_completed['placed_green']:
            self.tutorial_step = 4
            self._flash("Well done! Now install a solar panel using '1'.")
        elif self.tutorial_step == 4 and self.tutorial_actions_completed['placed_solar']:
            self.tutorial_step = 5
            self._flash("Perfect! Now check your missions using 'M'.")
        elif self.tutorial_step == 5 and self.tutorial_actions_completed['viewed_missions']:
            self.tutorial_step = 6  # Tutorial complete
            self.show_tutorial = False  # Hide tutorial and show regular help option
            self._flash("Tutorial complete! Press 'H' for help anytime.")

    def _draw_tutorial(self):
        # Draw tutorial message as an overlay
        if self.tutorial_step < len(self.tutorial_messages):
            message = self.tutorial_messages[self.tutorial_step]
        else:
            return  # No more tutorial steps
            
        # Create a semi-transparent overlay
        self.canvas.create_rectangle(0, 0, CANVAS_W, CANVAS_H, fill="#000000", stipple="gray25")
        
        # Create a tutorial box
        box_width = min(600, CANVAS_W - 40)
        box_height = 150
        x0 = (CANVAS_W - box_width) // 2
        y0 = CANVAS_H - box_height - 20
        
        self.canvas.create_rectangle(x0, y0, x0 + box_width, y0 + box_height,
                                    fill="#0f172a", outline="#64748b", width=2)
        
        # Add tutorial step indicator
        self.canvas.create_text(x0 + box_width // 2, y0 + 20,
                                text=f"Tutorial Step {self.tutorial_step + 1}/{len(self.tutorial_messages)}",
                                fill="#60a5fa", font=("Segoe UI", 12, "bold"))
        
        # Add tutorial message
        self.canvas.create_text(x0 + box_width // 2, y0 + 50,
                                text=message,
                                fill="#e2e8f0", font=("Segoe UI", 11), width=box_width - 20)
        
        # Add action hint based on tutorial step
        hints = [
            "Press any key to start moving",
            "Walk over the gray energy scraps to collect them", 
            "Find an empty space and press '2' to plant greenery",
            "Find a building and press '1' to install solar panels",
            "Press 'M' to view your daily missions",
            "Use '5' to buy solar panels and '6' to buy green spaces"
        ]
        
        if self.tutorial_step < len(hints):
            self.canvas.create_text(x0 + box_width // 2, y0 + 90,
                                    text=hints[self.tutorial_step],
                                    fill="#fbbf24", font=("Segoe UI", 10, "italic"), width=box_width - 20)
        
        # Add continue instruction
        self.canvas.create_text(x0 + box_width // 2, y0 + box_height - 20,
                                text="Continue to next step",
                                fill="#94a3b8", font=("Segoe UI", 9, "italic"))

    def _draw_missions(self):
        # Draw missions panel when missions are visible
        pad = 20
        box_width = min(400, CANVAS_W - 40)  # Responsive width
        # Count active missions to determine height
        active_missions = [m for m in self.daily_missions if not m["completed"]]
        completed_missions = [m for m in self.daily_missions if m["completed"]]
        total_missions = len(self.daily_missions)
        
        box_height = 100 + (len(active_missions) + len(completed_missions)) * 30  # Dynamic height
        
        x0 = CANVAS_W - box_width - pad  # Position on the right side
        y0 = pad
        
        # Draw mission panel with semi-transparent background
        self.canvas.create_rectangle(x0, y0, x0+box_width, y0+box_height, 
                                    fill="#0f172a", outline="#64748b", width=2)
        
        # Title
        self.canvas.create_text(x0 + box_width//2, y0 + 20, 
                                text="🎯 Daily Missions", 
                                fill="#e2e8f0", font=("Segoe UI", 14, "bold"))
        
        # Active missions
        mission_y = y0 + 40
        for i, mission in enumerate(self.daily_missions):
            # Determine color based on completion
            if mission["completed"]:
                color = "#22c55e"  # Green for completed
                status = "✅"
            else:
                color = "#fbbf24"  # Yellow for in-progress
                status = "⏳"
            
            # Draw mission text
            progress_text = f" {mission['current']}/{mission['target']}" if mission['type'] != 'reduce_carbon' else ""
            mission_text = f"{status} {mission['title']}{progress_text}"
            self.canvas.create_text(x0 + 10, mission_y + i*30, 
                                    text=mission_text, 
                                    fill=color, font=("Segoe UI", 10), anchor="w")
        
        # Add close instruction
        self.canvas.create_text(x0 + box_width//2, y0 + box_height - 20, 
                                text="Press M to close", 
                                fill="#94a3b8", font=("Segoe UI", 9, "italic"))

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
        # Semi-transparent overlay
        self.canvas.create_rectangle(0, 0, CANVAS_W, CANVAS_H, fill="#000000", stipple="gray50")
        
        # Centered results box with refined styling
        box_w = min(500, CANVAS_W - 40)  # Responsive width
        box_h = 280
        x0 = (CANVAS_W - box_w)//2
        y0 = (CANVAS_H - box_h)//2 - 20
        
        # Main result panel
        self.canvas.create_rectangle(x0, y0, x0+box_w, y0+box_h, 
                                    fill="#0f172a", outline="#64748b", width=2)
        self.canvas.create_text(x0+box_w//2, y0+30, 
                                text="Round Complete!", 
                                fill="#e2e8f0", font=("Segoe UI", 18, "bold"))
        
        # Performance summary with icons
        reduction = self.start_carbon - int(self.carbon)
        improvement_icon = "🎉" if reduction > 0 else "😅"
        
        # Stats with better layout
        stats_left_x = x0 + 30
        stats_right_x = x0 + box_w // 2 + 20
        stats_y_start = y0 + 60
        line_height = 28
        
        # Left column - Before/after
        self.canvas.create_text(stats_left_x, stats_y_start, 
                                text="📊 Performance", 
                                fill="#94a3b8", font=("Segoe UI", 12, "bold"), anchor="w")
        
        # Carbon change
        carbon_change = f"Carbon: {self.start_carbon} → {int(self.carbon)}"
        carbon_color = "#22c55e" if reduction > 0 else "#ef4444"
        self.canvas.create_text(stats_left_x, stats_y_start + line_height, 
                                text=carbon_change, fill=carbon_color, 
                                font=("Segoe UI", 11), anchor="w")
        
        # Happiness change
        self.canvas.create_text(stats_left_x, stats_y_start + 2*line_height, 
                                text=f"Happiness: 38 → {int(self.happiness)}", 
                                fill="#86efac", font=("Segoe UI", 11), anchor="w")
        
        # Right column - Improvements made
        self.canvas.create_text(stats_right_x, stats_y_start, 
                                text="🏗️ Improvements", 
                                fill="#94a3b8", font=("Segoe UI", 12, "bold"), anchor="w")
        
        self.canvas.create_text(stats_right_x, stats_y_start + line_height, 
                                text=f"☀️ Solar: {self.renewables}", 
                                fill="#93c5fd", font=("Segoe UI", 11), anchor="w")
        self.canvas.create_text(stats_right_x, stats_y_start + 2*line_height, 
                                text=f"🌿 Green: {self.green_spaces}", 
                                fill="#86efac", font=("Segoe UI", 11), anchor="w")
        
        # Narrative feedback with more personality
        if reduction > 0:
            msg = f"You reduced carbon by {reduction}%! {improvement_icon} Great job!"
            msg_color = "#a7f3d0"
        else:
            msg = f"Carbon only changed by {reduction}%. Keep trying! 💪"
            msg_color = "#fde68a"
            
        self.canvas.create_text(x0 + box_w//2, y0 + box_h - 100, 
                                text=msg, fill=msg_color, font=("Segoe UI", 12, "bold"))
        
        # Goal achievement with visual indicator
        achieved = int(self.carbon) <= self.challenge_target
        goal_text = "✅ Goal Achieved!" if achieved else "🎯 Keep Improving"
        goal_color = "#22c55e" if achieved else "#f59e0b"
        
        self.canvas.create_text(x0 + box_w//2, y0 + box_h - 70, 
                                text=goal_text, fill=goal_color, 
                                font=("Segoe UI", 13, "bold"))
        
        # World Health summary
        world_health = int(self._world_health_score())
        health_text = f"🌍 World Health: {world_health}%"
        health_color = "#60a5fa" if world_health > 70 else "#fbbf24" if world_health > 40 else "#f87171"
        self.canvas.create_text(x0 + box_w//2, y0 + box_h - 40, 
                                text=health_text, fill=health_color, 
                                font=("Segoe UI", 12, "bold"))
        
        # Play again instruction
        self.canvas.create_text(x0 + box_w//2, y0 + box_h - 15, 
                                text="Press SPACE or ENTER to play again", 
                                fill="#94a3b8", font=("Segoe UI", 10, "italic"))

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
