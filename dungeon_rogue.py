"""
dungeon_rogue.py  —  Main Pygame entry point for the D&D Rogue Roguelike.

Controls
--------
  Arrow keys / WASD   Move / attack (bumping into a monster attacks it)
  G                   Pick up item / open chest on current tile
  E                   Open equipment/inventory screen
  1                   Place Caltrops on current tile
  2                   Place Bear Trap on current tile
  3                   Place Poison Gas Trap on current tile
  4                   Apply Blade Poison to weapon
  H                   Use a Potion of Healing (lowest tier first)
  M                   Use Small Mirror (peek around next corner)
  .  / Space          Pass turn (rest for 1 turn)
  >                   Descend stairs (if standing on them)
  Escape              Quit game
"""
from __future__ import annotations

import sys
import math
import random
from typing import List, Optional, Set, Tuple

import pygame

from rules import (
    Rogue, Item, use_potion,
    SLOT_WEAPON, SLOT_ARMOR, SLOT_ITEM, SLOT_NONE,
    TRAP_ITEMS, roll, d20, modifier,
    StatusEffect,
)
from dungeon import (
    DungeonFloor, generate_floor, Trap, Chest, Monster,
    WALL, FLOOR, STAIRS, TORCH, CHEST, CHEST_OPEN,
    MAP_ROWS, MAP_COLS,
)
from fov import compute_fov, compute_mirror_fov
from pathfinding import astar

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCREEN_W, SCREEN_H = 1280, 768
CELL    = 18          # pixels per grid cell
VIEW_COLS = 55        # cells wide in the map viewport
VIEW_ROWS = 40        # cells tall in the map viewport
MAP_X  = 0            # map panel left x
MAP_Y  = 0            # map panel top y
HUD_X  = MAP_X + VIEW_COLS * CELL   # HUD panel starts here
HUD_W  = SCREEN_W - HUD_X
LOG_LINES = 14        # number of message log lines visible
TORCH_RADIUS = 5      # default player torch radius
FPS    = 60

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
C_BG         = ( 10,  10,  15)
C_WALL       = ( 40,  40,  50)
C_WALL_LIT   = ( 70,  70,  85)
C_FLOOR      = ( 30,  30,  38)
C_FLOOR_LIT  = ( 55,  52,  65)
C_FLOOR_SEEN = ( 35,  33,  42)
C_STAIRS     = ( 80, 200, 120)
C_TORCH_LIT  = (200, 160,  60)
C_CHEST      = (200, 170,  50)
C_CHEST_OPEN = (120, 100,  40)
C_PLAYER     = ( 80, 180, 255)
C_PLAYER_SH  = ( 30,  80, 150)
C_MONSTER    = (220,  60,  60)
C_TRAP       = (200, 100, 200)
C_MIRROR_GLOW= (100, 220, 255)
C_HUD_BG     = ( 18,  18,  28)
C_HUD_BORDER = ( 60,  60, 100)
C_TEXT       = (220, 220, 230)
C_TEXT_DIM   = (110, 110, 130)
C_TEXT_GOLD  = (255, 215,   0)
C_TEXT_RED   = (255,  80,  80)
C_TEXT_GREEN = ( 80, 220, 100)
C_TEXT_BLUE  = (100, 180, 255)
C_TEXT_PURPLE= (180, 100, 255)
C_HP_BAR_FG  = ( 80, 200,  80)
C_HP_BAR_BG  = ( 60,  20,  20)
C_XP_BAR_FG  = ( 80, 120, 220)
C_XP_BAR_BG  = ( 20,  20,  60)

# ---------------------------------------------------------------------------
# GameState
# ---------------------------------------------------------------------------

class GameState:
    def __init__(self):
        self.rogue = Rogue()
        self.rogue.hp = self.rogue.max_hp
        self.floor_num = 1
        self.dungeon: DungeonFloor = generate_floor(self.floor_num)
        pr, pc = self.dungeon.player_start
        self.player_row: int = pr
        self.player_col: int = pc
        self.visible:  Set[Tuple[int,int]] = set()
        self.explored: Set[Tuple[int,int]] = set()
        self.mirror_visible: Set[Tuple[int,int]] = set()
        self.messages: List[Tuple[str, Tuple[int,int,int]]] = []
        self.game_over = False
        self.won       = False
        self.show_inventory = False
        self.inv_cursor = 0
        self.turn = 0
        self._update_fov()
        self.log("Welcome to the Dungeon, Rogue. Find the stairs down!", C_TEXT_GREEN)

    # ---- Logging ------------------------------------------------------------

    def log(self, msg: str, color: Tuple[int,int,int] = C_TEXT):
        self.messages.append((msg, color))
        if len(self.messages) > 200:
            self.messages.pop(0)

    # ---- FOV ----------------------------------------------------------------

    def _update_fov(self):
        self.visible.clear()
        r = self.rogue
        light_r = TORCH_RADIUS
        # Darkvision supplement
        dv = r.darkvision_range

        def is_blocking(row, col):
            return self.dungeon.is_wall(row, col)

        def mark_visible(row, col):
            self.visible.add((row, col))
            self.explored.add((row, col))

        compute_fov(
            (self.player_row, self.player_col),
            is_blocking, mark_visible, light_r,
        )
        # Add darkvision radius (black-and-white, no colour)
        if dv > 0:
            compute_fov(
                (self.player_row, self.player_col),
                is_blocking, mark_visible, dv,
            )
        # Add wall-torch light halos
        for (tr, tc) in self.dungeon.wall_torches:
            if abs(tr - self.player_row) + abs(tc - self.player_col) <= TORCH_RADIUS + 4:
                compute_fov((tr, tc), is_blocking, mark_visible, 3)

    # ---- Mirror peek --------------------------------------------------------

    def use_mirror(self):
        """Reveal tiles around the next tile in the direction the player faces."""
        self.mirror_visible.clear()
        # Peek in all 4 directions one tile away
        revealed = 0
        for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
            peek_r = self.player_row + dr
            peek_c = self.player_col + dc
            if self.dungeon.is_wall(peek_r, peek_c):
                # Look from the other side
                peek_r2 = peek_r + dr
                peek_c2 = peek_c + dc
                compute_mirror_fov(
                    (peek_r2, peek_c2),
                    lambda r,c: self.dungeon.is_wall(r,c),
                    lambda r,c: (self.mirror_visible.add((r,c)), self.explored.add((r,c))),
                    3,
                )
                revealed += 1
        if revealed:
            self.log("You peek around the corner with the mirror...", C_TEXT_BLUE)
        else:
            self.log("Nothing to peek at here.", C_TEXT_DIM)

    # ---- Movement & action --------------------------------------------------

    def try_move(self, dr: int, dc: int) -> bool:
        """Attempt to move the player. Returns True if a turn was consumed."""
        nr, nc = self.player_row + dr, self.player_col + dc
        if self.dungeon.is_wall(nr, nc):
            return False

        # Check if monster is there → attack
        monster = self.dungeon.monster_at(nr, nc)
        if monster:
            self._attack_monster(monster)
            return True

        # Move
        self.player_row, self.player_col = nr, nc
        self._update_fov()
        self.mirror_visible.clear()

        # Check for trap
        trap = self.dungeon.trap_at(nr, nc)
        if trap:
            self._trigger_trap(trap, self.rogue, is_player=True)

        return True

    def _attack_monster(self, monster: Monster):
        r = self.rogue
        # Advantage if rogue is hidden (simplified: if not near any alerted monster)
        adv = not any(m.alerted for m in self.dungeon.monsters if m != monster
                       and abs(m.row - self.player_row) + abs(m.col - self.player_col) < 6)
        hit_roll = r.attack_roll(advantage=adv)
        if hit_roll >= monster.template.ac:
            wd, sd, pd = r.total_attack_damage()
            total = wd + sd + pd
            monster.hp -= total
            msg = f"You hit the {monster.name} for {wd}+{sd}(SA)"
            if pd:
                msg += f"+{pd}(poison)"
            msg += f" = {total} dmg!"
            self.log(msg, C_TEXT_GREEN)
            # Apply poison if dagger of venom
            if r.weapon and "Venom" in r.weapon.name and monster.hp > 0:
                monster.statuses.append("Poisoned")
            if monster.hp <= 0:
                xp = monster.template.xp
                self.log(f"The {monster.name} is slain! +{xp} XP", C_TEXT_GOLD)
                leveled = r.gain_xp(xp)
                if leveled:
                    self.log(f"*** LEVEL UP! You are now level {r.level}! ***", C_TEXT_PURPLE)
                self.dungeon.monsters.remove(monster)
        else:
            self.log(f"You miss the {monster.name}. (rolled {hit_roll} vs AC {monster.template.ac})", C_TEXT_DIM)
        monster.alerted = True

    def _trigger_trap(self, trap: Trap, target, is_player: bool = False):
        trap.triggered = True
        rogue = self.rogue
        kind = trap.kind
        if kind == "Caltrops":
            dmg = roll(4)
            if is_player:
                rogue.hp -= dmg
                self.log(f"You step on Caltrops! -{dmg} HP", C_TEXT_RED)
            else:
                target.hp -= dmg
                target.statuses.append("Slowed")
                self.log(f"{target.name} steps on Caltrops! -{dmg} HP, slowed.", C_TEXT_GREEN)
        elif kind == "Bear Trap":
            dmg = roll(6, 2)
            if is_player:
                rogue.hp -= dmg
                rogue.apply_status("Restrained", 2)
                self.log(f"SNAP! Bear Trap! -{dmg} HP, Restrained 2 turns!", C_TEXT_RED)
            else:
                target.hp -= dmg
                target.statuses.append("Restrained")
                target.restrained_turns = 2
                self.log(f"{target.name} is caught in a Bear Trap! -{dmg} HP, Restrained!", C_TEXT_GREEN)
        elif kind == "Poison Gas Trap":
            dmg = roll(8)
            if is_player:
                rogue.hp -= dmg
                rogue.apply_status("Poisoned", 3)
                self.log(f"Poison gas! -{dmg} HP, Poisoned!", C_TEXT_RED)
            else:
                target.hp -= dmg
                target.statuses.append("Poisoned")
                self.log(f"Poison gas engulfs {target.name}! -{dmg} HP, Poisoned!", C_TEXT_GREEN)

    def open_chest(self):
        chest = self.dungeon.chest_at(self.player_row, self.player_col)
        if chest and not chest.opened:
            chest.open()
            # Update tile
            self.dungeon.tiles[chest.row][chest.col] = CHEST_OPEN
            gold = chest.gold
            self.rogue.gold += gold
            leveled = self.rogue.gain_xp(gold)  # 1 gp = 1 xp
            msgs = [f"You open the chest and find {gold} gold!"]
            if leveled:
                msgs.append(f"*** LEVEL UP! You are now level {self.rogue.level}! ***")
            if chest.loot:
                self.rogue.add_to_inventory(chest.loot)
                msgs.append(f"Inside you also find: {chest.loot.name}!")
            for m in msgs:
                color = C_TEXT_GOLD if "gold" in m.lower() or "LEVEL" in m else C_TEXT_GREEN
                self.log(m, color)
        elif chest and chest.opened:
            self.log("This chest is empty.", C_TEXT_DIM)
        elif self.dungeon.tiles[self.player_row][self.player_col] == STAIRS:
            self.log("Press 'e' to descend the stairs.", C_TEXT_BLUE)

    def descend_stairs(self):
        if (self.player_row, self.player_col) == self.dungeon.stairs_pos:
            if self.floor_num >= 20:
                self.won = True
                self.game_over = True
                self.log("You escape the dungeon! Victory!", C_TEXT_GOLD)
                return
            self.floor_num += 1
            self.dungeon = generate_floor(self.floor_num)
            pr, pc = self.dungeon.player_start
            self.player_row, self.player_col = pr, pc
            self.visible.clear()
            self.mirror_visible.clear()
            self._update_fov()
            self.log(f"You descend to floor {self.floor_num}.", C_TEXT_BLUE)

    def use_potion(self):
        inv = self.rogue.inventory
        potion = next((i for i in inv if "Potion" in i.name), None)
        if potion:
            healed = use_potion(potion)
            self.rogue.heal(healed)
            inv.remove(potion)
            self.log(f"You drink the {potion.name} and recover {healed} HP!", C_TEXT_GREEN)
        else:
            self.log("You have no potions.", C_TEXT_DIM)

    def place_trap(self, kind: str):
        inv = self.rogue.inventory
        trap_item = next((i for i in inv if i.name == kind), None)
        if trap_item:
            # Check tile is clear
            if self.dungeon.trap_at(self.player_row, self.player_col):
                self.log("There is already a trap here!", C_TEXT_DIM)
                return
            inv.remove(trap_item)
            t = Trap(kind=kind, row=self.player_row, col=self.player_col, owner="player")
            self.dungeon.traps.append(t)
            self.log(f"You set a {kind} on the floor.", C_TEXT_BLUE)
        else:
            self.log(f"You have no {kind} in your inventory.", C_TEXT_DIM)

    def apply_blade_poison(self):
        inv = self.rogue.inventory
        poison = next((i for i in inv if i.name == "Blade Poison"), None)
        if poison:
            inv.remove(poison)
            self.rogue.poison_charges += 3
            self.log("You coat your blade with poison. Next 3 hits are poisonous!", C_TEXT_PURPLE)
        else:
            self.log("You have no Blade Poison in your inventory.", C_TEXT_DIM)

    # ---- Monster AI turn ----------------------------------------------------

    def _monster_turn(self):
        r = self.rogue
        for monster in list(self.dungeon.monsters):
            if monster.hp <= 0:
                continue
            mr, mc = monster.row, monster.col
            pr, pc = self.player_row, self.player_col
            dist = abs(mr - pr) + abs(mc - pc)

            # Tick status conditions
            if "Restrained" in monster.statuses:
                if monster.restrained_turns > 0:
                    monster.restrained_turns -= 1
                if monster.restrained_turns <= 0:
                    monster.statuses = [s for s in monster.statuses if s != "Restrained"]
                    self.log(f"{monster.name} breaks free!", C_TEXT_DIM)
                continue  # Can't move while restrained

            # Tick poison damage
            if "Poisoned" in monster.statuses:
                pdmg = roll(6)
                monster.hp -= pdmg
                if monster.hp <= 0:
                    xp = monster.template.xp
                    self.log(f"{monster.name} dies from poison! +{xp} XP", C_TEXT_GOLD)
                    self.rogue.gain_xp(xp)
                    self.dungeon.monsters.remove(monster)
                    continue

            # Detection
            if not monster.alerted:
                # Can the monster see the player?
                mon_visible: Set[Tuple[int,int]] = set()
                compute_fov(
                    (mr, mc),
                    lambda row, col: self.dungeon.is_wall(row, col),
                    lambda row, col: mon_visible.add((row, col)),
                    monster.template.darkvision,
                )
                if (pr, pc) in mon_visible:
                    # Stealth contest
                    stealth = r.stealth_check()
                    # Passive perception modifications
                    pp = monster.template.passive_perception
                    if getattr(monster, "behavior", None) == "Sleep":
                        pp -= 5
                    
                    # Directional perception modifiers
                    look_dr, look_dc = getattr(monster, "look_dir", (0, 1))
                    v_r, v_c = pr - mr, pc - mc
                    dot = v_r * look_dr + v_c * look_dc
                    if dot > 0:
                        pp += 5
                    elif dot < 0:
                        pp -= 5

                    if stealth < pp:
                        monster.alerted = True
                        self.log(f"The {monster.name} spots you!", C_TEXT_RED)

            if not monster.alerted:
                # Tick behavior countdown
                if hasattr(monster, "behavior_turns_left"):
                    monster.behavior_turns_left -= 1
                    if monster.behavior_turns_left <= 0:
                        monster.initialize_behavior(self.dungeon)

                # Execute behavior
                b = getattr(monster, "behavior", "Wander")
                if b == "Guard":
                    monster.look_dir = random.choice([(-1, 0), (1, 0), (0, -1), (0, 1)])
                elif b == "Sleep":
                    # Do not move, do not change look direction
                    pass
                elif b == "Wander":
                    dirs = [(-1, 0), (1, 0), (0, -1), (0, 1)]
                    random.shuffle(dirs)
                    moved = False
                    for dr, dc in dirs:
                        nr, nc = mr + dr, mc + dc
                        if self.dungeon.is_passable(nr, nc) and not self.dungeon.monster_at(nr, nc) and (nr, nc) != (pr, pc):
                            # Check for trap
                            trap = self.dungeon.trap_at(nr, nc)
                            if trap and trap.owner == "player":
                                self._trigger_trap(trap, monster, is_player=False)
                                if monster.hp <= 0:
                                    xp = monster.template.xp
                                    self.log(f"{monster.name} is killed by your trap! +{xp} XP", C_TEXT_GOLD)
                                    self.rogue.gain_xp(xp)
                                    self.dungeon.monsters.remove(monster)
                                    moved = True
                                    break
                            monster.row, monster.col = nr, nc
                            monster.look_dir = (dr, dc)
                            moved = True
                            break
                elif b == "Patrol":
                    if monster.patrol_points and monster.patrol_target:
                        path = astar(
                            (mr, mc), monster.patrol_target,
                            lambda row, col: self.dungeon.is_passable(row, col)
                        )
                        if path and len(path) > 1:
                            nr, nc = path[1]
                            monster.look_dir = (nr - mr, nc - mc)
                            if not self.dungeon.monster_at(nr, nc) and (nr, nc) != (pr, pc):
                                trap = self.dungeon.trap_at(nr, nc)
                                if trap and trap.owner == "player":
                                    self._trigger_trap(trap, monster, is_player=False)
                                    if monster.hp <= 0:
                                        xp = monster.template.xp
                                        self.log(f"{monster.name} is killed by your trap! +{xp} XP", C_TEXT_GOLD)
                                        self.rogue.gain_xp(xp)
                                        self.dungeon.monsters.remove(monster)
                                        continue
                                monster.row, monster.col = nr, nc
                        if (monster.row, monster.col) == monster.patrol_target:
                            pt_a, pt_b = monster.patrol_points
                            monster.patrol_target = pt_a if monster.patrol_target == pt_b else pt_b
                continue  # Skip chasing logic

            # Pathfind toward player
            path = astar(
                (mr, mc), (pr, pc),
                lambda row, col: self.dungeon.is_passable(row, col),
            )
            if path and len(path) > 1:
                nr, nc = path[1]
                monster.look_dir = (nr - mr, nc - mc)
                # Check if moving onto a trap
                trap = self.dungeon.trap_at(nr, nc)
                if trap and trap.owner == "player":
                    self._trigger_trap(trap, monster, is_player=False)
                    if monster.hp <= 0:
                        xp = monster.template.xp
                        self.log(f"{monster.name} is killed by your trap! +{xp} XP", C_TEXT_GOLD)
                        self.rogue.gain_xp(xp)
                        self.dungeon.monsters.remove(monster)
                        continue
                # Check if player is at next tile → attack
                if (nr, nc) == (pr, pc):
                    self._monster_attack(monster)
                else:
                    # Make sure no other monster is there
                    if not self.dungeon.monster_at(nr, nc):
                        monster.row, monster.col = nr, nc

    def _monster_attack(self, monster: Monster):
        r = self.rogue
        # Rogue has disadvantage if Poisoned
        atk = d20() + monster.template.attack_bonus
        if atk >= r.ac:
            nd, ns = monster.template.damage_dice
            dmg = roll(ns, nd) + monster.template.damage_bonus
            r.hp -= dmg
            self.log(f"The {monster.name} hits you for {dmg} damage!", C_TEXT_RED)
            if r.hp <= 0:
                self.game_over = True
                self.log("You have been slain... Game Over.", C_TEXT_RED)
        else:
            self.log(f"The {monster.name} misses you.", C_TEXT_DIM)

    # ---- Full turn tick -----------------------------------------------------

    def end_turn(self):
        if self.game_over:
            return
        self.turn += 1
        self._monster_turn()
        # Tick player statuses
        self.rogue.tick_statuses()
        # Poison damage on player
        if self.rogue.has_status("Poisoned"):
            pdmg = roll(4)
            self.rogue.hp -= pdmg
            self.log(f"Poison burns through you! -{pdmg} HP", C_TEXT_RED)
            if self.rogue.hp <= 0:
                self.game_over = True
                self.log("The poison kills you... Game Over.", C_TEXT_RED)

# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Renderer:
    def __init__(self, screen: pygame.Surface, fonts: dict):
        self.screen = screen
        self.fonts  = fonts
        self.cam_row = 0
        self.cam_col = 0

    def _world_to_screen(self, row, col):
        sx = (col - self.cam_col) * CELL + MAP_X
        sy = (row - self.cam_row) * CELL + MAP_Y
        return sx, sy

    def _update_camera(self, gs: GameState):
        half_r = VIEW_ROWS // 2
        half_c = VIEW_COLS // 2
        self.cam_row = max(0, min(gs.player_row - half_r, MAP_ROWS - VIEW_ROWS))
        self.cam_col = max(0, min(gs.player_col - half_c, MAP_COLS - VIEW_COLS))

    def draw_map(self, gs: GameState):
        self._update_camera(gs)
        floor = gs.dungeon
        all_vis    = gs.visible | gs.mirror_visible
        all_explore= gs.explored
        surf = self.screen

        for dr in range(VIEW_ROWS + 1):
            for dc in range(VIEW_COLS + 1):
                r = self.cam_row + dr
                c = self.cam_col + dc
                if r >= MAP_ROWS or c >= MAP_COLS:
                    continue
                sx, sy = self._world_to_screen(r, c)
                pos = (r, c)
                tile = floor.tiles[r][c]
                visible = pos in all_vis
                seen    = pos in all_explore

                if not seen:
                    pygame.draw.rect(surf, C_BG, (sx, sy, CELL, CELL))
                    continue

                # Choose base color
                if tile == WALL:
                    color = C_WALL_LIT if visible else C_WALL
                elif tile == STAIRS:
                    color = C_STAIRS if visible else _lerp_color(C_STAIRS, C_FLOOR_SEEN, 0.6)
                elif tile == TORCH:
                    color = C_TORCH_LIT if visible else C_FLOOR_SEEN
                elif tile in (CHEST, CHEST_OPEN):
                    color = (C_CHEST if tile == CHEST else C_CHEST_OPEN) if visible else C_FLOOR_SEEN
                else:
                    color = C_FLOOR_LIT if visible else C_FLOOR_SEEN

                pygame.draw.rect(surf, color, (sx, sy, CELL, CELL))

                # Tile decorations
                if visible:
                    mid = (sx + CELL // 2, sy + CELL // 2)
                    if tile == STAIRS:
                        self._draw_stairs(surf, sx, sy)
                    elif tile == TORCH:
                        pygame.draw.circle(surf, (255, 200, 80), mid, CELL // 3)
                        pygame.draw.circle(surf, (255, 255, 150), mid, CELL // 5)
                    elif tile == CHEST:
                        self._draw_chest(surf, sx, sy, open_=False)
                    elif tile == CHEST_OPEN:
                        self._draw_chest(surf, sx, sy, open_=True)

                # Mirror reveal highlight
                if pos in gs.mirror_visible and pos not in gs.visible:
                    s = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
                    s.fill((100, 220, 255, 40))
                    surf.blit(s, (sx, sy))

        # Player traps
        for trap in floor.traps:
            if trap.triggered:
                continue
            pos = (trap.row, trap.col)
            if pos not in all_vis:
                continue
            sx, sy = self._world_to_screen(trap.row, trap.col)
            pygame.draw.circle(surf, C_TRAP, (sx + CELL//2, sy + CELL//2), CELL // 4)

        # Monsters
        for monster in floor.monsters:
            pos = (monster.row, monster.col)
            if pos not in all_vis:
                continue
            sx, sy = self._world_to_screen(monster.row, monster.col)
            self._draw_monster(surf, sx, sy, monster)

        # Player
        px, py = self._world_to_screen(gs.player_row, gs.player_col)
        self._draw_player(surf, px, py, gs.rogue)

    def _draw_stairs(self, surf, sx, sy):
        color = C_STAIRS
        # Draw downward arrow
        pts = [
            (sx + CELL // 2, sy + CELL - 3),
            (sx + 3,          sy + 4),
            (sx + CELL - 3,   sy + 4),
        ]
        pygame.draw.polygon(surf, color, pts)

    def _draw_chest(self, surf, sx, sy, open_: bool):
        col = C_CHEST_OPEN if open_ else C_CHEST
        pygame.draw.rect(surf, col, (sx + 3, sy + 4, CELL - 6, CELL - 7))
        if not open_:
            pygame.draw.rect(surf, (80, 60, 20), (sx + 5, sy + CELL//2 - 1, CELL - 10, 3))

    def _draw_player(self, surf, sx, sy, rogue: Rogue):
        cx, cy = sx + CELL // 2, sy + CELL // 2
        r = CELL // 2 - 2
        pygame.draw.circle(surf, C_PLAYER_SH, (cx, cy), r)
        pygame.draw.circle(surf, C_PLAYER, (cx, cy), r - 2)
        # @ symbol
        txt = self.fonts["sm"].render("@", True, (255, 255, 255))
        surf.blit(txt, txt.get_rect(center=(cx, cy)))

    def _draw_monster(self, surf, sx, sy, m: Monster):
        cx, cy = sx + CELL // 2, sy + CELL // 2
        r = CELL // 2 - 2
        color = m.template.color
        pygame.draw.circle(surf, (30, 10, 10), (cx + 1, cy + 1), r)
        pygame.draw.circle(surf, color, (cx, cy), r)
        sym = self.fonts["sm"].render(m.template.symbol, True, (255, 255, 255))
        surf.blit(sym, sym.get_rect(center=(cx, cy)))

        # Draw look direction indicator
        dr, dc = getattr(m, "look_dir", (0, 1))
        if m.alerted:
            ind_color = (255, 50, 50)
        else:
            b = getattr(m, "behavior", "Wander")
            if b == "Guard":
                ind_color = (255, 215, 0)
            elif b == "Patrol":
                ind_color = (50, 205, 50)
            elif b == "Sleep":
                ind_color = (135, 206, 235)
            else: # Wander
                ind_color = (255, 140, 0)

        # Tip of arrowhead
        tip_x = cx + dc * (r + 3)
        tip_y = cy + dr * (r + 3)
        # Base of arrowhead
        base_x = cx + dc * r
        base_y = cy + dr * r
        # Perpendicular vector
        perpx = -dr
        perpy = dc
        # Arrow base corners
        p1_x = base_x + perpx * 3
        p1_y = base_y + perpy * 3
        p2_x = base_x - perpx * 3
        p2_y = base_y - perpy * 3

        pygame.draw.polygon(surf, ind_color, [(tip_x, tip_y), (p1_x, p1_y), (p2_x, p2_y)])

        # Sleeping visual effect (a small "z" near the top right of the monster)
        if getattr(m, "behavior", None) == "Sleep" and not m.alerted:
            z_txt = self.fonts["sm"].render("z", True, (135, 206, 235))
            surf.blit(z_txt, (sx + CELL - 6, sy - 4))

        # HP bar
        if m.hp < m.max_hp:
            bw = CELL - 2; bh = 2
            bx = sx + 1; by = sy + CELL - 3
            pygame.draw.rect(surf, (80, 0, 0),   (bx, by, bw, bh))
            pygame.draw.rect(surf, (0, 200, 0),  (bx, by, int(bw * m.hp / m.max_hp), bh))


    def draw_hud(self, gs: GameState):
        surf = self.screen
        hx = HUD_X
        pygame.draw.rect(surf, C_HUD_BG, (hx, 0, HUD_W, SCREEN_H))
        pygame.draw.line(surf, C_HUD_BORDER, (hx, 0), (hx, SCREEN_H), 2)

        r = gs.rogue
        y = 8
        lh = 22  # line height

        def text(msg, color=C_TEXT, font="md", indent=0):
            nonlocal y
            t = self.fonts[font].render(msg, True, color)
            surf.blit(t, (hx + 10 + indent, y))
            y += lh

        def bar(label, val, max_val, fg, bg, label_color=C_TEXT):
            nonlocal y
            bx = hx + 10; bw = HUD_W - 20; bh = 14
            lbl = self.fonts["sm"].render(label, True, label_color)
            surf.blit(lbl, (bx, y)); y += 14
            pygame.draw.rect(surf, bg,  (bx, y, bw, bh))
            filled = int(bw * max(0, val) / max(1, max_val))
            pygame.draw.rect(surf, fg,  (bx, y, filled, bh))
            pct = self.fonts["sm"].render(f"{val}/{max_val}", True, C_TEXT)
            surf.blit(pct, pct.get_rect(center=(bx + bw // 2, y + bh // 2)))
            y += bh + 4

        # Title
        text(f"FLOOR {gs.floor_num}  |  TURN {gs.turn}", C_TEXT_BLUE, "md")
        text(f"Level {r.level} Rogue", C_TEXT_GOLD, "lg")
        y += 4

        # HP / XP bars
        bar(f"HP  ({r.hp}/{r.max_hp})", r.hp, r.max_hp, C_HP_BAR_FG, C_HP_BAR_BG, C_TEXT_RED)
        from rules import XP_THRESHOLDS
        next_xp = XP_THRESHOLDS[min(r.level, 19)]
        prev_xp = XP_THRESHOLDS[r.level - 1]
        bar(f"XP  ({r.xp}/{next_xp})", r.xp - prev_xp, next_xp - prev_xp, C_XP_BAR_FG, C_XP_BAR_BG, C_TEXT_BLUE)

        # Stats
        text(f"Gold: {r.gold}", C_TEXT_GOLD)
        text(f"AC: {r.ac}   PP: {r.passive_perception}", C_TEXT)
        text(f"Stealth: +{r.stealth_bonus}   Tools: +{r.thieves_tools_bonus}", C_TEXT)
        if r.has_darkvision:
            text("Darkvision: 6 tiles", C_TEXT_PURPLE)
        if r.poison_charges > 0:
            text(f"Blade Poison: {r.poison_charges} hits", C_TEXT_PURPLE)

        # Statuses
        for st in r.statuses:
            text(f"[{st.name}: {st.duration}t]", C_TEXT_RED)

        y += 6
        pygame.draw.line(surf, C_HUD_BORDER, (hx + 5, y), (SCREEN_W - 5, y))
        y += 6

        # Equipment
        text("── EQUIPPED ──", C_TEXT_DIM, "sm")
        text(f"Weapon: {r.weapon.name if r.weapon else 'None'}", C_TEXT)
        text(f"Armor:  {r.armor.name  if r.armor  else 'None'}", C_TEXT)
        for i, item in enumerate(r.equipped_items):
            text(f"[{i+1}] {item.name}", C_TEXT_BLUE)

        y += 4
        pygame.draw.line(surf, C_HUD_BORDER, (hx + 5, y), (SCREEN_W - 5, y))
        y += 6

        # Inventory summary
        text("── INVENTORY ──", C_TEXT_DIM, "sm")
        potions   = [i for i in r.inventory if "Potion" in i.name]
        caltrops  = [i for i in r.inventory if i.name == "Caltrops"]
        beartraps = [i for i in r.inventory if i.name == "Bear Trap"]
        gas_traps = [i for i in r.inventory if i.name == "Poison Gas Trap"]
        poisons   = [i for i in r.inventory if i.name == "Blade Poison"]
        mirrors   = [i for i in r.inventory if i.name == "Small Mirror"]
        others    = [i for i in r.inventory if i not in potions + caltrops +
                     beartraps + gas_traps + poisons + mirrors]

        if potions:   text(f"H) Potions x{len(potions)}", C_TEXT_GREEN)
        if caltrops:  text(f"1) Caltrops x{len(caltrops)}", C_TRAP)
        if beartraps: text(f"2) Bear Trap x{len(beartraps)}", C_TRAP)
        if gas_traps: text(f"3) Gas Trap x{len(gas_traps)}", C_TRAP)
        if poisons:   text(f"4) Blade Poison x{len(poisons)}", C_TEXT_PURPLE)
        if mirrors:   text(f"M) Small Mirror x{len(mirrors)}", C_MIRROR_GLOW)
        for it in others[:5]:
            text(f"  {it.name}", C_TEXT_DIM, "sm")

        y += 4
        pygame.draw.line(surf, C_HUD_BORDER, (hx + 5, y), (SCREEN_W - 5, y))
        y += 6

        # Controls
        text("── CONTROLS ──", C_TEXT_DIM, "sm")
        controls = [
            "Arrows/WASD Move/Attack",
            "E  Open/Pick Up/Descend",
            "H  Use potion",
            "M  Use small mirror",
            "1  Place caltrops",
            "2  Place bear trap",
            "3  Place gas trap",
            "4  Apply blade poison",
            "Space/./Z/5 Pass turn (Wait)",
        ]
        for c in controls:
            text(c, C_TEXT_DIM, "sm")

        # Message log
        log_y = SCREEN_H - (LOG_LINES * 18 + 14)
        pygame.draw.rect(surf, (12, 12, 20), (hx, log_y - 4, HUD_W, SCREEN_H - log_y + 4))
        pygame.draw.line(surf, C_HUD_BORDER, (hx + 5, log_y - 4), (SCREEN_W - 5, log_y - 4))
        import textwrap
        display_lines = []
        for msg, color in reversed(gs.messages):
            wrapped = textwrap.wrap(msg, width=30)
            for line in reversed(wrapped):
                display_lines.append((line, color))
                if len(display_lines) >= LOG_LINES:
                    break
            if len(display_lines) >= LOG_LINES:
                break
        display_lines.reverse()
        for i, (line, color) in enumerate(display_lines):
            t = self.fonts["sm"].render(line, True, color)
            surf.blit(t, (hx + 8, log_y + i * 18))

    def draw_game_over(self, gs: GameState):
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        if gs.won:
            title = self.fonts["xl"].render("VICTORY!", True, C_TEXT_GOLD)
            sub   = self.fonts["lg"].render("You escaped the dungeon!", True, C_TEXT_GREEN)
        else:
            title = self.fonts["xl"].render("GAME OVER", True, C_TEXT_RED)
            sub   = self.fonts["lg"].render("Your adventure ends here.", True, C_TEXT_DIM)
        cx = SCREEN_W // 2
        self.screen.blit(title, title.get_rect(center=(cx, SCREEN_H // 2 - 40)))
        self.screen.blit(sub,   sub.get_rect(center=(cx, SCREEN_H // 2 + 10)))
        restart = self.fonts["md"].render("Press R to restart or Escape to quit.", True, C_TEXT)
        self.screen.blit(restart, restart.get_rect(center=(cx, SCREEN_H // 2 + 60)))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Dungeon Rogue  |  D&D 5.2.1 SRD")
    clock = pygame.time.Clock()

    # Fonts — use system fallback (no external file required)
    def mk_font(size):
        try:
            return pygame.font.SysFont("Consolas", size)
        except Exception:
            return pygame.font.Font(None, size)

    fonts = {
        "xl": mk_font(52),
        "lg": mk_font(26),
        "md": mk_font(20),
        "sm": mk_font(16),
    }

    gs  = GameState()
    ren = Renderer(screen, fonts)

    running = True
    while running:
        clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if gs.game_over:
                    if event.key == pygame.K_r:
                        gs  = GameState()
                        ren = Renderer(screen, fonts)
                    elif event.key == pygame.K_ESCAPE:
                        running = False
                    continue

                moved = False
                key = event.key

                # Movement / attack
                dirs = {
                    pygame.K_UP:    (-1,  0), pygame.K_w: (-1,  0),
                    pygame.K_DOWN:  ( 1,  0), pygame.K_s: ( 1,  0),
                    pygame.K_LEFT:  ( 0, -1), pygame.K_a: ( 0, -1),
                    pygame.K_RIGHT: ( 0,  1), pygame.K_d: ( 0,  1),
                }
                if key in dirs:
                    moved = gs.try_move(*dirs[key])

                elif key in (pygame.K_PERIOD, pygame.K_SPACE, pygame.K_z, pygame.K_KP_5):
                    moved = True   # pass turn

                elif key == pygame.K_e:
                    gs.open_chest()
                    gs.descend_stairs()
                    moved = True

                elif key == pygame.K_h:
                    gs.use_potion()
                    moved = True

                elif key == pygame.K_m:
                    gs.use_mirror()
                    # Mirror use doesn't consume a turn

                elif key == pygame.K_1:
                    gs.place_trap("Caltrops")
                    moved = True

                elif key == pygame.K_2:
                    gs.place_trap("Bear Trap")
                    moved = True

                elif key == pygame.K_3:
                    gs.place_trap("Poison Gas Trap")
                    moved = True

                elif key == pygame.K_4:
                    gs.apply_blade_poison()
                    moved = True

                elif key == pygame.K_ESCAPE:
                    running = False

                if moved:
                    gs.end_turn()

        # Render
        screen.fill(C_BG)
        ren.draw_map(gs)
        ren.draw_hud(gs)
        if gs.game_over:
            ren.draw_game_over(gs)

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
