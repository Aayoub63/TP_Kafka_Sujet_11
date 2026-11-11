# Procédure de mise à jour sûre de `persister-valid`

Procédure pour la solution minimale (une seule instance). Elle garantit une
reprise avec continuité métier bornée, pas une mise à jour sans interruption.

## Avant

1. **La plateforme répond** : `curl -fsS http://127.0.0.1:8082/health`.
2. **La sémantique est at-least-once.** En at-most-once, un message en cours
   peut être perdu (voir les résultats de la campagne). Vérifier la carte
   « SUB Kafka » sur `http://localhost:8082/` ou la variable
   `SIMULPIX_KAFKA_CONSUMER_SEMANTICS`.
3. **Le lag du groupe est bas** : `./scripts/tp-kafka.sh`, groupe
   `simulpix-persister-valid-...`. Une mise à jour ajoute environ 45 s de
   retard : il ne faut pas la lancer près de la limite de capacité.
4. **L'ancienne image est gardée**, pour pouvoir revenir en arrière :
   `docker image tag simulpix-persister-valid simulpix-persister-valid:precedente`.
5. **La nouvelle version a passé les tests** : `python3 -m unittest discover -s tests`.

## Pendant

6. **Remplacer le conteneur en gardant la sémantique** :

   ```sh
   SIMULPIX_KAFKA_CONSUMER_SEMANTICS=at_least_once \
     docker compose up -d --build --force-recreate --no-deps persister-valid
   ```

   Sans `--force-recreate`, une image identique ne remplace rien. Sans la
   variable, le conteneur recréé prend la valeur par défaut.
7. **Suivre le groupe** : le lag monte, puis redescend quand le nouveau membre
   reçoit les partitions. Avec la version actuelle, compter environ 45 s.
   Le script `scripts/sujet11-maj.sh` fait toutes ces étapes et les mesure.

## Après

8. **Le lag est revenu à 0** et le groupe a un membre, avec 6 partitions.
9. **La base est complète** : aucun paiement du topic `validated` ne manque,
   aucune valeur fausse. C'est la partie « oracle » de `scripts/sujet11-maj.sh`
   (`scripts/sujet11/oracle.py`).
10. **La pause est sous la borne** (60 s). Sinon, chercher la cause dans la
    chronologie du bilan : arrêt, démarrage, rebalance ou drainage.

## Retour arrière

Ces commandes n'ont pas encore été testées par le groupe : à valider avant
la soutenance.

Si la nouvelle version plante ou écrit des valeurs fausses :

```sh
docker image tag simulpix-persister-valid:precedente simulpix-persister-valid
SIMULPIX_KAFKA_CONSUMER_SEMANTICS=at_least_once \
  docker compose up -d --force-recreate --no-deps persister-valid
```

Avec une seule instance, le retour arrière provoque lui aussi une pause.
En at-least-once, les messages lus par la version fautive mais non validés
seront relus par l'ancienne version. Les lignes déjà écrites par la version
fautive restent en base : il faut les corriger à part.

## Procédure améliorée : deux instances et arrêt propre

Disponible depuis l'arrêt propre de `persister-valid` (SIGTERM : le message en
cours finit, l'offset est validé, `consumer.close()` quitte le groupe) et la
seconde instance `persister-valid-b` (profil `roulant`, même groupe).

1. **Avant** : mêmes vérifications que plus haut. En plus, la nouvelle version
   doit tenir seule la charge, car l'ancienne va s'arrêter.
2. **Démarrer la nouvelle version à côté de l'ancienne** :

   ```sh
   SIMULPIX_KAFKA_CONSUMER_SEMANTICS=at_least_once \
     docker compose --profile roulant up -d --build --force-recreate --no-deps persister-valid-b
   ```

3. **Attendre qu'elle soit dans le groupe** : 2 membres, puis le lag revient à 0
   (`./scripts/tp-kafka.sh` ou le tableau de bord Grafana du sujet 11).
4. **Arrêter l'ancienne proprement** : `docker compose stop persister-valid`.
   Elle reçoit SIGTERM, finit son message et quitte le groupe.
5. **Après** : mêmes vérifications que plus haut.

**Retour arrière** tant que l'ancienne tourne encore (avant l'étape 4) :
`docker compose --profile roulant rm -sf persister-valid-b`. L'ancienne reprend
toutes les partitions. Le groupe garde toujours un membre, mais il y a un
court moment sans lecture : à chaque entrée ou sortie de membre, le rebalance
« eager » rend toutes les partitions avant de les redistribuer.

Mesure : `./scripts/sujet11-maj.sh --mode amelioree --borne 60` fait toutes ces
étapes et les mesure. Résultat (campagne-amelioree-20261109-135532) : **aucune
pause mesurable au-delà du trou normal du flux** (pause de 0,94 à 1,03 s pour
un trou normal d'environ 0,98 s). Ce n'est pas « une pause de 1 s » : le
générateur émet par paquets, environ une fois par seconde, et un arrêt plus
court que ce rythme ne se voit pas. Le relevé du groupe montre un moment
sans propriétaire de 1,3 à 2,7 s pendant le rebalance, mais les journaux du
broker (10 novembre) montrent que l'ancienne instance continue de traiter les
messages déjà reçus pendant ce temps : c'est l'état du groupe vu par Kafka,
pas un arrêt du traitement.

## Limites connues

- Solution minimale : pause d'environ 3,4 s avec l'arrêt propre (médiane,
  campagne-minimale-20261109-113934), contre environ 44 s avec l'ancienne
  version, qui ne gérait pas SIGTERM (voir `chronologie-rebalance.md`).
  Environ 3 s : les journaux du broker montrent 3,000 s entre l'entrée du
  nouveau membre dans le groupe vide et sa stabilisation, et la configuration
  vaut `group.initial.rebalance.delay.ms = 3000`. Explication cohérente ; la
  contre-expérience (délai réglé autrement) n'a pas été faite.
- Solution améliorée : un court rebalance (de 1,3 à 2,7 s sans propriétaire
  dans le relevé du groupe, pendant lesquels l'ancienne instance continue de
  traiter ce qu'elle a déjà reçu) a lieu quand la nouvelle instance rejoint
  le groupe, puis un second quand l'ancienne le quitte. Toutes les
  partitions sont rendues pendant ces rebalances (comportement par défaut,
  voir KIP-429). La stratégie `cooperative-sticky` le réduirait : non testé.
- Une seule instance tourne à la fin : ce n'est pas le déploiement roulant de
  l'extension (plusieurs instances remplacées l'une après l'autre).
- Le format des messages ne change pas. Une mise à jour qui change le contrat
  demanderait une étude de compatibilité.
