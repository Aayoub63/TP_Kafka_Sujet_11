import importlib.util
import signal
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_persister_valid():
    if "confluent_kafka" not in sys.modules:
        fake_kafka = types.ModuleType("confluent_kafka")
        fake_kafka.Consumer = object
        fake_kafka.Producer = object
        fake_kafka.TopicPartition = object
        sys.modules["confluent_kafka"] = fake_kafka
    if "psycopg" not in sys.modules:
        fake_psycopg = types.ModuleType("psycopg")
        fake_psycopg.Connection = object
        sys.modules["psycopg"] = fake_psycopg
    spec = importlib.util.spec_from_file_location(
        "persister_valid_arret_propre", ROOT / "services/persister-valid/main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PERSISTER_VALID = load_persister_valid()


class FakeConsumer:
    def __init__(self):
        self.calls = []

    def commit(self, message=None, asynchronous=True):
        self.calls.append(("commit", message, asynchronous))

    def close(self):
        self.calls.append(("close",))


class FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class ArretPropreTest(unittest.TestCase):
    def setUp(self):
        PERSISTER_VALID.STOP_REQUESTED.clear()

    def test_sigterm_demande_l_arret_sans_quitter_tout_de_suite(self):
        PERSISTER_VALID.request_stop(signal.SIGTERM, None)
        self.assertTrue(PERSISTER_VALID.STOP_REQUESTED.is_set())

    def test_offset_en_attente_valide_avant_de_quitter_le_groupe(self):
        consumer, connection = FakeConsumer(), FakeConnection()
        PERSISTER_VALID.shutdown_gracefully(consumer, connection, pending_commit_record="record-42")
        self.assertEqual(consumer.calls, [("commit", "record-42", False), ("close",)])
        self.assertTrue(connection.closed)

    def test_sans_offset_en_attente_on_quitte_seulement_le_groupe(self):
        consumer, connection = FakeConsumer(), FakeConnection()
        PERSISTER_VALID.shutdown_gracefully(consumer, connection, pending_commit_record=None)
        self.assertEqual(consumer.calls, [("close",)])
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
