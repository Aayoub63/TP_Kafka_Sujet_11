# Résultats de la campagne

Généré par `scripts/sujet11/resume.py` à partir des essais listés ci-dessous.

## Un essai par ligne

| Essai | Sémantique | Charge | Pause (s) | Retard max | Perdus | Doublons absorbés | Rejets délai (flux) | Verdict |
|---|---|---|---:|---:|---:|---:|---:|---|
| 20261109-103231-crash-at_least_once-ralentie | at_least_once | ralentie (10/s) | 45.015 | 500 | 0 | 1 | 0 | REUSSITE |
| 20261109-103656-crash-at_most_once-ralentie | at_most_once | ralentie (10/s) | 45.095 | 460 | 1 | 0 | 0 | INVALIDE : flux pas terminé avant la collecte |
| 20261109-104608-crash-exactly_once_pg-ralentie | exactly_once_pg | ralentie (10/s) | 45.006 | 461 | 0 | 0 | 0 | REUSSITE |
| 20261109-105022-crash-at_least_once-ralentie | at_least_once | ralentie (10/s) | 45.009 | 461 | 0 | 1 | 0 | REUSSITE |
| 20261109-105432-crash-at_most_once-ralentie | at_most_once | ralentie (10/s) | 45.087 | 459 | 1 | 0 | 0 | INVALIDE : flux pas terminé avant la collecte |
| 20261109-110346-crash-exactly_once_pg-ralentie | exactly_once_pg | ralentie (10/s) | 45.008 | 461 | 0 | 0 | 0 | REUSSITE |
| 20261109-110758-crash-at_least_once-ralentie | at_least_once | ralentie (10/s) | 45.01 | 498 | 0 | 1 | 0 | REUSSITE |
| 20261109-111210-crash-at_most_once-ralentie | at_most_once | ralentie (10/s) | 45.097 | 501 | 1 | 0 | 0 | INVALIDE : flux pas terminé avant la collecte |
| 20261109-112125-crash-exactly_once_pg-ralentie | exactly_once_pg | ralentie (10/s) | 45.005 | 457 | 0 | 0 | 0 | REUSSITE |

## Par combinaison

| Sémantique | Charge | Essais | Pause min / médiane / max (s) | Perdus (total) | Doublons absorbés (total) | Réussites |
|---|---|---:|---|---:|---:|---:|
| at_least_once | ralentie | 3 | 45.009 / 45.01 / 45.015 | 0 | 3 | 3/3 |
| at_most_once | ralentie | 3 | 45.087 / 45.095 / 45.097 | 3 | 0 | 0/3 |
| exactly_once_pg | ralentie | 3 | 45.005 / 45.006 / 45.008 | 0 | 0 | 3/3 |

## En proportion (intervalle à 95 %)

| Sémantique | Charge | Essais | Essais avec perte | Taux de perte par paiement | Doublons par paiement | Essais sous la cible métier |
|---|---|---:|---|---:|---:|---|
| at_least_once | ralentie | 3 | 0/3 = 0 % [0 % ; 56,15 %] | 0/4500 = 0 % [0 % ; 0,09 %] | 3/4500 = 0,07 % [0,02 % ; 0,20 %] | 0/3 = 0 % [0 % ; 56,15 %] |
| at_most_once | ralentie | 3 | 3/3 = 100,00 % [43,85 % ; 100,00 %] | 3/4500 = 0,07 % [0,02 % ; 0,20 %] | 0/4500 = 0 % [0 % ; 0,09 %] | 0/3 = 0 % [0 % ; 56,15 %] |
| exactly_once_pg | ralentie | 3 | 0/3 = 0 % [0 % ; 56,15 %] | 0/4500 = 0 % [0 % ; 0,09 %] | 0/4500 = 0 % [0 % ; 0,09 %] | 0/3 = 0 % [0 % ; 56,15 %] |

Intervalle de Wilson à 95 %. Avec 0 perte sur N paiements, le vrai taux reste inférieur à la borne haute : plus on a de paiements, plus la borne est basse.
