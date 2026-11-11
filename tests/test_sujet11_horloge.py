import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sujet11_horloge", ROOT / "scripts/sujet11/horloge.py")
horloge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(horloge)


class HorlogeTest(unittest.TestCase):
    def test_ancien_essai_sans_mesure(self):
        self.assertEqual(horloge.decalage({}), 0.0)
        self.assertIsNone(horloge.derive({}))

    def test_moyenne_du_debut_et_de_la_fin(self):
        meta = {"decalage_debut_s": -423.0, "decalage_fin_s": -422.8}
        self.assertAlmostEqual(horloge.decalage(meta), -422.9)
        self.assertAlmostEqual(horloge.derive(meta), 0.2)

    def test_derive_au_dela_du_seuil(self):
        # resynchronisation pendant l'essai, comme le 9 novembre
        self.assertGreater(horloge.derive({"decalage_debut_s": -423.0, "decalage_fin_s": 0.1}), horloge.DERIVE_MAX_S)


if __name__ == "__main__":
    unittest.main()
