# Validation expérimentale finale, 10 novembre 2026

Campagnes lancées avec le code final de la branche `feat/consolidation-sujet11`
(non commité au moment des essais), sur un seul Mac (Docker Desktop), après
accord du groupe. Les preuves plus anciennes de `preuves/sujet11/` ne sont ni
déplacées ni modifiées.

**Mesuré** = lu dans les fichiers d'essai publiés ou dans les journaux du
broker. **Test unitaire** = vérifié par un test, pas par un essai réel.

## Les campagnes

| Étape | But | Commande | Essais | Résultat |
|---|---|---|---|---|
| 1 | nominal, code final | `SUJET11_SEMANTIQUES=at_least_once SUJET11_CHARGES=normale ./scripts/sujet11-campagne.sh 5 60 minimale` | 5 | 5 REUSSITE |
| 2 | solution améliorée | `SUJET11_SEMANTIQUES=at_least_once SUJET11_CHARGES=normale ./scripts/sujet11-campagne.sh 3 60 amelioree` | 3 | 3 REUSSITE |
| 3 | panne brutale, deux sémantiques | `SUJET11_SEMANTIQUES="at_least_once at_most_once" ./scripts/sujet11-campagne.sh 3 60 crash` | 6 | at-least-once 3 REUSSITE ; at-most-once 2 ECHEC (perte), 1 REUSSITE |
| 4 | charge forte | `SUJET11_SEMANTIQUES=at_least_once SUJET11_CHARGES=forte ./scripts/sujet11-campagne.sh 3 60 minimale` | 3 | 3 REUSSITE |
| 5 | essai interrompu (scénario E réel) | `./scripts/sujet11-maj.sh --mode minimale --semantique at_least_once --borne 60`, puis `kill -TERM` pendant le rattrapage | 1 | code 130, phase « interrompu », aucun bilan, verrou libéré |

Dossiers : `campagne-minimale-20261110-213353`, `campagne-amelioree-20261110-215436`,
`campagne-crash-20261110-221339`, `campagne-minimale-20261110-224013`. L'essai
interrompu (étape 5) est resté dans `runtime/sujet11/20261110-225230-minimale-at_least_once-normale/`
(il n'a pas de bilan à publier).

Chaque essai lancé par `run-scenario.sh` recrée les topics, vide les tables et
utilise un nouveau groupe Kafka : un essai ne lit pas les données d'un autre.

## Un essai par ligne

Généré à partir des `resultat.json` et `meta.json` publiés. « Relus » =
paiements livrés deux fois, absorbés par l'upsert (une seule ligne en base).
Toutes les durées sont comptées depuis le lancement de la mise à jour, sauf
l'interruption (plus long temps sans aucune écriture en base).

| Campagne / essai | Sémantique | Charge (débit mesuré) | Verdict | Attendus / présents | Perdus | Relus | Doubles effets | Trous | Interruption (s) | Reprise (s) | Retour à la normale (s) / limite | Base stable |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| minimale-20261110-213353 / r1-at_least_once-normale | at_least_once | normale (20,10/s) | **REUSSITE** | 3000 / 3000 | 0 | 0 | 0 | 0 | 3,42 | 4,99 | 5,95 / 120 | oui |
| minimale-20261110-213353 / r2-at_least_once-normale | at_least_once | normale (20,00/s) | **REUSSITE** | 3000 / 3000 | 0 | 0 | 0 | 0 | 3,42 | 4,97 | 7,04 / 120 | oui |
| minimale-20261110-213353 / r3-at_least_once-normale | at_least_once | normale (19,90/s) | **REUSSITE** | 3000 / 3000 | 0 | 0 | 0 | 0 | 3,40 | 4,97 | 6,96 / 120 | oui |
| minimale-20261110-213353 / r4-at_least_once-normale | at_least_once | normale (19,80/s) | **REUSSITE** | 3000 / 3000 | 0 | 0 | 0 | 0 | 3,62 | 6,14 | 6,82 / 120 | oui |
| minimale-20261110-213353 / r5-at_least_once-normale | at_least_once | normale (20,00/s) | **REUSSITE** | 3000 / 3000 | 0 | 0 | 0 | 0 | 3,72 | 5,11 | 6,70 / 120 | oui |
| amelioree-20261110-215436 / r1-at_least_once-normale | at_least_once | normale (20,20/s) | **REUSSITE** | 3000 / 3000 | 0 | 0 | 0 | 0 | 0,97 (= rythme normal) | sans objet | 5,28 / 120 | oui |
| amelioree-20261110-215436 / r2-at_least_once-normale | at_least_once | normale (19,80/s) | **REUSSITE** | 3000 / 3000 | 0 | 0 | 0 | 0 | 0,97 (= rythme normal) | sans objet | 4,73 / 120 | oui |
| amelioree-20261110-215436 / r3-at_least_once-normale | at_least_once | normale (20,00/s) | **REUSSITE** | 3000 / 3000 | 0 | 0 | 0 | 0 | 0,97 (= rythme normal) | sans objet | 5,50 / 120 | oui |
| crash-20261110-221339 / r1-at_least_once-ralentie | at_least_once | ralentie (9,90/s) | **REUSSITE** | 1500 / 1500 | 0 | 1 | 0 | 0 | 45,01 | 45,05 | 144,44 / 180 | oui |
| crash-20261110-221339 / r1-at_most_once-ralentie | at_most_once | ralentie (10,10/s) | **ECHEC** | 1500 / 1499 | 1 (tx-00000309) | 0 | 0 | 1 | 45,10 | 45,11 | 144,87 / 180 | oui |
| crash-20261110-221339 / r2-at_least_once-ralentie | at_least_once | ralentie (9,80/s) | **REUSSITE** | 1500 / 1500 | 0 | 1 | 0 | 0 | 45,00 | 45,06 | 144,04 / 180 | oui |
| crash-20261110-221339 / r2-at_most_once-ralentie | at_most_once | ralentie (9,80/s) | **ECHEC** | 1500 / 1499 | 1 (tx-00000324) | 0 | 0 | 1 | 45,09 | 45,13 | 144,33 / 180 | oui |
| crash-20261110-221339 / r3-at_least_once-ralentie | at_least_once | ralentie (10,10/s) | **REUSSITE** | 1500 / 1500 | 0 | 1 | 0 | 0 | 45,01 | 45,06 | 144,94 / 180 | oui |
| crash-20261110-221339 / r3-at_most_once-ralentie | at_most_once | ralentie (10,00/s) | **REUSSITE** | 1500 / 1500 | 0 | 0 | 0 | 0 | 45,02 | 44,99 | 145,46 / 180 | oui |
| minimale-20261110-224013 / r1-at_least_once-forte | at_least_once | forte (57,70/s) | **REUSSITE** | 9000 / 9000 | 0 | 0 | 0 | 0 | 3,41 | 4,14 | 5,56 / 120 | oui |
| minimale-20261110-224013 / r2-at_least_once-forte | at_least_once | forte (58,00/s) | **REUSSITE** | 9000 / 9000 | 0 | 0 | 0 | 0 | 4,37 | 5,89 | 7,12 / 120 | oui |
| minimale-20261110-224013 / r3-at_least_once-forte | at_least_once | forte (58,60/s) | **REUSSITE** | 9000 / 9000 | 0 | 0 | 0 | 0 | 3,46 | 4,24 | 5,29 / 120 | oui |

## Ce que montrent les trois niveaux de preuve

### Kafka (journaux du broker, dossier `kafka/`)

- **Solution minimale** : dans les 5 essais de l'étape 1, le broker attend de
  **3,000 à 3,008 s** entre l'entrée du nouveau membre dans le groupe vide et la
  stabilisation du groupe ; la configuration vaut `group.initial.rebalance.delay.ms = 3000`.
  C'est l'explication la plus probable des 3,4 s d'interruption. Causalité non
  démontrée : la contre-expérience (autre valeur du délai) n'a pas été faite.
- **Panne brutale** (at-most-once r1) : la nouvelle instance entre à
  21:19:16,330 ; le broker croit l'ancienne vivante jusqu'à la fin de sa
  session et ne la retire qu'à 21:20:00,853 (44,5 s). D'où les 45 s
  d'interruption en panne.
- **Solution améliorée** (r1) : quand la 2e instance entre, le broker prépare
  le rebalance pendant 2,66 s, mais l'ancienne instance continue de traiter les
  messages déjà reçus : les écritures ne s'arrêtent jamais plus de 0,97 s
  (égal au rythme normal du flux). Le relevé « sans propriétaire » décrit
  l'état du groupe vu par Kafka, pas l'arrêt du traitement.

### PostgreSQL et la chaîne d'une perte (at-most-once r1)

1. `tx-00000309` est dans le topic `validated`, partition 4, offset 102.
2. L'offset validé de la partition 4 vaut **103 avant la panne** : la lecture
   de 102 était déjà notée.
3. L'audit compte **0 tentative d'écriture** de `tx-00000309` ; il n'est ni dans
   `validated_transactions`, ni dans `rejected_transactions`.
4. La nouvelle instance reprend à l'offset 103 (`tx-00000310`) : le paiement
   ne sera jamais relu. L'oracle, le contrôle des trous et l'analyse des
   passations désignent tous les trois `tx-00000309`.

En at-least-once, la même panne laisse **1 paiement relu** par essai (écrit,
tué avant que la lecture soit notée, relu par la nouvelle instance), et la
base garde une seule ligne : 0 double effet.

### at-most-once ne perd pas à chaque panne

La panne r3 en at-most-once n'a **rien perdu**. Une perte n'arrive que si le
`docker kill` tombe entre « lecture notée » et « paiement écrit ». S'il tombe
pendant que le service attend le message suivant, rien n'est en cours. Sur
toutes les campagnes publiées du code actuel : **8 mises à jour avec perte
sur 9** (voir `captures/6-comparaison-des-semantiques.png`).

## Scénarios C et E, erreur de base

| Cas | Comment c'est vérifié | Niveau |
|---|---|---|
| C, double effet en base | dans la vraie base, dans une transaction annulée : une écriture brute en double est refusée par la clé primaire `transaction_id` ; deux écritures par l'upsert laissent 1 ligne (1500 lignes avant et après) | réel, sans effet sur les données |
| C, détection par le verdict | rejeu hors ligne sur une copie de l'essai A avec une ligne doublée : ECHEC « 1 double(s) effet(s) en base » | rejeu sur copie + test unitaire |
| E, essai interrompu | étape 5 : code 130, phase « interrompu », aucun bilan ; la page affiche « Un essai plus récent a été interrompu » (capture 1) | réel |
| E, mesures absentes | rejeu sur copies : audit vide ou absent, relevé vide, flux non terminé, base instable, topic tronqué ou illisible : tous INVALIDE, aucun REUSSITE | rejeu sur copie + tests unitaires |
| Erreur PostgreSQL en at-most-once | test contrôlé de la boucle réelle de `persister-valid` (`tests/test_sujet11_erreur_base.py`) : lecture notée avant l'échec, message jamais relu | test unitaire seulement, pas d'essai réel |

## Défauts trouvés pendant cette validation

| Défaut | Gravité | État |
|---|---|---|
| fichier d'audit absent : erreur Python au lieu d'INVALIDE | sans danger (aucun verdict), corrigé avant les campagnes, test ajouté | corrigé |
| topic entièrement illisible : ECHEC « lignes inattendues » au lieu d'INVALIDE | sans danger (jamais REUSSITE), corrigé, test ajouté | corrigé |
| page : en solution améliorée, « reprise » affichée à 14,4 s (c'est la fin d'un trou normal, pas une reprise) | affichage trompeur | corrigé après la validation (sans interruption mesurable : « pas de reprise à mesurer »), test ajouté |
| page : « personne ne lit pendant ce temps » faux en solution améliorée | affichage trompeur | corrigé après la validation (le texte dépend du cas et de la mesure), test ajouté |
| page : il manque un point avant « Non confirmé » dans une raison | coquille | corrigé, test ajouté |

## Limites

- Un seul Mac, peu d'essais par cas (3 à 5) : assez pour l'ordre de grandeur, pas pour une probabilité.
- La charge forte a réellement appliqué 57,7 à 58,6 Pix/s, pour 60 demandés.
- Pas de scénario `football_match_peak`, pas de déploiement roulant à plusieurs instances.
- La causalité du délai de 3 s n'est pas démontrée (pas de contre-expérience).
- Les captures 1 à 6 viennent d'un navigateur sans interface sur la page de synthèse. Les captures 7 ont été faites ensuite dans **Grafana connecté** (Brave sans interface, session Grafana ouverte, 1920 × 1080, menu latéral ouvert), après les dernières corrections d'affichage : elles montrent donc l'état final, et les captures 1 à 6 un état intermédiaire. La capture 4 (INVALIDE) est rendue sur une copie de l'essai A, pas sur un essai réel invalide. La capture 0 est l'en-tête Grafana rendu seul.
- Vérification visuelle faite par un navigateur piloté par script, pas par une personne devant l'écran : à revoir une fois sur l'écran de la soutenance (vidéoprojecteur).
- La démonstration de soutenance (4 minutes, essais déjà terminés) est décrite dans `docs/sujet11/demonstration-soutenance.md`.
