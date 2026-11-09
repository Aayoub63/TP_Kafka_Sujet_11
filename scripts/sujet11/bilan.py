"""Sujet 11 — bilan d'un essai de mise à jour et verdict.

Rassemble, pour un dossier d'essai :
  - meta.json      : paramètres et instants (écrit par sujet11-maj.sh) ;
  - lag.jsonl      : relevés du groupe (mesure.py) ;
  - evenements.txt : événements Docker du conteneur persister-valid ;
  - oracle.json    : classement des identités (oracle.py) ;
  - donnees/audit.json : heures des écritures (pause.py).

Écrit resultat.json et bilan.txt. En mode « minimale », le code de sortie
vaut 0 si la continuité est respectée, 1 sinon :
  - aucun paiement perdu, aucune valeur fausse, aucune ligne inattendue ;
  - drainage terminé avant la limite ;
  - pause <= borne.
En mode « observee », le bilan est affiché sans verdict (code 0).

Usage : python3 scripts/sujet11/bilan.py <dossier-essai>
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pause  # noqa: E402


def lire_json(dossier, nom):
    with open(os.path.join(dossier, nom)) as f:
        return json.load(f)


def lire_lag(dossier):
    with open(os.path.join(dossier, "lag.jsonl")) as f:
        return [json.loads(l) for l in f if l.strip()]


def lire_evenements(dossier):
    """Lignes « <TimeNano> <action> » de `docker events` (heure en nanosecondes)."""
    evenements = []
    chemin = os.path.join(dossier, "evenements.txt")
    if os.path.exists(chemin):
        for ligne in open(chemin):
            p = ligne.split()
            if len(p) >= 2 and p[0].isdigit():
                evenements.append((int(p[0]) / 1e9, p[1].rstrip(":")))
    return evenements


def chronologie(meta, lag, evenements):
    """Repères relatifs à t0, en secondes."""
    t0 = meta["t0"]
    rel = lambda t: round(t - t0, 3) if t is not None else None  # noqa: E731
    premier = lambda actions: next((t for t, a in evenements if a in actions), None)  # noqa: E731
    apres_t0 = [x for x in lag if x["t"] >= t0]
    vide = next((x["t"] for x in apres_t0 if x["membres"] == 0), None)
    reattribue = None
    if vide is not None:
        reattribue = next((x["t"] for x in apres_t0 if x["t"] > vide and x["membres"] > 0), None)
    fin_drainage = None
    if reattribue is not None:
        fin_drainage = next((x["t"] for x in apres_t0 if x["t"] >= reattribue and x["lag"] == 0), None)
    return {
        "signal_arret_s": rel(premier({"kill"})),
        "conteneur_mort_s": rel(premier({"die"})),
        "nouveau_conteneur_s": rel(premier({"start"})),
        "groupe_vide_s": rel(vide),
        "partitions_reattribuees_s": rel(reattribue),
        "lag_revenu_a_zero_s": rel(fin_drainage),
        "groupe_vide_duree_s": round(reattribue - vide, 3) if vide and reattribue else None,
    }


def verdict(meta, oracle, mesure_pause, drainage_ok):
    raisons = []
    classes = oracle["continuite"]["classes"]
    if classes["perdu"]:
        raisons.append(f"{classes['perdu']} paiement(s) perdu(s)")
    if classes["valeur_fausse"]:
        raisons.append(f"{classes['valeur_fausse']} valeur(s) fausse(s)")
    if oracle["continuite"]["lignes_inattendues"]:
        raisons.append(f"{oracle['continuite']['lignes_inattendues']} ligne(s) inattendue(s)")
    if not drainage_ok:
        raisons.append(f"drainage non terminé en {meta['drainage_max_s']} s")
    if mesure_pause["pause_s"] is None or not mesure_pause["reprise"]:
        raisons.append("pas de reprise des écritures")
    elif mesure_pause["pause_s"] > meta["borne_s"]:
        raisons.append(f"pause {mesure_pause['pause_s']} s > borne {meta['borne_s']} s")
    return ("REUSSITE" if not raisons else "ECHEC"), raisons


def main():
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    dossier = sys.argv[1]
    meta = lire_json(dossier, "meta.json")
    oracle = lire_json(dossier, "oracle.json")
    lag = lire_lag(dossier)
    evenements = lire_evenements(dossier)
    audit = lire_json(dossier, os.path.join("donnees", "audit.json"))

    t0 = meta["t0"]
    mesure_pause = pause.mesurer(audit, t0, meta["fin"], meta["debut_reference"])
    apres = [x for x in lag if x["t"] >= t0]
    resultat = {
        "parametres": {k: meta.get(k) for k in ("mode", "semantique", "charge", "total", "debit",
                                                 "borne_s", "cible_metier_s", "drainage_max_s")},
        "sous_cible_metier": (mesure_pause["pause_s"] is not None and meta.get("cible_metier_s") is not None
                              and mesure_pause["pause_s"] <= meta["cible_metier_s"]),
        "pause": mesure_pause,
        "retard_max_messages": max((x["lag"] for x in apres), default=None),
        "chronologie": chronologie(meta, lag, evenements),
        "drainage_termine": meta["drainage_termine"],
        "oracle": oracle,
    }
    if meta["mode"] == "minimale":
        resultat["verdict"], resultat["raisons"] = verdict(meta, oracle, mesure_pause,
                                                           meta["drainage_termine"])
    else:
        resultat["verdict"], resultat["raisons"] = "OBSERVATION", []

    with open(os.path.join(dossier, "resultat.json"), "w") as f:
        json.dump(resultat, f, indent=2, ensure_ascii=False)

    c = oracle["continuite"]["classes"]
    ch = resultat["chronologie"]
    p = resultat["parametres"]
    texte = [
        "=" * 66,
        f" BILAN SUJET 11 — mode={p['mode']} sémantique={p['semantique']} charge={p['charge']}",
        "=" * 66,
        f" Flux : {p['total']} Pix à {p['debit']} Pix/s",
        f" Pause en base         : {mesure_pause['pause_s']} s (borne {p['borne_s']} s,"
        f" cible métier {p['cible_metier_s']} s : {'atteinte' if resultat['sous_cible_metier'] else 'non atteinte'})",
        f" Trou normal (référence): {mesure_pause['trou_normal_s']} s",
        f" Retard maximal        : {resultat['retard_max_messages']} messages",
        " Chronologie (secondes après le lancement de la mise à jour) :",
        f"   signal d'arrêt {ch['signal_arret_s']} | conteneur mort {ch['conteneur_mort_s']}"
        f" | nouveau conteneur {ch['nouveau_conteneur_s']}",
        f"   groupe vide {ch['groupe_vide_s']} | partitions réattribuées {ch['partitions_reattribuees_s']}"
        f" | lag à 0 {ch['lag_revenu_a_zero_s']}",
        f"   dernière écriture {mesure_pause['derniere_ecriture_avant_s']}"
        f" | première écriture après {mesure_pause['premiere_ecriture_apres_s']}",
        f" Oracle : attendus={oracle['continuite']['attendus']} présents={c['present']}"
        f" perdus={c['perdu']} valeurs fausses={c['valeur_fausse']}"
        f" rejets délai={c['rejet_delai']} rejets métier={c['rejet_metier']}"
        f" lignes inattendues={oracle['continuite']['lignes_inattendues']}",
        f" Doublons absorbés (audit) : {oracle['doublons']['doublons_absorbes']}",
        f" Rejets pour délai sur tout le flux : {oracle.get('flux', {}).get('rejets_delai')}",
        f" Drainage terminé : {'oui' if meta['drainage_termine'] else 'non'}",
        "-" * 66,
        f" VERDICT : {resultat['verdict']}" + (" — " + " ; ".join(resultat["raisons"])
                                             if resultat["raisons"] else ""),
        "=" * 66,
    ]
    with open(os.path.join(dossier, "bilan.txt"), "w") as f:
        f.write("\n".join(texte) + "\n")
    print("\n".join(texte))
    return 1 if resultat["verdict"] == "ECHEC" else 0


if __name__ == "__main__":
    sys.exit(main())
