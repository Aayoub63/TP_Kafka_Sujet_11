# Note sur cette campagne

Les 3 essais at-most-once sont notés INVALIDE (« flux pas terminé avant la
collecte »). La cause est le critère de fin de flux du script, pas la mesure :
il exigeait autant de lignes en base que de paiements produits, ce qu'une
perte rend impossible. Corrigé le 9 novembre (`fix(maj): finir le flux même
avec une perte`).

Les compteurs de fin (`compteurs.jsonl`, phase « apres ») montrent que le flux
était fini dans les 3 essais : 1 500 produits, 1 500 dans le topic, lag de
persister-valid à 0, et 1 499 en base. L'écart de 1 est le paiement perdu.

Ces 3 essais sont refaits avec le critère corrigé dans une campagne suivante.
Le résumé de cette campagne a été produit avant la correction du résumé : il
compte encore ces 3 essais dans les proportions.
