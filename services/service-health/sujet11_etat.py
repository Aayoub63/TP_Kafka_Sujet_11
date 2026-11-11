"""Sujet 11 : état des essais affiché dans le panneau « Pilotage » de Grafana.

Le panneau contient un petit cadre (iframe) qui charge GET /sujet11/etat.
La page dit, dans la couleur du cas, quel essai tourne, ou pourquoi un clic
a été refusé. Elle se recharge toute seule toutes les 5 secondes.

L'essai en cours est lu dans le verrou posé par scripts/sujet11-maj.sh
(runtime/sujet11/verrou/essai), que le terminal et les boutons partagent.
"""
from __future__ import annotations

import html
import os
import time
from datetime import datetime

MODES = {
    "observee": ("1. Mise à jour observée", "#1d4ed8"),
    "minimale": ("2. Solution minimale", "#c2410c"),
    "amelioree": ("3. Solution améliorée", "#15803d"),
    "crash": ("4. Panne (crash)", "#a21caf"),
}
ROUGE = "#b91c1c"
GRIS = "#4b5563"
# Au-delà, le script considère le verrou comme abandonné et le reprend.
VERROU_PERIME_S = 1200


def essai_en_cours(workspace: str) -> dict | None:
    """Essai qui tient le verrou, ou None. L'identifiant a la forme
    AAAAMMJJ-HHMMSS-<mode>-<sémantique>-<charge>."""
    chemin = os.path.join(workspace, "runtime", "sujet11", "verrou", "essai")
    try:
        if time.time() - os.path.getmtime(chemin) > VERROU_PERIME_S:
            return None
        identifiant = open(chemin, encoding="utf-8").read().strip()
    except OSError:
        return None
    morceaux = identifiant.split("-")
    if len(morceaux) < 5:
        return {"id": identifiant, "mode": "", "semantique": "", "charge": "", "debut": ""}
    try:
        debut = datetime.strptime(morceaux[0] + morceaux[1], "%Y%m%d%H%M%S").strftime("%H:%M:%S")
    except ValueError:
        debut = ""
    return {"id": identifiant, "mode": morceaux[2], "semantique": morceaux[3],
            "charge": morceaux[4], "debut": debut}


def _bandeau(couleur: str, texte: str) -> str:
    return (f"<div style='background:{couleur};color:#fff;padding:4px 10px;border-radius:5px;"
            f"margin-bottom:4px;font-weight:600'>{texte}</div>")


def _libelle(mode: str) -> str:
    return MODES.get(mode, (mode or "essai", GRIS))[0]


def _couleur(mode: str) -> str:
    return MODES.get(mode, ("", GRIS))[1]


def rendre_etat(essai: dict | None, resultat: str = "", mode: str = "", semantique: str = "",
                charge: str = "") -> str:
    """Page HTML de l'état. resultat vient du dernier clic : accepted, busy, error ou vide."""
    e = {k: html.escape(str(v)) for k, v in (essai or {}).items()}
    if mode == "crash":  # réglage fixe, la charge de la liste ne s'applique pas
        charge = "ralentie"
    mode, semantique, charge = (html.escape(x) for x in (mode, semantique, charge))
    blocs = []
    if resultat == "accepted":
        blocs.append(_bandeau(_couleur(mode), f"Essai lancé : {_libelle(mode)}, {semantique}, charge {charge}. "
                                                 "Il dure de 5 à 7 minutes."))
    elif resultat == "busy":
        detail = f" ({_libelle(e.get('mode', ''))}, depuis {e['debut']})" if essai else ""
        blocs.append(_bandeau(ROUGE, f"Refusé : un essai est déjà en cours{detail}. "
                                     "Attendez sa fin avant d'en lancer un autre."))
    elif resultat:
        blocs.append(_bandeau(ROUGE, "Refusé : l'essai n'a pas pu démarrer. Voir la page de pilotage (port 8083)."))
    if essai:
        blocs.append(_bandeau(_couleur(e.get("mode", "")),
                              f"En cours : {_libelle(e.get('mode', ''))}, {e.get('semantique', '')}, "
                              f"charge {e.get('charge', '')}, depuis {e.get('debut', '')}"))
    elif resultat != "accepted":
        blocs.append(_bandeau(GRIS, "Aucun essai en cours. Choisissez un cas."))
    return ("<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
            # recharge sans les paramètres du clic : le message du clic ne reste que 5 s
            "<meta http-equiv='refresh' content='5;url=/sujet11/etat'>"
            # color-scheme : sans lui, un navigateur en thème sombre peint le cadre en blanc.
            "<meta name='color-scheme' content='light dark'>"
            "<style>html,body{margin:0;background:transparent;font:16px Inter,Roboto,system-ui,sans-serif}</style>"
            "</head><body>" + "".join(blocs) + "</body></html>")
