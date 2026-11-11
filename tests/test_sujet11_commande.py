"""Sujet 11 : contrôle des scénarios depuis Grafana (mission 6).

Tous ces tests tournent dans des dossiers temporaires, avec un faux script
d'essai qui imite le vrai (verrou, phase, réaction à SIGTERM). Aucun essai réel.
"""
import io
import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/service-health"))
import sujet11_pilotage as pilotage  # noqa: E402
import scenario_control  # noqa: E402

FAUX_SCRIPT = r'''#!/bin/sh
W="$1"; ID=20261111-000000-minimale-at_least_once-normale; S=runtime/sujet11/$ID
mkdir -p "$W/runtime/sujet11/verrou" "$W/$S"
echo $ID > "$W/runtime/sujet11/verrou/essai"; echo $S > "$W/runtime/sujet11/verrou/sortie"
T=0
fin() { [ "$T" = 1 ] || echo interrompu > "$W/$S/phase"; rm -rf "$W/runtime/sujet11/verrou"; }
trap fin EXIT
trap 'exit 130' TERM
echo "[sujet11] essai $ID : 3000 Pix à 20 Pix/s, sortie $S"
echo lance > "$W/$S/phase"
sleep "${DUREE:-0}"
[ -n "$CODE" ] && exit "$CODE"
echo " VERDICT : REUSSITE"
T=1; echo termine > "$W/$S/phase"
'''


def espace():
    ws = tempfile.mkdtemp()
    script = os.path.join(ws, "faux.sh")
    with open(script, "w") as f:
        f.write(FAUX_SCRIPT)
    return ws, ["/bin/sh", script, ws]


def phase(ws):
    with open(os.path.join(ws, "runtime/sujet11/20261111-000000-minimale-at_least_once-normale/phase")) as f:
        return f.read().strip()


CONTEXTE = {"lancement": "L1", "qui": "prof", "scenario": "minimale", "semantique": "at_least_once", "charge": "normale"}


class Reponse(io.BytesIO):
    pass


def grafana(role="Editor", login="prof", admin=False):
    """Faux Grafana : /api/user et /api/user/orgs."""
    def ouvrir(req, timeout=3):
        if "grafana_session=bon" not in req.headers.get("Cookie", ""):
            raise OSError("401")
        if req.full_url.endswith("/api/user"):
            return Reponse(json.dumps({"login": login, "orgId": 1, "isGrafanaAdmin": admin}).encode())
        return Reponse(json.dumps([{"orgId": 1, "role": role}]).encode())
    return ouvrir


ENTETES = {"Origin": "http://localhost:8083", "Cookie": "grafana_session=bon"}


class AutorisationTest(unittest.TestCase):
    def test_editeur_connecte_peut_lancer(self):
        ok, msg, u = pilotage.autoriser("sujet11_essai", {"mode": ["minimale"]}, ENTETES, grafana())
        self.assertTrue(ok, msg)
        self.assertEqual(u, {"login": "prof", "role": "Editor"})

    def test_sans_session_grafana_refuse(self):
        ok, msg, _ = pilotage.autoriser("sujet11_essai", {}, {"Origin": "http://localhost:8083"}, grafana())
        self.assertFalse(ok)
        self.assertIn("connectez-vous", msg)

    def test_session_invalide_refusee(self):
        ok, _, _ = pilotage.autoriser("sujet11_essai", {}, ENTETES | {"Cookie": "grafana_session=faux"}, grafana())
        self.assertFalse(ok)

    def test_lecteur_seul_refuse(self):
        ok, msg, _ = pilotage.autoriser("sujet11_essai", {}, ENTETES, grafana(role="Viewer"))
        self.assertFalse(ok)
        self.assertIn("rôle Viewer", msg)

    def test_page_tierce_refusee(self):
        for entetes in ({"Origin": "http://evil.example", "Cookie": "grafana_session=bon"},
                        {"Cookie": "grafana_session=bon"},
                        {"Origin": "http://localhost:3000", "Cookie": "grafana_session=bon"}):
            ok, msg, _ = pilotage.autoriser("sujet11_essai", {}, entetes, grafana())
            self.assertFalse(ok, entetes)
            self.assertIn("page de pilotage", msg)

    def test_panne_et_arret_demandent_une_confirmation(self):
        for action, form in (("sujet11_essai", {"mode": ["crash"]}), ("sujet11_arreter", {})):
            self.assertFalse(pilotage.autoriser(action, form, ENTETES, grafana())[0])
            self.assertTrue(pilotage.autoriser(action, form | {"confirmation": ["oui"]}, ENTETES, grafana())[0])


class ScenariosTest(unittest.TestCase):
    def test_scenarios_traduits_vers_le_script(self):
        for nom, mode, charge in (("minimale", "minimale", "normale"), ("charge_forte", "minimale", "forte"),
                                  ("panne", "crash", "normale")):
            form = {"scenario": [nom], "semantique": ["at_most_once"],
                    "charge": [pilotage.SCENARIOS[nom]["charges"][0]]}
            self.assertEqual(pilotage.traduire_scenario(form), (True, ""))
            self.assertEqual((form["mode"], form["charge"]), ([mode], [charge]))

    def test_combinaisons_non_proposees_refusees(self):
        for form in ({"scenario": ["inconnu"], "semantique": ["at_least_once"]},
                     {"scenario": ["minimale"], "semantique": ["exactly_once_kafka"]},
                     {"scenario": ["panne"], "semantique": ["at_least_once"], "charge": ["forte"]},
                     {"scenario": ["charge_forte"], "semantique": ["at_least_once"], "charge": ["normale"]}):
            self.assertFalse(pilotage.traduire_scenario(form)[0], form)

    def test_la_commande_finale_reste_celle_de_la_liste_blanche(self):
        form = {"action": ["sujet11_essai"], "scenario": ["panne"], "semantique": ["at_most_once"], "charge": ["ralentie"]}
        pilotage.traduire_scenario(form)
        ok, _, commande, _ = scenario_control.build_control_job(form)
        self.assertTrue(ok)
        self.assertEqual(commande[:4], ["/bin/sh", "./scripts/sujet11-maj.sh", "--mode", "crash"])
        self.assertIn("--drainage-max", commande)


class ExecutionTest(unittest.TestCase):
    def test_essai_valide_jusqu_au_bout(self):
        ws, cmd = espace()
        ok, _ = pilotage.executer_essai(cmd, ws, dict(os.environ), ws, CONTEXTE, delai_s=30)
        self.assertTrue(ok)
        self.assertEqual(phase(ws), "termine")
        h = pilotage.lire_historique(ws)[0]
        self.assertEqual((h["issue"], h["essai"], h["qui"]), ("REUSSITE", "20261111-000000-minimale-at_least_once-normale", "prof"))
        self.assertFalse(os.path.exists(os.path.join(ws, "runtime/sujet11/verrou")))
        self.assertTrue(os.path.exists(os.path.join(ws, h["journal"])))

    def test_fin_de_delai_arrete_proprement(self):
        ws, cmd = espace()
        ok, _ = pilotage.executer_essai(cmd, ws, dict(os.environ, DUREE="30"), ws, CONTEXTE, delai_s=1)
        self.assertFalse(ok)
        self.assertEqual(phase(ws), "interrompu")
        self.assertEqual(pilotage.lire_historique(ws)[0]["issue"], "fin de délai, arrêté")
        self.assertFalse(os.path.exists(os.path.join(ws, "runtime/sujet11/verrou")))

    def test_erreur_du_service_d_execution(self):
        ws, cmd = espace()
        ok, _ = pilotage.executer_essai(cmd, ws, dict(os.environ, CODE="3"), ws, CONTEXTE, delai_s=30)
        self.assertFalse(ok)
        self.assertEqual(pilotage.lire_historique(ws)[0]["issue"], "erreur (code 3)")

    def test_interruption_controlee(self):
        ws, cmd = espace()
        t = threading.Thread(target=pilotage.executer_essai,
                             args=(cmd, ws, dict(os.environ, DUREE="30"), ws, CONTEXTE, 60))
        t.start()
        for _ in range(50):
            if os.path.exists(os.path.join(ws, "runtime/sujet11/pilotage-processus.json")) and \
                    os.path.exists(os.path.join(ws, "runtime/sujet11/verrou/essai")):
                break
            time.sleep(0.1)
        resultat, message = pilotage.arreter(ws)
        t.join(10)
        self.assertEqual(resultat, "stop", message)
        self.assertEqual(phase(ws), "interrompu")
        self.assertEqual(pilotage.lire_historique(ws)[0]["issue"], "interrompu")

    def test_rien_a_arreter(self):
        ws, _ = espace()
        self.assertEqual(pilotage.arreter(ws), ("error", "Aucun essai en cours."))

    def test_essai_du_terminal_ne_peut_pas_etre_arrete_ici(self):
        ws, _ = espace()
        os.makedirs(os.path.join(ws, "runtime/sujet11/verrou"))
        with open(os.path.join(ws, "runtime/sujet11/verrou/essai"), "w") as f:
            f.write("20261111-000000-minimale-at_least_once-normale")
        self.assertIn("terminal", pilotage.arreter(ws)[1])


class RedemarrageTest(unittest.TestCase):
    def test_essai_coupe_par_un_redemarrage_est_marque_interrompu(self):
        ws, _ = espace()
        sortie = "runtime/sujet11/20261111-000000-minimale-at_least_once-normale"
        os.makedirs(os.path.join(ws, sortie))
        os.makedirs(os.path.join(ws, "runtime/sujet11/verrou"))
        for nom, contenu in (("verrou/essai", "x"), ("verrou/sortie", sortie)):
            with open(os.path.join(ws, "runtime/sujet11", nom), "w") as f:
                f.write(contenu)
        with open(os.path.join(ws, sortie, "phase"), "w") as f:
            f.write("drainage")
        with open(os.path.join(ws, "runtime/sujet11/pilotage-processus.json"), "w") as f:
            json.dump({"pid": 999999, "lancement": "L9", "api": 1.0}, f)  # API d'avant le redémarrage
        self.assertEqual(pilotage.reprise_au_demarrage(ws), sortie)
        self.assertEqual(phase(ws), "interrompu")
        self.assertFalse(os.path.exists(os.path.join(ws, "runtime/sujet11/verrou")))
        self.assertIn("redémarré", pilotage.lire_historique(ws)[0]["issue"])

    def test_essai_du_terminal_jamais_touche(self):
        ws, _ = espace()
        os.makedirs(os.path.join(ws, "runtime/sujet11/verrou"))
        self.assertIsNone(pilotage.reprise_au_demarrage(ws))
        self.assertTrue(os.path.exists(os.path.join(ws, "runtime/sujet11/verrou")))


class ConcurrenceTest(unittest.TestCase):
    def test_double_clic_et_deux_utilisateurs_un_seul_lancement(self):
        ws, cmd = espace()
        resultats = []
        faux = lambda form: (True, "sujet11_essai:minimale:at_least_once:normale", cmd,  # noqa: E731
                             {"DUREE": "2", "SIMULPIX_CONTROL_TIMEOUT_SECONDS": "30"})
        with mock.patch.object(scenario_control, "build_control_job", faux), \
                mock.patch.dict(os.environ, {"SIMULPIX_WORKSPACE_DIR": ws}):
            form = {"action": ["sujet11_essai"], "_qui": ["prof"]}
            fils = [threading.Thread(target=lambda: resultats.append(scenario_control.execute_control_action(dict(form))))
                    for _ in range(5)]
            for f in fils:
                f.start()
            for f in fils:
                f.join()
            self.assertEqual(sorted(r[0] for r in resultats), ["accepted", "busy", "busy", "busy", "busy"])
            for _ in range(60):  # le lancement accepté finit, et rend la main
                if scenario_control.CONTROL_LOCK.acquire(blocking=False):
                    scenario_control.CONTROL_LOCK.release()
                    break
                time.sleep(0.1)
            self.assertEqual(phase(ws), "termine")

    def test_scenario_deja_en_cours_refuse(self):
        ws, _ = espace()
        os.makedirs(os.path.join(ws, "runtime/sujet11/verrou"))
        with open(os.path.join(ws, "runtime/sujet11/verrou/essai"), "w") as f:
            f.write("20261111-000000-minimale-at_least_once-normale")
        with mock.patch.dict(os.environ, {"SIMULPIX_WORKSPACE_DIR": ws}):
            self.assertEqual(scenario_control.execute_control_action({"action": ["sujet11_essai"]})[0], "busy")


class PageTest(unittest.TestCase):
    def test_non_connecte_bouton_desactive(self):
        ws, _ = espace()
        page = pilotage.rendre_pilotage(ws, None)
        self.assertIn("Non connecté", page)
        self.assertIn("disabled>Lancer l'essai", page)

    def test_lecteur_bouton_desactive(self):
        ws, _ = espace()
        page = pilotage.rendre_pilotage(ws, {"login": "eleve", "role": "Viewer"})
        self.assertIn("rôle Editor ou Admin", page)
        self.assertIn("disabled>Lancer l'essai", page)

    def test_scenarios_et_parametres_de_la_configuration(self):
        ws, _ = espace()
        page = pilotage.rendre_pilotage(ws, {"login": "prof", "role": "Admin"})
        for s in pilotage.SCENARIOS.values():
            self.assertIn(s["titre"], page)
        self.assertIn("data-charges='ralentie' data-confirmation='1'", page)
        self.assertNotIn("disabled>Lancer", page)

    def test_suivi_pendant_un_essai_sans_pourcentage_invente(self):
        ws, cmd = espace()
        t = threading.Thread(target=pilotage.executer_essai, args=(cmd, ws, dict(os.environ, DUREE="3"), ws, CONTEXTE, 30))
        t.start()
        for _ in range(50):
            if os.path.exists(os.path.join(ws, "runtime/sujet11/verrou/essai")):
                break
            time.sleep(0.1)
        statut = pilotage.rendre_statut(ws, {"login": "prof", "role": "Admin"}, {"kafka": "ok", "postgres": "ok"})
        t.join(10)
        self.assertIn("Essai en cours", statut)
        self.assertIn("class='encours'", statut)
        self.assertIn("non disponible", statut)  # pas encore de compteurs : jamais de zéro inventé
        self.assertIn("calculés à la fin de l'essai", statut)
        self.assertNotIn("%", statut)
        self.assertIn("Arrêter l'essai", statut)

    def test_dernier_lancement_interrompu_sans_verdict(self):
        ws, cmd = espace()
        pilotage.executer_essai(cmd, ws, dict(os.environ, DUREE="30"), ws, CONTEXTE, delai_s=1)
        statut = pilotage.rendre_statut(ws, None, None)
        self.assertIn("fin de délai, arrêté", statut)
        self.assertIn("pas de verdict", statut)


if __name__ == "__main__":
    unittest.main()
