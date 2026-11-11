# Observation d'un rebalance pendant la mise à jour

Étape 3 du plan : observer un rebalance en situation contrôlée avant d'écrire
la campagne. Flux de 3000 Pix à 20 Pix/s, at-least-once, une seule instance de
`persister-valid`. Les fichiers bruts sont dans `preuves/sujet11/exploration/`.

## Premier constat : sans `--force-recreate`, rien n'est mis à jour

`docker compose up -d --build persister-valid` reconstruit l'image. Comme le
code n'a pas changé, l'image est identique et Compose garde le conteneur :

```
 Image simulpix-persister-valid Built
 Container persister-valid Running
```

Le lag n'a pas bougé. Pour simuler l'arrivée d'une nouvelle version, le script
utilise donc `docker compose up -d --build --force-recreate --no-deps persister-valid`.
Fichier : `rebuild-sans-force-recreate.txt`.

## Chronologie mesurée

Instants en secondes après le lancement de la mise à jour (t0).
Sources : `observee-evenements.txt` (Docker), `observee-lag.jsonl` (Kafka,
un relevé par seconde), table d'audit (PostgreSQL).

| Instant | Événement | Source |
|---:|---|---|
| +1,64 s | Docker envoie `SIGTERM` (premier `kill`) | Docker |
| +4,73 s | Docker envoie `SIGKILL` (second `kill`), le conteneur meurt | Docker |
| +4,83 s | le nouveau conteneur démarre | Docker |
| +5,03 s | dernière écriture de l'ancienne version | PostgreSQL |
| +5,10 s | le groupe n'a plus aucun membre | Kafka |
| +48,98 s | première écriture de la nouvelle version | PostgreSQL |
| +49,31 s | un membre a de nouveau les 6 partitions, lag à 0 | Kafka |

La dernière écriture (+5,03 s) est datée 0,3 s après la mort de l'ancien
conteneur (+4,73 s). Nous n'expliquons pas encore cet écart. t0 vient de
l'horloge du Mac, alors que Docker et PostgreSQL tournent dans la machine
virtuelle de Docker Desktop. Une différence d'horloge est possible. Depuis le
9 novembre, elle est mesurée au début et à la fin de chaque essai
(`scripts/sujet11/horloge.py`) et corrigée ; un essai dont l'horloge dérive de
plus de 0,5 s est INVALIDE. Cet écart ne change pas l'ordre de grandeur de la pause.

Résultat : **pause de 43,954 s**, retard maximal de **883 messages**, trou
normal avant la mise à jour de 0,992 s. Oracle : 3000 attendus, 3000 présents,
0 perdu, 0 doublon absorbé.

Sur trois mises à jour exploratoires, la pause vaut 43,73 s (calcul SQL à la
main), 43,86 s et 43,95 s.

## Pourquoi la pause dure environ 44 s

1. **Le signal d'arrêt est ignoré.** `persister-valid` tourne avec
   `CMD ["python", "main.py"]` : Python est le processus 1 du conteneur, et le
   code ne gère pas `SIGTERM`. Un processus 1 sans gestionnaire ignore ce signal.
   Docker attend, puis envoie `SIGKILL` 3 s plus tard.
2. **L'ancien membre ne quitte pas le groupe.** Tué par `SIGKILL`, le
   consommateur n'appelle jamais `close()`. Le coordinateur du groupe le croit
   encore vivant jusqu'à la fin de sa session : `session.timeout.ms`, 45 000 ms
   par défaut dans librdkafka 2.8.0 (version présente dans le conteneur).
3. **Le nouveau membre attend.** Le nouveau conteneur démarre en 5 s, mais il ne
   reçoit les partitions qu'après l'expiration de la session de l'ancien membre.

Docker ne compte que pour environ 5 s. L'attente de Kafka représente le reste.
C'est une hypothèse forte, cohérente avec les mesures. La solution améliorée la
testera directement : avec un arrêt propre (`close()`), le groupe devrait être
réattribué presque tout de suite.

## Ce que ça change pour la suite

- Le script force le remplacement (`--force-recreate`).
- Le script repasse la sémantique au moment du remplacement : elle est lue par
  le conteneur à sa création (`SIMULPIX_KAFKA_CONSUMER_SEMANTICS`).
- La borne de la solution minimale est fixée à 60 s (voir `garantie.md`).
