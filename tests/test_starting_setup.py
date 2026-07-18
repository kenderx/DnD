import unittest

from dungeon_rogue import GameState


class TestStartingSetup(unittest.TestCase):
    def test_starter_gear_is_available(self):
        gs = GameState()

        self.assertIsNotNone(gs.rogue.weapon)
        self.assertEqual(gs.rogue.weapon.name, "Dagger")
        self.assertIsNotNone(gs.rogue.armor)
        self.assertEqual(gs.rogue.armor.name, "Leather Armor")
        self.assertTrue(any(i.name == "Potion of Healing" for i in gs.rogue.inventory))
        self.assertTrue(any(i.name == "Caltrops" for i in gs.rogue.inventory))


if __name__ == "__main__":
    unittest.main()
