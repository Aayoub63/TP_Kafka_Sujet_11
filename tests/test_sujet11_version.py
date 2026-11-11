import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/sujet11"))
spec = importlib.util.spec_from_file_location("sujet11_bilan", ROOT / "scripts/sujet11/bilan.py")
bilan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bilan)


def depot_avec(code):
    racine = tempfile.mkdtemp()
    os.makedirs(os.path.join(racine, "services", "persister-valid"))
    with open(os.path.join(racine, "services", "persister-valid", "main.py"), "w") as f:
        f.write(code)
    return racine


class VersionTest(unittest.TestCase):
    def test_code_avec_arret_propre(self):
        self.assertEqual(bilan.version_persister_valid(depot_avec("STOP_REQUESTED = threading.Event()")),
                         "arret-propre")

    def test_ancien_code(self):
        self.assertEqual(bilan.version_persister_valid(depot_avec("while True:\n    pass")), "ancien-code")

    def test_fichier_absent(self):
        self.assertEqual(bilan.version_persister_valid(tempfile.mkdtemp()), "inconnue")


if __name__ == "__main__":
    unittest.main()
