import importlib.util
import os
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
        "persister_valid_exactly_once_pg", ROOT / "services/persister-valid/main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PERSISTER_VALID = load_persister_valid()


GROUP_ID = "test-group"
TOPIC = "simulpix.transactions.validated"
PARTITION = 0


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params=None):
        sql = " ".join(str(query).split())
        if "create table if not exists persister_offsets" in sql:
            self.connection.offsets_table_created = True
            return
        if "select next_offset from persister_offsets" in sql:
            group_id, topic, partition = params
            next_offset = self.connection.offsets.get((group_id, topic, partition))
            self._row = (next_offset,) if next_offset is not None else None
            return
        if "insert into validated_transactions" in sql:
            message = params
            self.connection.payments[message["transaction_id"]] = dict(message)
            return
        if "insert into persister_offsets" in sql:
            group_id, topic, partition, next_offset = params
            current = self.connection.offsets.get((group_id, topic, partition))
            if current is None or next_offset > current:
                self.connection.offsets[(group_id, topic, partition)] = next_offset
            return
        if "select count(*) from validated_transactions" in sql:
            self._row = (len(self.connection.payments),)
            return
        raise AssertionError(f"Requête inattendue : {sql}")

    def fetchone(self):
        return self._row

    def commit(self):
        self.connection.commit()


class FakeConnection:
    def __init__(self):
        self.offsets = {}
        self.payments = {}
        self.offsets_table_created = False
        self.commit_calls = 0
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commit_calls += 1

    def close(self):
        self.closed = True


class ExactlyOncePgTest(unittest.TestCase):
    def setUp(self):
        self.connection = FakeConnection()

    def test_premier_message_offset_5_est_ecrit_et_next_offset_vaut_6(self):
        message = {"transaction_id": "tx-1"}
        applied = PERSISTER_VALID.apply_exactly_once(self.connection, message, GROUP_ID, TOPIC, PARTITION, 5)
        self.assertTrue(applied)
        self.assertIn("tx-1", self.connection.payments)
        self.assertEqual(self.connection.offsets[(GROUP_ID, TOPIC, PARTITION)], 6)

    def test_meme_message_relui_renvoie_false_et_rien_de_plus_est_ecrit(self):
        message = {"transaction_id": "tx-1"}
        PERSISTER_VALID.apply_exactly_once(self.connection, message, GROUP_ID, TOPIC, PARTITION, 5)
        applied = PERSISTER_VALID.apply_exactly_once(self.connection, message, GROUP_ID, TOPIC, PARTITION, 5)
        self.assertFalse(applied)
        self.assertEqual(len(self.connection.payments), 1)
        self.assertEqual(self.connection.offsets[(GROUP_ID, TOPIC, PARTITION)], 6)

    def test_message_suivant_offset_6_est_ecrit_et_next_offset_vaut_7(self):
        PERSISTER_VALID.apply_exactly_once(self.connection, {"transaction_id": "tx-1"}, GROUP_ID, TOPIC, PARTITION, 5)
        applied = PERSISTER_VALID.apply_exactly_once(self.connection, {"transaction_id": "tx-2"}, GROUP_ID, TOPIC, PARTITION, 6)
        self.assertTrue(applied)
        self.assertEqual(len(self.connection.payments), 2)
        self.assertEqual(self.connection.offsets[(GROUP_ID, TOPIC, PARTITION)], 7)

    def test_offset_plus_petit_ne_fait_pas_reculer_next_offset(self):
        PERSISTER_VALID.apply_exactly_once(self.connection, {"transaction_id": "tx-1"}, GROUP_ID, TOPIC, PARTITION, 5)
        PERSISTER_VALID.apply_exactly_once(self.connection, {"transaction_id": "tx-2"}, GROUP_ID, TOPIC, PARTITION, 6)
        applied = PERSISTER_VALID.apply_exactly_once(self.connection, {"transaction_id": "tx-3"}, GROUP_ID, TOPIC, PARTITION, 3)
        self.assertFalse(applied)
        self.assertEqual(self.connection.offsets[(GROUP_ID, TOPIC, PARTITION)], 7)
        self.assertEqual(len(self.connection.payments), 2)

    def test_ensure_offsets_table_cree_la_table_et_commit(self):
        PERSISTER_VALID.ensure_offsets_table(self.connection)
        self.assertTrue(self.connection.offsets_table_created)
        self.assertEqual(self.connection.commit_calls, 1)

    def test_get_consumer_settings_exactly_once_pg_renvoie_commit_strategy_after(self):
        env_key = "SIMULPIX_KAFKA_CONSUMER_SEMANTICS"
        old_value = os.environ.get(env_key)
        try:
            os.environ[env_key] = "exactly_once_pg"
            settings = PERSISTER_VALID.get_consumer_settings()
        finally:
            if old_value is None:
                os.environ.pop(env_key, None)
            else:
                os.environ[env_key] = old_value
        self.assertEqual(settings["semantics"], "exactly_once_pg")
        self.assertEqual(settings["commit_strategy"], "after")
        self.assertFalse(settings["auto_commit"])
        self.assertEqual(settings["commit_batch_size"], 1)


if __name__ == "__main__":
    unittest.main()
