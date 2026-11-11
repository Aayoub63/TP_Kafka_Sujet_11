# Résultats de la campagne

Généré par `scripts/sujet11/resume.py` à partir des essais listés ci-dessous.

## Un essai par ligne

| Essai | Sémantique | Charge | Pause (s) | Retard max | Perdus | Doublons absorbés | Rejets délai (flux) | Verdict |
|---|---|---|---:|---:|---:|---:|---:|---|
| 20261109-135533-amelioree-at_least_once-normale | at_least_once | normale (20/s) | 0.969 | 8 | 0 | 0 | 0 | REUSSITE |
| 20261109-135930-amelioree-at_most_once-normale | at_most_once | normale (20/s) | 0.954 | 12 | 0 | 0 | 0 | REUSSITE |
| 20261109-140326-amelioree-exactly_once_pg-normale | exactly_once_pg | normale (20/s) | 0.938 | 8 | 0 | 0 | 0 | REUSSITE |
| 20261109-140723-amelioree-at_least_once-normale | at_least_once | normale (20/s) | 0.939 | 7 | 0 | 0 | 0 | REUSSITE |
| 20261109-141120-amelioree-at_most_once-normale | at_most_once | normale (20/s) | 0.98 | 6 | 0 | 0 | 0 | REUSSITE |
| 20261109-141518-amelioree-exactly_once_pg-normale | exactly_once_pg | normale (20/s) | 1.026 | 83 | 0 | 0 | 0 | REUSSITE |
| 20261109-141904-amelioree-at_least_once-normale | at_least_once | normale (20/s) | 0.964 | 29 | 0 | 0 | 0 | REUSSITE |
| 20261109-142250-amelioree-at_most_once-normale | at_most_once | normale (20/s) | 0.978 | 6 | 0 | 0 | 0 | REUSSITE |
| 20261109-142651-amelioree-exactly_once_pg-normale | exactly_once_pg | normale (20/s) | 0.976 | 29 | 0 | 0 | 0 | REUSSITE |

## Par combinaison

| Sémantique | Charge | Essais | Pause min / médiane / max (s) | Perdus (total) | Doublons absorbés (total) | Réussites |
|---|---|---:|---|---:|---:|---:|
| at_least_once | normale | 3 | 0.939 / 0.964 / 0.969 | 0 | 0 | 3/3 |
| at_most_once | normale | 3 | 0.954 / 0.978 / 0.98 | 0 | 0 | 3/3 |
| exactly_once_pg | normale | 3 | 0.938 / 0.976 / 1.026 | 0 | 0 | 3/3 |

## En proportion (intervalle à 95 %)

| Sémantique | Charge | Essais | Essais avec perte | Taux de perte par paiement | Doublons par paiement | Essais sous la cible métier |
|---|---|---:|---|---:|---:|---|
| at_least_once | normale | 3 | 0/3 = 0 % [0 % ; 56,15 %] | 0/9000 = 0 % [0 % ; 0,04 %] | 0/9000 = 0 % [0 % ; 0,04 %] | 3/3 = 100,00 % [43,85 % ; 100,00 %] |
| at_most_once | normale | 3 | 0/3 = 0 % [0 % ; 56,15 %] | 0/9000 = 0 % [0 % ; 0,04 %] | 0/9000 = 0 % [0 % ; 0,04 %] | 3/3 = 100,00 % [43,85 % ; 100,00 %] |
| exactly_once_pg | normale | 3 | 0/3 = 0 % [0 % ; 56,15 %] | 0/9000 = 0 % [0 % ; 0,04 %] | 0/9000 = 0 % [0 % ; 0,04 %] | 3/3 = 100,00 % [43,85 % ; 100,00 %] |

Essais invalides écartés de ce tableau : 0.

Intervalle de Wilson à 95 %. Avec 0 perte sur N paiements, le vrai taux reste inférieur à la borne haute : plus on a de paiements, plus la borne est basse.
