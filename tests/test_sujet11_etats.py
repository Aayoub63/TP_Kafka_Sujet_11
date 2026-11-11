"""Sujet 11 : états affichés par la page de synthèse (mission 4).

P1-2 : un essai interrompu ou en cours ne doit jamais faire croire que le
dernier essai s'est bien terminé. P1-3 : mêmes bornes officielles partout.
P1-4 : la comparaison ne compte que les essais publiés, diagnostics à part.
"""
import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/service-health"))
sys.path.insert(0, str(ROOT / "scripts/sujet11"))
import sujet11_synthese as synthese  # noqa: E402

spec = importlib.util.spec_from_file_location("sujet11_bilan_etats", ROOT / "scripts/sujet11/bilan.py")
bilan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bilan)


def resultat(verdict="REUSSITE", raisons=(), perdus=0, pause=3.4):
    return {"verdict": verdict, "raisons": list(raisons), "parametres": {"borne_s": 60},
            "version_persister_valid": "arret-propre",
            "pause": {"pause_s": pause, "trou_normal_s": 0.98, "premiere_ecriture_apres_s": 4.0},
            "pause_distincte": True, "retard_max_messages": 78, "drainage_termine": True,
            "chronologie": {"lag_revenu_a_zero_s": 6.9},
            "trous": {"trous": perdus},
            "oracle": {"continuite": {"attendus": 3000, "classes": {"present": 3000 - perdus, "perdu": perdus,
                                                                    "valeur_fausse": 0, "rejet_metier": 0,
                                                                    "rejet_delai": 0},
                                      "doubles_effets": 0, "champs_compares": ["amount"]},
                       "doublons": {"doublons_absorbes": 0}, "flux": {"rejets_total": 0}}}


def meta(ident, mode="minimale", borne=60, drainage=120, fin=None):
    return {"id": ident, "mode": mode, "semantique": "at_least_once", "charge": "normale", "total": 3000,
            "debit": 20, "borne_s": borne, "drainage_max_s": drainage, "debut_flux": (fin or 0) - 200,
            "fin_flux": fin}


def ecrire(dossier, m, r=None, phase=None):
    os.makedirs(dossier, exist_ok=True)
    with open(os.path.join(dossier, "meta.json"), "w") as f:
        json.dump(m, f)
    if r is not None:
        with open(os.path.join(dossier, "resultat.json"), "w") as f:
            json.dump(r, f)
    if phase:
        with open(os.path.join(dossier, "phase"), "w") as f:
            f.write(phase)


def espace():
    return tempfile.mkdtemp()


def runtime(ws, nom):
    return os.path.join(ws, "runtime", "sujet11", nom)


class EtatsTest(unittest.TestCase):
    def test_1_aucun_essai(self):
        self.assertIn("Aucun essai terminé", synthese.rendre_synthese("ensemble", espace(), None))

    def test_2_un_essai_termine(self):
        ws = espace()
        ecrire(runtime(ws, "a"), meta("20261110-100000-a", fin=1000.0), resultat())
        page = synthese.rendre_synthese("ensemble", ws, None)
        self.assertIn("Dernier essai terminé : Garantie respectée", page)
        self.assertIn("Lancé le", page)
        self.assertNotIn("interrompu", page)

    def test_3_termine_puis_interrompu(self):
        ws = espace()
        ecrire(runtime(ws, "a"), meta("20261110-100000-a", fin=1000.0), resultat())
        ecrire(runtime(ws, "b"), meta("20261110-110000-b"), phase="interrompu")
        page = synthese.rendre_synthese("ensemble", ws, None)
        self.assertIn("Un essai plus récent a été interrompu", page)
        self.assertIn("il n'a pas de verdict", page)
        self.assertIn("Dernier essai terminé : Garantie respectée", page)

    def test_3bis_interruption_plus_ancienne_que_le_dernier_essai_n_est_pas_signalee(self):
        ws = espace()
        ecrire(runtime(ws, "b"), meta("20261110-090000-b"), phase="interrompu")
        os.utime(os.path.join(runtime(ws, "b"), "phase"), (500, 500))
        ecrire(runtime(ws, "a"), meta("20261110-100000-a", fin=time.time()), resultat())
        self.assertNotIn("interrompu", synthese.rendre_synthese("ensemble", ws, None))

    def test_4_termine_puis_en_cours(self):
        ws = espace()
        ecrire(runtime(ws, "a"), meta("20261110-100000-a", fin=1000.0), resultat())
        os.makedirs(runtime(ws, "verrou"))
        open(os.path.join(runtime(ws, "verrou"), "sortie"), "w").write("runtime/sujet11/c")
        ecrire(runtime(ws, "c"), meta("20261110-120000-c"), phase="drainage")
        en_cours = {"id": "c", "mode": "minimale", "semantique": "at_least_once", "charge": "normale", "debut": "12:00:00"}
        page = synthese.rendre_synthese("ensemble", ws, en_cours)
        self.assertIn("Essai en cours : rattrapage des paiements en attente", page)
        self.assertIn("opacity:.6", page)  # l'ancien verdict est atténué
        self.assertIn("Dernier essai terminé", page)

    def test_5_plusieurs_essais_le_plus_recent_par_fin_du_flux(self):
        ws = espace()
        ecrire(runtime(ws, "a"), meta("20261110-100000-a", fin=1000.0), resultat())
        ecrire(runtime(ws, "b"), meta("20261110-110000-b", fin=2000.0), resultat("ECHEC", ["1 paiement(s) perdu(s)"], 1))
        page = synthese.rendre_synthese("ensemble", ws, None)
        self.assertIn("20261110-110000-b", page)
        self.assertIn("Garantie NON respectée", page)

    def test_6_invalide_apres_reussite(self):
        ws = espace()
        ecrire(runtime(ws, "a"), meta("20261110-100000-a", fin=1000.0), resultat())
        ecrire(runtime(ws, "b"), meta("20261110-110000-b", fin=2000.0),
               resultat("INVALIDE", ["mesure invalide : audit des écritures vide : pause non mesurable"]))
        page = synthese.rendre_synthese("ensemble", ws, None)
        self.assertIn("Mesure non valide, ni réussite, ni échec", page)
        self.assertIn("Dernier essai avec un verdict valide : 20261110-100000-a (REUSSITE)", page)

    def test_valeur_absente_jamais_zero(self):
        ws = espace()
        r = resultat()
        r["chronologie"] = {}
        ecrire(runtime(ws, "a"), meta("20261110-100000-a", fin=1000.0), r)
        page = synthese.rendre_synthese("ensemble", ws, None)
        self.assertIn("Retour à la normale", page)
        self.assertIn("Non disponible", page)


class BornesTest(unittest.TestCase):
    def test_memes_bornes_dans_le_bilan_et_la_page(self):
        self.assertEqual(synthese.BORNES_OFFICIELLES, bilan.BORNES_OFFICIELLES)

    def test_panne_a_180_s_est_officielle_et_borne_30_est_un_diagnostic(self):
        self.assertTrue(bilan.essai_officiel({"mode": "crash", "borne_s": 60, "drainage_max_s": 180}))
        self.assertFalse(bilan.essai_officiel({"mode": "crash", "borne_s": 30, "drainage_max_s": 180}))
        self.assertFalse(bilan.essai_officiel({"mode": "crash", "borne_s": 60, "drainage_max_s": 120}))
        self.assertTrue(bilan.essai_officiel({"mode": "minimale", "borne_s": 60, "drainage_max_s": 120}))

    def test_charge_reelle_vient_du_ralenti(self):
        self.assertTrue(bilan.charge_reelle({"charge": "normale", "debit": 10, "ralenti_ms": 80}).startswith("ralentie"))


class TexteTest(unittest.TestCase):
    def test_pause_expliquee(self):
        self.assertEqual(synthese.expliquer("pause 45.008 s > borne 30 s"),
                         "Interruption de 45,0 s : la limite autorisée de 30 s pour cet essai a été dépassée.")

    def test_non_confirme_garde_la_raison(self):
        t = synthese.expliquer("pause 70.0 s > borne 60 s (non confirmé : mesure du temps douteuse)")
        self.assertIn("Interruption de 70,0 s", t)
        self.assertIn("Non confirmé", t)


class ComparaisonTest(unittest.TestCase):
    def test_seuls_les_essais_publies_officiels_et_valides_comptent(self):
        ws = espace()
        base = os.path.join(ws, "preuves", "sujet11", "campagne-x", "essais")
        ecrire(os.path.join(base, "r1"), meta("20261109-120000-r1", "crash", 60, 180), resultat("ECHEC", [], 1))
        ecrire(os.path.join(base, "r2"), meta("20261109-121000-r2", "crash", 30, 180), resultat("ECHEC", [], 0))
        ecrire(os.path.join(base, "r3"), meta("20261109-122000-r3", "crash", 60, 180), resultat("INVALIDE"))
        ecrire(os.path.join(base, "r0"), meta("20261107-120000-r0", "crash", 60, 180), resultat("ECHEC", [], 1))
        page = synthese.rendre_synthese("comparaison", ws, None)
        self.assertIn("1 sur 1", page)
        self.assertIn("1 essais publiés", page)
        self.assertIn("Écartés : 1 essai(s) à la mesure invalide, 1 essai(s) de diagnostic", page)


if __name__ == "__main__":
    unittest.main()


class FinalisationTest(unittest.TestCase):
    """Corrections d'affichage d'avant la soutenance."""

    def page(self, mode, distincte, vue="deroulement"):
        ws = espace()
        r = resultat()
        r["pause_distincte"] = distincte
        r["chronologie"] = {"groupe_vide_s": 2.0, "groupe_vide_duree_s": 2.6, "lag_revenu_a_zero_s": 5.3}
        r["pause"]["premiere_ecriture_apres_s"] = 14.4
        ecrire(runtime(ws, "a"), meta("20261110-100000-a", mode=mode, fin=1000.0), r)
        return synthese.rendre_synthese(vue, ws, None)

    def test_amelioree_sans_interruption_n_affiche_pas_de_reprise(self):
        page = self.page("amelioree", False)
        self.assertIn("5. Pas d&#x27;interruption mesurable", page)  # apostrophe échappée en HTML
        self.assertNotIn("14,40 s", page)
        self.assertNotIn("Personne ne lit", page)
        self.assertIn("l'ancienne version continue de traiter", page)
        self.assertIn("pas de reprise à mesurer", self.page("amelioree", False, "ensemble"))

    def test_minimale_avec_interruption_garde_la_reprise(self):
        page = self.page("minimale", True)
        self.assertIn("5. La nouvelle version reprend", page)
        self.assertIn("Aucune version ne traite de paiement", page)
        self.assertIn("état du groupe vu par Kafka", page)

    def test_point_avant_non_confirme(self):
        self.assertEqual(synthese.expliquer("pas de reprise des écritures (non confirmé : mesure du temps douteuse)"),
                         "pas de reprise des écritures. Non confirmé : la mesure du temps est douteuse.")

    def test_essai_choisi_et_chemin_refuse(self):
        ws = espace()
        ecrire(runtime(ws, "a"), meta("20261110-100000-a", fin=1000.0), resultat())
        ecrire(runtime(ws, "b"), meta("20261110-110000-b"), phase="interrompu")
        page = synthese.rendre_synthese("ensemble", ws, None, essai="runtime/sujet11/a")
        self.assertIn("Essai choisi pour la démonstration", page)
        self.assertNotIn("interrompu", page)
        self.assertIn("Essai introuvable", synthese.rendre_synthese("ensemble", ws, None, essai="../../etc"))
