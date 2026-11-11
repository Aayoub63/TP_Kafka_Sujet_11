# Pilotage des scénarios depuis Grafana, 11 novembre 2026

Lancement d'essais **sans terminal**, depuis la section « 0. Contrôle des
scénarios expérimentaux » du tableau de bord Grafana du sujet 11.

## Ce qui a été fait en réel (2 essais, autorisés par le groupe)

Les clics ont été faits par un navigateur piloté par script (Brave sans
interface), **connecté à Grafana** avec le compte `admin`, sur la page
`http://localhost:8083/sujet11/pilotage`, celle qu'affiche le tableau de bord.

| Lancement | Action | Résultat |
|---|---|---|
| 20261111-082628 | clic « Lancer l'essai » : mise à jour minimale, at-least-once, charge normale | **REUSSITE** ; 3000 paiements attendus, 3000 en base (3000 identifiants distincts vérifiés dans PostgreSQL), 0 perte, 0 double effet, interruption de 3,465 s ; durée totale 694 s |
| 20261111-083858 | clic « Lancer l'essai », puis, en phase de rattrapage, case de confirmation et clic « Arrêter l'essai » | **interrompu** : code 130, phase « interrompu », aucun bilan, verrou libéré 11 s après la demande |

Fichiers : `journaux/` (journal de chaque lancement, historique
`lancements.jsonl`, bilan du premier essai) et `captures/`.

## Ce qui a été vérifié sans essai réel

- **Accès** : les ports de `service-health` n'écoutent que sur `127.0.0.1` ;
  depuis l'adresse réseau du Mac, la page est injoignable. Une demande sans
  origine ou sans session Grafana est refusée, sans aucun lancement.
- **Tests automatiques** (`tests/test_sujet11_commande.py`, 24 tests, dossiers
  temporaires et faux script d'essai) : rôles (Viewer refusé, Editor accepté),
  page tierce refusée, confirmation obligatoire pour la panne et l'arrêt,
  combinaisons non proposées refusées, double clic et 5 demandes simultanées
  (une seule acceptée), essai déjà en cours, erreur du script, fin de délai
  (arrêt propre), arrêt contrôlé, redémarrage du service pendant un essai
  (essai marqué « interrompu », verrou libéré, essai du terminal jamais
  touché), suivi sans pourcentage ni zéro inventé.

## Constat pendant les essais

Le premier lancement depuis `service-health` a **recréé les trois brokers
Kafka** (environ 8 minutes), parce que la version de Docker Compose du
conteneur écrit la configuration autrement que celle de Docker Desktop. Les
données (volumes) sont conservées. Ce comportement existait déjà avec les
anciens boutons. Le lancement suivant n'a rien recréé (rattrapage atteint en
69 s). Alterner les lancements depuis le terminal et depuis Grafana le refait
à chaque fois. Le délai maximal de 15 minutes a suffi (694 s).

## Limites

- Clics faits par un navigateur piloté par script, pas par une personne.
- Le redémarrage du service pendant un essai n'a été testé que par les tests
  automatiques, pas en réel.
- Un essai lancé depuis un terminal ne peut pas être arrêté depuis la page.
