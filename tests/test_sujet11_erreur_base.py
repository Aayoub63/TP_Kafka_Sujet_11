"""Sujet 11 : que devient un paiement si l'écriture PostgreSQL échoue ?

Test unitaire contrôlé de la boucle de persister-valid (services/persister-valid/main.py),
avec un faux consommateur Kafka et une fausse base. Ce n'est PAS un essai réel :
il montre l'ordre des opérations dans le code, pas le comportement de Kafka.

  - at-most-once : la lecture est validée (commit) AVANT l'écriture. Si l'écriture
    échoue, l'offset est déjà avancé : Kafka ne redonnera pas ce message. Paiement perdu.
  - at-least-once : rien n'est validé avant l'écriture. Après l'erreur, le service se
    reconnecte et Kafka redonne le message depuis le dernier offset validé : il est retraité.
"""
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def charger():
    if "confluent_kafka" not in sys.modules:
        k = types.ModuleType("confluent_kafka")
        k.Consumer = k.Producer = k.TopicPartition = object
        sys.modules["confluent_kafka"] = k
    if "psycopg" not in sys.modules:
        pg = types.ModuleType("psycopg")
        pg.Connection = object
        sys.modules["psycopg"] = pg
    spec = importlib.util.spec_from_file_location("persister_valid_erreur_base", ROOT / "services/persister-valid/main.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


PV = charger()


class Message:
    def __init__(self, offset):
        self._offset = offset

    def error(self):
        return None

    def value(self):
        return b'{"transaction_id": "tx-00000001", "amount": 10.0}'

    def topic(self):
        return "simulpix.transactions.validated"

    def partition(self):
        return 0

    def offset(self):
        return self._offset


class Consommateur:
    """Rejoue un journal Kafka : redonne les messages à partir du dernier offset validé."""

    def __init__(self, journal, valide, nom, evenements):
        self.journal, self.valide, self.nom, self.ev = journal, valide, nom, evenements
        self.position = valide["offset"]

    def poll(self, _):
        if self.position < len(self.journal):
            m = Message(self.position)
            self.position += 1
            self.ev.append((self.nom, "lu", m.offset()))
            return m
        PV.STOP_REQUESTED.set()
        return None

    def commit(self, message=None, asynchronous=True):
        self.valide["offset"] = message.offset() + 1
        self.ev.append((self.nom, "commit", message.offset()))

    def close(self):
        self.ev.append((self.nom, "close"))


class Base:
    def close(self):
        pass


def executer(semantique, echecs=1):
    """Lance main() avec une écriture qui échoue `echecs` fois. Renvoie (événements, écrits)."""
    evenements, ecrits, valide = [], [], {"offset": 0}
    consommateurs = iter(Consommateur([1], valide, f"instance {i}", evenements) for i in range(1, 4))
    reste = {"n": echecs}

    def inserer(connection, message):
        if reste["n"]:
            reste["n"] -= 1
            evenements.append(("base", "échec écriture"))
            raise RuntimeError("PostgreSQL indisponible")
        ecrits.append(message["transaction_id"])
        evenements.append(("base", "écrit"))
        return len(ecrits)

    PV.STOP_REQUESTED.clear()
    with mock.patch.dict(os.environ, {"SIMULPIX_KAFKA_CONSUMER_SEMANTICS": semantique}), \
            mock.patch.object(PV, "serve_http", lambda: None), \
            mock.patch.object(PV, "wait_for_dependencies", lambda *a: (Base(), next(consommateurs))), \
            mock.patch.object(PV, "ensure_validated_schema", lambda c: None), \
            mock.patch.object(PV, "ensure_offsets_table", lambda c: None), \
            mock.patch.object(PV, "load_existing_persisted_count", lambda c: 0), \
            mock.patch.object(PV, "insert_validated", inserer), \
            mock.patch.object(PV.time, "sleep", lambda s: None), \
            mock.patch.object(PV.signal, "signal", lambda *a: None):
        PV.main()
    return evenements, ecrits


class ErreurBaseTest(unittest.TestCase):
    def test_at_most_once_valide_la_lecture_avant_l_echec_donc_perte(self):
        ev, ecrits = executer("at_most_once")
        self.assertEqual(ev[:3], [("instance 1", "lu", 0), ("instance 1", "commit", 0), ("base", "échec écriture")])
        # la nouvelle connexion repart après l'offset validé : le message n'est jamais relu
        self.assertNotIn(("instance 2", "lu", 0), ev)
        self.assertEqual(ecrits, [])

    def test_at_least_once_ne_valide_rien_avant_l_echec_donc_relecture(self):
        ev, ecrits = executer("at_least_once")
        self.assertEqual(ev[:2], [("instance 1", "lu", 0), ("base", "échec écriture")])
        self.assertNotIn(("instance 1", "commit", 0), ev)
        # la nouvelle connexion relit le message et l'écrit, puis valide la lecture
        self.assertIn(("instance 2", "lu", 0), ev)
        self.assertEqual(ecrits, ["tx-00000001"])
        self.assertIn(("instance 2", "commit", 0), ev)


if __name__ == "__main__":
    unittest.main()
