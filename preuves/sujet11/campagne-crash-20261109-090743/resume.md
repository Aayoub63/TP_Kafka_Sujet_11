# Résultats de la campagne

Généré par `scripts/sujet11/resume.py` à partir des essais listés ci-dessous.

## Un essai par ligne

| Essai | Sémantique | Charge | Pause (s) | Retard max | Perdus | Doublons absorbés | Rejets délai (flux) | Verdict |
|---|---|---|---:|---:|---:|---:|---:|---|
| 20261109-090744-crash-at_least_once-ralentie | at_least_once | ralentie (10/s) | 45.009 | 460 | 0 | 1 | 0 | REUSSITE |
| 20261109-091237-crash-at_most_once-ralentie | at_most_once | ralentie (10/s) | 45.089 | 499 | 1 | 0 | 0 | ECHEC : 1 paiement(s) perdu(s) |
| 20261109-091927-crash-at_least_once-ralentie | at_least_once | ralentie (10/s) | 45.004 | 456 | 0 | 1 | 0 | REUSSITE |
| 20261109-092347-crash-at_most_once-ralentie | at_most_once | ralentie (10/s) | 45.088 | 461 | 1 | 0 | 0 | ECHEC : 1 paiement(s) perdu(s) |
| 20261109-093038-crash-at_least_once-ralentie | at_least_once | ralentie (10/s) | 45.005 | 495 | 0 | 1 | 0 | REUSSITE |
| 20261109-093512-crash-at_most_once-ralentie | at_most_once | ralentie (10/s) | 45.089 | 500 | 1 | 0 | 0 | ECHEC : 1 paiement(s) perdu(s) |

## Par combinaison

| Sémantique | Charge | Essais | Pause min / médiane / max (s) | Perdus (total) | Doublons absorbés (total) | Réussites |
|---|---|---:|---|---:|---:|---:|
| at_least_once | ralentie | 3 | 45.004 / 45.005 / 45.009 | 0 | 3 | 3/3 |
| at_most_once | ralentie | 3 | 45.088 / 45.089 / 45.089 | 3 | 0 | 0/3 |
