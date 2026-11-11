# Résultats de la campagne

Généré par `scripts/sujet11/resume.py` à partir des essais listés ci-dessous.

## Un essai par ligne

| Essai | Sémantique | Charge | Pause (s) | Retard max | Perdus | Doublons absorbés | Rejets délai (flux) | Verdict |
|---|---|---|---:|---:|---:|---:|---:|---|
| 20261109-144222-amelioree-at_least_once-forte | at_least_once | forte (60/s) | 0.998 | 37 | 0 | 0 | 0 | REUSSITE |
| 20261109-144609-amelioree-at_most_once-forte | at_most_once | forte (60/s) | 0.945 | 7 | 0 | 0 | 0 | REUSSITE |
| 20261109-144956-amelioree-exactly_once_pg-forte | exactly_once_pg | forte (60/s) | 0.947 | 7 | 0 | 0 | 0 | REUSSITE |

## Par combinaison

| Sémantique | Charge | Essais | Pause min / médiane / max (s) | Perdus (total) | Doublons absorbés (total) | Réussites |
|---|---|---:|---|---:|---:|---:|
| at_least_once | forte | 1 | 0.998 / 0.998 / 0.998 | 0 | 0 | 1/1 |
| at_most_once | forte | 1 | 0.945 / 0.945 / 0.945 | 0 | 0 | 1/1 |
| exactly_once_pg | forte | 1 | 0.947 / 0.947 / 0.947 | 0 | 0 | 1/1 |

## En proportion (intervalle à 95 %)

| Sémantique | Charge | Essais | Essais avec perte | Taux de perte par paiement | Doublons par paiement | Essais sous la cible métier |
|---|---|---:|---|---:|---:|---|
| at_least_once | forte | 1 | 0/1 = 0 % [0 % ; 79,35 %] | 0/9000 = 0 % [0 % ; 0,04 %] | 0/9000 = 0 % [0 % ; 0,04 %] | 1/1 = 100,00 % [20,65 % ; 100,00 %] |
| at_most_once | forte | 1 | 0/1 = 0 % [0 % ; 79,35 %] | 0/9000 = 0 % [0 % ; 0,04 %] | 0/9000 = 0 % [0 % ; 0,04 %] | 1/1 = 100,00 % [20,65 % ; 100,00 %] |
| exactly_once_pg | forte | 1 | 0/1 = 0 % [0 % ; 79,35 %] | 0/9000 = 0 % [0 % ; 0,04 %] | 0/9000 = 0 % [0 % ; 0,04 %] | 1/1 = 100,00 % [20,65 % ; 100,00 %] |

Essais invalides écartés de ce tableau : 0.

Intervalle de Wilson à 95 %. Avec 0 perte sur N paiements, le vrai taux reste inférieur à la borne haute : plus on a de paiements, plus la borne est basse.
