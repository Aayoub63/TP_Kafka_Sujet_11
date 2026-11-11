# Note : pauses mesurées avant le 9 novembre 2026

## Le problème

Avant le 9 novembre, l'audit datait chaque écriture avec `now()`. Dans
PostgreSQL, `now()` donne l'heure de **début de la transaction**, pas l'heure
de l'écriture.

`persister-valid` compte la table après chaque écriture
(`services/persister-valid/main.py`, lignes 266 et 267). Ce comptage ouvre une
transaction qui reste ouverte jusqu'au message suivant. Au démarrage, une
nouvelle instance fait aussi un comptage. Sa première écriture prenait donc
l'heure de son démarrage, et pas l'heure où elle a vraiment écrit.

## Ce qui a été mesuré

Essai « minimale », at-least-once, arrêt propre, le 9 novembre 2026 (ancien
réglage) :

| | heure (s après le lancement) |
|---|---|
| `tx-00000642` d'après le journal de la nouvelle instance | 6,496 |
| `tx-00000642` d'après l'audit | 3,488 |
| dernière vraie écriture de l'ancienne instance | 0,941 |
| pause affichée | 3,007 |
| pause réelle (6,494 - 0,941) | environ 5,5 |

Même essai, relancé avec `clock_timestamp()` : pause de 3,831 s. Le journal
donne 5,705 s pour la première écriture et l'audit 5,700 s.

## Conséquence

Les pauses des dossiers suivants sont **sous-estimées** quand une nouvelle
instance démarre pendant l'essai :

- `campagne-20261107-184829/` (minimale, ancien code, environ 44 s) ;
- `minimale-avec-arret-propre/` (environ 3 s) ;
- `campagne-amelioree-20261107-195243/` et `amelioree-premiers-essais/`
  (environ 1 s) ;
- `amo-ralenti-80ms/` et `exploration/`.

On ne connaît pas l'écart pour chacun : il dépend du moment où la nouvelle
instance a démarré. Les comptes de l'oracle (perdus, valeurs fausses,
doublons) ne dépendent pas de l'heure et restent valables.

Ces dossiers restent tels quels. Les campagnes sont refaites avec le nouveau
réglage.
