import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_proportions():
    spec = importlib.util.spec_from_file_location(
        "sujet11_proportions", ROOT / "scripts/sujet11/proportions.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


proportions = load_proportions()


def load_resume():
    spec = importlib.util.spec_from_file_location(
        "sujet11_resume", ROOT / "scripts/sujet11/resume.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WilsonTest(unittest.TestCase):
    def test_zero_perte_sur_dix(self):
        bas, haut = proportions.wilson(0, 10)
        self.assertEqual(bas, 0)
        self.assertAlmostEqual(haut, 0.2775, delta=1e-3)

    def test_cinq_sur_dix(self):
        bas, haut = proportions.wilson(5, 10)
        self.assertAlmostEqual(bas, 0.2366, delta=1e-3)
        self.assertAlmostEqual(haut, 0.7634, delta=1e-3)

    def test_zero_essai(self):
        self.assertIsNone(proportions.wilson(0, 0))


class SyntheseTest(unittest.TestCase):
    def test_trois_lignes_dont_une_avec_perte(self):
        lignes = [
            {"attendus": 100, "perdus": 0, "doublons_absorbes": 2, "sous_cible_metier": False},
            # un essai avec une perte et sous la cible métier
            {"attendus": 100, "perdus": 1, "doublons_absorbes": 0, "sous_cible_metier": True},
            {"attendus": 100, "perdus": 0, "doublons_absorbes": 1, "sous_cible_metier": False},
        ]
        s = proportions.synthese(lignes)
        self.assertEqual(s["essais"], 3)
        self.assertEqual(s["essais_avec_perte"], 1)
        self.assertAlmostEqual(s["part_essais_avec_perte"], 1 / 3)
        self.assertEqual((s["paiements"], s["perdus"]), (300, 1))
        self.assertAlmostEqual(s["taux_perte"], 1 / 300)
        self.assertAlmostEqual(s["taux_doublons"], 3 / 300)
        self.assertEqual(s["essais_sous_cible"], 1)
        self.assertAlmostEqual(s["part_sous_cible"], 1 / 3)
        bas, haut = s["ic_taux_perte"]
        self.assertLessEqual(bas, s["taux_perte"])
        self.assertGreaterEqual(haut, s["taux_perte"])

    def test_paiements_nuls(self):
        # sous_cible_metier peut être absent des essais : None compte comme faux
        lignes = [{"attendus": 0, "perdus": 0, "doublons_absorbes": 0, "sous_cible_metier": None}]
        s = proportions.synthese(lignes)
        self.assertIsNone(s["taux_perte"])
        self.assertIsNone(s["taux_doublons"])
        self.assertIsNone(s["ic_taux_perte"])
        self.assertEqual(s["essais_avec_perte"], 0)


class PourcentTest(unittest.TestCase):
    def test_format_francais(self):
        self.assertEqual(proportions.pourcent(0.0123), "1,23 %")

    def test_zero(self):
        self.assertEqual(proportions.pourcent(0), "0 %")

    def test_tres_petit_taux(self):
        self.assertEqual(proportions.pourcent(0.00005), "0,0050 %")

    def test_none(self):
        self.assertEqual(proportions.pourcent(None), "-")


class ResumeMainTest(unittest.TestCase):
    """Lance main() de resume.py sur deux essais minimaux créés à la volée."""

    def setUp(self):
        self.resume = load_resume()
        self._argv = sys.argv
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def tearDown(self):
        sys.argv = self._argv

    def ecrire_essai(self, dossier, id_essai, perdus, verdict="REUSSITE"):
        """Écrit les seules clés lues par ligne() de resume.py."""
        os.makedirs(dossier)
        resultat = {
            "verdict": verdict,
            "raisons": [],
            "drainage_termine": True,
            "sous_cible_metier": False,
            "pause": {"pause_s": 0.5, "trou_normal_s": 0.1},
            "retard_max_messages": 0,
            "chronologie": {"groupe_vide_duree_s": 0.0},
            "oracle": {
                "continuite": {"attendus": 100,
                               "classes": {"perdu": perdus, "valeur_fausse": 0},
                               "lignes_inattendues": 0},
                "doublons": {"doublons_absorbes": 0},
            },
        }
        meta = {"id": id_essai, "semantique": "au-moins-une", "charge": "legere",
                "debit": 10, "total": 100}
        with open(os.path.join(dossier, "resultat.json"), "w") as f:
            json.dump(resultat, f)
        with open(os.path.join(dossier, "meta.json"), "w") as f:
            json.dump(meta, f)
        with open(os.path.join(dossier, "bilan.txt"), "w") as f:
            f.write("bilan de l'essai\n")

    def test_main_ecrit_section_en_proportion(self):
        base = self._tmp.name
        preuves = os.path.join(base, "preuves")
        e1 = os.path.join(base, "essai-1")
        e2 = os.path.join(base, "essai-2")
        self.ecrire_essai(e1, "essai-1", 0)
        self.ecrire_essai(e2, "essai-2", 1)
        sys.argv = ["resume.py", preuves, e1, e2]
        self.assertEqual(self.resume.main(), 0)
        with open(os.path.join(preuves, "resume.md")) as f:
            contenu = f.read()
        self.assertIn("En proportion", contenu)

    def test_essai_invalide_ecarte(self):
        base = self._tmp.name
        preuves = os.path.join(base, "preuves")
        e1, e2 = os.path.join(base, "essai-1"), os.path.join(base, "essai-2")
        self.ecrire_essai(e1, "essai-1", 0)
        self.ecrire_essai(e2, "essai-2", 1, verdict="INVALIDE")
        sys.argv = ["resume.py", preuves, e1, e2]
        self.assertEqual(self.resume.main(), 0)
        contenu = open(os.path.join(preuves, "resume.md")).read()
        self.assertIn("Essais invalides écartés de ce tableau : 1.", contenu)
        # seul l'essai valide compte : 0 perte sur 100 paiements
        self.assertIn("0/100 = 0 %", contenu)
        # la section « Par combinaison » écarte aussi l'essai invalide
        self.assertIn("| 1/1 |", contenu)

    def test_presque_zero(self):
        self.assertEqual(proportions.pourcent(1e-20), "0 %")


if __name__ == "__main__":
    unittest.main()
