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

## Les identités attendues et les rejets

Les paiements attendus en base sont ceux du topic `validated` : la banque les
a validés. Un **rejet métier légitime** n'en fait pas partie : il est publié
dans `rejected`, jamais dans `validated`, et il est compté à part. Il ne fait
pas échouer l'essai. En revanche, un paiement du topic `validated` retrouvé
**seulement** dans `rejected_transactions` fait échouer l'essai : le client a
reçu « validé », alors que la base dit « rejeté ».

## Les définitions

| Notion | Définition retenue | Où elle est calculée |
|---|---|---|
| Pause de traitement | plus long intervalle sans écriture dans `validated_transactions` qui touche la fenêtre de l'opération | `scripts/sujet11/pause.py`, heures de la table d'audit |
| Trou normal | plus long intervalle sans écriture pendant la période de référence, avant la mise à jour | idem |
| Retard maximal | lag maximal du groupe `persister-valid` après le lancement de la mise à jour | `scripts/sujet11/mesure.py` |
| Drainage (retour à la normale) | le groupe a de nouveau un membre et son lag est revenu à 0, avant la limite de l'essai, comptée depuis le lancement de la mise à jour : 120 s, ou 180 s en panne brutale (voir « Les bornes ») | `scripts/sujet11-maj.sh` |
| Temps de reprise | du lancement de la mise à jour à la première écriture après l'interruption | `pause.py` |
| Temps de rattrapage | de la reprise au retour à la normale (information, sans borne propre) | page de synthèse |
| Réussite | toutes les mesures sont valides, et : 0 perdu, 0 paiement validé retrouvé seulement dans les rejets, 0 valeur fausse (montant, devise, comptes), 0 ligne inattendue, 0 double effet, 0 paiement à la fois validé et rejeté, 0 trou de `transaction_id`, retard résorbé avant la limite de l'essai, reprise des écritures, pause ≤ borne | `scripts/sujet11/bilan.py`, `decider` |
| Échec | au moins une anomalie **démontrée** : une anomalie d'intégrité quand les mesures d'intégrité sont valides, une anomalie de temps quand les mesures de temps sont valides | idem |
| Invalide | aucune anomalie démontrée, mais une mesure manque ou est douteuse. Intégrité : flux non terminé, tables non relues, relecture du topic incomplète, base encore en écriture. Temps : horloge Docker qui dérive de plus de 0,5 s, audit vide, aucun relevé du groupe. Scénario : sémantique appliquée différente, avant ou après la mise à jour | `bilan.py`, `invalidites_par_type` |
| Raisons | toutes sont gardées, même quand l'essai est INVALIDE : une anomalie non confirmée est écrite avec « (non confirmé : …) », une invalidité avec « mesure invalide : … » | `bilan.py`, `decider` |
| Pause distincte | la pause dépasse 1,5 fois le trou normal. Sinon, la mise à jour n'a pas d'effet mesurable : le générateur émet par paquets (trou normal d'environ 1 s à 20 Pix/s), et une pause plus courte que ce rythme est invisible | `bilan.py`, `pause_distincte` |

`validated_transactions` n'a pas de colonne d'heure d'écriture : `validated_at`
est l'heure de la décision, qui arrive avec le message. L'heure d'écriture vient
donc de la table d'audit installée par `scripts/toggle-unique.sh off`, qui
enregistre l'heure de chaque tentative d'écriture.

Depuis le 9 novembre, `scripts/sujet11-maj.sh` règle cette heure sur
`clock_timestamp()` (heure réelle de l'écriture) au lieu de `now()` (heure de
début de la transaction). `persister-valid` compte la table après chaque
écriture et garde cette transaction ouverte jusqu'au message suivant. Avec
`now()`, la première écriture d'une nouvelle instance prenait l'heure de son
démarrage, et la pause mesurée était trop courte. Les essais d'avant cette date
sont concernés : voir `preuves/sujet11/NOTE-heure-audit.md`.

## Les bornes

Décision du groupe, une table dans le code (`BORNES_OFFICIELLES` dans
`scripts/sujet11/bilan.py`, la même dans la page du tableau de bord, vérifiée
par un test) :

| Cas | Pause maximale | Retour à la normale (du lancement à 0 paiement en attente) |
|---|---|---|
| Solution minimale, solution améliorée | 60 s | 120 s |
| Panne brutale (contre-exemple, `--mode crash`) | 60 s | 180 s |

Pourquoi 180 s en panne : ce cas n'est pas notre solution, c'est un
contre-exemple qui sert à comparer les sémantiques. Il tourne à 10 Pix/s avec
80 ms d'écart ajouté entre la lecture notée et l'écriture : le service ne
traite alors qu'environ 12 Pix/s, et la session Kafka du membre tué dure à
elle seule environ 45 s. 120 s ne laisse pas le temps de rattraper le retard
(mesuré : de 144 à 170 s dans les campagnes publiées). La garantie annoncée,
elle, porte sur la solution minimale et la solution améliorée : 60 s et 120 s.

Un essai lancé avec d'autres limites est un **essai de diagnostic** : le
bilan, le tableau de bord et le résumé de campagne le disent, et la
comparaison des sémantiques l'écarte. Exemple : l'essai B du 10 novembre,
avec une borne de pause de test de 30 s, pour vérifier l'affichage d'un
dépassement.

Une **cible métier de 10 s** est rapportée à côté.

- 60 s : les essais exploratoires montrent une pause d'environ 44 s. Elle vient
  surtout de la session Kafka de l'ancien membre (`session.timeout.ms`,
  45 000 ms par défaut dans librdkafka 2.8.0), plus environ 5 s de redémarrage
  Docker. On ajoute une marge pour la variabilité normale.
- 10 s : c'est le délai de décision d'un paiement (TTL), rapporté à côté.
  Attention : la décision est prise avant `persister-valid`, par
  `pix-decision-engine`. Une pause de `persister-valid` retarde l'écriture en
  base, pas la réponse au client. Cette cible sert de repère, pas de borne.

La borne a été fixée avant la campagne. Elle ne change pas pour faire passer
un essai.
