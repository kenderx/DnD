# Implementation Plan: Standalone D&D 5.2.1 Rogue Roguelike

We are building a standalone Windows executable (`.exe`) game in **Python** using **Pygame**, compiled via **PyInstaller** (`pyinstaller --onefile --noconsole`). The game is a tactical, grid-based, top-down solo Roguelike centered on a D&D Rogue exploring dark dungeons, setting traps, applying poisons, and executing Sneak Attacks.

## User Review Required

> [!IMPORTANT]
> **Windows EXE Toolchain:**
> - Based on system environment checks, **Python 3.11.9** and **Node.js** are installed. Compiler toolchains like `g++`, `dotnet`, and `MSVC` are missing.
> - Therefore, we will build the game in **Python** using the **Pygame** library, and compile it to a standalone `.exe` using **PyInstaller** (`pyinstaller --onefile --noconsole`).
> - This delivers a zero-dependency, double-clickable Windows executable.

> [!WARNING]
> **Old Web Project Backup:**
> - To make room for the new Python structure in the workspace `c:\Users\Makhew3\antigravity\DnD`, the previous HTML/CSS/JS files will be moved into a subdirectory named `web_backup/`.

---

## Game Design & SRD 5.2.1 Rules Integration

### 1. 20-Floor Dungeon & Level Progression
- The dungeon has **20 floors**. The stairs down to the next floor must be found by exploring the map.
- The game is balanced so that the Rogue's level corresponds to the current dungeon floor (e.g. Floor 1 is balanced for Level 1, Floor 5 for Level 5, up to Floor 20 for Level 20).
- Level progression is tied directly to exploring, killing monsters, and looting treasure gold (which awards XP). Clearing most of Floor N will award enough XP to reach Level N+1, preparing the Rogue for Floor N+1.
- Rogue stats scale up to Level 20:
  - **HP Increase**: `5 + CON mod` (+1 CON = +6 HP) per level. Starts at 9 HP.
  - **Sneak Attack**: Every attack from the Rogue is a Sneak Attack. Damage starts at `2d6` and increases by `1d6` every odd level (standard D&D rogue sneak scaling, e.g., level 3: 2d6, level 5: 3d6, level 20: 10d6).

### 2. Equipment Slots & Inventory
- The player can equip:
  - **1 Weapon** (either Dagger or Shortbow; switching is a Free Action).
  - **1 Set of Armor**.
  - **Up to 3 Equipable Items** (skills or stat bonuses).
- Unequipped items, consumable traps, poison vials, and Thieves' Tools are kept in the general Inventory.

### 3. Treasure Rooms & Level-Appropriate Loot
Chests hidden in rooms contain loot determined dynamically based on the current floor's level:
- **Gold**: Directly adds to gold count and awards equivalent XP.
- **Weapons**:
  - Floors 1-4: Dagger (+0, 1d4), Shortbow (+0, 1d6)
  - Floors 5-9: +1 Weapons (Dagger/Shortbow +1 to hit/damage)
  - Floors 10-14: +2 Weapons, Flame Tongue Dagger (+1d6 fire damage)
  - Floors 15-20: +3 Weapons, Dagger of Venom (+1d6 poison, applies poisoned condition)
- **Armor**:
  - Floors 1-4: Leather Armor (AC 11), Studded Leather (AC 12)
  - Floors 5-9: Studded Leather +1 (AC 13)
  - Floors 10-14: Studded Leather +2 (AC 14)
  - Floors 15-20: Studded Leather +3 (AC 15)
- **Special Items**:
  - **Small Mirror**: Reusable utility item in inventory. Using it adjacent to a corner or closed door reveals the tiles on the other side (calculates a temporary FOV sweep from the adjacent tile), allowing the player to spot patrols/traps without stepping out.
  - **Potions of Healing (SRD defined)**: Consumable healing items.
    - *Potion of Healing* (Common, Floors 1-5): Heals `2d4 + 2` HP.
    - *Potion of Greater Healing* (Uncommon, Floors 6-10): Heals `4d4 + 4` HP.
    - *Potion of Superior Healing* (Rare, Floors 11-15): Heals `8d4 + 8` HP.
    - *Potion of Supreme Healing* (Very Rare, Floors 16-20): Heals `10d4 + 20` HP.
  - **Gem of Trueseeing**: Equipable slot item. Grants the player **Darkvision** (allows the player to see up to 6 tiles in pitch black without using a torch, letting them sneak in shadows) and adds **+5 to Passive Perception** (making it easy to spot hidden traps and ambushes).
  - *Ring of Protection*: +1 AC.
  - *Boots of Elvenkind*: +3 to Stealth.
  - *Gloves of Thievery*: +3 to Thieves' Tools / lockpicking and trap disarming.
  - *Cloak of Protection*: +1 AC and +1 to all saving throws.
  - *Amulet of Health*: Sets CON to 14 (+2 mod) or increases Max HP by +10.

### 4. Traps & Poison Systems
The Rogue can set three types of mechanical and chemical traps on walkable grid tiles:
- **Caltrops (Consumable)**: Deals 1d4 piercing damage, cuts monster speed in half, and alerts nearby patrols with noise.
- **Bear Trap (Consumable)**: Deals 2d6 piercing damage and inflicts the *Restrained* condition (speed = 0) for 2 turns.
- **Poison Gas Trap (Consumable)**: Triggers a 3x3 toxic cloud. Deals 1d8 poison damage and inflicts the *Poisoned* condition.
- **Blade Poison (Consumable)**: Consumes a poison vial to coat the rogue's dagger or shortbow. The next 3 hits deal +1d6 extra poison damage and apply the *Poisoned* condition (disadvantage on attack rolls, DC 11 Constitution save to resist).

### 5. Light and Vision (Dynamic Lighting FOV)
- The dungeon is pitch black.
- The player carries a **Torch** that casts dynamic light using **Symmetric Shadowcasting** (base light radius: 5 tiles, modifiable by items).
- Walls block light, creating realistic shadows.
- Static wall torches are scattered across rooms to create glowing safe pockets.
- **Darkvision**: Monsters have Darkvision (6 tiles), meaning they can see the player in the dark. The player must rely on **Stealth** and wall placement to avoid detection.

### 6. Monsters & Combat Loop
- High hit points relative to the Rogue:
  - **Goblin**: 12 HP, AC 12, deals 1d6+2 damage.
  - **Skeleton**: 18 HP, AC 13, deals 1d6+2 damage.
  - **Zombie**: 30 HP, AC 8, deals 1d6+1 damage.
  - **Orc**: 25 HP, AC 13, deals 1d12+3 damage.
  - **Owlbear (Floor 20 Boss)**: 120 HP, AC 13, deals 2d8+5 damage.
- Turn-based movement: Time moves only when the Rogue moves or performs an action (classic Roguelike).
- If a monster spots the player (or hears a trap trigger), it pathfinds toward the player using A*.

---

## Proposed Architecture

We will create the following files inside `c:\Users\Makhew3\antigravity\DnD/`:

```
c:\Users\Makhew3\antigravity\DnD/
├── dungeon_rogue.py        # Main Entry: Pygame loop, drawing, input, and GUI panels
├── rules.py                # SRD calculations: dice, stealth checks, levels, damage, poison state
├── fov.py                  # FOV Module: Symmetric Shadowcasting (Albert Ford) lighting calculations
├── pathfinding.py          # Path Module: BFS (movement/trap ranges) and A* (monster AI chase)
├── dungeon.py              # Map Module: Procedural BSP dungeon map generator (20 levels)
└── build.bat               # Build utility script compiling to EXE via PyInstaller
```

---

## Proposed Changes

### [Backup Old Files]
- Move existing `index.html`, `style.css`, and `js/` folder into `web_backup/` to clear the workspace.

### [Game Implementation]

#### [NEW] fov.py
- Implements `round_ties_up`, `round_ties_down`, `Quadrant`, and `Row` classes.
- Core recursive `scan` function that updates a grid representation with light levels (1.0 = lit, 0.5 = dim, 0.0 = dark).

#### [NEW] pathfinding.py
- BFS flood fill for checking trap ranges and path indicators.
- A* algorithm using Manhattan distance to return path list for monster AI.

#### [NEW] dungeon.py
- Procedural BSP (Binary Space Partitioning) map generator: splits map into grid cells, places rectangular rooms, and connects them with L-shaped corridors.
- Handles generation of 20 floors, placing stairs down, wall torches, traps, chests, and spawning level-appropriate monsters.

#### [NEW] rules.py
- Roll functions (`1d20+5`, `2d6`) with advantage/disadvantage.
- Rogue character sheet stats (HP, Level, XP, Gold, Poison Vials, Traps, Equipment Slots, Inventory).
- Item templates and loot generator (random items scaled by floor level).
- Stealth check resolution and Sneak Attack damage multipliers.

#### [NEW] dungeon_rogue.py
- Sets up Pygame window (1024x768), grid cell rendering (40x40 pixel cells), and programmatic drawing for assets (using vectors/circles/lines so no external images are required).
- Event handler (Arrows/WASD for movement, numbers for traps/poison, Space to pass turn).
- HUD side panels showing player stats, item slots, and a scrolling message log.
- Turn manager: player takes an action, then all active monsters execute their AI steps.

#### [NEW] build.bat
- Installs `pygame-ce` and `pyinstaller` via pip.
- Runs `pyinstaller --onefile --noconsole --name=dungeon_rogue dungeon_rogue.py`.
- Copies the final binary from `dist/dungeon_rogue.exe` to the project root for easy launch.

---

## Verification Plan

### Automated Tests
- Run `python dungeon_rogue.py` locally and verify the window opens.
- The console will output rule engine diagnostic tests on launch (verifying math, dice rolls, and fov calculations).

### Manual Verification
- Verify that moving blocks light behind walls correctly.
- Place caltrops and bear traps, lure monsters into them, and verify that damage is applied and statuses are reflected.
- Apply blade poison, attack an Orc, and ensure Sneak Attack + Poison Damage logs appear in the message area.
- Verify compiling to `.exe` runs successfully and yields a launchable executable.
