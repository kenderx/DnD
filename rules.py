"""
rules.py  —  D&D 5.2.1 SRD Rogue rules engine.

Covers:
  • Dice rolling (advantage / disadvantage)
  • Rogue character sheet (stats, proficiency, saves)
  • XP thresholds and level-up logic
  • Sneak Attack scaling
  • Status conditions (Poisoned, Restrained)
  • Item definitions and loot generation
  • Monster stat-blocks (scaled to floor level)
  • Combat resolution helpers
"""
from __future__ import annotations
import copy
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Dice
# ---------------------------------------------------------------------------

def roll(sides: int, n: int = 1) -> int:
    """Roll n dice with the given number of sides, return total."""
    return sum(random.randint(1, sides) for _ in range(n))


def roll_adv(sides: int, n: int = 1) -> int:
    """Roll with advantage (best of two)."""
    return max(roll(sides, n), roll(sides, n))


def roll_dis(sides: int, n: int = 1) -> int:
    """Roll with disadvantage (worst of two)."""
    return min(roll(sides, n), roll(sides, n))


def d20(advantage: bool = False, disadvantage: bool = False) -> int:
    if advantage and not disadvantage:
        return roll_adv(20)
    if disadvantage and not advantage:
        return roll_dis(20)
    return roll(20)


def modifier(score: int) -> int:
    return (score - 10) // 2

# ---------------------------------------------------------------------------
# XP Table (SRD 5.2.1 Rogue)
# ---------------------------------------------------------------------------

XP_THRESHOLDS = [
    0,        # Level 1
    300,      # Level 2
    900,      # Level 3
    2700,     # Level 4
    6500,     # Level 5
    14000,    # Level 6
    23000,    # Level 7
    34000,    # Level 8
    48000,    # Level 9
    64000,    # Level 10
    85000,    # Level 11
    100000,   # Level 12
    120000,   # Level 13
    140000,   # Level 14
    165000,   # Level 15
    195000,   # Level 16
    225000,   # Level 17
    265000,   # Level 18
    305000,   # Level 19
    355000,   # Level 20
]

PROFICIENCY_BONUS = {
    1: 2, 2: 2, 3: 2, 4: 2,
    5: 3, 6: 3, 7: 3, 8: 3,
    9: 4, 10: 4, 11: 4, 12: 4,
    13: 5, 14: 5, 15: 5, 16: 5,
    17: 6, 18: 6, 19: 6, 20: 6,
}

def sneak_attack_dice(level: int) -> int:
    """Number of d6s for Sneak Attack at the given Rogue level."""
    # Starts at 1d6 at level 1, +1d6 every odd level → max 10d6 at level 19+
    return max(1, (level + 1) // 2)

# ---------------------------------------------------------------------------
# Item Definitions
# ---------------------------------------------------------------------------

SLOT_WEAPON = "weapon"
SLOT_ARMOR  = "armor"
SLOT_ITEM   = "item"       # max 3 equipped
SLOT_NONE   = "consumable" # stays in inventory

@dataclass
class Item:
    name: str
    slot: str                           # weapon / armor / item / consumable
    ac_bonus: int = 0
    to_hit_bonus: int = 0
    damage_bonus: int = 0
    extra_damage_dice: int = 0          # e.g. flame tongue +1d6 fire
    extra_damage_sides: int = 0
    skill_bonus: Dict[str, int] = field(default_factory=dict)  # {"Stealth": 3}
    passive_perception_bonus: int = 0
    darkvision: bool = False
    max_hp_bonus: int = 0
    saving_throw_bonus: int = 0
    uses: int = -1                      # -1 = infinite / permanent
    description: str = ""

    def __str__(self) -> str:
        parts = [self.name]
        if self.ac_bonus:       parts.append(f"+{self.ac_bonus} AC")
        if self.to_hit_bonus:   parts.append(f"+{self.to_hit_bonus} hit")
        if self.damage_bonus:   parts.append(f"+{self.damage_bonus} dmg")
        if self.darkvision:     parts.append("Darkvision")
        if self.passive_perception_bonus:
            parts.append(f"+{self.passive_perception_bonus} PP")
        for sk, v in self.skill_bonus.items():
            parts.append(f"+{v} {sk}")
        return ", ".join(parts)


# ---- Weapons ----------------------------------------------------------------
def _weapon(name, to_hit, damage_bonus, extra_dice=0, extra_sides=0, desc="") -> Item:
    return Item(name=name, slot=SLOT_WEAPON,
                to_hit_bonus=to_hit, damage_bonus=damage_bonus,
                extra_damage_dice=extra_dice, extra_damage_sides=extra_sides,
                description=desc)

WEAPONS_BY_TIER: Dict[int, List[Item]] = {
    1: [_weapon("Dagger",            0, 0, desc="1d4 piercing"),
        _weapon("Shortbow",          0, 0, desc="1d6 piercing, range 80/320")],
    2: [_weapon("+1 Dagger",         1, 1, desc="1d4+1 piercing"),
        _weapon("+1 Shortbow",       1, 1, desc="1d6+1 piercing")],
    3: [_weapon("+2 Dagger",         2, 2, desc="1d4+2 piercing"),
        _weapon("Flame Tongue Dagger",2,2,1,6, desc="1d4+2+1d6 fire")],
    4: [_weapon("+3 Dagger",         3, 3, desc="1d4+3 piercing"),
        _weapon("Dagger of Venom",   2, 2, 1, 6, desc="1d4+2+1d6 poison, Poisoned cond.")],
}

# ---- Armor ------------------------------------------------------------------
def _armor(name, ac, desc="") -> Item:
    return Item(name=name, slot=SLOT_ARMOR, ac_bonus=ac, description=desc)

ARMORS_BY_TIER: Dict[int, List[Item]] = {
    1: [_armor("Leather Armor",         11, "Light armor"),
        _armor("Studded Leather",       12, "Light armor")],
    2: [_armor("Studded Leather +1",    13, "Light armor +1")],
    3: [_armor("Studded Leather +2",    14, "Light armor +2")],
    4: [_armor("Studded Leather +3",    15, "Light armor +3")],
}

# ---- Special equippable items -----------------------------------------------
SPECIAL_ITEMS: List[Item] = [
    Item("Ring of Protection",   SLOT_ITEM, ac_bonus=1, saving_throw_bonus=1,
         description="+1 AC and +1 to all saving throws"),
    Item("Boots of Elvenkind",   SLOT_ITEM, skill_bonus={"Stealth": 3},
         description="+3 to Stealth checks"),
    Item("Gloves of Thievery",   SLOT_ITEM, skill_bonus={"Thieves' Tools": 3, "Sleight of Hand": 3},
         description="+3 Thieves' Tools and Sleight of Hand"),
    Item("Cloak of Protection",  SLOT_ITEM, ac_bonus=1, saving_throw_bonus=1,
         description="+1 AC and +1 to saving throws"),
    Item("Amulet of Health",     SLOT_ITEM, max_hp_bonus=10,
         description="+10 max HP"),
    Item("Gem of Trueseeing",    SLOT_ITEM, darkvision=True, passive_perception_bonus=5,
         description="Darkvision 6 tiles + +5 Passive Perception"),
    Item("Small Mirror",         SLOT_NONE, uses=-1,
         description="Peek around corners without exposing yourself"),
]

# ---- Consumables ------------------------------------------------------------
POTIONS_BY_TIER: Dict[int, Item] = {
    1: Item("Potion of Healing",         SLOT_NONE, uses=1,
            description="Heals 2d4+2 HP (Common)"),
    2: Item("Potion of Greater Healing", SLOT_NONE, uses=1,
            description="Heals 4d4+4 HP (Uncommon)"),
    3: Item("Potion of Superior Healing",SLOT_NONE, uses=1,
            description="Heals 8d4+8 HP (Rare)"),
    4: Item("Potion of Supreme Healing", SLOT_NONE, uses=1,
            description="Heals 10d4+20 HP (Very Rare)"),
}

TRAP_ITEMS = {
    "Caltrops":        Item("Caltrops",        SLOT_NONE, uses=1, description="1d4 dmg, half speed"),
    "Bear Trap":       Item("Bear Trap",       SLOT_NONE, uses=1, description="2d6 dmg, Restrained 2 turns"),
    "Poison Gas Trap": Item("Poison Gas Trap", SLOT_NONE, uses=1, description="3x3 cloud, 1d8 poison, Poisoned"),
    "Blade Poison":    Item("Blade Poison",    SLOT_NONE, uses=1, description="Next 3 hits +1d6 poison, Poisoned"),
}


def use_potion(potion: Item) -> int:
    """Return HP healed by a given potion."""
    n = potion.name
    if "Supreme"  in n: return roll(4, 10) + 20
    if "Superior" in n: return roll(4,  8) +  8
    if "Greater"  in n: return roll(4,  4) +  4
    return roll(4, 2) + 2  # Standard Healing


def _floor_to_tier(floor: int) -> int:
    if floor <= 5:  return 1
    if floor <= 10: return 2
    if floor <= 15: return 3
    return 4


def generate_loot(floor: int) -> Item:
    """
    Return a random loot item appropriate for the given dungeon floor.
    Probability weights: gold-equivalent handled by caller.
    """
    tier = _floor_to_tier(floor)
    roll_d = random.random()

    # 30% chance potion
    if roll_d < 0.30:
        import copy
        return copy.copy(POTIONS_BY_TIER[tier])

    # 20% weapon
    if roll_d < 0.50:
        options = WEAPONS_BY_TIER[min(tier, 4)]
        import copy
        return copy.copy(random.choice(options))

    # 15% armor
    if roll_d < 0.65:
        options = ARMORS_BY_TIER[min(tier, 4)]
        import copy
        return copy.copy(random.choice(options))

    # 20% special equippable item (Gem of Trueseeing available from tier 3)
    if roll_d < 0.85:
        candidates = [i for i in SPECIAL_ITEMS if i.slot == SLOT_ITEM]
        if tier < 3:
            candidates = [i for i in candidates if i.name != "Gem of Trueseeing"]
        if candidates:
            import copy
            return copy.copy(random.choice(candidates))

    # 10% utility (mirror, trap)
    import copy
    util = [TRAP_ITEMS["Caltrops"], TRAP_ITEMS["Blade Poison"],
            SPECIAL_ITEMS[-1]]  # Small Mirror
    return copy.copy(random.choice(util))


def gold_for_floor(floor: int) -> int:
    """Return a random gold amount suitable for the given floor."""
    base = floor * 10
    return random.randint(base, base * 3)


def xp_for_gold(gold: int) -> int:
    return gold  # 1 gp = 1 xp (house rule for simplicity)

# ---------------------------------------------------------------------------
# Monster stat blocks
# ---------------------------------------------------------------------------

@dataclass
class MonsterTemplate:
    name: str
    symbol: str
    color: Tuple[int, int, int]
    hp: int
    ac: int
    attack_bonus: int
    damage_dice: Tuple[int, int]   # (n, sides)
    damage_bonus: int
    xp: int
    darkvision: int = 6
    passive_perception: int = 10
    min_floor: int = 1
    max_floor: int = 20


MONSTER_TEMPLATES: List[MonsterTemplate] = [
    MonsterTemplate("Rat",      "r", (160,  80,  40),  2,  10, 0, (1, 4),  0,   5, min_floor=1,  max_floor=3),
    MonsterTemplate("Goblin",   "g", ( 80, 160,  40), 12,  12, 4, (1, 6),  2,  25, min_floor=1,  max_floor=8),
    MonsterTemplate("Skeleton", "s", (200, 200, 200), 18,  13, 4, (1, 6),  2,  50, min_floor=2,  max_floor=12),
    MonsterTemplate("Zombie",   "z", ( 80, 120,  40), 30,   8, 3, (1, 6),  1,  50, min_floor=3,  max_floor=12),
    MonsterTemplate("Orc",      "O", (100, 160,  60), 25,  13, 5, (2, 6),  3, 100, min_floor=4,  max_floor=14),
    MonsterTemplate("Gnoll",    "n", (180, 140,  80), 22,  15, 5, (2, 4),  3, 100, min_floor=5,  max_floor=16),
    MonsterTemplate("Bugbear",  "B", (120,  80,  40), 40,  14, 6, (2, 8),  4, 200, min_floor=7,  max_floor=18),
    MonsterTemplate("Troll",    "T", ( 60, 160,  60), 84,  15, 7, (2, 6),  4, 700, min_floor=11, max_floor=20),
    MonsterTemplate("Wight",    "W", ( 80, 100, 140), 45,  14, 6, (1, 6),  4, 450, min_floor=9,  max_floor=20),
    MonsterTemplate("Vampire",  "V", (140,  20,  20), 80,  15, 8, (1, 8),  5,1800, min_floor=15, max_floor=20),
    MonsterTemplate("Owlbear",  "*", (120,  80,  20),120,  13, 7, (2, 8),  5,2300, min_floor=20, max_floor=20),
]


def monsters_for_floor(floor: int) -> List[MonsterTemplate]:
    """Return monster templates eligible to spawn on the given floor."""
    return [m for m in MONSTER_TEMPLATES if m.min_floor <= floor <= m.max_floor]

# ---------------------------------------------------------------------------
# Rogue Character Sheet
# ---------------------------------------------------------------------------

@dataclass
class StatusEffect:
    name: str
    duration: int   # turns remaining (-1 = permanent until cured)


@dataclass
class Rogue:
    # Base ability scores (SRD Rogue)
    STR: int = 8
    DEX: int = 17   # +3 mod
    CON: int = 12   # +1 mod
    INT: int = 14
    WIS: int = 12
    CHA: int = 10

    level: int = 1
    xp: int = 0
    gold: int = 0

    # Derived at __post_init__
    max_hp: int = 0
    hp: int = 0
    ac: int = 0
    proficiency: int = 2

    # Equipment slots
    weapon: Optional[Item] = None
    armor:  Optional[Item] = None
    equipped_items: List[Item] = field(default_factory=list)   # max 3

    # Inventory (consumables, extra weapons, etc.)
    inventory: List[Item] = field(default_factory=list)

    # Active statuses
    statuses: List[StatusEffect] = field(default_factory=list)

    # Poison vials applied to weapon (turns left)
    poison_charges: int = 0

    def __post_init__(self):
        self._apply_starting_kit()
        self._recalc()

    def _apply_starting_kit(self):
        """Give the rogue a basic weapon, armor, and a few consumables."""
        if self.weapon is None:
            self.equip(copy.copy(WEAPONS_BY_TIER[1][0]))
        if self.armor is None:
            self.equip(copy.copy(ARMORS_BY_TIER[1][0]))

        has_potion = any(i.name == "Potion of Healing" for i in self.inventory)
        if not has_potion:
            self.inventory.append(copy.copy(POTIONS_BY_TIER[1]))

        has_caltrops = any(i.name == "Caltrops" for i in self.inventory)
        if not has_caltrops:
            self.inventory.append(copy.copy(TRAP_ITEMS["Caltrops"]))

        has_poison = any(i.name == "Blade Poison" for i in self.inventory)
        if not has_poison:
            self.inventory.append(copy.copy(TRAP_ITEMS["Blade Poison"]))

    # ---- Derived stats ------------------------------------------------------

    def _recalc(self):
        """Recompute all derived stats from base scores and equipment."""
        self.proficiency = PROFICIENCY_BONUS[self.level]
        con_mod = modifier(self.CON)
        # Base max HP: 8 + CON at level 1, then 5 + CON per additional level
        self.max_hp = (8 + con_mod) + (self.level - 1) * (5 + con_mod)
        # Equipment bonuses
        for item in self.equipped_items:
            self.max_hp += item.max_hp_bonus
        self.hp = min(self.hp if self.hp > 0 else self.max_hp, self.max_hp)
        self._recalc_ac()

    def _recalc_ac(self):
        dex_mod = modifier(self.DEX)
        base_ac = 10 + dex_mod  # unarmored
        armor_ac = (self.armor.ac_bonus if self.armor else 0)
        if armor_ac:
            # Light armour: AC = armor base + DEX mod
            self.ac = armor_ac + dex_mod
        else:
            self.ac = base_ac
        # Item AC bonuses (ring, cloak)
        for item in self.equipped_items:
            self.ac += item.ac_bonus

    @property
    def passive_perception(self) -> int:
        pp = 10 + modifier(self.WIS) + self.proficiency
        for item in self.equipped_items:
            pp += item.passive_perception_bonus
        return pp

    @property
    def stealth_bonus(self) -> int:
        bonus = modifier(self.DEX) + self.proficiency
        for item in self.equipped_items:
            bonus += item.skill_bonus.get("Stealth", 0)
        return bonus

    @property
    def thieves_tools_bonus(self) -> int:
        bonus = modifier(self.DEX) + self.proficiency
        for item in self.equipped_items:
            bonus += item.skill_bonus.get("Thieves' Tools", 0)
        return bonus

    @property
    def has_darkvision(self) -> bool:
        return any(i.darkvision for i in self.equipped_items)

    @property
    def darkvision_range(self) -> int:
        return 6 if self.has_darkvision else 0

    @property
    def saving_throw_bonus(self) -> int:
        bonus = 0
        for item in self.equipped_items:
            bonus += item.saving_throw_bonus
        return bonus

    # ---- Attack helpers -----------------------------------------------------

    def attack_roll(self, advantage: bool = False, disadvantage: bool = False) -> int:
        weapon_bonus = self.weapon.to_hit_bonus if self.weapon else 0
        return d20(advantage, disadvantage) + modifier(self.DEX) + self.proficiency + weapon_bonus

    def sneak_attack_damage(self) -> int:
        num_dice = sneak_attack_dice(self.level)
        return roll(6, num_dice)

    def weapon_damage(self) -> int:
        """Base weapon damage (without sneak attack)."""
        if self.weapon is None:
            # Unarmed
            return 1 + modifier(self.STR)
        name = self.weapon.name.lower()
        dmg_bonus = self.weapon.damage_bonus + modifier(self.DEX)
        if "shortbow" in name:
            base = roll(6)
        else:
            base = roll(4)  # dagger
        extra = 0
        if self.weapon.extra_damage_dice:
            extra = roll(self.weapon.extra_damage_sides, self.weapon.extra_damage_dice)
        return max(1, base + dmg_bonus + extra)

    def total_attack_damage(self) -> Tuple[int, int, int]:
        """Return (weapon_dmg, sneak_dmg, poison_dmg)."""
        w = self.weapon_damage()
        s = self.sneak_attack_damage()
        p = 0
        if self.poison_charges > 0:
            p = roll(6)  # +1d6 poison
            self.poison_charges -= 1
        return w, s, p

    # ---- Level-up -----------------------------------------------------------

    def gain_xp(self, amount: int) -> bool:
        """Add XP. Returns True if the rogue leveled up."""
        self.xp += amount
        new_level = 1
        for i, threshold in enumerate(XP_THRESHOLDS):
            if self.xp >= threshold:
                new_level = i + 1
        if new_level > self.level:
            old_hp = self.max_hp
            self.level = min(new_level, 20)
            self._recalc()
            # Give full new HP on level-up
            self.hp += (self.max_hp - old_hp)
            self.hp = min(self.hp, self.max_hp)
            return True
        return False

    # ---- Equipment management -----------------------------------------------

    def equip(self, item: Item) -> Optional[str]:
        """
        Try to equip an item. Returns None on success or an error string.
        Removes the item from inventory if present.
        """
        if item.slot == SLOT_WEAPON:
            if self.weapon:
                self.inventory.append(self.weapon)
            self.weapon = item
        elif item.slot == SLOT_ARMOR:
            if self.armor:
                self.inventory.append(self.armor)
            self.armor = item
        elif item.slot == SLOT_ITEM:
            if len(self.equipped_items) >= 3:
                return "No free item slots (max 3)."
            self.equipped_items.append(item)
        else:
            return f"{item.name} is a consumable and cannot be equipped."

        if item in self.inventory:
            self.inventory.remove(item)
        self._recalc()
        return None

    def unequip_item(self, item: Item):
        """Move an equipped item back to inventory."""
        if item == self.weapon:
            self.weapon = None
        elif item == self.armor:
            self.armor = None
        elif item in self.equipped_items:
            self.equipped_items.remove(item)
        if item not in self.inventory:
            self.inventory.append(item)
        self._recalc()

    def add_to_inventory(self, item: Item):
        self.inventory.append(item)

    # ---- Status conditions --------------------------------------------------

    def has_status(self, name: str) -> bool:
        return any(s.name == name for s in self.statuses)

    def apply_status(self, name: str, duration: int):
        # Refresh duration if already present
        for s in self.statuses:
            if s.name == name:
                s.duration = max(s.duration, duration)
                return
        self.statuses.append(StatusEffect(name, duration))

    def tick_statuses(self):
        kept = []
        for s in self.statuses:
            if s.duration < 0:
                kept.append(s)
                continue
            s.duration -= 1
            if s.duration > 0:
                kept.append(s)
        self.statuses = kept

    # ---- Healing ------------------------------------------------------------

    def heal(self, amount: int):
        self.hp = min(self.hp + amount, self.max_hp)

    # ---- Stealth check ------------------------------------------------------

    def stealth_check(self, advantage: bool = False) -> int:
        if self.has_status("Poisoned"):
            advantage = False
        return d20(advantage=advantage) + self.stealth_bonus
