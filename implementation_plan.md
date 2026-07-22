# Add Monster Behaviors and Look-Direction Perception

Implement modular AI behaviors for monsters when they are not chasing the player, update their perception based on their looking direction, and render a premium-looking direction/state indicator.

## User Review Required

> [!NOTE]
> The behaviors are randomly chosen upon spawn and cycle every 20 rounds for each monster individually when they are not alert. This creates a natural, asynchronous movement flow in the dungeon.
> We will also implement a visual indicator (colored arrowheads) at the edge of the monster circle to show where they are looking:
> - **Guard**: Yellow arrow (changes look direction randomly every turn)
> - **Patrol**: Green arrow (moves back and forth between two points, looking forward)
> - **Sleep**: Light blue arrow, and a small "z" floating next to them (does not move/look around, -5 PP penalty)
> - **Wander**: Orange arrow (moves randomly, looking in the last moved direction)
> - **Alerted (Chasing)**: Bright red arrow (chases player, looking towards the player or movement direction)

## Proposed Changes

### Game Rules & Dungeon State

#### [MODIFY] [dungeon.py](file:///c:/Users/Makhew3/antigravity/DnD/dungeon.py)

- Modify the `Monster` dataclass:
  - Add fields for `behavior`, `behavior_turns_left`, `look_dir` (as `Tuple[int, int]`), `patrol_points`, and `patrol_target`.
  - Add `initialize_behavior(self, dungeon_floor)` method to set or randomly transition behaviors. It will automatically find a second valid tile for the patrol points if the chosen behavior is **Patrol**, using pathfinding to ensure reachability.
- In `generate_floor`, call `initialize_behavior` on all generated monsters after the `DungeonFloor` is created.

### Monster Turn & Detection Logic

#### [MODIFY] [dungeon_rogue.py](file:///c:/Users/Makhew3/antigravity/DnD/dungeon_rogue.py)

- Update `_monster_turn` in `GameState`:
  - If a monster is not alerted:
    - Tick down `behavior_turns_left`.
    - If it reaches 0, call `initialize_behavior` to choose a new behavior randomly.
    - Run the specific behavior actions:
      - **Guard**: Select a random look direction from `[(-1,0), (1,0), (0,-1), (0,1)]`.
      - **Patrol**: Pathfind toward `patrol_target`. If the next step is valid, move and look in that direction. If arrived at `patrol_target`, swap the target to the other patrol point.
      - **Sleep**: Do not move, do not change look direction.
      - **Wander**: Select a random valid adjacent tile to move to. If moved, update the look direction.
  - If a monster *is* alerted and chasing:
    - Update look direction to point to their next move or attack target.
- Update the **Detection/Stealth** check inside `_monster_turn`:
  - Calculate effective passive perception `pp` by applying:
    - `-5` if the monster is in the **Sleep** behavior.
    - `+5` if looking in the direction of the player (positive dot product between the look direction and the vector from monster to player).
    - `-5` if looking away from the player (negative dot product).

### Visual Rendering

#### [MODIFY] [dungeon_rogue.py](file:///c:/Users/Makhew3/antigravity/DnD/dungeon_rogue.py)

- Update `_draw_monster` in the `Renderer` class:
  - Determine indicator color based on the current state:
    - Alerted (chasing): Red `(255, 50, 50)`
    - Guard: Yellow `(255, 215, 0)`
    - Patrol: Green `(50, 205, 50)`
    - Sleep: Light blue `(135, 206, 235)`
    - Wander: Orange `(255, 140, 0)`
  - Draw a neat arrowhead polygon pointing in `m.look_dir` along the edge of the monster circle.
  - If the monster is asleep (`m.behavior == "Sleep" and not m.alerted`), render a small `"z"` next to them to make their status immediately recognizable.

## Verification Plan

### Automated Tests
- Run `python -m unittest discover -s tests` to ensure existing game tests continue to pass.
- Write new tests to verify behavior assignment and the perception modifiers based on looking direction.

### Manual Verification
- Run the Pygame client using `python dungeon_rogue.py`.
- Observe monster movement in unexplored rooms or when sneak status is active.
- Verify that sleep states, wandering paths, patrol paths, and look indicators render correctly and update dynamically.
