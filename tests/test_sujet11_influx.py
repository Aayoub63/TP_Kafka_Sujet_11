import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_influx():
    spec = importlib.util.spec_from_file_location("sujet11_influx", ROOT / "scripts/sujet11/influx.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


influx = load_influx()


class LineProtocolTest(unittest.TestCase):
    def test_types_des_champs(self):
        l = influx.ligne("m", {"mode": "amelioree"},
                         {"pause_s": 1.5, "perdus": 0, "reussite": True, "id": "r1"}, t=2.0)
        self.assertEqual(l, 'm,mode=amelioree pause_s=1.5,perdus=0i,reussite=true,id="r1" 2000000000')

    def test_echappement_des_tags_et_du_texte(self):
        l = influx.ligne("m", {"essai": "a b,c=d"}, {"texte": 'dit "oui"'}, t=1.0)
        self.assertEqual(l, 'm,essai=a\\ b\\,c\\=d texte="dit \\"oui\\"" 1000000000')

    def test_valeurs_absentes_ignorees(self):
        l = influx.ligne("m", {"vide": "", "x": "1"}, {"a": None, "b": 2}, t=0.0)
        self.assertEqual(l, "m,x=1 b=2i 0")


if __name__ == "__main__":
    unittest.main()
