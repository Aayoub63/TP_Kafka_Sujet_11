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

## Limites connues

- Pause d'environ 45 s, due à l'absence d'arrêt propre (voir
  `chronologie-rebalance.md`). La solution améliorée la vise.
- Le format des messages ne change pas. Une mise à jour qui change le contrat
  demanderait une étude de compatibilité.
