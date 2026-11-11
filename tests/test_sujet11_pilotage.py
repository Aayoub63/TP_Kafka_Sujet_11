import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_HEALTH = str(ROOT / "services/service-health")


def load_scenario_control():
    for name in ("psycopg", "docker"):
        sys.modules.setdefault(name, types.ModuleType(name))
    if SERVICE_HEALTH not in sys.path:
        sys.path.insert(0, SERVICE_HEALTH)
    import scenario_control
    return scenario_control


CONTROL = load_scenario_control()


def formulaire(**valeurs):
    return {cle: [valeur] for cle, valeur in valeurs.items()}


class PilotageSujet11Test(unittest.TestCase):
    def test_essai_ameliore_construit_la_commande_du_script(self):
        ok, label, commande, env = CONTROL.build_control_job(formulaire(
            action="sujet11_essai", mode="amelioree", semantique="at_least_once", charge="forte", debit="60"))
        self.assertTrue(ok)
        self.assertEqual(label, "sujet11_essai:amelioree:at_least_once:forte")
        self.assertEqual(commande, ["/bin/sh", "./scripts/sujet11-maj.sh", "--mode", "amelioree",
                                    "--semantique", "at_least_once", "--charge", "forte",
                                    "--debit", "60", "--borne", "60"])
        self.assertEqual(env["SUJET11_INFLUX_URL"], "http://influxdb:8086")
        self.assertEqual(env["SIMULPIX_CONTROL_TIMEOUT_SECONDS"], "900")

    def test_crash_reglage_fixe(self):
        ok, label, commande, _ = CONTROL.build_control_job(formulaire(
            action="sujet11_essai", mode="crash", semantique="at_most_once", charge="forte"))
        self.assertTrue(ok)
        self.assertEqual(commande, ["/bin/sh", "./scripts/sujet11-maj.sh", "--mode", "crash",
                                    "--semantique", "at_most_once", "--charge", "ralentie",
                                    "--debit", "10", "--ralenti", "80", "--drainage-max", "180",
                                    "--borne", "60"])

    def test_exactly_once_pg_accepte(self):
        ok, label, _, _ = CONTROL.build_control_job(formulaire(
            action="sujet11_essai", mode="crash", semantique="exactly_once_pg", charge="normale"))
        self.assertTrue(ok)
        self.assertIn("exactly_once_pg", label)

    def test_debit_deduit_de_la_charge(self):
        for charge, debit in (("normale", "20"), ("forte", "60")):
            _, _, commande, _ = CONTROL.build_control_job(formulaire(
                action="sujet11_essai", mode="minimale", semantique="at_least_once", charge=charge))
            self.assertEqual(commande[commande.index("--debit") + 1], debit)

    def test_valeur_hors_liste_refusee(self):
        ok, label, commande, _ = CONTROL.build_control_job(formulaire(
            action="sujet11_essai", mode="minimale; rm -rf /", semantique="at_least_once"))
        self.assertFalse(ok)
        self.assertEqual(label, "sujet11_parametres_refuses")
        self.assertIsNone(commande)

    def test_debit_borne(self):
        _, _, commande, _ = CONTROL.build_control_job(formulaire(
            action="sujet11_essai", mode="minimale", semantique="at_most_once", charge="normale", debit="99999"))
        self.assertEqual(commande[commande.index("--debit") + 1], "200")

    def test_actions_existantes_inchangees(self):
        ok, label, commande, env = CONTROL.build_control_job(formulaire(action="reset"))
        self.assertEqual((ok, label, commande, env),
                         (True, "reset_scenario", ["/bin/sh", "./scripts/reset-scenario.sh"], None))


class RefusAnticipeTest(unittest.TestCase):
    def test_essai_refuse_si_le_verrou_est_pris(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as racine:
            dossier = os.path.join(racine, "runtime", "sujet11", "verrou")
            os.makedirs(dossier)
            with open(os.path.join(dossier, "essai"), "w") as f:
                f.write("20261108-195517-minimale-at_least_once-normale\n")
            ancien = os.environ.get("SIMULPIX_WORKSPACE_DIR")
            os.environ["SIMULPIX_WORKSPACE_DIR"] = racine
            try:
                resultat, label = CONTROL.execute_control_action(formulaire(
                    action="sujet11_essai", mode="amelioree", semantique="at_least_once", charge="normale"))
            finally:
                if ancien is None:
                    del os.environ["SIMULPIX_WORKSPACE_DIR"]
                else:
                    os.environ["SIMULPIX_WORKSPACE_DIR"] = ancien
        self.assertEqual((resultat, label), ("busy", "sujet11_occupe"))
        self.assertIn("20261108-195517-minimale", CONTROL.CONTROL_STATE["busy_message"])


if __name__ == "__main__":
    unittest.main()
