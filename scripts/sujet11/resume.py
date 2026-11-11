"""Sujet 11 — résumé d'une campagne d'essais.

Lit les resultat.json et bilan.txt de chaque essai, puis écrit dans le
dossier de preuves :
  - resultats.csv : une ligne par essai ;
  - resume.md     : tableau par essai et synthèse par combinaison ;
  - essais/<id>/  : bilan.txt, resultat.json et meta.json de chaque essai, plus
    les fichiers bruts légers qui permettent de refaire l'analyse : relevé du
    groupe (lag.jsonl), compteurs avant / pendant / après (compteurs.jsonl),
    événements Docker (evenements.txt) et oracle.json. Environ 80 Ko par essai.
Les sorties brutes lourdes (topic relu, base, audit) restent dans runtime/.

Usage : python3 scripts/sujet11/resume.py <dossier-preuves> <dossier-essai>...
"""
import csv
import json
import os
import shutil
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proportions  # noqa: E402

FICHIERS = ("bilan.txt", "resultat.json", "meta.json")
# copiés s'ils existent : les anciens essais n'ont pas tous ces fichiers
BRUTS = ("lag.jsonl", "compteurs.jsonl", "evenements.txt", "oracle.json")

COLONNES = ["id", "semantique", "charge", "debit", "total", "pause_s", "trou_normal_s",
            "retard_max", "groupe_vide_duree_s", "attendus", "perdus", "valeurs_fausses",
            "inattendues", "doubles_effets", "trous", "doublons_absorbes", "rejets_delai_flux",
            "drainage_termine", "pause_distincte",
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
        # absents des anciens essais : vide dans le CSV, jamais 0
        "doubles_effets": c.get("doubles_effets"), "trous": (r.get("trous") or {}).get("trous"),
        "pause_distincte": r.get("pause_distincte"),
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
        for f in FICHIERS:
            shutil.copy(os.path.join(d, f), cible)
        for f in BRUTS:
            if os.path.exists(os.path.join(d, f)):
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
        # un essai INVALIDE n'est pas une mesure (même règle que la section suivante)
        g = [l for l in lignes if (l["semantique"], l["charge"]) == (sem, ch) and l["verdict"] != "INVALIDE"]
        if not g:
            continue
        pauses = [l["pause_s"] for l in g if l["pause_s"] is not None]
        md.append(f"| {sem} | {ch} | {len(g)} | "
                  f"{min(pauses)} / {statistics.median(pauses)} / {max(pauses)} | "
                  f"{sum(l['perdus'] for l in g)} | {sum(l['doublons_absorbes'] for l in g)} | "
                  f"{sum(1 for l in g if l['verdict'] == 'REUSSITE')}/{len(g)} |")
    md += ["", "## En proportion (intervalle à 95 %)", "",
           "Chaque essai contient une seule mise à jour (ou une seule panne). La colonne qui compte est "
          "donc « Mises à jour avec perte » : la perte arrive par mise à jour, pas par paiement. Le taux "
          "par paiement dépend de la longueur du flux : il est donné pour information.", "",
          "| Sémantique | Charge | Essais | Mises à jour avec perte | Taux de perte par paiement | Doublons par paiement | Essais sous la cible métier |",
           "|---|---|---:|---|---:|---:|---|"]

    def cellule(k, n, ic):
        """Écrit une proportion mesurée : k/n = x % [bas ; haut]."""
        if not n or ic is None:
            return f"{k}/{n} = -"
        return f"{k}/{n} = {proportions.pourcent(k / n)} [{proportions.pourcent(ic[0])} ; {proportions.pourcent(ic[1])}]"

    invalides = 0
    for sem, ch in combinaisons:
        g = [l for l in lignes if (l["semantique"], l["charge"]) == (sem, ch)]
        # un essai INVALIDE n'est pas une mesure : il ne compte pas dans les proportions
        invalides += sum(1 for l in g if l["verdict"] == "INVALIDE")
        g = [l for l in g if l["verdict"] != "INVALIDE"]
        if not g:
            continue
        s = proportions.synthese(g)
        doublons = sum(l["doublons_absorbes"] for l in g)
        md.append(
            f"| {sem} | {ch} | {s['essais']} | "
            f"{cellule(s['essais_avec_perte'], s['essais'], s['ic_essais_avec_perte'])} | "
            f"{cellule(s['perdus'], s['paiements'], s['ic_taux_perte'])} | "
            f"{cellule(doublons, s['paiements'], proportions.wilson(doublons, s['paiements']))} | "
            f"{cellule(s['essais_sous_cible'], s['essais'], s['ic_sous_cible'])} |")
    md += ["", f"Essais invalides écartés de ce tableau : {invalides}.",
           "", "Intervalle de Wilson à 95 %. Avec 0 perte sur N paiements, le vrai taux "
           "reste inférieur à la borne haute : plus on a de paiements, plus la borne est basse."]
    with open(os.path.join(preuves, "resume.md"), "w") as f:
        f.write("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
