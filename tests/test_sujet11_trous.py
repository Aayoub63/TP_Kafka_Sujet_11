import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_trous():
    spec = importlib.util.spec_from_file_location("sujet11_trous", ROOT / "scripts/sujet11/trous.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


trous = load_trous()


class NumeroTest(unittest.TestCase):
    def test_format_valide(self):
        self.assertEqual(trous.numero("tx-00000042"), 42)

    def test_format_invalide(self):
        self.assertIsNone(trous.numero("abc"))


class RechercheTest(unittest.TestCase):
    def test_un_trou_sur_cinq_paiements(self):
        # 5 paiements : 3 validés, 1 rejeté, tx-00000004 absent des deux tables
        valides = [{"transaction_id": "tx-00000001"},
                   {"transaction_id": "tx-00000002"},
                   {"transaction_id": "tx-00000003"}]
        rejetes = [{"transaction_id": "tx-00000005"}]
        r = trous.chercher(valides, rejetes, 5)
        self.assertEqual(r["attendus"], 5)
        self.assertEqual(r["en_base"], 4)
        self.assertEqual(r["trous"], 1)
        self.assertEqual(r["exemples"], ["tx-00000004"])

    def test_aucun_trou_quand_tout_est_present(self):
        valides = [{"transaction_id": "tx-%08d" % i} for i in range(1, 6)]
        rejetes = [{"transaction_id": "tx-00000003"}]
        r = trous.chercher(valides, rejetes, 5)
        self.assertEqual(r["trous"], 0)
        self.assertEqual(r["exemples"], [])

    def test_identifiant_hors_plage(self):
        r = trous.chercher([{"transaction_id": "tx-00000099"}], [], 5)
        self.assertIn("tx-00000099", r["hors_plage"])
        self.assertEqual(r["en_base"], 0)
        self.assertEqual(r["trous"], 5)

    def test_doublon_compte_une_seule_fois(self):
        valides = [{"transaction_id": "tx-00000001"}, {"transaction_id": "tx-00000001"}]
        rejetes = [{"transaction_id": "tx-00000001"}]
        r = trous.chercher(valides, rejetes, 5)
        self.assertEqual(r["en_base"], 1)


if __name__ == "__main__":
    unittest.main()
