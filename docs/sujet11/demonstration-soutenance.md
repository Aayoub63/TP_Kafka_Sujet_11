# Démonstration de soutenance (4 minutes, sans essai en direct)

La démonstration utilise des essais **déjà terminés et publiés** dans
`preuves/sujet11/`. Elle ne dépend donc pas d'un essai de 5 minutes lancé
pendant la soutenance. Toutes les valeurs affichées viennent des fichiers de
ces essais.

## Avant la soutenance (5 minutes)

1. `./start.sh` (n'efface rien). Ne pas lancer `./stop.sh` : il efface les données.
2. Ouvrir Grafana : http://localhost:3000 (`admin` / `adminpass`), tableau
   **Simul-Pix - Sujet 11**, écran 1920 × 1080.
3. Ouvrir à l'avance ces quatre onglets (page de synthèse, essai choisi) :

| Onglet | Essai | Lien |
|---|---|---|
| A, réussite | solution minimale, at-least-once | http://localhost:8083/sujet11/synthese?vue=ensemble&essai=preuves/sujet11/campagne-minimale-20261110-213353/essais/r1-at_least_once-normale |
| B, déroulement | le même essai | http://localhost:8083/sujet11/synthese?vue=deroulement&essai=preuves/sujet11/campagne-minimale-20261110-213353/essais/r1-at_least_once-normale |
| C, contre-exemple | panne brutale, at-most-once (perte de `tx-00000309`) | http://localhost:8083/sujet11/synthese?vue=deroulement&essai=preuves/sujet11/campagne-crash-20261110-221339/essais/r1-at_most_once-ralentie |
| D, comparaison | tous les essais publiés | http://localhost:8083/sujet11/synthese?vue=comparaison |

Remplacer `vue=` par `ensemble`, `deroulement` ou `integrite` pour changer de
vue sur le même essai. Un bandeau bleu « Essai choisi pour la démonstration »
rappelle qu'on ne regarde pas forcément le dernier essai lancé.

## Le déroulé

| Temps | À montrer | À dire |
|---|---|---|
| 0:00-0:30 | en-tête de Grafana | « On remplace le programme qui enregistre les paiements dans la base pendant qu'ils arrivent. Question : en perd-on, en enregistre-t-on deux fois, et combien de temps s'arrête-t-on ? » |
| 0:30-1:00 | en-tête, légende des couleurs | « Les paiements passent par Kafka, une file d'attente. Le programme les lit et les écrit dans PostgreSQL. Vert : objectif tenu ; rouge : non tenu ; chaque carte a aussi un libellé écrit. » |
| 1:00-1:50 | onglet A (vue d'ensemble) | lire les cartes : 3000 attendus, 3000 enregistrés, 0 manquant, 0 double effet, interruption de 3,4 s sous la limite de 60 s, retour à la normale en 6 s sous la limite de 120 s. « Il y a une interruption : on ne dit pas "sans interruption", on dit "interruption bornée". » |
| 1:50-2:30 | onglet B (déroulement) | les sept étapes. Étape 4 : « pendant la nouvelle répartition, aucune version ne traite, mais les paiements attendent dans la file : rien n'est perdu ». Les 3 s viennent surtout d'un délai d'attente du broker (3,000 s mesurés dans ses journaux). |
| 2:30-3:20 | onglet C (contre-exemple) | « Ici, on tue le programme brutalement, en at-most-once : il note la lecture avant d'écrire. » Montrer le résumé : `tx-00000309 jamais écrit : perdu`. « Sa lecture était notée, il n'a jamais été écrit, la nouvelle version repart après lui. » |
| 3:20-4:00 | onglet D (comparaison) | « En panne brutale, at-most-once a perdu un paiement dans 8 pannes sur 9 ; at-least-once, aucun, et la base absorbe les relectures. Limites : un seul Mac, 3 à 12 essais par cas, environ 58 paiements par seconde au maximum. » |

## Si l'enseignant demande un essai en direct

Bouton **Solution minimale** dans Grafana (5 à 7 minutes). Pendant l'essai, un
bandeau bleu « Essai en cours » s'affiche ; continuer la présentation sur les
onglets A à D, puis revenir au résultat à la fin.

## Phrases à éviter

« sans interruption » ; « at-most-once perd toujours » ; « at-least-once
empêche les doublons » (c'est la clé primaire et l'upsert) ; « exactly-once »
sans préciser qu'il s'agit de l'écriture en base de ce seul service ; « la
pause de la solution améliorée est de 1 s » (aucune interruption mesurable) ;
« la cause des 3 s est prouvée » (observée et cohérente, pas démontrée par une
contre-expérience).
