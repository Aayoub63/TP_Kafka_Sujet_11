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

   Code 0 : continuité respectée (REUSSITE). Code 1 : ECHEC (perte, valeur
   fausse, double effet, paiement sans décision, retard non résorbé, pause
   au-dessus de la borne) ou INVALIDE (une mesure manque : le résultat n'est ni
   une réussite, ni un échec). Code 2 : erreur d'utilisation. La dernière ligne
   du bilan donne le verdict et ses raisons.

4. Provoquer une panne (mode `crash`) pour comparer les sémantiques. Ce
   n'est pas une solution : `persister-valid` est tué par `docker kill`
   (SIGKILL), sans arrêt propre, puis redémarré. `--ralenti 80` ajoute 80 ms
   entre le commit et l'écriture, pour que la panne tombe dans cette fenêtre.
   À 80 ms par message, l'instance traite environ 12 Pix/s : on baisse le
   débit à 10 et on laisse plus de temps au drainage.

   ```sh
   ./scripts/sujet11-maj.sh --mode crash --semantique at_most_once --borne 60 \
     --ralenti 80 --debit 10 --drainage-max 180
   ./scripts/sujet11-maj.sh --mode crash --semantique at_least_once --borne 60 \
     --ralenti 80 --debit 10 --drainage-max 180
   ```

   Sans `--drainage-max`, le mode `crash` prend 180 s, et `--ralenti` donne
   l'étiquette de charge « ralentie » (sauf `--charge` explicite).

   Mesuré le 9 novembre 2026 (un essai de chaque, drainage limité à 120 s, avant
   la règle des 180 s : ces deux essais exploratoires ne sont pas publiés) :
   en at-most-once, 1 paiement perdu (`tx-00000322`, validé dans Kafka mais
   jamais écrit) ; en at-least-once, 0 perdu et 1 doublon absorbé
   (`tx-00000309`, écrit, tué avant le commit, relu). Pause d'environ 45 s
   dans les deux cas : le membre tué ne quitte pas le groupe, Kafka attend la
   fin de sa session. La panne ne tombe pas toujours dans la fenêtre : il faut
   plusieurs essais pour conclure.

5. Lancer la campagne complète (12 essais, environ une heure) :

   ```sh
   ./scripts/sujet11-campagne.sh 3 60
   ```

   Résumé : `preuves/sujet11/campagne-<date>/resume.md` et `resultats.csv`.
   Chaque essai y garde `bilan.txt`, `meta.json`, `resultat.json`, et les
   fichiers bruts légers pour refaire l'analyse : `lag.jsonl`,
   `compteurs.jsonl`, `evenements.txt`, `oracle.json` (environ 80 Ko).

6. Tests unitaires de l'oracle et de la mesure de la pause :

   ```sh
   python3 -m unittest discover -s tests
   ```

## Ce que fait un essai

| Étape | Ce qui se passe | Fichier produit dans `runtime/sujet11/<essai>/` |
|---|---|---|
| 1 | audit des écritures installé et vidé (`toggle-unique.sh`) | |
| 2 | flux de paiements (`run-scenario.sh nominal`) avec la sémantique choisie | `run-scenario.txt` |
| 3 | relevé du groupe chaque seconde, écoute des événements Docker, compteurs de la plateforme toutes les 2 s (avant, pendant, après) | `lag.jsonl`, `evenements.txt`, `compteurs.jsonl` |
| 4 | après 30 s de référence, remplacement de `persister-valid` (ou `docker kill` en mode `crash`) | `rebuild.txt` |
| 5 | attente du lag à 0 (limite 120 s, 180 s par défaut en mode `crash`), puis de la fin du flux, puis d'une base stable (même nombre de lignes deux relevés de suite, 30 s au plus) | `meta.json` |
| 6 | collecte, oracle, bilan | `donnees/`, `oracle.json`, `resultat.json`, `bilan.txt` |
| tout au long | phase de l'essai (lance, mise_a_jour, drainage, collecte, termine, interrompu), lue par le tableau de bord | `phase` |

## Lire le bilan

- **Pause en base** : comparée à la borne (60 s) et à la cible métier (10 s).
- **Trou normal** : le plus long trou avant la mise à jour. C'est aussi la
  résolution de la mesure. Si la pause ne dépasse pas 1,5 fois ce trou, le
  bilan écrit « AUCUNE pause mesurable au-delà du rythme normal du flux ».
- **Débit** : demandé, et mesuré à partir des compteurs de la plateforme.
- **Compteurs** : topic `validated`, lignes en base et écart, avant la mise à
  jour, au pire moment et après le flux.
- **Chronologie** : instants en secondes après le lancement de la mise à jour.
- **Oracle** : une seule classe compte comme perte, `perdus`. Un rejet pour
  délai n'est pas une perte. Les valeurs comparées sont le montant, la devise
  et les deux comptes. Les doubles effets, les paiements à la fois validés et
  rejetés et les conflits du topic font aussi échouer l'essai.
- **Trous de `transaction_id`** : numéros de l'essai absents des deux tables.
  Ils font échouer l'essai : c'est le contrôle qui rattrape une relecture
  incomplète du topic.
- **Doublons absorbés** : livraisons en trop, sans second effet en base grâce
  à l'upsert sur `transaction_id`. Une relecture laisse deux lignes dans
  l'audit (INSERT, puis UPDATE de l'upsert) : seules les lignes INSERT
  comptent.
- **Passations de partitions** : pour chaque partition qui change de main,
  l'offset de reprise et le sort du paiement en cours (pas encore écrit, relu,
  ou « ATTENTION … jamais écrit » quand il a été validé sans être écrit).

## Précautions

- `./stop.sh` efface les données : ne pas l'utiliser entre deux essais.
- Ne pas conclure à partir d'un offset Kafka seul : le verdict vient de
  PostgreSQL.
