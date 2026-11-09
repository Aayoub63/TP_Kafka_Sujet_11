"""Sujet 11 — résumé d'une campagne d'essais.

Lit les resultat.json et bilan.txt de chaque essai, puis écrit dans le
dossier de preuves :
  - resultats.csv : une ligne par essai ;
  - resume.md     : tableau par essai et synthèse par combinaison ;
  - essais/<id>/  : bilan.txt, resultat.json et meta.json de chaque essai.
Les sorties brutes (topic relu, base, audit) restent dans runtime/.

Usage : python3 scripts/sujet11/resume.py <dossier-preuves> <dossier-essai>...
"""
import csv
import json
import os
import shutil
import statistics
import sys

COLONNES = ["id", "semantique", "charge", "debit", "total", "pause_s", "trou_normal_s",
            "retard_max", "groupe_vide_duree_s", "attendus", "perdus", "valeurs_fausses",
            "inattendues", "doublons_absorbes", "rejets_delai_flux", "drainage_termine",
            "sous_cible_metier", "verdict", "raisons"]


def ligne(dossier):
    r = json.load(open(os.path.join(dossier, "resultat.json")))
    m = json.load(open(os.path.join(dossier, "meta.json")))
    c = r["oracle"]["continuite"]
    return {
        "id": m["id"], "semantique": m["semantique"], "charge": m["charge"],
        "debit": m["debit"], "total": m["total"],
        "pause_s": r["pause"]["pause_s"], "trou_normal_s": r["pause"]["trou_normal_s"],
        "retard_max": r["retard_max_messages"],
        "groupe_vide_duree_s": r["chronologie"]["groupe_vide_duree_s"],
        "attendus": c["attendus"], "perdus": c["classes"]["perdu"],
        "valeurs_fausses": c["classes"]["valeur_fausse"], "inattendues": c["lignes_inattendues"],
        "doublons_absorbes": r["oracle"]["doublons"]["doublons_absorbes"],
        "rejets_delai_flux": r["oracle"].get("flux", {}).get("rejets_delai"),
        "drainage_termine": r["drainage_termine"], "sous_cible_metier": r.get("sous_cible_metier"),
        "verdict": r["verdict"], "raisons": " ; ".join(r["raisons"]),
    }


def main():
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    preuves, essais = sys.argv[1], sys.argv[2:]
    os.makedirs(os.path.join(preuves, "essais"), exist_ok=True)
    lignes = []
    for d in essais:
        if not os.path.exists(os.path.join(d, "resultat.json")):
            print(f"[sujet11] essai incomplet ignoré : {d}", file=sys.stderr)
            continue
        lignes.append(ligne(d))
        cible = os.path.join(preuves, "essais", os.path.basename(d.rstrip("/")))
        os.makedirs(cible, exist_ok=True)
        for f in ("bilan.txt", "resultat.json", "meta.json"):
            shutil.copy(os.path.join(d, f), cible)

    with open(os.path.join(preuves, "resultats.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES)
        w.writeheader()
        w.writerows(lignes)

    md = ["# Résultats de la campagne", "",
          "Généré par `scripts/sujet11/resume.py` à partir des essais listés ci-dessous.", "",
          "## Un essai par ligne", "",
          "| Essai | Sémantique | Charge | Pause (s) | Retard max | Perdus | Doublons absorbés | Rejets délai (flux) | Verdict |",
          "|---|---|---|---:|---:|---:|---:|---:|---|"]
    for l in lignes:
        md.append(f"| {l['id']} | {l['semantique']} | {l['charge']} ({l['debit']}/s) | {l['pause_s']} | "
                  f"{l['retard_max']} | {l['perdus']} | {l['doublons_absorbes']} | {l['rejets_delai_flux']} | "
                  f"{l['verdict']}{(' : ' + l['raisons']) if l['raisons'] else ''} |")
    md += ["", "## Par combinaison", "",
           "| Sémantique | Charge | Essais | Pause min / médiane / max (s) | Perdus (total) | Doublons absorbés (total) | Réussites |",
           "|---|---|---:|---|---:|---:|---:|"]
    combinaisons = sorted({(l["semantique"], l["charge"]) for l in lignes})
    for sem, ch in combinaisons:
        g = [l for l in lignes if (l["semantique"], l["charge"]) == (sem, ch)]
        pauses = [l["pause_s"] for l in g if l["pause_s"] is not None]
        md.append(f"| {sem} | {ch} | {len(g)} | "
                  f"{min(pauses)} / {statistics.median(pauses)} / {max(pauses)} | "
                  f"{sum(l['perdus'] for l in g)} | {sum(l['doublons_absorbes'] for l in g)} | "
                  f"{sum(1 for l in g if l['verdict'] == 'REUSSITE')}/{len(g)} |")
    with open(os.path.join(preuves, "resume.md"), "w") as f:
        f.write("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
