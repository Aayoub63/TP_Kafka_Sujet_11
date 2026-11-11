# Résultats de la campagne

Généré par `scripts/sujet11/resume.py` à partir des essais listés ci-dessous.

## Un essai par ligne

| Essai | Sémantique | Charge | Pause (s) | Retard max | Perdus | Doublons absorbés | Rejets délai (flux) | Verdict |
|---|---|---|---:|---:|---:|---:|---:|---|
| 20261110-221339-crash-at_least_once-ralentie | at_least_once | ralentie (10/s) | 45.007 | 458 | 0 | 1 | 0 | REUSSITE |
| 20261110-221754-crash-at_most_once-ralentie | at_most_once | ralentie (10/s) | 45.1 | 459 | 1 | 0 | 0 | ECHEC : 1 paiement(s) perdu(s) ; 1 paiement(s) sans décision en base (ni validé, ni rejeté) |
| 20261110-222207-crash-at_least_once-ralentie | at_least_once | ralentie (10/s) | 45.004 | 454 | 0 | 1 | 0 | REUSSITE |
| 20261110-222639-crash-at_most_once-ralentie | at_most_once | ralentie (10/s) | 45.089 | 457 | 1 | 0 | 0 | ECHEC : 1 paiement(s) perdu(s) ; 1 paiement(s) sans décision en base (ni validé, ni rejeté) |
| 20261110-223054-crash-at_least_once-ralentie | at_least_once | ralentie (10/s) | 45.006 | 501 | 0 | 1 | 0 | REUSSITE |
| 20261110-223511-crash-at_most_once-ralentie | at_most_once | ralentie (10/s) | 45.018 | 458 | 0 | 0 | 0 | REUSSITE |

## Par combinaison

| Sémantique | Charge | Essais | Pause min / médiane / max (s) | Perdus (total) | Doublons absorbés (total) | Réussites |
|---|---|---:|---|---:|---:|---:|
| at_least_once | ralentie | 3 | 45.004 / 45.006 / 45.007 | 0 | 3 | 3/3 |
| at_most_once | ralentie | 3 | 45.018 / 45.089 / 45.1 | 2 | 0 | 1/3 |

## En proportion (intervalle à 95 %)

Chaque essai contient une seule mise à jour (ou une seule panne). La colonne qui compte est donc « Mises à jour avec perte » : la perte arrive par mise à jour, pas par paiement. Le taux par paiement dépend de la longueur du flux : il est donné pour information.

| Sémantique | Charge | Essais | Mises à jour avec perte | Taux de perte par paiement | Doublons par paiement | Essais sous la cible métier |
|---|---|---:|---|---:|---:|---|
| at_least_once | ralentie | 3 | 0/3 = 0 % [0 % ; 56,15 %] | 0/4500 = 0 % [0 % ; 0,09 %] | 3/4500 = 0,07 % [0,02 % ; 0,20 %] | 0/3 = 0 % [0 % ; 56,15 %] |
| at_most_once | ralentie | 3 | 2/3 = 66,67 % [20,77 % ; 93,85 %] | 2/4500 = 0,04 % [0,01 % ; 0,16 %] | 0/4500 = 0 % [0 % ; 0,09 %] | 0/3 = 0 % [0 % ; 56,15 %] |

Essais invalides écartés de ce tableau : 0.

Intervalle de Wilson à 95 %. Avec 0 perte sur N paiements, le vrai taux reste inférieur à la borne haute : plus on a de paiements, plus la borne est basse.
