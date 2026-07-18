"""
fov.py - Symmetric Shadowcasting Field-of-View
Based on Albert Ford's algorithm: https://www.albertford.com/shadowcasting/
Uses Python's fractions.Fraction for exact slope comparisons (no float drift).
"""
from __future__ import annotations
import math
from fractions import Fraction
from typing import Callable, Set, Tuple

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_fov(
    origin: Tuple[int, int],
    is_blocking: Callable[[int, int], bool],
    mark_visible: Callable[[int, int], None],
    radius: int,
) -> None:
    """
    Compute FOV from *origin* up to *radius* tiles away.

    Parameters
    ----------
    origin       : (row, col) of the viewer
    is_blocking  : returns True if tile (row, col) blocks light (i.e. a wall)
    mark_visible : called for every tile determined to be visible
    radius       : maximum light radius in tiles
    """
    mark_visible(*origin)
    for i in range(4):
        quadrant = _Quadrant(i, origin)
        first_row = _Row(1, Fraction(-1), Fraction(1))
        _scan(quadrant, first_row, is_blocking, mark_visible, radius)


def compute_mirror_fov(
    peek_from: Tuple[int, int],
    is_blocking: Callable[[int, int], bool],
    mark_visible: Callable[[int, int], None],
    radius: int,
) -> None:
    """
    Same as compute_fov but from a temporary vantage point (e.g. Small Mirror).
    Results are added to whatever the caller tracks via mark_visible.
    """
    compute_fov(peek_from, is_blocking, mark_visible, radius)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _round_ties_up(n: Fraction) -> int:
    return math.floor(n + Fraction(1, 2))


def _round_ties_down(n: Fraction) -> int:
    return math.ceil(n - Fraction(1, 2))


class _Quadrant:
    NORTH = 0
    EAST  = 1
    SOUTH = 2
    WEST  = 3

    def __init__(self, cardinal: int, origin: Tuple[int, int]) -> None:
        self.cardinal = cardinal
        self.ox, self.oy = origin  # note: we use (col, row) internally → (x, y)
        # Remap: origin is (row, col); store as (ox=col, oy=row) for transform
        self.ox, self.oy = origin[1], origin[0]

    def transform(self, row: int, col: int) -> Tuple[int, int]:
        """Return the world (row, col) for a quadrant-local (row, col)."""
        if self.cardinal == _Quadrant.NORTH:
            return (self.oy - row, self.ox + col)
        if self.cardinal == _Quadrant.SOUTH:
            return (self.oy + row, self.ox + col)
        if self.cardinal == _Quadrant.EAST:
            return (self.oy + col, self.ox + row)
        if self.cardinal == _Quadrant.WEST:
            return (self.oy + col, self.ox - row)
        raise ValueError(f"Unknown cardinal: {self.cardinal}")


class _Row:
    def __init__(self, depth: int, start_slope: Fraction, end_slope: Fraction) -> None:
        self.depth = depth
        self.start_slope = start_slope
        self.end_slope = end_slope

    def tiles(self):
        min_col = _round_ties_up(self.depth * self.start_slope)
        max_col = _round_ties_down(self.depth * self.end_slope)
        for col in range(min_col, max_col + 1):
            yield col

    def next(self) -> "_Row":
        return _Row(self.depth + 1, self.start_slope, self.end_slope)


def _slope(depth: int, col: int) -> Fraction:
    return Fraction(2 * col - 1, 2 * depth)


def _is_symmetric(row: _Row, col: int) -> bool:
    return (col >= row.depth * row.start_slope and
            col <= row.depth * row.end_slope)


def _scan(
    quadrant: _Quadrant,
    row: _Row,
    is_blocking: Callable[[int, int], bool],
    mark_visible: Callable[[int, int], None],
    radius: int,
) -> None:
    if row.depth > radius:
        return

    prev_tile_was_wall = None
    current_row = row

    for col in current_row.tiles():
        world_pos = quadrant.transform(current_row.depth, col)
        tile_blocks = is_blocking(*world_pos)

        if tile_blocks or _is_symmetric(current_row, col):
            mark_visible(*world_pos)

        if prev_tile_was_wall is not None:
            if prev_tile_was_wall and not tile_blocks:
                # Transitioning from wall to floor: update start slope
                current_row = _Row(
                    current_row.depth,
                    _slope(current_row.depth, col),
                    current_row.end_slope,
                )
            if not prev_tile_was_wall and tile_blocks:
                # Transitioning from floor to wall: recurse with narrower end slope
                next_row = _Row(
                    current_row.depth + 1,
                    current_row.start_slope,
                    _slope(current_row.depth, col),
                )
                _scan(quadrant, next_row, is_blocking, mark_visible, radius)

        prev_tile_was_wall = tile_blocks

    if prev_tile_was_wall is False:
        _scan(quadrant, current_row.next(), is_blocking, mark_visible, radius)
