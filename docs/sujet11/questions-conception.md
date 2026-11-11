# Questions de conception du sujet 11

Réponses du groupe aux questions de la fiche. On sépare ce qui est
**mesuré** (preuve dans `preuves/sujet11/`), ce qui est un **fait établi**
sur Kafka ou PostgreSQL, et ce qui reste une **hypothèse**.

## Que se passe-t-il pour le message en cours de traitement au moment de l'arrêt du conteneur ?

Cela dépend de la façon dont le conteneur s'arrête.

- **Arrêt propre (SIGTERM)** : `persister-valid` lève un drapeau, finit le
  paiement en cours, valide son offset, puis appelle `consumer.close()` pour
  quitter le groupe (`services/persister-valid/main.py`, `request_stop` et
  `shutdown_gracefully`). Le message en cours n'est ni perdu ni relu.
  Mesuré : 0 perte et 0 relecture dans les campagnes minimale et améliorée
  du 9 novembre, pour les trois sémantiques.
- **Panne brutale (SIGKILL, `docker kill`)** : le programme s'arrête au
  milieu du paiement. Ce qui arrive dépend de la sémantique (question 4).
  Mesuré : en at-most-once, le paiement validé mais pas encore écrit est
  perdu, si la panne tombe entre « lecture notée » et « écrit » (8 pannes sur 9
  dans les campagnes publiées ; la panne r3 du 10 novembre est tombée entre deux
  paiements et n'a rien perdu) ;
  en at-least-once, le paiement écrit mais pas encore validé est relu (1 relecture
  par essai, sans second effet).

L'analyse des passations de partitions (`scripts/sujet11/partitions.py`)
retrouve, pour chaque partition qui change de main, l'offset de reprise et le
paiement qui s'y trouve.

## Pourquoi le rebalance prend-il du temps, et que devient le flux pendant ce temps ?

Pendant un rebalance, aucun consommateur du groupe ne lit les partitions
concernées. Les paiements continuent d'arriver dans le topic `validated` :
ils attendent, le lag monte, puis la nouvelle instance les rattrape
(drainage). Rien n'est perdu à ce stade : les messages restent dans Kafka.

Le temps vient de plusieurs causes :

| Cause | Durée | Statut |
|---|---|---|
| Ancien membre tué sans quitter le groupe : le coordinateur attend la fin de sa session (`session.timeout.ms`, 45 s par défaut dans librdkafka 2.8.0) | environ 44 à 45 s | mesuré (ancien code, mode crash) |
| Démarrage du nouveau conteneur et entrée dans le groupe | moins d'une seconde à quelques secondes | mesuré (événements Docker) |
| Délai du premier rebalance d'un groupe vide côté broker (`group.initial.rebalance.delay.ms`) | environ 3 s | **Observation** : dans les journaux du broker (essai du 10 novembre), le nouveau membre entre dans le groupe vide à 19:30:10,257 et le groupe est stabilisé à 19:30:13,257, soit 3,000 s (3,001 s au premier démarrage). **Configuration** : le broker affiche `group.initial.rebalance.delay.ms = 3000`. **Interprétation** : ce délai explique l'essentiel des 3 s mesurées. **Causalité expérimentale** : non démontrée, il faudrait refaire l'essai avec un autre délai |
| Rebalance « eager » quand un membre entre ou sort : toutes les partitions sont rendues puis redistribuées (stratégie par défaut `range,roundrobin`, voir KIP-429) | de 1,3 à 2,7 s sans propriétaire dans le relevé, en solution améliorée ; le broker prépare le rebalance pendant 2,66 s (10 novembre), et l'ancienne instance continue de traiter pendant ce temps : les écritures ne s'arrêtent pas plus que le rythme normal du flux | fait établi sur Kafka, durée mesurée |

## Un trou de `transaction_id` dans PostgreSQL est-il une perte ? Comment le distinguer d'un rejet métier ?

Pas forcément. Les paiements d'un essai sont numérotés `tx-00000001` à
`tx-<total>`. Chacun doit finir dans une table, et une seule :

| Cas | Où il est | Perte ? |
|---|---|---|
| Validé et enregistré | `validated_transactions` | non |
| Rejeté par la banque (règle métier) | `rejected_transactions`, motif métier | non : décision normale |
| Rejeté pour délai dépassé | `rejected_transactions`, motif `processing_timeout` | non pour `persister-valid` ; compté à part |
| Encore en attente | dans Kafka, pas encore en base | indéterminé : on attend la fin du flux et un lag à 0 avant de conclure, sinon l'essai est INVALIDE |
| Validé mais absent de la base | topic `validated`, pas en base | **oui** |
| Sans aucune décision | ni dans `validated_transactions`, ni dans `rejected_transactions` | **oui** (trou de `transaction_id`) |
| Relu | deux livraisons dans l'audit, une seule ligne en base | non : relecture absorbée |

Deux contrôles indépendants le vérifient, et chacun fait échouer l'essai :
l'oracle (`scripts/sujet11/oracle.py`, identité par identité depuis le topic
`validated`) et le contrôle des trous (`scripts/sujet11/trous.py`, numéro par
numéro depuis la base). Le second rattrape une relecture incomplète du topic.

## La garantie de continuité dépend-elle de la sémantique de livraison configurée ?

Oui, mais seulement si l'arrêt n'est pas propre.

| Sémantique | Ordre | Panne brutale (mesuré) |
|---|---|---|
| at-most-once | valider la lecture, puis écrire | perte du paiement en cours |
| at-least-once | écrire, puis valider la lecture | relecture, absorbée par l'upsert sur `transaction_id` |
| exactly-once PostgreSQL | écrire le paiement et la position de lecture dans la même transaction | message déjà écrit écarté, sans réécriture |

Avec l'arrêt propre, le paiement en cours finit avant l'arrêt : les trois
sémantiques donnent le même résultat (mesuré). Notre garantie est donc
annoncée **en at-least-once**, la seule des deux sémantiques Kafka qui ne
perd rien même en panne.

Le périmètre de l'exactly-once PostgreSQL est l'effet en base de ce seul
service (Kafka vers PostgreSQL). Ce n'est pas l'exactly-once de Kafka, qui ne
couvre que les échanges entre topics Kafka. Comme l'upsert rend déjà
l'écriture idempotente, la base finale est la même qu'en at-least-once : le
gain est qu'une relecture n'écrit rien.

## Quelle différence entre redémarrer un producteur et redémarrer un consommateur ?

- **Consommateur** (notre cas) : il appartient à un groupe. Son départ
  déclenche un rebalance, pendant lequel ses partitions ne sont pas lues. Le
  risque porte sur le message en cours (perte ou relecture selon l'ordre
  commit / écriture).
- **Producteur** : il n'appartient à aucun groupe, donc pas de rebalance.
  Pendant son arrêt, il n'envoie rien : les paiements ne sont pas produits
  (ou attendent en amont). Le risque est un envoi en double s'il renvoie un
  message dont il n'a pas reçu l'accusé ; l'idempotence du producteur
  (`enable.idempotence`) l'évite. Un producteur transactionnel doit garder
  son `transactional.id` à son redémarrage. Ce cas n'est **pas mesuré** dans
  notre projet.

## Messages au format ancien et nouveau pendant la mise à jour

Notre mise à jour ne change pas le format des messages. L'extension
« changer le contrat pendant la mise à jour » n'est **pas réalisée**. Dans la
plateforme, aucun registre de schéma ne vérifie les messages : une
évolution de format demanderait l'étude de compatibilité du sujet 3.

## Ordre de déploiement (consommateur ou producteur d'abord)

Sans changement de contrat, l'ordre n'a pas d'importance pour notre cas : on
ne met à jour qu'un consommateur. Avec un changement de contrat, l'ordre se
déduirait de la compatibilité choisie (BACKWARD : consommateur d'abord ;
FORWARD : producteur d'abord). Non réalisé.
