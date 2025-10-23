# EcoDistrict Game

A vertical mobile-style environmental simulation game built with Python and Tkinter.

## Running with Docker

### Prerequisites
- Docker Desktop installed
- Docker Compose installed

### Running the Game

#### On Windows:
Docker Desktop on Windows has limitations with GUI applications. You have two options:

**Option 1: Use WSL2 with X-server**
1. Install an X-server like VcXsrv or Xming on Windows
2. Start the X-server with "Allow connections from network clients" enabled
3. Set DISPLAY environment variable: `export DISPLAY=host.docker.internal:0.0`
4. Run: `docker-compose up --build`

**Option 2: Run directly on Windows**
```bash
# Simply run the Python file directly since tkinter is included with Python
cd game3
python main.py
```

## How to Play

1. Use ARROW KEYS or WASD to move around
2. Collect energy scraps (gray circles) by walking over them
3. Place green spaces by pressing '2' on empty areas
4. Install solar panels by pressing '1' on buildings
5. Upgrade roads by pressing '3' on roads
6. Feed buildings with energy by pressing 'F' on buildings
7. Check missions by pressing 'M'
8. Toggle help by pressing 'H'

## Game Features

- Vertical mobile-friendly layout
- Pollution cleanup mechanics
- Daily missions system
- Economic system with money and purchasable items
- Progressive tutorial system
- Atmospheric fog effects based on pollution levels

Enjoy making your virtual city more eco-friendly!