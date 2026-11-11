import os
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_HEALTH = str(ROOT / "services/service-health")
if SERVICE_HEALTH not in sys.path:
    sys.path.insert(0, SERVICE_HEALTH)
import sujet11_etat as etat  # noqa: E402


def poser_verrou(racine, identifiant, age_s=0):
    dossier = os.path.join(racine, "runtime", "sujet11", "verrou")
    os.makedirs(dossier)
    chemin = os.path.join(dossier, "essai")
    with open(chemin, "w") as f:
        f.write(identifiant + "\n")
    if age_s:
        ancien = time.time() - age_s
        os.utime(chemin, (ancien, ancien))


class EssaiEnCoursTest(unittest.TestCase):
    def test_lit_le_mode_la_semantique_et_la_charge(self):
        with tempfile.TemporaryDirectory() as racine:
            poser_verrou(racine, "20261108-195517-amelioree-at_least_once-forte")
            e = etat.essai_en_cours(racine)
        self.assertEqual((e["mode"], e["semantique"], e["charge"], e["debut"]),
                         ("amelioree", "at_least_once", "forte", "19:55:17"))

    def test_sans_verrou(self):
        with tempfile.TemporaryDirectory() as racine:
            self.assertIsNone(etat.essai_en_cours(racine))

    def test_verrou_perime_ignore(self):
        with tempfile.TemporaryDirectory() as racine:
            poser_verrou(racine, "20261108-195517-minimale-at_least_once-normale", age_s=1300)
            self.assertIsNone(etat.essai_en_cours(racine))


class RenduTest(unittest.TestCase):
    EN_COURS = {"id": "x", "mode": "minimale", "semantique": "at_most_once", "charge": "normale", "debut": "10:00:00"}

    def test_chaque_cas_a_sa_couleur(self):
        for mode, (_, couleur) in etat.MODES.items():
            page = etat.rendre_etat(dict(self.EN_COURS, mode=mode))
            self.assertIn(couleur, page)

    def test_refus_en_rouge_avec_l_essai_en_cours(self):
        page = etat.rendre_etat(self.EN_COURS, resultat="busy")
        self.assertIn(etat.ROUGE, page)
        self.assertIn("déjà en cours (2. Solution minimale, depuis 10:00:00)", page)

    def test_essai_lance(self):
        page = etat.rendre_etat(None, resultat="accepted", mode="amelioree", semantique="at_least_once", charge="forte")
        self.assertIn("Essai lancé : 3. Solution améliorée", page)
        self.assertNotIn("Aucun essai", page)

    def test_aucun_essai(self):
        self.assertIn("Aucun essai en cours", etat.rendre_etat(None))

    def test_texte_echappe(self):
        page = etat.rendre_etat(None, resultat="accepted", mode="<script>", semantique="x", charge="y")
        self.assertNotIn("<script>", page)

    def test_recharge_sans_les_parametres_du_clic(self):
        self.assertIn("content='5;url=/sujet11/etat'", etat.rendre_etat(None))


class CrashTest(unittest.TestCase):
    def test_charge_ralentie_affichee(self):
        page = etat.rendre_etat(None, "accepted", "crash", "at_most_once", "forte")
        self.assertIn("charge ralentie", page)
        self.assertIn("#a21caf", page)

if __name__ == "__main__":
    unittest.main()
