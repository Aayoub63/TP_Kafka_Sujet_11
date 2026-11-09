import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_pause():
    spec = importlib.util.spec_from_file_location("sujet11_pause", ROOT / "scripts/sujet11/pause.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pause = load_pause()


def audit(instants):
    return [{"transaction_id": f"tx-{i}", "t": t} for i, t in enumerate(instants)]


class PauseTest(unittest.TestCase):
    def test_pause_pendant_l_operation_et_trou_normal_avant(self):
        # une écriture par seconde, puis 30 s sans écriture après t0 = 100
        instants = [float(t) for t in range(80, 103)] + [133.0, 134.0, 135.0]
        r = pause.mesurer(audit(instants), t0=100.0, fin=150.0, debut_reference=85.0)
        self.assertEqual(r["trou_normal_s"], 1.0)
        self.assertEqual(r["pause_s"], 31.0)
        self.assertTrue(r["reprise"])
        self.assertEqual(r["derniere_ecriture_avant_s"], 2.0)
        self.assertEqual(r["premiere_ecriture_apres_s"], 33.0)

    def test_trou_avant_t0_ignore_pour_la_pause(self):
        # un grand trou avant la fenêtre ne doit pas être pris pour la pause
        instants = [10.0, 60.0] + [float(t) for t in range(61, 120)]
        r = pause.mesurer(audit(instants), t0=100.0, fin=120.0, debut_reference=61.0)
        self.assertEqual(r["pause_s"], 1.0)

    def test_service_qui_ne_reprend_pas(self):
        instants = [float(t) for t in range(90, 102)]
        r = pause.mesurer(audit(instants), t0=100.0, fin=160.0, debut_reference=90.0)
        self.assertEqual(r["pause_s"], 59.0)
        self.assertFalse(r["reprise"])
        self.assertIsNone(r["premiere_ecriture_apres_s"])

    def test_aucune_ecriture(self):
        r = pause.mesurer([], t0=100.0, fin=160.0, debut_reference=90.0)
        self.assertIsNone(r["pause_s"])
        self.assertIsNone(r["trou_normal_s"])


if __name__ == "__main__":
    unittest.main()
