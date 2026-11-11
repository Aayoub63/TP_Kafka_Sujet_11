# Résultats de la campagne

Généré par `scripts/sujet11/resume.py` à partir des essais listés ci-dessous.

## Un essai par ligne

| Essai | Sémantique | Charge | Pause (s) | Retard max | Perdus | Doublons absorbés | Rejets délai (flux) | Verdict |
|---|---|---|---:|---:|---:|---:|---:|---|
| 20261110-213353-minimale-at_least_once-normale | at_least_once | normale (20/s) | 3.425 | 110 | 0 | 0 | 0 | REUSSITE |
| 20261110-213753-minimale-at_least_once-normale | at_least_once | normale (20/s) | 3.425 | 124 | 0 | 0 | 0 | REUSSITE |
| 20261110-214140-minimale-at_least_once-normale | at_least_once | normale (20/s) | 3.404 | 99 | 0 | 0 | 0 | REUSSITE |
| 20261110-214527-minimale-at_least_once-normale | at_least_once | normale (20/s) | 3.624 | 101 | 0 | 0 | 0 | REUSSITE |
| 20261110-214918-minimale-at_least_once-normale | at_least_once | normale (20/s) | 3.719 | 128 | 0 | 0 | 0 | REUSSITE |

## Par combinaison

| Sémantique | Charge | Essais | Pause min / médiane / max (s) | Perdus (total) | Doublons absorbés (total) | Réussites |
|---|---|---:|---|---:|---:|---:|
| at_least_once | normale | 5 | 3.404 / 3.425 / 3.719 | 0 | 0 | 5/5 |

## En proportion (intervalle à 95 %)

Chaque essai contient une seule mise à jour (ou une seule panne). La colonne qui compte est donc « Mises à jour avec perte » : la perte arrive par mise à jour, pas par paiement. Le taux par paiement dépend de la longueur du flux : il est donné pour information.

| Sémantique | Charge | Essais | Mises à jour avec perte | Taux de perte par paiement | Doublons par paiement | Essais sous la cible métier |
|---|---|---:|---|---:|---:|---|
| at_least_once | normale | 5 | 0/5 = 0 % [0 % ; 43,45 %] | 0/15000 = 0 % [0 % ; 0,03 %] | 0/15000 = 0 % [0 % ; 0,03 %] | 5/5 = 100,00 % [56,55 % ; 100,00 %] |

Essais invalides écartés de ce tableau : 0.

Intervalle de Wilson à 95 %. Avec 0 perte sur N paiements, le vrai taux reste inférieur à la borne haute : plus on a de paiements, plus la borne est basse.
