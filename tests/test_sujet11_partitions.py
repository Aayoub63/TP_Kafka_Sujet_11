import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sujet11_partitions", ROOT / "scripts/sujet11/partitions.py")
partitions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(partitions)

T0 = 100.0


def releve(t, **parts):
    return {"t": t, "parts": {p[1:]: v for p, v in parts.items()}}


# Partition 0 : A lit jusqu'à t0, groupe vide 2 s, puis B reprend à l'offset 5.
LAG = [
    releve(98, p0=["A", 4], p1=["A", 2]),
    releve(99, p0=["A", 5], p1=["A", 2]),
    releve(100, p0=["-", 5], p1=["-", 2]),
    releve(101, p0=["-", 5], p1=["-", 2]),
    releve(102, p0=["B", 5], p1=["B", 2]),
    releve(103, p0=["B", 7], p1=["B", 2]),
]
TOPIC = [{"transaction_id": f"tx-{o}", "partition": 0, "offset": o} for o in range(8)] + [
    {"transaction_id": "tx-p1-0", "partition": 1, "offset": 0},
    {"transaction_id": "tx-p1-1", "partition": 1, "offset": 1},
]


class PassationsTest(unittest.TestCase):
    def test_instances_dans_l_ordre(self):
        self.assertEqual(partitions.nommer_instances(LAG), {"A": "instance 1", "B": "instance 2"})

    def test_une_passation_par_partition(self):
        p = partitions.passations(LAG, T0)
        self.assertEqual([(x["partition"], x["avant"], x["apres"]) for x in p], [(0, "A", "B"), (1, "A", "B")])
        self.assertEqual(p[0]["sans_proprietaire_s"], 2.0)
        self.assertEqual(p[0]["offset_reprise"], 5)
        self.assertTrue(p[0]["sur"])

    def test_partition_absente_sans_proprietaire(self):
        # Kafka n'affiche pas une partition sans propriétaire ni offset validé
        lag = [releve(99, p2=["A", None]), releve(100), releve(101, p2=["B", None])]
        lag[1]["parts"] = {"9": ["-", 0]}
        p = partitions.passations(lag, T0)[0]
        self.assertEqual((p["sans_proprietaire_s"], p["offset_reprise"]), (1.0, None))

    def test_passation_directe_pas_sure(self):
        lag = [releve(99, p0=["A", 4]), releve(101, p0=["B", 9])]
        p = partitions.passations(lag, T0)[0]
        self.assertEqual((p["offset_reprise"], p["sur"]), (4, False))

    def test_changement_avant_t0_ignore(self):
        self.assertEqual(partitions.passations(LAG, 200.0), [])


class MessageEnCoursTest(unittest.TestCase):
    def test_relecture_at_least_once(self):
        # tx-5 écrit par A avant la passation, puis relu par B
        audit = [{"transaction_id": f"tx-{o}", "t": 90 + o} for o in range(6)] + [
            {"transaction_id": "tx-5", "t": 102.5}]
        p = partitions.analyser(LAG, TOPIC, audit, T0)["passations"][0]
        self.assertEqual(p["message_repris"], "tx-5")
        self.assertTrue(p["deja_ecrit_avant"])
        self.assertEqual(p["ecritures_du_message_repris"], 2)
        self.assertTrue(p["precedent_ecrit"])
        self.assertIn("doublon absorbé", partitions.resume({"passations": [p]})[0])

    def test_update_ne_compte_pas(self):
        audit = [{"transaction_id": f"tx-{o}", "t": 90 + o, "kind": "INSERT"} for o in range(6)] + [
            {"transaction_id": "tx-5", "t": 102.5, "kind": "INSERT"},
            {"transaction_id": "tx-5", "t": 102.5, "kind": "UPDATE"}]
        p = partitions.analyser(LAG, TOPIC, audit, T0)["passations"][0]
        self.assertEqual(p["ecritures_du_message_repris"], 2)

    def test_perte_at_most_once(self):
        # tx-4 validé (offset 5) mais jamais écrit
        audit = [{"transaction_id": f"tx-{o}", "t": 90 + o} for o in range(4)]
        p = partitions.analyser(LAG, TOPIC, audit, T0)["passations"][0]
        self.assertFalse(p["deja_ecrit_avant"])
        self.assertFalse(p["precedent_ecrit"])
        self.assertIn("ATTENTION tx-4 jamais écrit", partitions.resume({"passations": [p]})[0])

    def test_nouvelle_instance_ecrit_avant_le_releve(self):
        # crash du 9 novembre : la nouvelle instance écrit 0,26 s avant le relevé qui la voit
        audit = [{"transaction_id": f"tx-{o}", "t": 90 + o} for o in range(5)] + [
            {"transaction_id": "tx-5", "t": 101.8}]
        p = partitions.analyser(LAG, TOPIC, audit, T0)["passations"][0]
        self.assertFalse(p["deja_ecrit_avant"])
        self.assertIn("pas encore écrit", partitions.resume({"passations": [p]})[0])

    def test_ecrit_une_seule_fois_pas_relu(self):
        audit = [{"transaction_id": f"tx-{o}", "t": 90 + o} for o in range(6)]
        p = partitions.analyser(LAG, TOPIC, audit, T0)["passations"][0]
        self.assertIn("pas relu", partitions.resume({"passations": [p]})[0])

    def test_exactly_once_pg_ecarte(self):
        audit = [{"transaction_id": f"tx-{o}", "t": 90 + o} for o in range(6)]
        p = partitions.analyser(LAG, TOPIC, audit, T0)["passations"][0]
        self.assertIn("écarté sans réécriture", partitions.resume({"passations": [p]}, "exactly_once_pg")[0])

    def test_rien_en_attente(self):
        # partition 1 : offset 2 au-delà du dernier message
        p = partitions.analyser(LAG, TOPIC, [], T0)["passations"][1]
        self.assertIsNone(p["message_repris"])
        self.assertIn("rien en attente", partitions.resume({"passations": [p]})[0])

    def test_noms_lisibles(self):
        a = partitions.analyser(LAG, TOPIC, [], T0)
        self.assertEqual((a["passations"][0]["avant"], a["passations"][0]["apres"]), ("instance 1", "instance 2"))
        self.assertEqual(a["instances"], {"instance 1": "A", "instance 2": "B"})


if __name__ == "__main__":
    unittest.main()
