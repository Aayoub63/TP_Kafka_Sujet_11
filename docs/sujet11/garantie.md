# Sujet 11 : le problème et la garantie

## Le problème

Pour mettre à jour un service consommateur, on remplace son conteneur. Avec une
seule instance, le groupe de consommateurs n'a plus aucun membre pendant un
moment. Personne ne lit le topic : les paiements attendent dans Kafka et le
retard augmente. Quand la nouvelle version rejoint le groupe, Kafka lui donne
les partitions (rebalance), puis elle rattrape le retard (drainage).

Le risque concerne le message en cours au moment de l'arrêt :

| Sémantique | Commit de l'offset | Si l'arrêt tombe au mauvais moment |
|---|---|---|
| at-most-once | avant l'écriture en base | le message n'est jamais relu : perte |
| at-least-once | après l'écriture en base | le message est relu : doublon, absorbé par l'upsert |

Nous mettons à jour `persister-valid`, qui lit `simulpix.transactions.validated`
et écrit dans `validated_transactions`. Son effet se vérifie directement en base.

## La garantie

> Pendant la mise à jour de `persister-valid` en at-least-once, aucun paiement
> validé ne doit être perdu ni écrit avec un second effet, et l'arrêt des
> écritures en base ne doit pas dépasser la borne de 60 s. C'est prouvé par
> l'oracle (topic `validated` comparé à PostgreSQL) et par la table d'audit des
> écritures, après un drainage limité à 120 s.

Avec une seule instance, une pause existe forcément. Nous parlons donc de
**reprise avec continuité métier bornée**, pas de mise à jour sans interruption.

at-most-once n'est pas notre solution : nous le testons comme contre-exemple,
pour montrer la perte possible.

## Les définitions

| Notion | Définition retenue | Où elle est calculée |
|---|---|---|
| Pause de traitement | plus long intervalle sans écriture dans `validated_transactions` qui touche la fenêtre de l'opération | `scripts/sujet11/pause.py`, heures de la table d'audit |
| Trou normal | plus long intervalle sans écriture pendant la période de référence, avant la mise à jour | idem |
| Retard maximal | lag maximal du groupe `persister-valid` après le lancement de la mise à jour | `scripts/sujet11/mesure.py` |
| Drainage | le groupe a de nouveau un membre et son lag est revenu à 0, avant 120 s | `scripts/sujet11-maj.sh` |
| Réussite | 0 perdu, 0 valeur fausse, 0 ligne inattendue, drainage terminé, pause ≤ borne | `scripts/sujet11/bilan.py` |

`validated_transactions` n'a pas de colonne d'heure d'écriture : `validated_at`
est l'heure de la décision, qui arrive avec le message. L'heure d'écriture vient
donc de la table d'audit installée par `scripts/toggle-unique.sh off`, qui
enregistre `now()` pour chaque tentative d'écriture.

## La borne

Décision du groupe : **60 s pour la solution minimale**, avec une **cible
métier de 10 s** rapportée à côté.

- 60 s : les essais exploratoires montrent une pause d'environ 44 s. Elle vient
  surtout de la session Kafka de l'ancien membre (`session.timeout.ms`,
  45 000 ms par défaut dans librdkafka 2.8.0), plus environ 5 s de redémarrage
  Docker. On ajoute une marge pour la variabilité normale.
- 10 s : c'est le délai de décision d'un paiement (TTL). La solution minimale ne
  l'atteint pas. La solution améliorée devra s'en approcher.

La borne a été fixée avant la campagne. Elle ne change pas pour faire passer
un essai.
