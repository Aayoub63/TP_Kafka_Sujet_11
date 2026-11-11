"""Sujet 11 : décision finale (bilan.decider).

P0-1 : un paiement validé retrouvé seulement dans les rejets ne doit jamais
donner REUSSITE, mais un rejet métier légitime n'est pas une perte.
P1-1 : une mesure invalide ne doit jamais effacer une anomalie démontrée, et
plusieurs anomalies doivent apparaître ensemble.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/sujet11"))


def charger(nom):
    spec = importlib.util.spec_from_file_location(f"sujet11_{nom}_d", ROOT / f"scripts/sujet11/{nom}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bilan = charger("bilan")
oracle = charger("oracle")

META = {"semantique": "at_least_once", "borne_s": 60, "drainage_max_s": 120, "decalage_debut_s": 0.0,
        "decalage_fin_s": 0.0, "flux_termine": True, "semantique_effective": "at_least_once"}
HORLOGE_KO = dict(META, decalage_debut_s=0.0, decalage_fin_s=5.0)
AUDIT = [{"transaction_id": "tx-00000001", "t": 1.0}]
LAG = [{"t": 1.0, "ok": True, "partitions": 6, "lag": 0, "membres": 1}]
TROUS = {"attendus": 3, "en_base": 3, "trous": 0, "exemples": [], "hors_plage": []}
PAUSE = {"pause_s": 3.4, "reprise": True, "trou_normal_s": 0.98}


def p(n, montant="10.00", **x):
    return {"transaction_id": f"tx-{n:08d}", "amount": montant, "currency": "BRL",
            "emitter_account_id": "a", "beneficiary_account_id": "b", **x}


def rejet(n, motif="amount_must_be_positive", type_="BUSINESS_VALIDATION"):
    return {"transaction_id": f"tx-{n:08d}", "rejection_type": type_, "rejection_reason": motif}


def o(topic, valides, rejetes=()):
    return {"continuite": oracle.classer(topic, list(valides), list(rejetes)), "doublons": {"doublons_absorbes": 0}}


def decider(meta=META, orc=None, pause=PAUSE, drainage=True, trous=TROUS, audit=AUDIT, lag=LAG, **k):
    orc = orc or o([p(1), p(2)], [p(1), p(2)])
    return bilan.decider(meta, orc, pause, drainage, trous, audit, lag, **k)


class P0RejetsTest(unittest.TestCase):
    def test_1_paiement_valide_correctement(self):
        self.assertEqual(decider()[0], "REUSSITE")

    def test_2_rejet_metier_legitime_n_est_pas_une_perte(self):
        # tx-3 a été rejeté par la banque : il n'est jamais publié dans validated
        statut, raisons, _ = decider(orc=o([p(1), p(2)], [p(1), p(2)], [rejet(3)]))
        self.assertEqual((statut, raisons), ("REUSSITE", []))

    def test_3_paiement_valide_retrouve_seulement_dans_les_rejets(self):
        statut, raisons, _ = decider(orc=o([p(1), p(2)], [p(1)], [rejet(2)]))
        self.assertEqual(statut, "ECHEC")
        self.assertIn("1 paiement(s) validé(s) retrouvé(s) seulement dans les rejets", raisons)

    def test_3bis_rejet_pour_delai_d_un_paiement_valide(self):
        statut, raisons, _ = decider(orc=o([p(1), p(2)], [p(1)], [rejet(2, "processing_timeout", "TECHNICAL_TIMEOUT")]))
        self.assertEqual(statut, "ECHEC")
        self.assertIn("1 paiement(s) validé(s) retrouvé(s) seulement dans les rejets", raisons)

    def test_4_paiement_dans_deux_categories_incompatibles(self):
        statut, raisons, _ = decider(orc=o([p(1), p(2)], [p(1), p(2)], [rejet(2)]))
        self.assertEqual(statut, "ECHEC")
        self.assertIn("1 paiement(s) à la fois validé(s) et rejeté(s)", raisons)

    def test_5_paiement_absent_de_tous_les_resultats(self):
        statut, raisons, _ = decider(orc=o([p(1), p(2)], [p(1)]), trous=dict(TROUS, trous=1))
        self.assertEqual(statut, "ECHEC")
        self.assertIn("1 paiement(s) perdu(s)", raisons)
        self.assertIn("1 paiement(s) sans décision en base (ni validé, ni rejeté)", raisons)

    def test_6_donnees_differentes_entre_les_flux(self):
        statut, raisons, _ = decider(orc=o([p(1), p(2)], [p(1), p(2, emitter_account_id="z")]))
        self.assertEqual(statut, "ECHEC")
        self.assertIn("1 valeur(s) fausse(s)", raisons)

    def test_7_scenario_normal_avec_rejets_legitimes(self):
        topic = [p(i) for i in range(1, 6)]
        statut, _, _ = decider(orc=o(topic, topic, [rejet(6), rejet(7)]), trous=dict(TROUS, attendus=7))
        self.assertEqual(statut, "REUSSITE")


class P1MasquageTest(unittest.TestCase):
    PERTE = o([p(1), p(2)], [p(1)])
    TROUS_PERTE = dict(TROUS, trous=1)

    def test_perte_seule(self):
        self.assertEqual(decider(orc=self.PERTE, trous=self.TROUS_PERTE)[0], "ECHEC")

    def test_mesure_manquante_seule(self):
        statut, raisons, _ = decider(audit=[])
        self.assertEqual(statut, "INVALIDE")
        self.assertEqual(raisons, ["mesure invalide : audit des écritures vide : pause non mesurable"])

    def test_perte_et_horloge_invalide(self):
        statut, raisons, a = decider(meta=HORLOGE_KO, orc=self.PERTE, trous=self.TROUS_PERTE)
        # la perte vient des identités, pas de l'horloge : elle reste démontrée
        self.assertEqual(statut, "ECHEC")
        self.assertIn("1 paiement(s) perdu(s)", raisons)
        self.assertTrue(any(r.startswith("mesure invalide : horloge") for r in raisons))
        self.assertTrue(a["integrite_confirmee"])
        self.assertFalse(a["temps_confirme"])

    def test_doublon_et_mesure_manquante(self):
        orc = o([p(1), p(2)], [p(1), p(2), p(2)])
        statut, raisons, _ = decider(orc=orc, lag=[])
        self.assertEqual(statut, "ECHEC")
        self.assertIn("1 double(s) effet(s) en base", raisons)
        self.assertIn("mesure invalide : aucun relevé du groupe : retard et chronologie non mesurables", raisons)

    def test_pause_excessive_et_horloge_invalide(self):
        statut, raisons, a = decider(meta=HORLOGE_KO, pause=dict(PAUSE, pause_s=70.0))
        # la pause dépend de l'horloge : elle est gardée, mais pas comptée comme démontrée
        self.assertEqual(statut, "INVALIDE")
        self.assertIn("pause 70.0 s > borne 60 s (non confirmé : mesure du temps douteuse)", raisons)
        self.assertEqual(a["temps"], ["pause 70.0 s > borne 60 s"])

    def test_perte_quand_le_flux_n_est_pas_termine_reste_non_confirmee(self):
        statut, raisons, _ = decider(meta=dict(META, flux_termine=False), orc=self.PERTE, trous=self.TROUS_PERTE)
        # un paiement encore en route n'est pas une perte démontrée : INVALIDE, mais la perte reste écrite
        self.assertEqual(statut, "INVALIDE")
        self.assertIn("1 paiement(s) perdu(s) (non confirmé : mesure incomplète)", raisons)

    def test_essai_interrompu_jamais_reussite(self):
        # interrompu = flux non terminé, audit et relevé vides, tables non relues
        statut, _, _ = decider(meta=dict(META, flux_termine=False), audit=[], lag=[], trous=None)
        self.assertNotEqual(statut, "REUSSITE")

    def test_essai_totalement_valide(self):
        self.assertEqual(decider(), ("REUSSITE", [], decider()[2]))

    def test_plusieurs_anomalies_ensemble(self):
        orc = o([p(1), p(2), p(3)], [p(1), p(2, montant="9.00")])
        statut, raisons, _ = decider(orc=orc, trous=dict(TROUS, trous=1), pause=dict(PAUSE, pause_s=61.0), drainage=False)
        self.assertEqual(statut, "ECHEC")
        for attendu in ("1 paiement(s) perdu(s)", "1 valeur(s) fausse(s)",
                        "1 paiement(s) sans décision en base (ni validé, ni rejeté)",
                        "retard non résorbé en 120 s (drainage)", "pause 61.0 s > borne 60 s"):
            self.assertIn(attendu, raisons)

    def test_relecture_du_topic_impossible_est_invalide_pas_un_echec_trompeur(self):
        # 0 message relu (lecture impossible) : la base contient 3000 lignes « inattendues »,
        # mais c'est la relecture qui manque, pas les paiements
        compteurs = {"apres": {"validated_topic_end_offsets": 3000}}
        orc = o([], [p(1), p(2)])
        statut, raisons, _ = decider(orc=orc, topic_lus=0, compteurs=compteurs)
        self.assertEqual(statut, "INVALIDE")
        self.assertIn("mesure invalide : relecture du topic incomplète : 0 messages lus sur 3000", raisons)
        self.assertIn("2 ligne(s) inattendue(s) (non confirmé : mesure incomplète)", raisons)

    def test_relecture_du_topic_incomplete_est_invalide(self):
        compteurs = {"apres": {"validated_topic_end_offsets": 3000}}
        statut, raisons, _ = decider(topic_lus=2990, compteurs=compteurs)
        self.assertEqual(statut, "INVALIDE")
        self.assertIn("mesure invalide : relecture du topic incomplète : 2990 messages lus sur 3000", raisons)


if __name__ == "__main__":
    unittest.main()


class FichierAuditAbsentTest(unittest.TestCase):
    """bilan.py de bout en bout sur un essai sans donnees/audit.json : INVALIDE, pas d'erreur Python."""

    def test_audit_absent_donne_invalide(self):
        import json
        import os
        import subprocess
        import tempfile
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "donnees"))
        meta = dict(META, id="20261110-000000-minimale-at_least_once-normale", mode="minimale", charge="normale",
                    total=2, debit=20, cible_metier_s=10, ralenti_ms=0, t0=10.0, fin=20.0, debut_reference=0.0,
                    debut_flux=0.0, fin_flux=30.0, drainage_termine=True)
        ecrits = {"meta.json": meta,
                  "oracle.json": o([p(1), p(2)], [p(1), p(2)]) | {"flux": {"rejets_total": 0, "rejets_delai": 0}},
                  "donnees/topic_validated.json": [p(1), p(2)], "donnees/db_validated.json": [p(1), p(2)],
                  "donnees/db_rejected.json": []}
        for nom, contenu in ecrits.items():
            with open(os.path.join(d, nom), "w") as f:
                json.dump(contenu, f)
        with open(os.path.join(d, "lag.jsonl"), "w") as f:
            f.write(json.dumps(LAG[0]) + "\n")
        r = subprocess.run([sys.executable, str(ROOT / "scripts/sujet11/bilan.py"), d], capture_output=True, text=True,
                           env=dict(os.environ, SUJET11_INFLUX_URL="http://127.0.0.1:9"))
        self.assertEqual(r.returncode, 1, r.stderr)
        with open(os.path.join(d, "resultat.json")) as f:
            res = json.load(f)
        self.assertEqual(res["verdict"], "INVALIDE")
        self.assertIn("mesure invalide : audit des écritures vide : pause non mesurable", res["raisons"])
