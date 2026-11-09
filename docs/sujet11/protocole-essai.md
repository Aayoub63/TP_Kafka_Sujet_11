# Protocole d'essai, rejouable par un autre groupe

## Prérequis

- Docker Desktop (au moins 4 Go de mémoire), `python3` (bibliothèque standard),
  `sh`, `curl`. Testé sur macOS (bash 3.2, outils BSD).
- Aucune autre plateforme simul-pix lancée : les noms de conteneurs sont fixes.

## Étapes

1. Démarrer la plateforme :

   ```sh
   ./start.sh
   ```

2. Lancer un essai observé (sans verdict), pour voir la chronologie :

   ```sh
   ./scripts/sujet11-maj.sh --mode observee --semantique at_least_once --debit 20 --duree 150
   ```

3. Lancer un essai de la solution minimale, avec la borne du groupe :

   ```sh
   ./scripts/sujet11-maj.sh --mode minimale --semantique at_least_once --borne 60
   echo "code de sortie : $?"
   ```

   Code 0 : continuité respectée. Code 1 : échec (perte, valeur fausse, drainage
   non terminé ou pause au-dessus de la borne). Code 2 : erreur d'utilisation.

4. Lancer la campagne complète (12 essais, environ une heure) :

   ```sh
   ./scripts/sujet11-campagne.sh 3 60
   ```

   Résumé : `preuves/sujet11/campagne-<date>/resume.md` et `resultats.csv`.

5. Tests unitaires de l'oracle et de la mesure de la pause :

   ```sh
   python3 -m unittest discover -s tests
   ```

## Ce que fait un essai

| Étape | Ce qui se passe | Fichier produit dans `runtime/sujet11/<essai>/` |
|---|---|---|
| 1 | audit des écritures installé et vidé (`toggle-unique.sh`) | |
| 2 | flux de paiements (`run-scenario.sh nominal`) avec la sémantique choisie | `run-scenario.txt` |
| 3 | relevé du groupe chaque seconde, écoute des événements Docker | `lag.jsonl`, `evenements.txt` |
| 4 | après 30 s de référence, remplacement de `persister-valid` | `rebuild.txt` |
| 5 | attente du lag à 0 (limite 120 s), puis de la fin du flux | `meta.json` |
| 6 | collecte, oracle, bilan | `donnees/`, `oracle.json`, `resultat.json`, `bilan.txt` |

## Lire le bilan

- **Pause en base** : comparée à la borne (60 s) et à la cible métier (10 s).
- **Trou normal** : le plus long trou avant la mise à jour. Si la pause est
  proche de ce trou, la mise à jour n'a presque rien coûté.
- **Chronologie** : instants en secondes après le lancement de la mise à jour.
- **Oracle** : une seule classe compte comme perte, `perdus`. Un rejet pour
  délai n'est pas une perte.
- **Doublons absorbés** : tentatives d'écriture en trop, sans second effet en
  base grâce à l'upsert sur `transaction_id`.

## Précautions

- `./stop.sh` efface les données : ne pas l'utiliser entre deux essais.
- Ne pas conclure à partir d'un offset Kafka seul : le verdict vient de
  PostgreSQL.
