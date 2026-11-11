# Résultats de la campagne

Généré par `scripts/sujet11/resume.py` à partir des essais listés ci-dessous.

## Un essai par ligne

| Essai | Sémantique | Charge | Pause (s) | Retard max | Perdus | Doublons absorbés | Rejets délai (flux) | Verdict |
|---|---|---|---:|---:|---:|---:|---:|---|
| 20261109-112700-crash-at_most_once-ralentie | at_most_once | ralentie (10/s) | 45.092 | 502 | 1 | 0 | 0 | ECHEC : 1 paiement(s) perdu(s) |
| 20261109-113113-crash-at_most_once-ralentie | at_most_once | ralentie (10/s) | 45.095 | 460 | 1 | 0 | 0 | ECHEC : 1 paiement(s) perdu(s) |
| 20261109-113523-crash-at_most_once-ralentie | at_most_once | ralentie (10/s) | 45.1 | 453 | 1 | 0 | 0 | ECHEC : 1 paiement(s) perdu(s) |

## Par combinaison

| Sémantique | Charge | Essais | Pause min / médiane / max (s) | Perdus (total) | Doublons absorbés (total) | Réussites |
|---|---|---:|---|---:|---:|---:|
| at_most_once | ralentie | 3 | 45.092 / 45.095 / 45.1 | 3 | 0 | 0/3 |

## En proportion (intervalle à 95 %)

| Sémantique | Charge | Essais | Essais avec perte | Taux de perte par paiement | Doublons par paiement | Essais sous la cible métier |
|---|---|---:|---|---:|---:|---|
| at_most_once | ralentie | 3 | 3/3 = 100,00 % [43,85 % ; 100,00 %] | 3/4500 = 0,07 % [0,02 % ; 0,20 %] | 0/4500 = 0 % [0 % ; 0,09 %] | 0/3 = 0 % [0 % ; 56,15 %] |

Essais invalides écartés de ce tableau : 0.

Intervalle de Wilson à 95 %. Avec 0 perte sur N paiements, le vrai taux reste inférieur à la borne haute : plus on a de paiements, plus la borne est basse.
