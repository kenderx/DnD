"""
dungeon.py  —  Procedural BSP dungeon map generator for 20 floors.

Tile types
----------
  WALL    = 0
  FLOOR   = 1
  STAIRS  = 2  (stairs down)
  TORCH   = 3  (wall torch, emits light)
  CHEST   = 4  (treasure chest, closed)
  CHEST_OPEN = 5

Each floor is a 2-D list of integers (rows × cols).
"""
from __future__ import annotations
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from rules import (
    MonsterTemplate, generate_loot, gold_for_floor, monsters_for_floor, Item,
    TRAP_ITEMS,
)

# ---------------------------------------------------------------------------
# Tile constants
# ---------------------------------------------------------------------------
WALL      = 0
FLOOR     = 1
STAIRS    = 2
TORCH     = 3
CHEST     = 4
CHEST_OPEN= 5

MAP_ROWS  = 50
MAP_COLS  = 80

# ---------------------------------------------------------------------------
# Supporting data structures
# ---------------------------------------------------------------------------

@dataclass
class Rect:
    """An axis-aligned rectangle in tile coordinates."""
    r: int; c: int; h: int; w: int

    @property
    def center(self) -> Tuple[int, int]:
        return (self.r + self.h // 2, self.c + self.w // 2)

    def inner_tiles(self) -> List[Tuple[int, int]]:
        return [(self.r + dr, self.c + dc)
                for dr in range(1, self.h - 1)
                for dc in range(1, self.w - 1)]

    def all_tiles(self) -> List[Tuple[int, int]]:
        return [(self.r + dr, self.c + dc)
                for dr in range(self.h)
                for dc in range(self.w)]


@dataclass
class Monster:
    template: MonsterTemplate
    row: int
    col: int
    hp: int
    max_hp: int
    statuses: List[str] = field(default_factory=list)   # ["Poisoned", "Restrained"]
    restrained_turns: int = 0
    alerted: bool = False
    path: List[Tuple[int, int]] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.template.name

    @property
    def pos(self) -> Tuple[int, int]:
        return (self.row, self.col)


@dataclass
class Trap:
    kind: str          # "Caltrops" | "Bear Trap" | "Poison Gas Trap"
    row: int
    col: int
    owner: str = "player"   # who set it
    triggered: bool = False


@dataclass
class Chest:
    row: int
    col: int
    floor: int
    opened: bool = False
    # loot is generated lazily when the player opens it
    loot: Optional[Item]   = None
    gold: int              = 0

    def open(self):
        if not self.opened:
            self.opened = True
            self.gold  = gold_for_floor(self.floor)
            self.loot  = generate_loot(self.floor) if random.random() < 0.75 else None


@dataclass
class DungeonFloor:
    floor_num: int           # 1-based
    tiles: List[List[int]]   # [row][col]
    rooms: List[Rect]
    player_start: Tuple[int, int]
    stairs_pos: Tuple[int, int]
    monsters: List[Monster]
    traps: List[Trap]        # pre-placed dungeon traps (player traps added at runtime)
    chests: List[Chest]
    wall_torches: List[Tuple[int, int]]   # positions of ambient light sources

    def is_wall(self, r: int, c: int) -> bool:
        if r < 0 or r >= MAP_ROWS or c < 0 or c >= MAP_COLS:
            return True
        return self.tiles[r][c] == WALL

    def is_passable(self, r: int, c: int) -> bool:
        if r < 0 or r >= MAP_ROWS or c < 0 or c >= MAP_COLS:
            return False
        return self.tiles[r][c] != WALL

    def monster_at(self, r: int, c: int) -> Optional[Monster]:
        for m in self.monsters:
            if m.row == r and m.col == c:
                return m
        return None

    def chest_at(self, r: int, c: int) -> Optional[Chest]:
        for ch in self.chests:
            if ch.row == r and ch.col == c:
                return ch
        return None

    def trap_at(self, r: int, c: int) -> Optional[Trap]:
        for t in self.traps:
            if t.row == r and t.col == c and not t.triggered:
                return t
        return None

# ---------------------------------------------------------------------------
# BSP map generator
# ---------------------------------------------------------------------------

MIN_ROOM_H, MIN_ROOM_W = 5, 5
MAX_ROOM_H, MAX_ROOM_W = 12, 16

class _BSPNode:
    def __init__(self, rect: Rect):
        self.rect = rect
        self.left:  Optional[_BSPNode] = None
        self.right: Optional[_BSPNode] = None
        self.room:  Optional[Rect]     = None

    def split(self, min_size: int = 10) -> bool:
        if self.left or self.right:
            return False
        # Decide split direction
        h_split = self.rect.h > self.rect.w
        if abs(self.rect.h - self.rect.w) < min_size:
            h_split = random.random() < 0.5
        if h_split:
            if self.rect.h < min_size * 2:
                return False
            split_at = random.randint(min_size, self.rect.h - min_size)
            self.left  = _BSPNode(Rect(self.rect.r, self.rect.c, split_at, self.rect.w))
            self.right = _BSPNode(Rect(self.rect.r + split_at, self.rect.c,
                                       self.rect.h - split_at, self.rect.w))
        else:
            if self.rect.w < min_size * 2:
                return False
            split_at = random.randint(min_size, self.rect.w - min_size)
            self.left  = _BSPNode(Rect(self.rect.r, self.rect.c, self.rect.h, split_at))
            self.right = _BSPNode(Rect(self.rect.r, self.rect.c + split_at,
                                       self.rect.h, self.rect.w - split_at))
        return True

    def create_rooms(self, tiles: List[List[int]]):
        if self.left or self.right:
            if self.left:  self.left.create_rooms(tiles)
            if self.right: self.right.create_rooms(tiles)
            # Connect the two children's rooms
            left_center  = self._get_room(self.left).center
            right_center = self._get_room(self.right).center
            _carve_corridor(tiles, left_center, right_center)
        else:
            r_h = random.randint(MIN_ROOM_H, min(MAX_ROOM_H, self.rect.h - 2))
            r_w = random.randint(MIN_ROOM_W, min(MAX_ROOM_W, self.rect.w - 2))
            r_r = random.randint(self.rect.r + 1, self.rect.r + self.rect.h - r_h - 1)
            r_c = random.randint(self.rect.c + 1, self.rect.c + self.rect.w - r_w - 1)
            self.room = Rect(r_r, r_c, r_h, r_w)
            for (rr, rc) in self.room.inner_tiles():
                tiles[rr][rc] = FLOOR

    def _get_room(self, node: "_BSPNode") -> Rect:
        if node.room:
            return node.room
        rooms = []
        def _collect(n):
            if n.room: rooms.append(n.room)
            if n.left:  _collect(n.left)
            if n.right: _collect(n.right)
        _collect(node)
        return random.choice(rooms) if rooms else node.rect

    def collect_rooms(self) -> List[Rect]:
        result = []
        if self.room:
            result.append(self.room)
        if self.left:  result.extend(self.left.collect_rooms())
        if self.right: result.extend(self.right.collect_rooms())
        return result


def _carve_corridor(tiles, a: Tuple[int, int], b: Tuple[int, int]):
    """Carve an L-shaped corridor between two points."""
    r1, c1 = a; r2, c2 = b
    # horizontal then vertical
    if random.random() < 0.5:
        for c in range(min(c1, c2), max(c1, c2) + 1):
            tiles[r1][c] = FLOOR
        for r in range(min(r1, r2), max(r1, r2) + 1):
            tiles[r][c2] = FLOOR
    else:
        for r in range(min(r1, r2), max(r1, r2) + 1):
            tiles[r][c1] = FLOOR
        for c in range(min(c1, c2), max(c1, c2) + 1):
            tiles[r2][c] = FLOOR


# ---------------------------------------------------------------------------
# Floor generator
# ---------------------------------------------------------------------------

def _count_monsters(floor: int) -> int:
    """Number of monsters to place on a given floor."""
    return floor + random.randint(2, 5)


def _count_chests(floor: int) -> int:
    return random.randint(1, max(1, floor // 3 + 1))


def generate_floor(floor_num: int, seed: Optional[int] = None) -> DungeonFloor:
    """
    Generate a complete dungeon floor using BSP partitioning.

    Parameters
    ----------
    floor_num : 1-based floor number (1 = easiest, 20 = hardest)
    seed      : optional RNG seed for reproducibility
    """
    if seed is not None:
        random.seed(seed)

    # --- 1. Build tile grid ---------------------------------------------------
    tiles: List[List[int]] = [[WALL] * MAP_COLS for _ in range(MAP_ROWS)]

    root = _BSPNode(Rect(0, 0, MAP_ROWS, MAP_COLS))
    _recursive_split(root, depth=5)
    root.create_rooms(tiles)
    rooms = root.collect_rooms()

    # --- 2. Player start (first room) ----------------------------------------
    player_start = rooms[0].center

    # --- 3. Stairs (last room, not same as player start) ---------------------
    stair_room = rooms[-1] if len(rooms) > 1 else rooms[0]
    stairs_pos = stair_room.center
    tiles[stairs_pos[0]][stairs_pos[1]] = STAIRS

    # --- 4. Wall torches (one per room roughly) ------------------------------
    wall_torches: List[Tuple[int, int]] = []
    for room in rooms:
        if random.random() < 0.6:
            # Place on the inner-wall edge of the room
            tr = room.r + 1
            tc = room.c + random.randint(1, max(1, room.w - 2))
            tiles[tr][tc] = TORCH
            wall_torches.append((tr, tc))

    # --- 5. Monsters ----------------------------------------------------------
    templates = monsters_for_floor(floor_num)
    monsters: List[Monster] = []
    used_positions = {player_start, stairs_pos}
    num_monsters = _count_monsters(floor_num)

    for _ in range(num_monsters):
        if not templates:
            break
        tmpl = random.choice(templates)
        pos = _random_floor_pos(tiles, rooms, used_positions)
        if pos is None:
            break
        used_positions.add(pos)
        # Scale HP slightly with floor depth
        hp_bonus = (floor_num - tmpl.min_floor) * 2
        hp = tmpl.hp + hp_bonus
        monsters.append(Monster(template=tmpl, row=pos[0], col=pos[1],
                                hp=hp, max_hp=hp))

    # --- 6. Chests ------------------------------------------------------------
    chests: List[Chest] = []
    num_chests = _count_chests(floor_num)
    for _ in range(num_chests):
        pos = _random_floor_pos(tiles, rooms, used_positions)
        if pos is None:
            break
        used_positions.add(pos)
        tiles[pos[0]][pos[1]] = CHEST
        chests.append(Chest(row=pos[0], col=pos[1], floor=floor_num))

    # --- 7. Pre-placed dungeon traps (not player traps) ----------------------
    pre_traps: List[Trap] = []
    num_traps = floor_num // 3
    trap_kinds = ["Caltrops", "Bear Trap", "Poison Gas Trap"]
    for _ in range(num_traps):
        pos = _random_floor_pos(tiles, rooms, used_positions)
        if pos is None:
            break
        used_positions.add(pos)
        kind = random.choice(trap_kinds)
        pre_traps.append(Trap(kind=kind, row=pos[0], col=pos[1], owner="dungeon"))

    return DungeonFloor(
        floor_num    = floor_num,
        tiles        = tiles,
        rooms        = rooms,
        player_start = player_start,
        stairs_pos   = stairs_pos,
        monsters     = monsters,
        traps        = pre_traps,
        chests       = chests,
        wall_torches = wall_torches,
    )


def _recursive_split(node: _BSPNode, depth: int):
    if depth == 0:
        return
    if node.split():
        _recursive_split(node.left, depth - 1)
        _recursive_split(node.right, depth - 1)


def _random_floor_pos(
    tiles: List[List[int]],
    rooms: List[Rect],
    used: set,
    attempts: int = 50,
) -> Optional[Tuple[int, int]]:
    """Pick a random FLOOR tile not in *used*."""
    for _ in range(attempts):
        room = random.choice(rooms)
        inner = room.inner_tiles()
        if not inner:
            continue
        pos = random.choice(inner)
        if tiles[pos[0]][pos[1]] == FLOOR and pos not in used:
            return pos
    return None
