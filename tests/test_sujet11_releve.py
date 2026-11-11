import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/sujet11"))


def charger(nom):
    spec = importlib.util.spec_from_file_location(f"sujet11_{nom}", ROOT / f"scripts/sujet11/{nom}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mesure = charger("mesure")
collecte = charger("collecte")

GROUPE = "simulpix-persister-valid-1"
DESCRIBE = f"""
GROUP TOPIC PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG CONSUMER-ID HOST CLIENT-ID
{GROUPE} simulpix.transactions.validated 0 12 15 3 rdkafka-aaa /172.19.0.14 rdkafka
{GROUPE} simulpix.transactions.validated 1 - 0 - rdkafka-bbb /172.19.0.15 rdkafka
{GROUPE} simulpix.transactions.validated 2 7 7 0 - - -
"""


class DescribeTest(unittest.TestCase):
    def test_proprietaire_et_offset_par_partition(self):
        r = mesure.lire_describe(DESCRIBE, GROUPE)
        self.assertEqual(r["parts"], {"0": ["rdkafka-aaa", 12], "1": ["rdkafka-bbb", None], "2": ["-", 7]})

    def test_totaux(self):
        r = mesure.lire_describe(DESCRIBE, GROUPE)
        self.assertEqual((r["lag"], r["membres"], r["partitions"]), (3, 2, 3))

    def test_en_tete_ignore(self):
        self.assertEqual(mesure.lire_describe("GROUP TOPIC PARTITION\n", GROUPE)["partitions"], 0)


class MessageTest(unittest.TestCase):
    def test_avec_position(self):
        m = collecte.lire_message('Partition:4\tOffset:1\t{"transaction_id": "tx-4", "amount": 9}')
        self.assertEqual(m, {"transaction_id": "tx-4", "amount": 9, "partition": 4, "offset": 1})

    def test_sans_position(self):
        m = collecte.lire_message('{"transaction_id": "tx-4", "amount": 9}')
        self.assertEqual((m["partition"], m["offset"]), (None, None))

    def test_ligne_sans_json(self):
        self.assertIsNone(collecte.lire_message("Processed a total of 2 messages"))
        self.assertIsNone(collecte.lire_message("Partition:1\tOffset:2\t{pas du json"))


if __name__ == "__main__":
    unittest.main()
