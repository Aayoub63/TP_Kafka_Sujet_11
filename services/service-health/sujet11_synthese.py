"""Sujet 11 : page de synthèse affichée dans le tableau de bord Grafana.

Pensée pour un enseignant qui ne connaît pas Kafka, sur un vidéoprojecteur
1920 × 1080. Cinq vues, chacune dans un cadre (iframe) de Grafana :

  - ensemble    : ce qu'on teste et si la garantie est tenue ;
  - deroulement : les étapes de la mise à jour, avec leurs temps mesurés ;
  - integrite   : les paiements attendus comparés aux paiements en base ;
  - essais      : chaque essai publié face à SA propre limite ;
  - comparaison : les sémantiques, sur les seuls essais publiés dans preuves/.

Sources (jamais de valeur inventée, « Non disponible » si absente) :
  - dernier essai terminé, essai en cours ou interrompu : runtime/sujet11/ ;
  - essais et comparaison : preuves/sujet11/*/essais/*/ (les preuves publiées),
    donc exactement les mêmes chiffres que les bilans et les resume.md.
"""
from __future__ import annotations

import glob
import html
import json
import os
import re
import statistics
from datetime import datetime, timezone

# Couleurs : variables CSS, plus claires en thème sombre (contraste >= 4,5:1 sur
# les cartes dans les deux thèmes, mesuré). Les bandeaux gardent un fond plein et
# un texte blanc (>= 5:1).
VERT, ROUGE, ORANGE, BLEU, GRIS = "var(--vert)", "var(--rouge)", "var(--orange)", "var(--bleu)", "var(--gris)"
FOND = {"vert": "#15803d", "rouge": "#b91c1c", "orange": "#c2410c", "bleu": "#1d4ed8", "gris": "#4b5563"}
ND = "Non disponible"

# Mêmes bornes que scripts/sujet11/bilan.py (BORNES_OFFICIELLES), vérifié par un test.
BORNES_OFFICIELLES = {"minimale": (60, 120), "amelioree": (60, 120), "observee": (60, 120), "crash": (60, 180)}
# Essais du code actuel : arrêt propre et heure d'audit corrigée (commit 9c7e312, 9 novembre 8 h 36).
DEBUT_CODE_ACTUEL = "20261109-0836"

CAS = {
    "observee": "Mise à jour observée (sans verdict)",
    "minimale": "Solution minimale : une seule instance, remplacée",
    "amelioree": "Solution améliorée : une 2e instance prend le relais",
    "crash": "Panne brutale : le service est tué (docker kill)",
}
CAS_COURT = {"observee": "Observée", "minimale": "Solution minimale", "amelioree": "Solution améliorée",
             "crash": "Panne brutale"}
SEMANTIQUES = {
    "at_least_once": "at-least-once : écrire en base, puis noter la lecture",
    "at_most_once": "at-most-once : noter la lecture, puis écrire en base",
    "exactly_once_pg": "exactly-once PostgreSQL : écriture et lecture notées ensemble",
}
COURT = {"at_least_once": "at-least-once", "at_most_once": "at-most-once",
         "exactly_once_pg": "exactly-once PostgreSQL"}
NOMS_CHAMPS = {"amount": "montant", "currency": "devise", "emitter_account_id": "compte émetteur",
               "beneficiary_account_id": "compte bénéficiaire"}
PHASES = {
    "lance": "flux de paiements lancé, mesure du fonctionnement normal (30 s)",
    "mise_a_jour": "remplacement du service en cours",
    "drainage": "rattrapage des paiements en attente",
    "collecte": "vérification des paiements dans PostgreSQL",
    "termine": "terminé",
    "interrompu": "interrompu avant la fin",
}
STATUTS = {VERT: "Respecté", ROUGE: "Non respecté", ORANGE: "Attention", BLEU: "Information", GRIS: ND}


# ---------------------------------------------------------------- données

def _json(chemin):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _derniere_ligne(chemin):
    try:
        with open(chemin, encoding="utf-8") as f:
            lignes = [l for l in f if l.strip()]
        return json.loads(lignes[-1]) if lignes else None
    except (OSError, ValueError):
        return None


def _dossiers_essais(workspace: str) -> list[str]:
    racine = os.path.join(workspace, "runtime", "sujet11")
    return sorted({os.path.dirname(c) for motif in ("*/meta.json", "*/*/meta.json", "*/phase", "*/*/phase")
                   for c in glob.glob(os.path.join(racine, motif))})


def _essai(dossier: str) -> dict | None:
    resultat, meta = _json(os.path.join(dossier, "resultat.json")), _json(os.path.join(dossier, "meta.json"))
    if not resultat or not meta:
        return None
    # fin = fin du flux (meta) ; à défaut, heure d'écriture du bilan
    fin = meta.get("fin_flux") or os.path.getmtime(os.path.join(dossier, "resultat.json"))
    return {"resultat": resultat, "meta": meta, "debut": meta.get("debut_flux"), "fin": fin, "dossier": dossier}


def dernier_essai(workspace: str) -> dict | None:
    """Dernier essai terminé (bilan écrit), essais seuls ou de campagne."""
    essais = [e for e in (_essai(d) for d in _dossiers_essais(workspace)) if e]
    return max(essais, key=lambda e: e["fin"]) if essais else None


def dernier_avec_verdict(workspace: str) -> dict | None:
    """Dernier essai terminé dont la mesure est valide (REUSSITE ou ECHEC)."""
    essais = [e for e in (_essai(d) for d in _dossiers_essais(workspace)) if e
              and e["resultat"].get("verdict") in ("REUSSITE", "ECHEC")]
    return max(essais, key=lambda e: e["fin"]) if essais else None


def dernier_interrompu(workspace: str, apres: float | None) -> dict | None:
    """Essai interrompu (phase « interrompu », pas de bilan) plus récent que `apres`."""
    trouves = []
    for d in _dossiers_essais(workspace):
        chemin = os.path.join(d, "phase")
        try:
            phase = open(chemin, encoding="utf-8").read().strip()
        except OSError:
            continue
        if phase == "interrompu" and not os.path.exists(os.path.join(d, "resultat.json")):
            quand = os.path.getmtime(chemin)
            if apres is None or quand > apres:
                trouves.append({"id": os.path.basename(d), "quand": quand})
    return max(trouves, key=lambda x: x["quand"]) if trouves else None


def essai_direct(workspace: str, en_cours: dict | None) -> dict | None:
    """Mesures en direct de l'essai qui tient le verrou : phase, compteurs, groupe."""
    if not en_cours:
        return None
    try:
        sortie = open(os.path.join(workspace, "runtime", "sujet11", "verrou", "sortie"),
                      encoding="utf-8").read().strip()
    except OSError:
        sortie = os.path.join("runtime", "sujet11", en_cours["id"])
    dossier = os.path.join(workspace, sortie)
    try:
        phase = open(os.path.join(dossier, "phase"), encoding="utf-8").read().strip()
    except OSError:
        phase = None
    return {**en_cours, "phase": phase,
            "compteurs": _derniere_ligne(os.path.join(dossier, "compteurs.jsonl")),
            "groupe": _derniere_ligne(os.path.join(dossier, "lag.jsonl"))}


def officiel(meta: dict) -> bool | None:
    """Bornes officielles du cas ? (même règle que bilan.essai_officiel)."""
    if meta.get("mode") == "observee":
        return None
    return (meta.get("borne_s"), meta.get("drainage_max_s")) == BORNES_OFFICIELLES.get(meta.get("mode"))


def essais_publies(workspace: str) -> list[dict]:
    """Essais publiés dans preuves/, du code actuel (arrêt propre, heure d'audit corrigée)."""
    liste = []
    for m in glob.glob(os.path.join(workspace, "preuves", "sujet11", "*", "essais", "*", "meta.json")):
        meta = _json(m)
        resultat = _json(os.path.join(os.path.dirname(m), "resultat.json"))
        if not meta or not resultat or meta.get("id", "") < DEBUT_CODE_ACTUEL:
            continue
        if resultat.get("version_persister_valid", "arret-propre") != "arret-propre":
            continue
        liste.append({"meta": meta, "resultat": resultat,
                      "campagne": m.split(os.sep)[-4]})
    return sorted(liste, key=lambda e: e["meta"]["id"])


# ---------------------------------------------------------------- textes

def _e(x) -> str:
    return html.escape(str(x))


def _nb(x, unite="") -> str:
    if x is None:
        return ND
    if isinstance(x, float):
        x = f"{x:.2f}".replace(".", ",")
    return f"{x}{(' ' + unite) if unite else ''}"


def _s(x, chiffres=1) -> str:
    """Durée en secondes, écrite en français."""
    return ND if x is None else f"{float(x):.{chiffres}f} s".replace(".", ",")


def _heure(epoch) -> str:
    """Heure lisible. Le conteneur est en UTC : le navigateur la remet dans son fuseau
    (script en bas de page) ; sans script, l'heure UTC reste affichée, marquée « UTC »."""
    if not epoch:
        return ND
    utc = datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%d/%m à %H:%M:%S UTC")
    return f"<span class='heure' data-t='{epoch:.0f}'>{utc}</span>"


def expliquer(raison: str) -> str:
    """Raison du bilan, réécrite pour un lecteur non spécialiste. Le sens ne change pas."""
    r = raison
    suffixe = ""
    for marque, texte in ((" (non confirmé : mesure incomplète)", " Non confirmé : la mesure est incomplète."),
                          (" (non confirmé : mesure du temps douteuse)", " Non confirmé : la mesure du temps est douteuse.")):
        if r.endswith(marque):
            r, suffixe = r[: -len(marque)], texte
    m = re.fullmatch(r"pause ([\d.]+) s > borne ([\d.]+) s", r)
    if m:
        r = (f"Interruption de {_s(m.group(1))} : la limite autorisée de {_s(m.group(2), 0)} "
             "pour cet essai a été dépassée.")
    m = re.fullmatch(r"retard non résorbé en ([\d.]+) s \(drainage\)", r)
    if m:
        r = f"Les paiements en attente n'ont pas été rattrapés dans la limite de {_s(m.group(1), 0)}."
    if r.startswith("mesure invalide : "):
        r = "Mesure non valide : " + r[len("mesure invalide : "):]
    if suffixe and not r.endswith("."):
        r += "."
    return r + suffixe


def charge_lisible(meta: dict) -> str:
    """Charge réellement appliquée (débit et ralenti), pas seulement l'étiquette."""
    if meta.get("ralenti_ms"):
        return f"charge ralentie ({_e(meta.get('debit'))} paiements/s, {_e(meta['ralenti_ms'])} ms d'écart ajouté)"
    return f"charge {_e(meta.get('charge'))} ({_e(meta.get('debit'))} paiements/s)"


# ---------------------------------------------------------------- rendu

STYLE = """
:root{--fond:#f8fafc;--carte:#ffffff;--texte:#0f172a;--doux:#475569;--bord:#e2e8f0;
  --vert:#15803d;--rouge:#b91c1c;--orange:#c2410c;--bleu:#1d4ed8;--gris:#4b5563}
@media (prefers-color-scheme: dark){:root{--fond:#0b1220;--carte:#111a2e;--texte:#e5e7eb;--doux:#a3adbf;
  --bord:#24324d;--vert:#4ade80;--rouge:#f87171;--orange:#fb923c;--bleu:#60a5fa;--gris:#a3adbf}}
*{box-sizing:border-box}
html,body{margin:0;background:var(--fond);color:var(--texte);
  font:17px/1.4 Inter,Roboto,"Segoe UI",system-ui,sans-serif}
body{padding:12px 18px}
.bandeau{border-radius:10px;padding:12px 18px;color:#fff;margin-bottom:10px}
.bandeau b{font-size:24px;display:block;margin-bottom:2px}
.bandeau ul{margin:4px 0 0 20px;padding:0}
.contexte{color:var(--doux);margin:0 0 10px}
.grille{display:grid;grid-template-columns:repeat(6,1fr);gap:12px}
.carte{background:var(--carte);border:1px solid var(--bord);border-left:8px solid var(--c,var(--gris));
  border-radius:10px;padding:12px 14px}
.carte h3{margin:0 0 4px;font-size:20px;font-weight:600}
.carte .v{font-size:38px;font-weight:700;line-height:1.1;color:var(--c,inherit)}
.carte p{margin:6px 0 0;color:var(--doux);font-size:16px}
.etiquette{display:inline-block;font-size:15px;font-weight:700;color:var(--c);border:2px solid var(--c);
  border-radius:6px;padding:0 6px;margin-bottom:6px}
.etapes{display:grid;grid-template-columns:repeat(7,1fr);gap:10px}
.etape{background:var(--carte);border:1px solid var(--bord);border-top:8px solid var(--c,var(--gris));
  border-radius:10px;padding:10px 12px}
.etape h3{margin:0;font-size:18px}
.etape .t{font-size:26px;font-weight:700;color:var(--c,inherit);margin:2px 0}
.etape p{margin:2px 0 0;color:var(--doux);font-size:16px}
.deux{display:grid;grid-template-columns:3fr 2fr;gap:18px;align-items:start}
.barres{display:grid;gap:6px}
.barre{display:grid;grid-template-columns:300px 1fr 150px;align-items:center;gap:10px}
.barre .fond{background:var(--bord);border-radius:6px;height:22px;overflow:hidden}
.barre .plein{height:100%;background:var(--c,var(--gris))}
.barre .n{font-size:22px;font-weight:700;text-align:right;color:var(--c,inherit)}
.note{color:var(--doux);font-size:16px;margin:8px 0 0}
small{font-size:15px;color:var(--doux)}
.titre2{font-size:20px;margin:12px 0 6px}
.tab{border-collapse:collapse;width:100%;background:var(--carte);border:1px solid var(--bord)}
.tab th,.tab td{padding:6px 10px;border-bottom:1px solid var(--bord);text-align:left;font-size:17px}
.tab th{color:var(--doux);font-weight:600}
details summary{cursor:pointer;font-size:17px;margin-top:10px}
.axe{position:relative;height:30px;background:var(--bord);border-radius:6px}
.axe .lim{position:absolute;top:-4px;bottom:-4px;width:3px;background:var(--rouge)}
.axe .pt{position:absolute;top:7px;width:16px;height:16px;border-radius:50%;margin-left:-8px;
  background:var(--c);border:2px solid var(--carte)}
"""


def _page(corps: str) -> str:
    return ("<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
            "<meta http-equiv='refresh' content='5'>"
            "<meta name='color-scheme' content='light dark'>"
            f"<style>{STYLE}</style></head><body>{corps}"
            "<script>for(const e of document.querySelectorAll('.heure')){const d=new Date(1000*e.dataset.t);"
            "e.textContent=d.toLocaleDateString('fr-FR',{day:'2-digit',month:'2-digit'})+' à '+"
            "d.toLocaleTimeString('fr-FR')}</script></body></html>")


def _bandeau(fond: str, titre: str, corps: str = "", attenue=False) -> str:
    style = f"background:{FOND[fond]}" + (";opacity:.6" if attenue else "")
    return f"<div class='bandeau' style='{style}'><b>{titre}</b>{corps}</div>"


def _carte(titre, valeur, couleur, texte="") -> str:
    return (f"<div class='carte' style='--c:{couleur}'><span class='etiquette'>{STATUTS[couleur]}</span>"
            f"<h3>{_e(titre)}</h3><div class='v'>{_e(valeur)}</div>{f'<p>{texte}</p>' if texte else ''}</div>")


def bandeau_direct(direct: dict | None) -> str:
    """Bandeau bleu de l'essai en cours, avec ses mesures en direct."""
    if not direct:
        return ""
    c, g = direct.get("compteurs") or {}, direct.get("groupe") or {}
    phase = PHASES.get(direct.get("phase") or "", "démarrage")
    attente, lecteurs = c.get("ecart_topic_base"), g.get("membres")
    mesures = [f"{_e(attente)} paiement(s) pas encore en base" if attente is not None else
               "paiements pas encore en base : non disponible (premier relevé après 30 s)",
               f"{_e(lecteurs)} instance(s) en train de lire" if lecteurs is not None else
               "instances en train de lire : non disponible"]
    return _bandeau("bleu", f"Essai en cours : {_e(phase)}",
                    f"{_e(CAS.get(direct.get('mode'), direct.get('mode') or ''))}, "
                    f"{_e(COURT.get(direct.get('semantique'), direct.get('semantique') or ''))}, "
                    f"depuis {_e(direct.get('debut') or ND)}. En ce moment : {'; '.join(mesures)}. "
                    "Résultat en attente de validation : les cartes ci-dessous sont celles du "
                    "<u>dernier essai terminé</u>.")


def bandeau_interrompu(interrompu: dict | None) -> str:
    if not interrompu:
        return ""
    return _bandeau("orange", "Un essai plus récent a été interrompu",
                    f"{_e(interrompu['id'])}, arrêté le {_heure(interrompu['quand'])} avant la fin : "
                    "il n'a pas de verdict. Ce qui suit est le dernier essai terminé.")


def bandeau_verdict(dernier: dict, attenue: bool = False, precedent: dict | None = None) -> str:
    """Verdict du dernier essai terminé. Atténué pendant un essai : ce n'est pas le résultat en cours."""
    r = dernier["resultat"]
    v, raisons = r.get("verdict"), r.get("raisons") or []
    liste = "<ul>" + "".join(f"<li>{_e(expliquer(x))}</li>" for x in raisons) + "</ul>" if raisons else ""
    if v == "REUSSITE":
        oc = r["oracle"]["continuite"]
        pause, borne = r["pause"].get("pause_s"), r.get("parametres", {}).get("borne_s")
        faits = ["aucun paiement perdu",
                 "aucun double effet" if oc.get("doubles_effets") == 0 else
                 "doubles effets non vérifiés par cet essai ancien",
                 f"interruption de {_s(pause)}, sous la limite de {_s(borne, 0)}", "retard rattrapé"]
        return _bandeau("vert", "Dernier essai terminé : Garantie respectée",
                        f"{_e(', '.join(faits).capitalize())}.", attenue)
    if v == "ECHEC":
        return _bandeau("rouge", "Dernier essai terminé : Garantie NON respectée", liste, attenue)
    if v == "INVALIDE":
        avant = ""
        if precedent:
            avant = (f"<p style='margin:6px 0 0'>Dernier essai avec un verdict valide : "
                     f"{_e(precedent['meta'].get('id'))} ({_e(precedent['resultat'].get('verdict'))}).</p>")
        return _bandeau("gris", "Dernier essai terminé : Mesure non valide, ni réussite, ni échec",
                        liste + avant, attenue)
    return _bandeau("bleu", "Dernier essai terminé : Observation sans verdict",
                    "Ce cas mesure la mise à jour sans la juger.", attenue)


def contexte(dernier: dict) -> str:
    m, r = dernier["meta"], dernier["resultat"]
    debit = (r.get("compteurs") or {}).get("debit_mesure")
    diag = ("" if officiel(m) in (True, None) else
            f" <b>Essai de diagnostic</b> : limites {_s(m.get('borne_s'), 0)} et {_s(m.get('drainage_max_s'), 0)}, "
            "différentes des limites officielles du cas.")
    return (f"<p class='contexte'><b>{_e(CAS.get(m.get('mode'), m.get('mode')))}</b>, "
            f"{_e(SEMANTIQUES.get(m.get('semantique'), m.get('semantique')))}. "
            f"{_e(m.get('total'))} paiements, {charge_lisible(m)}"
            f"{(', ' + _e(_nb(debit)) + ' paiements/s mesurés') if debit else ''}. "
            f"Lancé le {_heure(dernier.get('debut'))}, terminé le {_heure(dernier['fin'])} "
            f"<small>({_e(m.get('id'))})</small>.{diag}<br>"
            "On met à jour <b>persister-valid</b>, le programme qui enregistre les paiements validés dans la "
            "base PostgreSQL. Les paiements lui arrivent par <b>Kafka</b>, une file d'attente : pendant la mise "
            "à jour, ils y attendent sans être perdus.</p>")


def _entete(direct, dernier, workspace) -> str:
    """Bandeaux communs : essai en cours, essai interrompu, verdict du dernier essai."""
    interrompu = dernier_interrompu(workspace, dernier["fin"] if dernier else None)
    if not dernier:
        return (bandeau_direct(direct) + bandeau_interrompu(interrompu)
                + _bandeau("gris", "Aucun essai terminé", "Lancez un essai avec les boutons au-dessus."))
    precedent = dernier_avec_verdict(workspace) if dernier["resultat"].get("verdict") == "INVALIDE" else None
    return (bandeau_direct(direct) + bandeau_interrompu(interrompu)
            + bandeau_verdict(dernier, attenue=bool(direct), precedent=precedent) + contexte(dernier))


def rappel(direct, dernier, workspace) -> str:
    """Une ligne, pour les vues 2 et 3 : de quel essai il s'agit, et s'il y a un essai en cours ou interrompu."""
    if not dernier:
        return _entete(direct, dernier, workspace)
    m, v = dernier["meta"], dernier["resultat"].get("verdict")
    couleur, mot = {"REUSSITE": (VERT, "Garantie respectée"), "ECHEC": (ROUGE, "Garantie NON respectée"),
                    "INVALIDE": (GRIS, "Mesure non valide")}.get(v, (BLEU, "Observation"))
    morceaux = [f"<span class='etiquette' style='--c:{couleur}'>{mot}</span> <b>Dernier essai terminé</b> : "
                f"{_e(CAS_COURT.get(m.get('mode'), m.get('mode')))}, {_e(COURT.get(m.get('semantique'), ''))}, "
                f"{charge_lisible(m)}, terminé le {_heure(dernier['fin'])}."]
    if direct:
        morceaux.append(f"<span class='etiquette' style='--c:{BLEU}'>Essai en cours</span> "
                        f"{_e(PHASES.get(direct.get('phase') or '', 'démarrage'))} : résultat en attente de validation.")
    interrompu = dernier_interrompu(workspace, dernier["fin"])
    if interrompu:
        morceaux.append(f"<span class='etiquette' style='--c:{ORANGE}'>Interrompu</span> un essai plus récent "
                        f"({_e(interrompu['id'])}) s'est arrêté avant la fin, sans verdict.")
    return "<p class='contexte'>" + " ".join(morceaux) + "</p>"


def durees(r: dict, m: dict) -> dict:
    """Les trois durées, chacune avec son point de départ."""
    ch, p = r.get("chronologie") or {}, r["pause"]
    # Sans interruption mesurable, le plus long trou est un écart normal du flux, pris
    # n'importe où dans l'essai : sa fin n'est pas une « reprise ».
    sans_interruption = r.get("pause_distincte") is False
    reprise = None if sans_interruption else p.get("premiere_ecriture_apres_s")
    normal = ch.get("lag_revenu_a_zero_s")
    rattrapage = round(normal - reprise, 3) if normal is not None and reprise is not None and normal >= reprise else None
    return {"interruption": p.get("pause_s"), "reprise": reprise, "normal": normal, "rattrapage": rattrapage,
            "sans_interruption": sans_interruption,
            "limite_pause": m.get("borne_s"), "limite_normal": m.get("drainage_max_s")}


def vue_ensemble(dernier, direct, workspace) -> str:
    entete = _entete(direct, dernier, workspace)
    if not dernier:
        return _page(entete)
    r, m = dernier["resultat"], dernier["meta"]
    oc = r["oracle"]["continuite"]
    cl = oc["classes"]
    trous = (r.get("trous") or {}).get("trous")
    d = durees(r, m)
    doubles, relus = oc.get("doubles_effets"), r["oracle"]["doublons"].get("doublons_absorbes")
    if d["interruption"] is None:
        c_pause, t_pause = GRIS, "Interruption non mesurée."
    elif d["limite_pause"] and d["interruption"] > d["limite_pause"]:
        c_pause, t_pause = ROUGE, f"Au-dessus de la limite de {_s(d['limite_pause'], 0)} fixée pour cet essai."
    else:
        distincte = r.get("pause_distincte")
        c_pause = VERT
        t_pause = (f"Sous la limite de {_s(d['limite_pause'], 0)}. Temps sans aucune écriture en base. "
                   + ("Il y a bien eu une interruption." if distincte else
                      "Pas d'interruption mesurable : la valeur égale le rythme normal du flux "
                      f"({_s(r['pause'].get('trou_normal_s'), 2)})." if distincte is False else ""))
    drain = r.get("drainage_termine")
    c_normal = GRIS if drain is None else VERT if drain else ROUGE
    cartes = [
        _carte("Paiements à enregistrer", _nb(oc.get("attendus")), BLEU,
               "Paiements validés par la banque pendant l'essai."),
        _carte("Enregistrés en base", _nb(cl.get("present")),
               VERT if cl.get("present") == oc.get("attendus") else ROUGE,
               "Retrouvés un par un dans PostgreSQL, avec les bonnes valeurs."),
        _carte("Paiements manquants", _nb(cl.get("perdu")), VERT if cl.get("perdu") == 0 else ROUGE,
               f"Contrôle indépendant : {_e(_nb(trous))} paiement(s) sans aucune décision en base."),
        _carte("Doubles effets", _nb(doubles), GRIS if doubles is None else VERT if doubles == 0 else ROUGE,
               f"Un double effet = un même paiement enregistré deux fois. {_e(_nb(relus))} paiement(s) "
               "lu(s) deux fois après la reprise, sans second enregistrement."),
        _carte("Interruption", _s(d["interruption"], 2), c_pause, t_pause),
        _carte("Retour à la normale", _s(d["normal"]), c_normal,
               f"Plus aucun paiement en attente, {_s(d['normal'])} après le lancement "
               f"(limite {_s(d['limite_normal'], 0)}). "
               + ("Les écritures ne se sont pas arrêtées plus longtemps que le rythme normal du flux : "
                  "pas de reprise à mesurer." if d["sans_interruption"] else
                  f"Reprise des écritures à {_s(d['reprise'])} ; rattrapage du retard en {_s(d['rattrapage'])}.")),
    ]
    return _page(entete + "<div class='grille'>" + "".join(cartes) + "</div>")


def _etape(titre, temps, texte, couleur) -> str:
    return (f"<div class='etape' style='--c:{couleur}'><span class='etiquette'>"
            f"{'Observé' if couleur != GRIS else 'Non observé'}</span><h3>{_e(titre)}</h3>"
            f"<div class='t'>{_e(temps)}</div><p>{texte}</p></div>")


def sort_du_paiement(p: dict, semantique: str | None) -> tuple[str, str]:
    """Phrase et couleur pour une passation de file (resultat.json, partitions.passations)."""
    tid = p.get("message_repris")
    if p.get("offset_reprise") is None:
        phrase, couleur = "aucun paiement dans cette file", GRIS
    elif tid is None:
        phrase, couleur = "rien en attente à cet endroit", GRIS
    elif p.get("deja_ecrit_avant") and (p.get("ecritures_du_message_repris") or 0) >= 2:
        phrase, couleur = f"{_e(tid)} était déjà écrit : relu et réécrit, sans second effet", ORANGE
    elif p.get("deja_ecrit_avant") and semantique == "exactly_once_pg":
        phrase, couleur = f"{_e(tid)} était déjà écrit : relu et écarté, sans réécriture", BLEU
    elif p.get("deja_ecrit_avant"):
        phrase, couleur = f"{_e(tid)} déjà écrit avant (position relevée à une seconde près)", GRIS
    else:
        phrase, couleur = f"{_e(tid)} pas encore écrit : la nouvelle version le reprend", VERT
    if p.get("precedent_ecrit") is False:
        phrase += f" ; <b>{_e(p.get('message_precedent'))} jamais écrit : perdu</b>"
        couleur = ROUGE
    return phrase, couleur


def passations(r: dict, semantique: str | None) -> str:
    """Résumé visible, puis le détail des 6 files parallèles (replié)."""
    liste = (r.get("partitions") or {}).get("passations") or []
    if not liste:
        return "<p class='note'>Paiement en cours, file par file : non disponible pour cet essai.</p>"
    sorts = [sort_du_paiement(p, semantique) for p in liste]
    perdus = [p.get("message_precedent") for p in liste if p.get("precedent_ecrit") is False]
    repris = sum(1 for _, c in sorts if c == VERT)
    relus = sum(1 for _, c in sorts if c in (ORANGE, BLEU))
    resume = (f"<p class='note'><b>Le paiement en cours au moment de l'arrêt</b>, dans chacune des "
              f"{len(liste)} files parallèles où Kafka range les paiements : {repris} repris par la nouvelle "
              f"version, {relus} relu(s) sans second effet, "
              + (f"<b style='color:{ROUGE}'>{len(perdus)} perdu(s) : {_e(', '.join(perdus))}</b>" if perdus
                 else "aucun perdu") + ".</p>")
    lignes = "".join(
        f"<tr><td>{_e(p.get('partition'))}</td><td>{_e(p.get('avant'))} → {_e(p.get('apres'))}</td>"
        f"<td>{_e(_s(p.get('sans_proprietaire_s'), 2))}</td><td style='color:{c}'>{phrase}</td></tr>"
        for p, (phrase, c) in zip(liste, sorts))
    return (resume + "<details><summary>Voir le détail des 6 files parallèles <small>(partitions Kafka)"
            "</small></summary><table class='tab'><tr><th>file</th><th>passe de</th><th>sans lecteur pendant</th>"
            "<th>ce qu'est devenu le paiement en cours</th></tr>" + lignes + "</table></details>")


def vue_deroulement(dernier, direct, workspace) -> str:
    entete = rappel(direct, dernier, workspace)
    if not dernier:
        return _page(entete)
    r, m = dernier["resultat"], dernier["meta"]
    ch, p = r.get("chronologie") or {}, r["pause"]
    d = durees(r, m)
    mode = m.get("mode")
    vu = lambda x: BLEU if x is not None else GRIS  # noqa: E731
    if mode == "amelioree":
        arret = ch.get("arret_ancien_demande_s")
        t_arret = "On demande à l'ancienne version de s'arrêter proprement, une fois la nouvelle prête."
    elif mode == "crash":
        arret = ch.get("conteneur_mort_s")
        t_arret = "L'ancienne version est tuée sans prévenir : elle ne finit pas son paiement en cours."
    else:
        arret = ch.get("conteneur_mort_s")
        t_arret = "Elle finit le paiement en cours, note où elle en est, puis s'arrête."
    duree = ch.get("groupe_vide_duree_s")
    drain = r.get("drainage_termine")
    etapes = [
        _etape("1. Fonctionnement normal", "avant", "Un paiement est enregistré au moins toutes les "
               f"{_e(_s(p.get('trou_normal_s'), 2))}.", VERT),
        _etape("2. Mise à jour lancée", "0 s", "On remplace le programme qui enregistre les paiements.", BLEU),
        _etape("3. L'ancienne version s'arrête", _s(arret, 2), t_arret, vu(arret)),
        _etape("4. Nouvelle répartition du travail", _s(ch.get("groupe_vide_s"), 2),
               "Kafka confie la file d'attente à la nouvelle version. "
               + ("Pendant ce temps, l'ancienne version continue de traiter les paiements qu'elle a déjà "
                  "reçus : les écritures ne s'arrêtent pas." if mode == "amelioree" or d["sans_interruption"] else
                  "Aucune version ne traite de paiement pendant ce temps (l'ancienne est arrêtée), mais rien "
                  "n'est perdu : les paiements attendent dans la file.")
               + (f" <small>(état du groupe vu par Kafka : {_e(_s(duree))} sans propriétaire, à une seconde "
                  "près ; « rebalance »)</small>" if duree else " <small>(« rebalance »)</small>"),
               vu(ch.get("groupe_vide_s"))),
        (_etape("5. Pas d'interruption mesurable", "sans objet",
                "La nouvelle version a pris le relais sans que les écritures s'arrêtent plus longtemps que le "
                f"rythme normal du flux ({_e(_s(p.get('trou_normal_s'), 2))}).", BLEU)
         if d["sans_interruption"] else
         _etape("5. La nouvelle version reprend", _s(d["reprise"], 2),
                f"Premier paiement enregistré, après une interruption de {_e(_s(d['interruption'], 2))}.",
                vu(d["reprise"]))),
        _etape("6. Le retard est rattrapé", _s(d["normal"], 2),
               f"Jusqu'à {_e(_nb(r.get('retard_max_messages')))} paiements attendaient ; "
               + (f"plus aucun en attente à {_e(_s(d['normal']))}." if d["sans_interruption"] else
                  f"rattrapés en {_e(_s(d['rattrapage']))} après la reprise."), vu(d["normal"])),
        _etape("7. Retour à la normale", "Oui" if drain else "Non" if drain is False else ND,
               f"Plus aucun paiement en attente avant la limite de {_e(_s(d['limite_normal'], 0))} "
               f"(comptée depuis le lancement) : {'oui' if drain else 'non'}.",
               GRIS if drain is None else VERT if drain else ROUGE),
    ]
    return _page(entete + "<div class='etapes'>" + "".join(etapes) + "</div>"
                 + passations(r, m.get("semantique"))
                 + "<p class='note'>Temps mesurés après le lancement de la mise à jour : événements Docker, "
                   "état de Kafka relevé chaque seconde, heures d'écriture dans PostgreSQL.</p>")


def _barre(nom, n, total, couleur, aide="") -> str:
    largeur = 0 if not total or n is None else max(0.0, min(100.0, 100.0 * n / total))
    return (f"<div class='barre' style='--c:{couleur}'><div>{_e(nom)}"
            f"{f'<br><small>{aide}</small>' if aide else ''}</div>"
            f"<div class='fond'><div class='plein' style='width:{largeur:.1f}%'></div></div>"
            f"<div class='n'>{_e(_nb(n))}</div></div>")


def vue_integrite(dernier, direct, workspace) -> str:
    entete = rappel(direct, dernier, workspace)
    if not dernier:
        return _page(entete)
    r, m = dernier["resultat"], dernier["meta"]
    oc = r["oracle"]["continuite"]
    cl = oc["classes"]
    rejets = r["oracle"].get("flux", {}).get("rejets_total")
    trous = (r.get("trous") or {}).get("trous")
    rejetes_a_tort = None if "classes" not in oc else cl.get("rejet_metier", 0) + cl.get("rejet_delai", 0)
    total = m.get("total")
    rouge_si = lambda x: GRIS if x is None else VERT if x == 0 else ROUGE  # noqa: E731
    champs = ", ".join(NOMS_CHAMPS.get(c, c) for c in oc.get("champs_compares") or []) or ND
    barres = [
        _barre("Paiements envoyés", total, total, BLEU, "pendant l'essai"),
        _barre("Rejetés par la banque", rejets, total, BLEU, "décision normale, pas une perte"),
        _barre("Validés, à enregistrer", oc.get("attendus"), total, BLEU),
        _barre("Enregistrés avec les bonnes valeurs", cl.get("present"), total,
               VERT if cl.get("present") == oc.get("attendus") else ROUGE, f"comparés : {_e(champs)}"),
        _barre("Manquants", cl.get("perdu"), total, rouge_si(cl.get("perdu")), "validés mais absents de la base"),
        _barre("Sans aucune décision", trous, total, rouge_si(trous), "ni validés, ni rejetés en base"),
        _barre("Validés mais rangés dans les rejets", rejetes_a_tort, total, rouge_si(rejetes_a_tort)),
        _barre("Valeurs fausses", cl.get("valeur_fausse"), total, rouge_si(cl.get("valeur_fausse"))),
        _barre("Doubles effets", oc.get("doubles_effets"), total, rouge_si(oc.get("doubles_effets")),
               "deux lignes pour un même paiement"),
    ]
    cp = r.get("compteurs") or {}

    def case(cle, champ):
        return f"<td>{_e(_nb((cp.get(cle) or {}).get(champ)))}</td>"
    compteurs = ("<h3 class='titre2'>Avant, pendant et après la mise à jour</h3>"
                 "<table class='tab'><tr><th></th><th>avant</th><th>pire moment</th><th>après</th></tr>"
                 + "".join(f"<tr><td>{nom}</td>" + case("avant", champ) + case("pire", champ) + case("apres", champ)
                           + "</tr>" for nom, champ in (("validés (dans Kafka)", "validated_topic_end_offsets"),
                                                         ("enregistrés en base", "db_validated_count"),
                                                         ("<b>en attente</b>", "ecart_topic_base")))
                 + "</table><p class='note'>« En attente » = validés mais pas encore en base. Ce nombre doit "
                   "revenir à 0.</p>")
    c = (direct or {}).get("compteurs") or {}
    attente = ("" if not direct else
               f"<p class='note'><b>Essai en cours</b> : {_e(_nb(c.get('ecart_topic_base')))} paiement(s) "
               "validé(s) pas encore en base.</p>")
    return _page(entete + "<div class='deux'><div class='barres'>" + "".join(barres) + "</div><div>"
                 + compteurs + attente
                 + "<p class='note'>Chaque paiement est cherché par son identifiant dans PostgreSQL : pas "
                   "seulement des compteurs. Un rejet de la banque n'est pas une perte : il est dans la table "
                   "des rejets.</p></div></div>")


def _axe(valeurs: list[tuple[float | None, float | None, str]], couleur_ok, titre) -> str:
    """Une ligne par cas : un point par essai, et la limite de CHAQUE essai (trait rouge)."""
    connues = [v for v, lim, _ in valeurs if v is not None] + [lim for _, lim, _ in valeurs if lim is not None]
    if not connues:
        return f"<div>{_e(titre)} : {ND}</div>"
    echelle = max(connues) * 1.1
    traits = sorted({lim for _, lim, _ in valeurs if lim is not None})
    pts = "".join(f"<span class='pt' title='{_e(t)}' style='left:{100 * v / echelle:.1f}%;"
                  f"--c:{couleur_ok if lim is None or v <= lim else ROUGE}'></span>"
                  for v, lim, t in valeurs if v is not None)
    lims = "".join(f"<span class='lim' style='left:{100 * l / echelle:.1f}%'></span>" for l in traits)
    return f"<div class='axe'>{lims}{pts}</div>"


def vue_essais(dernier, direct, workspace) -> str:
    """Chaque essai publié, face à sa propre limite (pas une ligne fixe)."""
    essais = essais_publies(workspace)
    if not essais:
        return _page(_bandeau("gris", "Aucun essai publié du code actuel"))
    groupes = {}
    for e in essais:
        m = e["meta"]
        if m.get("mode") == "observee" or e["resultat"].get("verdict") == "INVALIDE":
            continue
        groupes.setdefault((m["mode"], m["semantique"]), []).append(e)
    lignes = []
    for (mode, sem), g in sorted(groupes.items()):
        pause = [(x["resultat"]["pause"].get("pause_s"), x["meta"].get("borne_s"), x["meta"]["id"]) for x in g]
        normal = [((x["resultat"].get("chronologie") or {}).get("lag_revenu_a_zero_s"),
                   x["meta"].get("drainage_max_s"), x["meta"]["id"]) for x in g]
        diag = sum(1 for x in g if officiel(x["meta"]) is False)
        charges = ", ".join(sorted({x["meta"].get("charge", "?") for x in g}))
        lim_p = sorted({l for _, l, _ in pause if l is not None})
        lim_n = sorted({l for _, l, _ in normal if l is not None})
        lignes.append(
            f"<tr><td><b>{_e(CAS_COURT.get(mode, mode))}</b><br><small>{_e(COURT.get(sem, sem))}, {len(g)} essai(s), "
            f"charge {_e(charges)}"
            f"{f', dont {diag} de diagnostic' if diag else ''}</small></td>"
            f"<td>{_axe(pause, VERT, 'interruption')}<small>limite(s) : {_e(', '.join(_s(l, 0) for l in lim_p))}"
            f" ; max {_e(_s(max((v for v, _, _ in pause if v is not None), default=None), 2))}</small></td>"
            f"<td>{_axe(normal, VERT, 'retour')}<small>limite(s) : {_e(', '.join(_s(l, 0) for l in lim_n))}"
            f" ; max {_e(_s(max((v for v, _, _ in normal if v is not None), default=None)))}"
            f"{'' if any(v is not None for v, _, _ in normal) else ' (non mesuré par ces anciens bilans)'}</small></td></tr>")
    return _page("<table class='tab'><tr><th style='width:22%'>cas</th>"
                 "<th>interruption (s)<br><small>temps sans aucune écriture en base</small></th>"
                 "<th>retour à la normale (s)<br><small>du lancement à 0 paiement en attente</small></th></tr>"
                 + "".join(lignes) + "</table>"
                 "<p class='note'>Un point = un essai publié (passer la souris dessus donne son nom). Trait rouge = "
                 "la limite utilisée par ces essais : 60 s pour l'interruption ; 120 s pour revenir à la normale, "
                 "180 s en panne brutale (le service ralenti traite environ 12 paiements/s). Point rouge = "
                 "limite dépassée. Échelle propre à chaque ligne.</p>")


def vue_comparaison(dernier, direct, workspace) -> str:
    """Sémantiques comparées sur les seuls essais publiés dans preuves/ (mêmes chiffres que resume.md)."""
    essais = essais_publies(workspace)
    invalides = [e for e in essais if e["resultat"].get("verdict") == "INVALIDE"]
    diag = [e for e in essais if officiel(e["meta"]) is False]
    retenus = [e for e in essais if e not in invalides and e not in diag and e["meta"].get("mode") != "observee"]
    campagnes = sorted({e["campagne"] for e in retenus})
    groupes = {}
    for e in retenus:
        groupes.setdefault((e["meta"]["mode"], e["meta"]["semantique"]), []).append(e)
    lignes = []
    for (mode, sem), g in sorted(groupes.items()):
        perdus = [e["resultat"]["oracle"]["continuite"]["classes"]["perdu"] for e in g]
        relus = sum(e["resultat"]["oracle"]["doublons"]["doublons_absorbes"] for e in g)
        pauses = [e["resultat"]["pause"]["pause_s"] for e in g if e["resultat"]["pause"].get("pause_s") is not None]
        avec = sum(1 for p in perdus if p)
        c = ROUGE if avec else VERT
        charges = ", ".join(sorted({e["meta"].get("charge", "?") for e in g}))
        lignes.append(f"<tr><td>{_e(CAS_COURT.get(mode, mode))}</td><td>{_e(charges)}</td>"
                      f"<td>{_e(COURT.get(sem, sem))}</td><td>{len(g)}</td><td style='color:{c};font-weight:700'>{avec} sur {len(g)} "
                      f"({'Non respecté' if avec else 'Respecté'})</td><td>{sum(perdus)}</td><td>{relus}</td>"
                      f"<td>{_e(_s(statistics.median(pauses), 2) if pauses else ND)}</td></tr>")
    bloc = "<div class='carte' style='--c:{c}'><h3>{t}</h3><p style='color:inherit'>{x}</p></div>"
    theorie = ("<h3 class='titre2' style='margin-top:0'>Ce que dit la théorie</h3><div class='grille' "
               "style='grid-template-columns:repeat(3,1fr)'>"
               + bloc.format(c=ROUGE, t="at-most-once", x="Le service note qu'il a lu le paiement, <i>puis</i> "
                             "l'écrit. Tué entre les deux, il ne le relit jamais : <b>perte</b>.")
               + bloc.format(c=VERT, t="at-least-once", x="Il écrit, <i>puis</i> note la lecture. Tué entre les "
                             "deux, il relit et réécrit le paiement ; la base le reconnaît : <b>pas de double effet</b>.")
               + bloc.format(c=BLEU, t="exactly-once PostgreSQL", x="La position de lecture est rangée dans la "
                             "base avec le paiement : un paiement déjà écrit est écarté.")
               + "</div><p class='note'>Arrêt propre : le paiement en cours est fini avant l'arrêt, aucune "
                 "différence attendue. Elle n'apparaît qu'en panne brutale.</p>")
    mesures = ("<h3 class='titre2'>Ce que nous avons mesuré</h3>"
               "<table class='tab'><tr><th>cas</th><th>charge</th><th>sémantique</th><th>essais</th>"
               "<th>mises à jour avec perte</th><th>paiements perdus</th><th>lus deux fois, sans second effet</th>"
               "<th>interruption médiane</th></tr>" + "".join(lignes) + "</table>"
               f"<p class='note'><b>Périmètre</b> : {len(retenus)} essais publiés dans <code>preuves/</code> "
               f"(code actuel, depuis le 9 novembre 8 h 36), campagnes : {_e(', '.join(campagnes) or ND)}. "
               f"Écartés : {len(invalides)} essai(s) à la mesure invalide, {len(diag)} essai(s) de diagnostic "
               "(limites différentes des limites officielles). Les essais non publiés ne sont pas comptés.</p>")
    return _page(theorie + mesures)


VUES = {"ensemble": vue_ensemble, "deroulement": vue_deroulement, "integrite": vue_integrite,
        "essais": vue_essais, "comparaison": vue_comparaison}


def essai_choisi(workspace: str, chemin: str) -> dict | None:
    """Essai terminé désigné par son dossier, relatif au dépôt. Limité à preuves/sujet11/
    et runtime/sujet11/ : on ne peut pas lire d'autres fichiers par ce paramètre."""
    dossier = os.path.realpath(os.path.join(workspace, chemin))
    autorises = [os.path.realpath(os.path.join(workspace, x, "sujet11")) + os.sep for x in ("preuves", "runtime")]
    if not any(dossier.startswith(a) for a in autorises):
        return None
    return _essai(dossier)


def bandeau_choisi(choisi: dict) -> str:
    return _bandeau("bleu", "Essai choisi pour la démonstration",
                    f"{_e(choisi['meta'].get('id'))} : ce n'est pas forcément le dernier essai lancé.")


def rendre_synthese(vue: str, workspace: str, en_cours: dict | None, essai: str = "") -> str:
    if essai:
        choisi = essai_choisi(workspace, essai)
        if not choisi:
            return _page(_bandeau("gris", "Essai introuvable", f"{_e(essai)} n'est pas un essai terminé de "
                                  "preuves/sujet11/ ou de runtime/sujet11/."))
        if vue in ("essais", "comparaison"):
            return VUES[vue](choisi, None, workspace)
        # pas de bandeau « essai en cours » ni « interrompu » : on regarde un essai précis
        page = VUES.get(vue, vue_ensemble)(choisi, None, os.path.join(workspace, "__aucun__"))
        return page.replace("<body>", "<body>" + bandeau_choisi(choisi), 1)
    return VUES.get(vue, vue_ensemble)(dernier_essai(workspace), essai_direct(workspace, en_cours), workspace)
