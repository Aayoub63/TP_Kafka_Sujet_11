import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_oracle():
    spec = importlib.util.spec_from_file_location("sujet11_oracle", ROOT / "scripts/sujet11/oracle.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


oracle = load_oracle()


class ClassementTest(unittest.TestCase):
    def setUp(self):
        self.topic = [
            {"transaction_id": "tx-1", "amount": 10.5},
            {"transaction_id": "tx-2", "amount": 20.0},
            {"transaction_id": "tx-3", "amount": 30.0},
            {"transaction_id": "tx-4", "amount": 40.0},
            {"transaction_id": "tx-5", "amount": 50.0},
            # doublon dans le topic (producteur at-least-once) : une seule identité attendue
            {"transaction_id": "tx-1", "amount": 10.5},
        ]
        self.valides = [
            {"transaction_id": "tx-1", "amount": "10.50"},   # numeric PostgreSQL en texte
            {"transaction_id": "tx-2", "amount": "21.00"},   # montant différent
            {"transaction_id": "tx-9", "amount": "1.00"},    # pas dans le topic
        ]
        self.rejetes = [
            {"transaction_id": "tx-3", "rejection_type": "TECHNICAL_TIMEOUT", "rejection_reason": "processing_timeout"},
            {"transaction_id": "tx-4", "rejection_type": "BUSINESS_VALIDATION", "rejection_reason": "amount_must_be_positive"},
        ]

    def test_chaque_identite_recoit_une_seule_classe(self):
        r = oracle.classer(self.topic, self.valides, self.rejetes)
        self.assertEqual(r["attendus"], 5)
        self.assertEqual(r["messages_topic"], 6)
        self.assertEqual(r["classes"], {
            "present": 1, "valeur_fausse": 1, "rejet_delai": 1, "rejet_metier": 1, "perdu": 1,
        })
        self.assertEqual(r["exemples"]["perdu"], ["tx-5"])

    def test_ligne_en_base_sans_message_est_signalee(self):
        r = oracle.classer(self.topic, self.valides, self.rejetes)
        self.assertEqual(r["lignes_inattendues"], 1)
        self.assertEqual(r["exemples"]["lignes_inattendues"], ["tx-9"])

    def test_aucun_ecart_quand_tout_est_present(self):
        valides = [{"transaction_id": f"tx-{i}", "amount": f"{i * 10}.00"} for i in range(2, 6)]
        valides.append({"transaction_id": "tx-1", "amount": "10.50"})
        r = oracle.classer(self.topic, valides, [])
        self.assertEqual(r["classes"]["present"], 5)
        self.assertEqual(r["lignes_inattendues"], 0)


class DoublonsTest(unittest.TestCase):
    def test_tentatives_en_trop_comptees_par_identite(self):
        audit = [{"transaction_id": t, "t": 0.0} for t in ("tx-1", "tx-1", "tx-1", "tx-2", "tx-3", "tx-3")]
        valides = [{"transaction_id": t, "amount": "1.00"} for t in ("tx-1", "tx-2", "tx-3")]
        r = oracle.doublons_absorbes(audit, valides)
        self.assertEqual(r["tentatives"], 6)
        self.assertEqual(r["doublons_absorbes"], 3)
        self.assertEqual(r["exemples"][0], "tx-1")

    def test_audit_absent(self):
        r = oracle.doublons_absorbes([], [])
        self.assertFalse(r["audit_actif"])
        self.assertEqual(r["doublons_absorbes"], 0)


if __name__ == "__main__":
    unittest.main()
