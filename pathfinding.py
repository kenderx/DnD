"""
pathfinding.py - BFS flood fill + A* pathfinding for the D&D Roguelike.

BFS:  Used to highlight tiles reachable within a move range (not currently
      used for combat range — the Rogue acts instantly).
A*:   Used by monster AI to chase the player through corridors.
"""
from __future__ import annotations
import heapq
from collections import deque
from typing import Callable, Dict, List, Optional, Set, Tuple

Pos = Tuple[int, int]

# ---------------------------------------------------------------------------
# BFS — flood fill within a given step budget
# ---------------------------------------------------------------------------

def bfs_reachable(
    start: Pos,
    max_steps: int,
    passable: Callable[[int, int], bool],
) -> Set[Pos]:
    """
    Return the set of positions reachable from *start* within *max_steps*
    cardinal moves, considering only tiles where passable(r, c) is True.
    The start tile is always included.
    """
    visited: Set[Pos] = {start}
    queue: deque[Tuple[Pos, int]] = deque([(start, 0)])

    while queue:
        pos, dist = queue.popleft()
        if dist >= max_steps:
            continue
        for nb in _neighbors(pos):
            if nb not in visited and passable(*nb):
                visited.add(nb)
                queue.append((nb, dist + 1))

    return visited


# ---------------------------------------------------------------------------
# A* — optimal path for monster AI
# ---------------------------------------------------------------------------

def astar(
    start: Pos,
    goal: Pos,
    passable: Callable[[int, int], bool],
    max_nodes: int = 2000,
) -> Optional[List[Pos]]:
    """
    Return the shortest path (list of positions from start to goal, inclusive)
    using A* with Manhattan-distance heuristic.

    Returns None if no path exists or *max_nodes* is exceeded (to prevent
    freezes on large open maps).
    """
    if start == goal:
        return [start]

    h = _manhattan
    open_heap: List[Tuple[int, int, Pos, Optional[Pos]]] = []
    # heap item: (f, g, pos, parent)
    counter = 0  # tie-breaker
    heapq.heappush(open_heap, (h(start, goal), counter, start, None))

    came_from: Dict[Pos, Optional[Pos]] = {}
    g_score: Dict[Pos, int] = {start: 0}
    visited = 0

    while open_heap:
        f, _, current, parent = heapq.heappop(open_heap)
        if current in came_from:
            continue
        came_from[current] = parent
        visited += 1
        if visited > max_nodes:
            return None
        if current == goal:
            return _reconstruct(came_from, goal)
        g = g_score[current]
        for nb in _neighbors(current):
            if not passable(*nb) and nb != goal:
                continue
            new_g = g + 1
            if new_g < g_score.get(nb, 10**9):
                g_score[nb] = new_g
                counter += 1
                heapq.heappush(open_heap, (new_g + h(nb, goal), counter, nb, current))

    return None  # no path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CARDINALS = [(-1, 0), (1, 0), (0, -1), (0, 1)]


def _neighbors(pos: Pos) -> List[Pos]:
    r, c = pos
    return [(r + dr, c + dc) for dr, dc in _CARDINALS]


def _manhattan(a: Pos, b: Pos) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _reconstruct(came_from: Dict[Pos, Optional[Pos]], goal: Pos) -> List[Pos]:
    path: List[Pos] = []
    node: Optional[Pos] = goal
    while node is not None:
        path.append(node)
        node = came_from[node]
    path.reverse()
    return path
