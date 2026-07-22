import unittest
import random
from dungeon import Monster, generate_floor, DungeonFloor
from rules import MONSTER_TEMPLATES

class TestMonsterAI(unittest.TestCase):
    def test_monster_initialization(self):
        floor = generate_floor(1, seed=42)
        self.assertTrue(len(floor.monsters) > 0)
        for m in floor.monsters:
            self.assertIn(m.behavior, ["Guard", "Patrol", "Sleep", "Wander"])
            self.assertEqual(m.behavior_turns_left, 20)
            self.assertIn(m.look_dir, [(-1, 0), (1, 0), (0, -1), (0, 1)])
            if m.behavior == "Patrol":
                self.assertIsNotNone(m.patrol_points)
                self.assertIsNotNone(m.patrol_target)
                self.assertIn(m.patrol_target, m.patrol_points)

    def test_sleep_perception_penalty(self):
        template = MONSTER_TEMPLATES[0] # Rat
        m = Monster(template=template, row=10, col=10, hp=10, max_hp=10)
        m.behavior = "Sleep"
        m.look_dir = (0, 1) # East
        
        pp = m.template.passive_perception
        if m.behavior == "Sleep":
            pp -= 5
        
        pr, pc = 10, 15
        mr, mc = m.row, m.col
        v_r, v_c = pr - mr, pc - mc
        dot = v_r * m.look_dir[0] + v_c * m.look_dir[1]
        if dot > 0:
            pp += 5
        elif dot < 0:
            pp -= 5
            
        self.assertEqual(pp, 10)

    def test_looking_away_perception_penalty(self):
        template = MONSTER_TEMPLATES[0] # Rat
        m = Monster(template=template, row=10, col=10, hp=10, max_hp=10)
        m.behavior = "Guard"
        m.look_dir = (-1, 0) # North
        
        pp = m.template.passive_perception
        if m.behavior == "Sleep":
            pp -= 5
        
        pr, pc = 15, 10
        mr, mc = m.row, m.col
        v_r, v_c = pr - mr, pc - mc
        dot = v_r * m.look_dir[0] + v_c * m.look_dir[1]
        if dot > 0:
            pp += 5
        elif dot < 0:
            pp -= 5
            
        self.assertEqual(pp, 5)

if __name__ == "__main__":
    unittest.main()
