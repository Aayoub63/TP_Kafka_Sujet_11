"""Sujet 11 : la page de synthèse du tableau de bord dit-elle la vérité ?

États testés : aucun essai, essai en cours, réussite, échec, mesure
invalide, valeur absente (« Non disponible », jamais 0).
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/service-health"))
import sujet11_synthese as synthese  # noqa: E402


def resultat(verdict="REUSSITE", raisons=(), perdus=0, doubles=0, pause=3.4, drainage=True):
    return {
        "verdict": verdict, "raisons": list(raisons), "parametres": {"borne_s": 60},
        "pause": {"pause_s": pause, "trou_normal_s": 0.98, "premiere_ecriture_apres_s": 4.0},
        "pause_distincte": True, "retard_max_messages": 78, "drainage_termine": drainage,
        "chronologie": {"conteneur_mort_s": 0.8, "groupe_vide_s": 1.9, "groupe_vide_duree_s": 3.0,
                        "partitions_reattribuees_s": 4.9, "lag_revenu_a_zero_s": 5.0},
        "trous": {"trous": perdus},
        "oracle": {"continuite": {"attendus": 3000, "classes": {"present": 3000 - perdus, "perdu": perdus,
                                                                "valeur_fausse": 0},
                                  "doubles_effets": doubles, "champs_compares": ["amount"]},
                   "doublons": {"doublons_absorbes": 0}, "flux": {"rejets_total": 0}},
    }


META = {"id": "20261110-100000-minimale-at_least_once-normale", "mode": "minimale",
        "semantique": "at_least_once", "total": 3000, "debit": 20, "borne_s": 60, "drainage_max_s": 120}


def espace(res=None, en_cours=None):
    """Dépôt temporaire avec un essai terminé et, au besoin, un essai en cours."""
    ws = tempfile.mkdtemp()
    if res is not None:
        d = os.path.join(ws, "runtime", "sujet11", META["id"])
        os.makedirs(d)
        json.dump(META, open(os.path.join(d, "meta.json"), "w"))
        json.dump(res, open(os.path.join(d, "resultat.json"), "w"))
    if en_cours:
        d = os.path.join(ws, "runtime", "sujet11", "en-cours")
        os.makedirs(d)
        open(os.path.join(d, "phase"), "w").write("drainage")
        open(os.path.join(d, "compteurs.jsonl"), "w").write(json.dumps({"ecart_topic_base": 42}) + "\n")
        verrou = os.path.join(ws, "runtime", "sujet11", "verrou")
        os.makedirs(verrou)
        open(os.path.join(verrou, "sortie"), "w").write("runtime/sujet11/en-cours")
    return ws


EN_COURS = {"id": "x", "mode": "minimale", "semantique": "at_least_once", "charge": "normale", "debut": "10:00:00"}


class SyntheseTest(unittest.TestCase):
    def test_aucun_essai(self):
        page = synthese.rendre_synthese("ensemble", espace(), None)
        self.assertIn("Aucun essai terminé", page)

    def test_reussite_explique_pourquoi(self):
        page = synthese.rendre_synthese("ensemble", espace(resultat()), None)
        self.assertIn("Garantie respectée", page)
        self.assertIn("aucun double effet", page)
        self.assertIn("Dernier essai terminé", page)

    def test_echec_affiche_les_raisons_et_pas_de_vert_global(self):
        page = synthese.rendre_synthese("ensemble", espace(resultat("ECHEC", ["1 paiement(s) perdu(s)"], perdus=1)), None)
        self.assertIn("Garantie NON respectée", page)
        self.assertIn("1 paiement(s) perdu(s)", page)
        self.assertNotIn("Garantie respectée<", page)

    def test_pause_au_dessus_de_la_borne_en_rouge(self):
        page = synthese.rendre_synthese("ensemble", espace(resultat("ECHEC", ["pause 61.0 s > borne 60 s"], pause=61.0)), None)
        self.assertIn("Au-dessus de la limite", page)

    def test_double_effet_signale(self):
        page = synthese.rendre_synthese("integrite", espace(resultat("ECHEC", ["1 double(s) effet(s) en base"], doubles=1)), None)
        self.assertIn("Doubles effets", page)
        self.assertIn(synthese.ROUGE, page)

    def test_invalide_n_est_ni_reussite_ni_echec(self):
        page = synthese.rendre_synthese("ensemble", espace(resultat("INVALIDE", ["flux pas terminé"])), None)
        self.assertIn("ni réussite, ni échec", page)

    def test_valeur_absente_est_non_disponible(self):
        r = resultat()
        del r["oracle"]["continuite"]["doubles_effets"]
        page = synthese.rendre_synthese("ensemble", espace(r), None)
        self.assertIn("Non disponible", page)
        self.assertIn("non vérifiés", page)

    def test_essai_en_cours_n_est_pas_confondu_avec_le_dernier(self):
        ws = espace(resultat(), en_cours=True)
        page = synthese.rendre_synthese("ensemble", ws, EN_COURS)
        self.assertIn("Essai en cours : rattrapage des paiements en attente", page)
        self.assertIn("42 paiement(s) pas encore en base", page)
        self.assertIn("attente de validation", page)
        self.assertIn("dernier essai terminé", page)

    def test_les_trois_vues_se_rendent(self):
        ws = espace(resultat())
        for vue in synthese.VUES:
            self.assertIn("<!doctype html>", synthese.rendre_synthese(vue, ws, None))


if __name__ == "__main__":
    unittest.main()
