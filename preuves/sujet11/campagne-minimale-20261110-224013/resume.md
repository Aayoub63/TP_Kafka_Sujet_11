# Résultats de la campagne

Généré par `scripts/sujet11/resume.py` à partir des essais listés ci-dessous.

## Un essai par ligne

| Essai | Sémantique | Charge | Pause (s) | Retard max | Perdus | Doublons absorbés | Rejets délai (flux) | Verdict |
|---|---|---|---:|---:|---:|---:|---:|---|
| 20261110-224013-minimale-at_least_once-forte | at_least_once | forte (60/s) | 3.413 | 168 | 0 | 0 | 0 | REUSSITE |
| 20261110-224404-minimale-at_least_once-forte | at_least_once | forte (60/s) | 4.369 | 217 | 0 | 0 | 0 | REUSSITE |
| 20261110-224755-minimale-at_least_once-forte | at_least_once | forte (60/s) | 3.458 | 192 | 0 | 0 | 0 | REUSSITE |

## Par combinaison

| Sémantique | Charge | Essais | Pause min / médiane / max (s) | Perdus (total) | Doublons absorbés (total) | Réussites |
|---|---|---:|---|---:|---:|---:|
| at_least_once | forte | 3 | 3.413 / 3.458 / 4.369 | 0 | 0 | 3/3 |

## En proportion (intervalle à 95 %)

Chaque essai contient une seule mise à jour (ou une seule panne). La colonne qui compte est donc « Mises à jour avec perte » : la perte arrive par mise à jour, pas par paiement. Le taux par paiement dépend de la longueur du flux : il est donné pour information.

| Sémantique | Charge | Essais | Mises à jour avec perte | Taux de perte par paiement | Doublons par paiement | Essais sous la cible métier |
|---|---|---:|---|---:|---:|---|
| at_least_once | forte | 3 | 0/3 = 0 % [0 % ; 56,15 %] | 0/27000 = 0 % [0 % ; 0,01 %] | 0/27000 = 0 % [0 % ; 0,01 %] | 3/3 = 100,00 % [43,85 % ; 100,00 %] |

Essais invalides écartés de ce tableau : 0.

Intervalle de Wilson à 95 %. Avec 0 perte sur N paiements, le vrai taux reste inférieur à la borne haute : plus on a de paiements, plus la borne est basse.
