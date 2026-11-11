# Résultats de la campagne

Généré par `scripts/sujet11/resume.py` à partir des essais listés ci-dessous.

## Un essai par ligne

| Essai | Sémantique | Charge | Pause (s) | Retard max | Perdus | Doublons absorbés | Rejets délai (flux) | Verdict |
|---|---|---|---:|---:|---:|---:|---:|---|
| 20261109-113934-minimale-at_least_once-normale | at_least_once | normale (20/s) | 3.463 | 78 | 0 | 0 | 0 | REUSSITE |
| 20261109-114433-minimale-at_most_once-normale | at_most_once | normale (20/s) | 4.416 | 123 | 0 | 0 | 0 | REUSSITE |
| 20261109-115010-minimale-exactly_once_pg-normale | exactly_once_pg | normale (20/s) | 3.443 | 85 | 0 | 0 | 0 | REUSSITE |
| 20261109-115352-minimale-at_least_once-normale | at_least_once | normale (20/s) | 3.504 | 94 | 0 | 0 | 0 | REUSSITE |
| 20261109-115735-minimale-at_most_once-normale | at_most_once | normale (20/s) | 3.514 | 94 | 0 | 0 | 0 | REUSSITE |
| 20261109-120135-minimale-exactly_once_pg-normale | exactly_once_pg | normale (20/s) | 3.443 | 68 | 0 | 0 | 0 | REUSSITE |
| 20261109-120534-minimale-at_least_once-normale | at_least_once | normale (20/s) | 3.418 | 78 | 0 | 0 | 0 | REUSSITE |
| 20261109-120937-minimale-at_most_once-normale | at_most_once | normale (20/s) | None | 64 | 0 | 0 | 35 | INVALIDE : horloge de Docker décalée de -0.891 s puis -994.709 s ; flux pas terminé avant la collecte |
| 20261109-135122-minimale-exactly_once_pg-normale | exactly_once_pg | normale (20/s) | 3.676 | 94 | 0 | 0 | 0 | REUSSITE |
| 20261109-145957-minimale-at_most_once-normale | at_most_once | normale (20/s) | 3.377 | 78 | 0 | 0 | 0 | REUSSITE |

## Par combinaison

| Sémantique | Charge | Essais | Pause min / médiane / max (s) | Perdus (total) | Doublons absorbés (total) | Réussites |
|---|---|---:|---|---:|---:|---:|
| at_least_once | normale | 3 | 3.418 / 3.463 / 3.504 | 0 | 0 | 3/3 |
| at_most_once | normale | 3 | 3.377 / 3.514 / 4.416 | 0 | 0 | 3/3 |
| exactly_once_pg | normale | 3 | 3.443 / 3.443 / 3.676 | 0 | 0 | 3/3 |

## En proportion (intervalle à 95 %)

| Sémantique | Charge | Essais | Essais avec perte | Taux de perte par paiement | Doublons par paiement | Essais sous la cible métier |
|---|---|---:|---|---:|---:|---|
| at_least_once | normale | 3 | 0/3 = 0 % [0 % ; 56,15 %] | 0/9000 = 0 % [0 % ; 0,04 %] | 0/9000 = 0 % [0 % ; 0,04 %] | 3/3 = 100,00 % [43,85 % ; 100,00 %] |
| at_most_once | normale | 3 | 0/3 = 0 % [0 % ; 56,15 %] | 0/9000 = 0 % [0 % ; 0,04 %] | 0/9000 = 0 % [0 % ; 0,04 %] | 3/3 = 100,00 % [43,85 % ; 100,00 %] |
| exactly_once_pg | normale | 3 | 0/3 = 0 % [0 % ; 56,15 %] | 0/9000 = 0 % [0 % ; 0,04 %] | 0/9000 = 0 % [0 % ; 0,04 %] | 3/3 = 100,00 % [43,85 % ; 100,00 %] |

Essais invalides écartés de ce tableau : 1.

Intervalle de Wilson à 95 %. Avec 0 perte sur N paiements, le vrai taux reste inférieur à la borne haute : plus on a de paiements, plus la borne est basse.
