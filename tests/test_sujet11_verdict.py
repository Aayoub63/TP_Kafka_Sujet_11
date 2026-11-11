"""Sujet 11 : le verdict raconte-t-il le bon résultat ?

Un test par scénario : réussite, pause au-dessus de la borne, double effet,
paiement manquant, résultat incomplet. Plus les nouveaux contrôles de l'oracle
(valeurs comparées, doubles effets, incohérents, conflits du topic).
"""
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


bilan = charger("bilan")
oracle = charger("oracle")

META = {"semantique": "at_least_once", "borne_s": 60, "drainage_max_s": 120,
        "decalage_debut_s": 0.0, "decalage_fin_s": 0.0, "flux_termine": True,
        "semantique_effective": "at_least_once"}
AUDIT = [{"transaction_id": "tx-00000001", "t": 1.0}]
LAG = [{"t": 1.0, "ok": True, "partitions": 6, "lag": 0, "membres": 1}]
TROUS_OK = {"attendus": 3, "en_base": 3, "trous": 0, "exemples": [], "hors_plage": []}
PAUSE_OK = {"pause_s": 3.4, "reprise": True, "trou_normal_s": 0.98}


def paiement(n, montant="10.00", **autres):
    return {"transaction_id": f"tx-{n:08d}", "amount": montant, "currency": "BRL",
            "emitter_account_id": "acc-1", "beneficiary_account_id": "acc-2", **autres}


def oracle_de(topic, valides, rejetes=()):
    return {"continuite": oracle.classer(topic, list(valides), list(rejetes)),
            "doublons": {"doublons_absorbes": 0}}


TOPIC = [paiement(1), paiement(2), paiement(3)]


class ScenariosTest(unittest.TestCase):
    def test_a_reussite_quand_tout_est_tenu(self):
        v, raisons = bilan.verdict(META, oracle_de(TOPIC, TOPIC), PAUSE_OK, True, TROUS_OK)
        self.assertEqual((v, raisons), ("REUSSITE", []))

    def test_b_pause_au_dessus_de_la_borne_echoue_meme_sans_perte(self):
        pause = dict(PAUSE_OK, pause_s=61.0)
        v, raisons = bilan.verdict(META, oracle_de(TOPIC, TOPIC), pause, True, TROUS_OK)
        self.assertEqual(v, "ECHEC")
        self.assertEqual(raisons, ["pause 61.0 s > borne 60 s"])

    def test_c_double_effet_en_base_echoue(self):
        valides = TOPIC + [paiement(2)]  # deux lignes pour tx-00000002
        v, raisons = bilan.verdict(META, oracle_de(TOPIC, valides), PAUSE_OK, True, TROUS_OK)
        self.assertEqual(v, "ECHEC")
        self.assertIn("1 double(s) effet(s) en base", raisons)

    def test_d_paiement_manquant_echoue(self):
        v, raisons = bilan.verdict(META, oracle_de(TOPIC, TOPIC[:2]), PAUSE_OK, True,
                                   dict(TROUS_OK, trous=1, exemples=["tx-00000003"]))
        self.assertEqual(v, "ECHEC")
        self.assertIn("1 paiement(s) perdu(s)", raisons)
        self.assertIn("1 paiement(s) sans décision en base (ni validé, ni rejeté)", raisons)

    def test_d_trou_detecte_meme_si_la_relecture_du_topic_l_a_manque(self):
        # la relecture du topic n'a vu que 2 messages sur 3 : l'oracle ne voit rien,
        # le contrôle des trous trouve tx-00000003
        v, raisons = bilan.verdict(META, oracle_de(TOPIC[:2], TOPIC[:2]), PAUSE_OK, True,
                                   dict(TROUS_OK, trous=1))
        self.assertEqual(v, "ECHEC")
        self.assertEqual(raisons, ["1 paiement(s) sans décision en base (ni validé, ni rejeté)"])

    def test_retard_non_resorbe_echoue(self):
        v, raisons = bilan.verdict(META, oracle_de(TOPIC, TOPIC), PAUSE_OK, False, TROUS_OK)
        self.assertEqual(v, "ECHEC")
        self.assertEqual(raisons, ["retard non résorbé en 120 s (drainage)"])

    def test_e_flux_non_termine_est_invalide(self):
        raisons = bilan.invalidites(dict(META, flux_termine=False), AUDIT, LAG, TROUS_OK)
        self.assertEqual(raisons, ["flux pas terminé avant la collecte : résultat indéterminé"])

    def test_e_mesures_absentes_sont_invalides_pas_reussies(self):
        raisons = bilan.invalidites(META, [], [], None)
        self.assertEqual(raisons, ["audit des écritures vide : pause non mesurable",
                                   "aucun relevé du groupe : retard et chronologie non mesurables",
                                   "tables PostgreSQL non relues : trous non vérifiables"])

    def test_e_semantique_differente_apres_la_mise_a_jour_est_invalide(self):
        raisons = bilan.invalidites(dict(META, semantique_effective_apres="at_most_once"), AUDIT, LAG, TROUS_OK)
        self.assertEqual(raisons, ["persister-valid appliquait at_most_once après la mise à jour, pas at_least_once"])

    def test_mesures_completes_ne_donnent_aucune_invalidite(self):
        self.assertEqual(bilan.invalidites(META, AUDIT, LAG, TROUS_OK), [])


class OracleTest(unittest.TestCase):
    def test_un_mauvais_beneficiaire_est_une_valeur_fausse(self):
        valides = [paiement(1), paiement(2, beneficiary_account_id="acc-9"), paiement(3)]
        r = oracle.classer(TOPIC, valides, [])
        self.assertEqual(r["classes"]["valeur_fausse"], 1)
        self.assertEqual(r["champs_faux"], {"beneficiary_account_id": 1})
        self.assertEqual(r["champs_compares"], ["amount", "beneficiary_account_id", "currency", "emitter_account_id"])

    def test_paiement_valide_et_rejete_est_incoherent(self):
        rejet = {"transaction_id": "tx-00000001", "rejection_type": "BUSINESS_VALIDATION", "rejection_reason": "x"}
        r = oracle.classer(TOPIC, TOPIC, [rejet])
        self.assertEqual(r["incoherents"], 1)

    def test_meme_identite_publiee_avec_deux_montants_est_un_conflit(self):
        r = oracle.classer(TOPIC + [paiement(1, montant="99.00")], TOPIC, [])
        self.assertEqual(r["conflits_topic"], 1)

    def test_ancien_essai_avec_le_seul_montant(self):
        topic = [{"transaction_id": "tx-1", "amount": 10.5}]
        r = oracle.classer(topic, [{"transaction_id": "tx-1", "amount": "10.50"}], [])
        self.assertEqual((r["classes"]["present"], r["champs_compares"]), (1, ["amount"]))


class PauseDistincteTest(unittest.TestCase):
    def test_pause_nettement_plus_longue_que_le_trou_normal(self):
        self.assertTrue(bilan.pause_distincte({"pause_s": 3.4, "trou_normal_s": 0.98}))

    def test_pause_egale_au_trou_normal_n_est_pas_mesurable(self):
        # cas mesuré de la solution améliorée : 0,969 s pour un trou normal de 0,987 s
        self.assertFalse(bilan.pause_distincte({"pause_s": 0.969, "trou_normal_s": 0.987}))

    def test_sans_trou_normal_on_ne_sait_pas(self):
        self.assertIsNone(bilan.pause_distincte({"pause_s": 3.4, "trou_normal_s": None}))


class CompteursTest(unittest.TestCase):
    def test_avant_pire_apres_et_debit(self):
        lignes = [
            {"t": 0.0, "phase": "avant", "generated": 600, "validated_topic_end_offsets": 600,
             "db_validated_count": 590, "ecart_topic_base": 10},
            {"t": 2.0, "phase": "pendant", "generated": 640, "validated_topic_end_offsets": 640,
             "db_validated_count": 590, "ecart_topic_base": 50},
            {"t": 4.0, "phase": "pendant", "generated": 680, "validated_topic_end_offsets": 680,
             "db_validated_count": 660, "ecart_topic_base": 20},
            {"t": 6.0, "phase": "apres", "generated": 680, "validated_topic_end_offsets": 680,
             "db_validated_count": 680, "ecart_topic_base": 0},
        ]
        r = bilan.resumer_compteurs(lignes)
        self.assertEqual(r["avant"]["ecart_topic_base"], 10)
        self.assertEqual(r["pire"]["ecart_topic_base"], 50)
        self.assertEqual(r["apres"]["ecart_topic_base"], 0)
        self.assertEqual(r["debit_mesure"], 20.0)

    def test_sans_compteurs(self):
        self.assertIsNone(bilan.resumer_compteurs([]))
        self.assertEqual(bilan.texte_compteurs(None), ["   non mesuré (pas de compteurs.jsonl)"])


if __name__ == "__main__":
    unittest.main()
