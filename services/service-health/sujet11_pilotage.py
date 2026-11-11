"""Sujet 11 : contrôle des scénarios expérimentaux depuis Grafana.

Réutilise le lancement existant (action sujet11_essai de scenario_control.py,
liste blanche et commande fixe du script scripts/sujet11-maj.sh) et ajoute ce
qui manquait pour qu'un enseignant lance un essai sans terminal :

  - autoriser()      : contrôle de l'origine de la requête, de la session
                       Grafana (rôle Editor ou Admin) et de la confirmation ;
  - executer_essai() : lancement dans un groupe de processus, arrêt propre
                       (SIGTERM, puis SIGKILL 20 s plus tard) en fin de délai ;
  - arreter()        : interruption contrôlée de l'essai lancé ici ;
  - reprise_au_demarrage() : un essai coupé par un redémarrage du service est
                       marqué « interrompu » et son verrou libéré ;
  - historique des lancements (runtime/sujet11/lancements.jsonl) ;
  - la page /sujet11/pilotage et son suivi /sujet11/pilotage/statut.

Ne touche jamais aux preuves (preuves/), ni aux bornes, ni au script d'essai.
"""
from __future__ import annotations

import glob
import json
import os
import re
import signal
import subprocess
import time
import urllib.request
from typing import Any, Callable

from sujet11_etat import essai_en_cours
from sujet11_synthese import FOND, STYLE, _e, _essai, _heure

GRAFANA = os.getenv("SUJET11_GRAFANA_URL", "http://grafana:3000")
ORIGINES = {"http://localhost:8083", "http://127.0.0.1:8083"}
ROLES_AUTORISES = {"Admin", "Editor"}
DEMARRAGE_API = time.time()
DELAI_ARRET_S = 20

COURT = {"at_least_once": "at-least-once", "at_most_once": "at-most-once", "exactly_once_pg": "exactly-once PostgreSQL"}
SEMANTIQUES = {"at_least_once": "at-least-once (notre solution)",
               "at_most_once": "at-most-once (contre-exemple)",
               "exactly_once_pg": "exactly-once PostgreSQL (comparaison)"}
CHARGES = {"normale": "normale (20 paiements/s)", "forte": "forte (60 paiements/s)",
           "ralentie": "ralentie (10 paiements/s, 80 ms ajoutées), réglage fixe de la panne"}
# Les combinaisons proposées sont celles que build_control_job accepte (scenario_control.py).
SCENARIOS = {
    "minimale": {"titre": "Mise à jour minimale", "mode": "minimale", "charges": ["normale", "forte"],
                 "duree": "5 à 6 min", "confirmation": False,
                 "texte": "Une seule instance du programme est remplacée. Il y a une courte interruption, "
                          "qui doit rester sous 60 s, sans perte ni double effet."},
    "amelioree": {"titre": "Mise à jour améliorée", "mode": "amelioree", "charges": ["normale", "forte"],
                  "duree": "5 à 6 min", "confirmation": False,
                  "texte": "Une deuxième instance démarre, puis l'ancienne s'arrête proprement : pas "
                           "d'interruption mesurable attendue."},
    "charge_forte": {"titre": "Charge forte", "mode": "minimale", "charges": ["forte"],
                     "duree": "5 à 6 min", "confirmation": False,
                     "texte": "La mise à jour minimale, avec trois fois plus de paiements par seconde."},
    "panne": {"titre": "Panne brutale", "mode": "crash", "charges": ["ralentie"],
              "duree": "environ 7 min", "confirmation": True,
              "texte": "Ce n'est pas une solution : le programme est tué sans prévenir. Sert à comparer "
                       "les sémantiques (perte possible en at-most-once)."},
}


def _chemin(workspace: str, *morceaux: str) -> str:
    return os.path.join(workspace, "runtime", "sujet11", *morceaux)


# ---------------------------------------------------------------- autorisation

def lire_utilisateur(cookie: str, ouvrir: Callable = urllib.request.urlopen) -> dict | None:
    """Utilisateur Grafana de cette session (cookie du navigateur), ou None.

    Le cookie grafana_session est envoyé par le navigateur à localhost:8083 (même
    hôte que Grafana) : on demande à Grafana qui c'est et quel est son rôle.
    """
    if not cookie or "grafana_session=" not in cookie:
        return None
    entetes = {"Cookie": cookie}
    try:
        u = json.load(ouvrir(urllib.request.Request(f"{GRAFANA}/api/user", headers=entetes), timeout=3))
        orgs = json.load(ouvrir(urllib.request.Request(f"{GRAFANA}/api/user/orgs", headers=entetes), timeout=3))
    except Exception:
        return None
    role = next((o.get("role") for o in orgs if o.get("orgId") == u.get("orgId")), None)
    return {"login": u.get("login"), "role": "Admin" if u.get("isGrafanaAdmin") else role}


def origine_acceptee(entetes: dict) -> bool:
    """La requête vient-elle de la page de pilotage elle-même ? (contre les pages tierces)"""
    origine = entetes.get("Origin")
    if origine:
        return origine in ORIGINES
    referent = entetes.get("Referer") or ""
    return any(referent.startswith(o + "/") for o in ORIGINES)


def autoriser(action: str, form: dict, entetes: dict, ouvrir: Callable = urllib.request.urlopen) -> tuple[bool, str, dict | None]:
    """Contrôles avant toute action sujet11_*. Renvoie (accepté, message, utilisateur)."""
    if not origine_acceptee(entetes):
        return False, "Refusé : la demande ne vient pas de la page de pilotage.", None
    utilisateur = lire_utilisateur(entetes.get("Cookie", ""), ouvrir)
    if not utilisateur:
        return False, "Refusé : connectez-vous d'abord à Grafana (http://localhost:3000).", None
    if utilisateur["role"] not in ROLES_AUTORISES:
        return False, (f"Refusé : le compte {utilisateur['login']} a le rôle {utilisateur['role']} ; il faut "
                       "le rôle Editor ou Admin pour lancer ou arrêter un essai."), utilisateur
    sensible = action == "sujet11_arreter" or _valeur(form, "mode") == "crash"
    if sensible and _valeur(form, "confirmation") != "oui":
        return False, "Refusé : cochez la case de confirmation pour cette action.", utilisateur
    return True, "", utilisateur


def _valeur(form: dict, nom: str, defaut: str = "") -> str:
    v = form.get(nom)
    return (v[0] if isinstance(v, list) and v else v if isinstance(v, str) else defaut).strip()


def traduire_scenario(form: dict) -> tuple[bool, str]:
    """Scénario choisi → mode et charge du script. Refuse une combinaison non proposée."""
    nom = _valeur(form, "scenario")
    if not nom:
        return True, ""  # ancien formulaire (mode, semantique, charge) : vérifié par build_control_job
    s = SCENARIOS.get(nom)
    if not s:
        return False, "Refusé : scénario inconnu."
    semantique, charge = _valeur(form, "semantique"), _valeur(form, "charge", s["charges"][0])
    if semantique not in SEMANTIQUES:
        return False, "Refusé : mode de livraison inconnu."
    if charge not in s["charges"]:
        return False, f"Refusé : la charge « {charge} » n'est pas proposée pour ce scénario."
    form["mode"], form["charge"] = [s["mode"]], [charge if charge != "ralentie" else "normale"]
    return True, ""


# ---------------------------------------------------------------- historique

def journaliser(workspace: str, **entree: Any) -> None:
    """Ajoute une ligne à runtime/sujet11/lancements.jsonl (jamais réécrit)."""
    os.makedirs(_chemin(workspace), exist_ok=True)
    with open(_chemin(workspace, "lancements.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": round(time.time(), 3)} | entree, ensure_ascii=False) + "\n")


def lire_historique(workspace: str, n: int = 8) -> list[dict]:
    try:
        with open(_chemin(workspace, "lancements.jsonl"), encoding="utf-8") as f:
            lignes = [json.loads(l) for l in f if l.strip()]
    except (OSError, ValueError):
        return []
    # une ligne « lance » puis une ligne « fin » par essai : on regroupe par numéro de lancement
    par_numero: dict[str, dict] = {}
    for l in lignes:
        par_numero.setdefault(l.get("lancement", ""), {}).update(l)
    return sorted(par_numero.values(), key=lambda x: x.get("debut", x["t"]), reverse=True)[:n]


# ---------------------------------------------------------------- exécution

def _processus(workspace: str) -> dict | None:
    try:
        with open(_chemin(workspace, "pilotage-processus.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _vivant(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def executer_essai(command: list[str], workdir: str, env: dict, workspace: str, contexte: dict,
                   delai_s: int) -> tuple[bool, list[str]]:
    """Lance le script d'essai dans son propre groupe de processus, avec un journal.

    En fin de délai : SIGTERM au groupe (le script marque l'essai « interrompu » et
    libère son verrou), puis SIGKILL si rien ne s'est arrêté au bout de 20 s.
    """
    numero = contexte["lancement"]
    os.makedirs(_chemin(workspace, "lancements"), exist_ok=True)
    journal = _chemin(workspace, "lancements", f"{numero}.log")
    with open(journal, "w", encoding="utf-8") as sortie:
        p = subprocess.Popen(command, cwd=workdir, env=env, stdout=sortie, stderr=subprocess.STDOUT,
                             start_new_session=True)
        with open(_chemin(workspace, "pilotage-processus.json"), "w", encoding="utf-8") as f:
            json.dump({"pid": p.pid, "lancement": numero, "api": DEMARRAGE_API, "debut": time.time()}, f)
        journaliser(workspace, etat="lance", debut=time.time(), journal=os.path.relpath(journal, workspace), **contexte)
        fin_de_delai = False
        try:
            code = p.wait(timeout=delai_s)
        except subprocess.TimeoutExpired:
            fin_de_delai = True
            _signaler(p.pid, signal.SIGTERM)
            try:
                code = p.wait(timeout=DELAI_ARRET_S)
            except subprocess.TimeoutExpired:
                _signaler(p.pid, signal.SIGKILL)
                code = p.wait()
    texte = open(journal, encoding="utf-8", errors="replace").read()
    m = re.search(r"essai (\S+) : .* sortie (\S+)", texte)
    verdict = re.findall(r"VERDICT : (\w+)", texte)
    try:
        os.remove(_chemin(workspace, "pilotage-processus.json"))
    except OSError:
        pass
    issue = ("fin de délai, arrêté" if fin_de_delai else verdict[-1] if verdict else
             "interrompu" if code in (130, -signal.SIGTERM, 143) else f"erreur (code {code})")
    journaliser(workspace, lancement=numero, etat="fin", code=code, issue=issue,
                essai=m.group(1) if m else None, sortie=m.group(2) if m else None)
    lignes = [l for l in texte.splitlines() if l.strip()]
    return code == 0, lignes[-20:] or ["[sujet11] pas de sortie"]


def _signaler(pid: int, sig: int) -> None:
    try:
        os.killpg(os.getpgid(pid), sig)
    except OSError:
        pass


def arreter(workspace: str) -> tuple[str, str]:
    """Interruption contrôlée de l'essai lancé depuis le pilotage. Renvoie (résultat, message)."""
    proc = _processus(workspace)
    if proc and proc.get("api") == DEMARRAGE_API and _vivant(proc["pid"]):
        _signaler(proc["pid"], signal.SIGTERM)
        journaliser(workspace, lancement=proc["lancement"], etat="arret_demande")
        return "stop", "Arrêt demandé : l'essai s'arrête proprement et sera marqué « interrompu »."
    if essai_en_cours(workspace):
        return "error", ("Cet essai a été lancé depuis un terminal : arrêtez-le dans ce terminal "
                         "(Ctrl+C).")
    return "error", "Aucun essai en cours."


def reprise_au_demarrage(workspace: str) -> str | None:
    """Au démarrage du service : un essai lancé ici avant un redémarrage n'a pas pu se terminer.

    Il est marqué « interrompu » (phase, historique), et son verrou est libéré s'il
    lui appartient. Un essai lancé depuis un terminal n'est jamais touché.
    """
    proc = _processus(workspace)
    if not proc or proc.get("api") == DEMARRAGE_API:
        return None
    sortie = None
    try:
        sortie = open(_chemin(workspace, "verrou", "sortie"), encoding="utf-8").read().strip()
    except OSError:
        pass
    if sortie:
        phase = os.path.join(workspace, sortie, "phase")
        try:
            actuelle = open(phase, encoding="utf-8").read().strip()
        except OSError:
            actuelle = ""
        if actuelle != "termine" and os.path.isdir(os.path.dirname(phase)):
            with open(phase, "w", encoding="utf-8") as f:
                f.write("interrompu")
        verrou = _chemin(workspace, "verrou")
        for nom in ("essai", "sortie"):
            try:
                os.remove(os.path.join(verrou, nom))
            except OSError:
                pass
        try:
            os.rmdir(verrou)
        except OSError:
            pass
    journaliser(workspace, lancement=proc.get("lancement"), etat="fin", code=None,
                issue="interrompu (service redémarré pendant l'essai)", sortie=sortie)
    try:
        os.remove(_chemin(workspace, "pilotage-processus.json"))
    except OSError:
        pass
    return sortie or "?"


# ---------------------------------------------------------------- page

PHASES = [("lance", "Paiements envoyés, fonctionnement normal"), ("mise_a_jour", "Mise à jour du programme"),
          ("drainage", "Rattrapage des paiements en attente"), ("collecte", "Vérification dans PostgreSQL"),
          ("termine", "Terminé")]
CSS = STYLE + """
.cols{display:grid;grid-template-columns:3fr 2fr;gap:16px;align-items:start}
.choix{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.choix label{display:block;background:var(--carte);border:2px solid var(--bord);border-radius:10px;
  padding:10px 12px;cursor:pointer}
.choix input{margin-right:6px}
.choix label:has(input:checked){border-color:var(--bleu)}
.choix b{font-size:19px}.choix small{display:block;margin-top:4px}
.ligne{display:flex;flex-wrap:wrap;gap:16px;align-items:center;margin:12px 0}
select{font-size:17px;padding:6px 8px;border-radius:8px}
.bouton{font-size:18px;font-weight:700;padding:10px 20px;border:0;border-radius:8px;color:#fff;cursor:pointer}
.bouton:disabled{opacity:.45;cursor:not-allowed}
.resume{background:var(--carte);border:1px solid var(--bord);border-radius:10px;padding:10px 12px}
.etapes2{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}
.etapes2 span{padding:4px 8px;border-radius:6px;border:2px solid var(--bord);font-size:15px}
.etapes2 .faite{border-color:var(--vert)}.etapes2 .encours{border-color:var(--bleu);font-weight:700}
"""


def _message(texte: str, genre: str) -> str:
    if not texte:
        return ""
    fond = {"ok": "vert", "erreur": "rouge", "info": "bleu"}.get(genre, "gris")
    return f"<div class='bandeau' style='background:{FOND[fond]}'><b>{_e(texte)}</b></div>"


def rendre_statut(workspace: str, utilisateur: dict | None, services: dict | None = None) -> str:
    """Fragment de suivi, rechargé toutes les 3 s par la page (sans recharger le formulaire)."""
    en_cours = essai_en_cours(workspace)
    proc = _processus(workspace)
    if services:
        ko = sorted(k for k, v in services.items() if v != "ok")
        etat_services = (f"Services : {len(services) - len(ko)} sur {len(services)} en marche"
                         + (f" (problème : {_e(', '.join(ko))})" if ko else "") + ".")
    else:
        etat_services = "Services : état non disponible."
    if en_cours:
        try:
            sortie = open(_chemin(workspace, "verrou", "sortie"), encoding="utf-8").read().strip()
        except OSError:
            sortie = os.path.join("runtime", "sujet11", en_cours["id"])
        dossier = os.path.join(workspace, sortie)
        try:
            phase = open(os.path.join(dossier, "phase"), encoding="utf-8").read().strip()
        except OSError:
            phase = ""
        rangs = [p for p, _ in PHASES]
        i = rangs.index(phase) if phase in rangs else -1
        etapes = "".join(f"<span class='{'faite' if k < i else 'encours' if k == i else ''}'>{_e(t)}</span>"
                         for k, (_, t) in enumerate(PHASES))
        c = {}
        try:
            lignes = [l for l in open(os.path.join(dossier, "compteurs.jsonl"), encoding="utf-8") if l.strip()]
            c = json.loads(lignes[-1]) if lignes else {}
        except (OSError, ValueError):
            pass
        nd = lambda x: "non disponible" if x is None else _e(x)  # noqa: E731
        lance_ici = proc and proc.get("api") == DEMARRAGE_API
        arret = ("<form method='post' action='/control'><input type='hidden' name='action' value='sujet11_arreter'>"
                 "<input type='hidden' name='return_view' value='pilotage'><label><input type='checkbox' "
                 "name='confirmation' value='oui' required> je confirme l'arrêt</label> <button class='bouton' "
                 f"style='background:{FOND['orange']}' onclick='this.form.requestSubmit();this.disabled=true'>"
                 "Arrêter l'essai</button></form>" if lance_ici and utilisateur else
                 "<p class='note'>Essai lancé depuis un terminal : il s'arrête depuis ce terminal.</p>"
                 if not lance_ici else "")
        return (f"<div class='bandeau' style='background:{FOND['bleu']}'><b>Essai en cours</b>"
                f"{_e(en_cours['id'])}, depuis {_e(en_cours.get('debut') or '?')}.</div>"
                f"<div class='etapes2'>{etapes}</div>"
                f"<p>Paiements envoyés : <b>{nd(c.get('generated'))}</b> ; validés : <b>{nd(c.get('validated_topic_end_offsets'))}</b> ; "
                f"enregistrés en base : <b>{nd(c.get('db_validated_count'))}</b> ; en attente : <b>{nd(c.get('ecart_topic_base'))}</b>.</p>"
                "<p class='note'>Pertes, doubles effets et durées (interruption, reprise, retour à la normale) "
                "sont calculés à la fin de l'essai, à partir de PostgreSQL : ils ne sont pas connus avant.</p>"
                f"<p class='note'>{etat_services}</p>{arret}")
    hist = lire_historique(workspace, 1)
    if not hist:
        return f"<p>Aucun essai lancé depuis cette page pour l'instant.</p><p class='note'>{etat_services}</p>"
    h = hist[0]
    essai = _essai(os.path.join(workspace, h["sortie"])) if h.get("sortie") else None
    if essai:
        r = essai["resultat"]
        v = r.get("verdict")
        fond = {"REUSSITE": "vert", "ECHEC": "rouge", "INVALIDE": "gris"}.get(v, "bleu")
        mot = {"REUSSITE": "Garantie respectée", "ECHEC": "Garantie NON respectée",
               "INVALIDE": "Mesure non valide (ni réussite, ni échec)"}.get(v, v)
        oc = r["oracle"]["continuite"]
        raisons = "".join(f"<li>{_e(x)}</li>" for x in r.get("raisons") or [])
        lien = f"/sujet11/synthese?vue=ensemble&essai={_e(h['sortie'])}"
        return (f"<div class='bandeau' style='background:{FOND[fond]}'><b>Dernier essai lancé ici : {_e(mot)}</b>"
                f"{_e(essai['meta'].get('id'))}{'<ul>' + raisons + '</ul>' if raisons else ''}</div>"
                f"<p>Paiements attendus : <b>{_e(oc.get('attendus'))}</b> ; enregistrés : "
                f"<b>{_e(oc['classes'].get('present'))}</b> ; pertes : <b>{_e(oc['classes'].get('perdu'))}</b> ; "
                f"doubles effets : <b>{_e(oc.get('doubles_effets', 'non mesuré'))}</b> ; interruption : "
                f"<b>{_e(r['pause'].get('pause_s'))} s</b>.</p>"
                f"<p><a href='{lien}' target='_blank'>Voir le détail de cet essai</a></p><p class='note'>{etat_services}</p>")
    issue = h.get("issue") or ("en cours" if h.get("etat") == "lance" else "?")
    return (f"<div class='bandeau' style='background:{FOND['orange']}'><b>Dernier essai lancé ici : {_e(issue)}</b>"
            "Il n'a pas de verdict (essai interrompu ou erreur avant la fin).</div>"
            f"<p class='note'>Journal : {_e(h.get('journal', '?'))}. {etat_services}</p>")


def rendre_pilotage(workspace: str, utilisateur: dict | None, message: str = "", genre: str = "") -> str:
    """Page de pilotage : choisir, vérifier, confirmer, lancer ; suivi et historique."""
    autorise = bool(utilisateur and utilisateur.get("role") in ROLES_AUTORISES)
    choix = "".join(
        f"<label><input type='radio' name='scenario' value='{k}' {'checked' if k == 'minimale' else ''} "
        f"data-charges='{','.join(s['charges'])}' data-confirmation='{int(s['confirmation'])}' "
        f"data-titre='{_e(s['titre'])}' data-duree='{_e(s['duree'])}'><b>{_e(s['titre'])}</b>"
        f"<small>{_e(s['texte'])} Durée : {_e(s['duree'])}.</small></label>" for k, s in SCENARIOS.items())
    sem = "".join(f"<option value='{k}'>{_e(v)}</option>" for k, v in SEMANTIQUES.items())
    ch = "".join(f"<option value='{k}'>{_e(v)}</option>" for k, v in CHARGES.items())
    if autorise:
        qui = f"Connecté : <b>{_e(utilisateur['login'])}</b> ({_e(utilisateur['role'])})."
    elif utilisateur:
        qui = (f"Connecté : {_e(utilisateur['login'])} ({_e(utilisateur['role'])}). Il faut le rôle Editor ou Admin "
               "pour lancer un essai.")
    else:
        qui = "Non connecté : ouvrez cette page depuis Grafana, après vous être connecté, pour lancer un essai."
    historique = "".join(
        f"<tr><td>{_heure(h.get('debut') or h.get('t'))}</td><td>{_e(h.get('qui', '?'))}</td>"
        f"<td>{_e(SCENARIOS.get(h.get('scenario'), {}).get('titre', h.get('scenario', '?')))}</td>"
        f"<td>{_e(COURT.get(h.get('semantique'), h.get('semantique', '')))}</td><td>{_e(h.get('charge', ''))}</td>"
        f"<td>{_e(h.get('issue') or ('en cours' if h.get('etat') in ('lance', 'arret_demande') else '?'))}</td>"
        f"<td>{_lien_essai(workspace, h)}</td></tr>" for h in lire_historique(workspace))
    publies = "".join(
        f"<option value='{_e(os.path.relpath(e['dossier'], workspace))}'>{_e(e['meta']['id'])} "
        f"({_e(e['resultat'].get('verdict'))})</option>"
        for e in sorted(_tous_publies(workspace), key=lambda e: e["meta"]["id"], reverse=True))
    return ("<!doctype html><html lang='fr'><head><meta charset='utf-8'><meta name='color-scheme' content='light dark'>"
            f"<style>{CSS}</style></head><body>"
            + _message(message, genre)
            + f"<p class='contexte'>{qui} Un seul essai à la fois ; chaque essai repart de données vides et ne "
              "touche jamais aux preuves publiées.</p>"
            "<div class='cols'><div>"
            "<form id='lancer' method='post' action='/control'>"
            "<input type='hidden' name='action' value='sujet11_essai'><input type='hidden' name='return_view' value='pilotage'>"
            f"<div class='choix'>{choix}</div>"
            f"<div class='ligne'><label>Mode de livraison <select name='semantique' id='semantique'>{sem}</select></label>"
            f"<label id='bloc-charge'>Charge <select name='charge' id='charge'>{ch}</select></label></div>"
            "<div class='resume' id='resume'></div>"
            "<div class='ligne'><label id='bloc-confirmation' style='display:none'><input type='checkbox' "
            "name='confirmation' value='oui' id='confirmation'> je confirme : le programme sera tué sans prévenir"
            "</label><button class='bouton' id='bouton' type='submit' style='background:" + FOND["vert"] + "' "
            + ("" if autorise else "disabled") + ">Lancer l'essai</button></div></form>"
            "</div><div><h3 class='titre2' style='margin-top:0'>Suivi de l'essai</h3><div id='statut'>chargement…</div>"
            "</div></div>"
            "<h3 class='titre2'>Derniers lancements depuis cette page</h3><table class='tab'><tr><th>quand</th><th>qui</th>"
            "<th>scénario</th><th>mode</th><th>charge</th><th>issue</th><th></th></tr>"
            + (historique or "<tr><td colspan='7'>aucun</td></tr>") + "</table>"
            "<div class='ligne'><label>Consulter un essai publié <select id='ancien'><option value=''>choisir…</option>"
            + publies + "</select></label><a id='voir' href='#' target='_blank'>ouvrir</a></div>"
            "<script>"
            "const f=document.getElementById('lancer'),b=document.getElementById('bouton');"
            "function maj(){const s=f.querySelector('input[name=scenario]:checked');"
            "const charges=s.dataset.charges.split(','),c=document.getElementById('charge');"
            "for(const o of c.options){o.hidden=!charges.includes(o.value)}"
            "if(!charges.includes(c.value)){c.value=charges[0]}"
            "document.getElementById('bloc-charge').style.display=charges.length>1?'':'none';"
            "const conf=s.dataset.confirmation==='1';document.getElementById('bloc-confirmation').style.display=conf?'':'none';"
            "document.getElementById('confirmation').required=conf;"
            "const sem=document.getElementById('semantique');"
            "document.getElementById('resume').innerHTML='<b>Résumé</b> : '+s.dataset.titre+', '+sem.options[sem.selectedIndex].text"
            "+', charge '+c.options[c.selectedIndex].text+'. Durée : '+s.dataset.duree+'.'}"
            "f.addEventListener('change',maj);maj();"
            "f.addEventListener('submit',()=>{b.disabled=true;b.textContent='Lancement…'});"
            "document.getElementById('ancien').addEventListener('change',e=>{document.getElementById('voir').href="
            "'/sujet11/synthese?vue=ensemble&essai='+encodeURIComponent(e.target.value)});"
            "async function statut(){try{const r=await fetch('/sujet11/pilotage/statut',{cache:'no-store'});"
            "const t=await r.text();document.getElementById('statut').innerHTML=t;"
            "const enCours=t.includes('Essai en cours');if(" + ("true" if autorise else "false") + "){b.disabled=enCours;"
            "if(enCours){b.textContent='Un essai est en cours'}else if(b.textContent!=='Lancement…'){b.textContent=\"Lancer l'essai\"}}"
            "}catch(e){document.getElementById('statut').textContent='Suivi indisponible : service injoignable.'}}"
            "statut();setInterval(statut,3000);"
            # heures dans le fuseau du navigateur (le service tourne en UTC), comme la page de synthèse
            "for(const e of document.querySelectorAll('.heure')){const d=new Date(1000*e.dataset.t);"
            "e.textContent=d.toLocaleDateString('fr-FR',{day:'2-digit',month:'2-digit'})+' à '+d.toLocaleTimeString('fr-FR')}"
            "</script></body></html>")


def _lien_essai(workspace: str, h: dict) -> str:
    """Lien vers le détail d'un essai lancé ici, seulement s'il a un bilan."""
    if not h.get("sortie") or not _essai(os.path.join(workspace, h["sortie"])):
        return ""
    return f"<a href='/sujet11/synthese?vue=ensemble&essai={_e(h['sortie'])}' target='_blank'>voir</a>"


def _tous_publies(workspace: str) -> list[dict]:
    liste = []
    for m in glob.glob(os.path.join(workspace, "preuves", "sujet11", "*", "essais", "*", "meta.json")):
        e = _essai(os.path.dirname(m))
        if e:
            liste.append(e)
    return liste
