# Résultats de la campagne

Généré par `scripts/sujet11/resume.py` à partir des essais listés ci-dessous.

## Un essai par ligne

| Essai | Sémantique | Charge | Pause (s) | Retard max | Perdus | Doublons absorbés | Rejets délai (flux) | Verdict |
|---|---|---|---:|---:|---:|---:|---:|---|
| 20261109-145342-observee-at_least_once-normale | at_least_once | normale (20/s) | 3.54 | 128 | 0 | 0 | 0 | OBSERVATION |

## Par combinaison

| Sémantique | Charge | Essais | Pause min / médiane / max (s) | Perdus (total) | Doublons absorbés (total) | Réussites |
|---|---|---:|---|---:|---:|---:|
| at_least_once | normale | 1 | 3.54 / 3.54 / 3.54 | 0 | 0 | 0/1 |

## En proportion (intervalle à 95 %)

| Sémantique | Charge | Essais | Essais avec perte | Taux de perte par paiement | Doublons par paiement | Essais sous la cible métier |
|---|---|---:|---|---:|---:|---|
| at_least_once | normale | 1 | 0/1 = 0 % [0 % ; 79,35 %] | 0/3000 = 0 % [0 % ; 0,13 %] | 0/3000 = 0 % [0 % ; 0,13 %] | 1/1 = 100,00 % [20,65 % ; 100,00 %] |

Essais invalides écartés de ce tableau : 0.

Intervalle de Wilson à 95 %. Avec 0 perte sur N paiements, le vrai taux reste inférieur à la borne haute : plus on a de paiements, plus la borne est basse.
