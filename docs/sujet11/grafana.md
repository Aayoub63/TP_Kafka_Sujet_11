# Le tableau de bord du sujet 11

Ce guide est écrit pour quelqu'un qui ne connaît pas Kafka. Les mots
techniques sont expliqués quand ils sont nécessaires.

## Ce qu'on teste, en deux phrases

Un programme, `persister-valid`, enregistre dans une base de données
(PostgreSQL) les paiements que la banque a validés. On remplace ce programme
par une nouvelle version **pendant que les paiements arrivent**, et on
vérifie, paiement par paiement, qu'aucun n'est perdu ni enregistré deux fois,
et que l'interruption reste sous une limite fixée à l'avance (60 s).

Les paiements passent par Kafka, une file d'attente : pendant que le
programme est remplacé, ils attendent dans cette file et ne sont pas perdus,
à condition que le programme note correctement où il en était.

## Ouvrir le tableau de bord

1. `./start.sh` (une seule fois ; il n'efface rien).
2. Ouvrir http://localhost:3000 (identifiants `admin` / `adminpass`).
3. *Dashboards* → dossier *Simul-Pix* → **Simul-Pix - Sujet 11 (mise à jour de persister-valid)**.

L'écran est prévu pour 1920 × 1080. L'en-tête et la vue d'ensemble tiennent
sans défiler.

## Lancer un essai : section « Contrôle des scénarios expérimentaux »

Tout se fait à la souris, sans terminal. Il faut être **connecté à Grafana**
avec le rôle **Editor** ou **Admin** (le compte `admin` convient). Sans
connexion, ou avec un compte en lecture seule, le bouton « Lancer » reste grisé
et le service refuse toute demande.

1. **Choisir un scénario** (une carte) :

| Scénario | Ce qui se passe | Paramètres proposés | Durée |
|---|---|---|---|
| Mise à jour minimale | une seule instance du programme est remplacée ; courte interruption attendue, sous 60 s | mode de livraison ; charge normale ou forte | 5 à 6 min |
| Mise à jour améliorée | une 2e instance démarre, puis l'ancienne s'arrête proprement | mode de livraison ; charge normale ou forte | 5 à 6 min |
| Charge forte | la mise à jour minimale à 60 paiements/s | mode de livraison | 5 à 6 min |
| Panne brutale | ce n'est pas une solution : le programme est tué sans prévenir, à 10 paiements/s, avec 80 ms ajoutées entre « noter la lecture » et « écrire » | mode de livraison (la charge est fixe) ; **case de confirmation obligatoire** | environ 7 min |

2. **Choisir le mode de livraison** : at-least-once (notre solution),
   at-most-once (contre-exemple) ou exactly-once PostgreSQL (comparaison).
   Seules les charges acceptées par le scénario sont proposées.
3. **Lire le résumé**, puis cliquer sur **Lancer l'essai**. Le bouton se
   désactive aussitôt : un double clic ne lance rien de plus.
4. **Suivre l'essai** à droite (mis à jour toutes les 3 s) : identifiant,
   étape en cours (envoi, mise à jour, rattrapage, vérification, terminé),
   état des services, paiements envoyés, validés, enregistrés et en attente.
   Les pertes, doubles effets et durées sont calculés à la fin, à partir de
   PostgreSQL : ils ne sont pas affichés avant.
5. **Interruption contrôlée** : pendant un essai lancé depuis cette page,
   cocher la confirmation puis cliquer **Arrêter l'essai**. Le script s'arrête
   proprement ; l'essai est marqué « interrompu », sans verdict.
6. **Résultat** : à la fin, le verdict (Garantie respectée, Garantie NON
   respectée, ou Mesure non valide) et ses raisons, avec un lien « Voir le
   détail ». Les sections 1 à 3 du tableau de bord montrent le même essai.
7. **Anciens essais** : le tableau « Derniers lancements » garde chaque
   lancement (qui, quand, scénario, mode, charge, issue), avec un lien vers
   son détail ; la liste « Consulter un essai publié » ouvre n'importe quel
   essai de `preuves/`, sans le relancer.

Un seul essai tourne à la fois : un deuxième clic, un deuxième utilisateur
ou un essai lancé depuis un terminal donnent « Refusé : un essai est déjà en
cours ». Chaque essai repart de topics et de tables vides, avec un nouveau
groupe Kafka, et ne touche jamais aux preuves publiées.

**Ce qui protège le lancement** (détail technique) :

- la page appartient à `service-health` (`/sujet11/pilotage`) ; elle n'envoie
  que des choix pris dans une liste fixe, et le service construit lui-même la
  commande `scripts/sujet11-maj.sh` : aucune commande n'est saisie ;
- le service vérifie, pour chaque demande, l'origine (la page de pilotage),
  la session Grafana (il demande à Grafana qui est connecté) et la
  confirmation pour la panne et l'arrêt ;
- les ports de `service-health` n'écoutent que sur `localhost` : une autre
  machine du réseau ne peut pas les joindre ;
- délai maximal de 15 min : au-delà, l'essai est arrêté proprement (SIGTERM,
  puis SIGKILL 20 s plus tard) et marqué « interrompu » ;
- si `service-health` redémarre pendant un essai lancé depuis la page,
  l'essai est marqué « interrompu » au redémarrage et le verrou est libéré ;
- historique : `runtime/sujet11/lancements.jsonl`, et un journal par
  lancement dans `runtime/sujet11/lancements/`.

## Lire le tableau de bord, de haut en bas

Sous l'en-tête, une **légende des couleurs** reste visible : vert = objectif
respecté, rouge = objectif non respecté, orange = attention, bleu =
information ou traitement en cours, gris = donnée non disponible. Chaque carte
et chaque étape porte aussi un **libellé écrit** (Respecté, Non respecté,
Information, Non disponible, Observé) : la couleur n'est jamais le seul signal.
En thème sombre, les couleurs du texte sont plus claires (contraste d'au moins
4,5:1, mesuré).

### 1. Vue d'ensemble

Un bandeau donne le verdict du **dernier essai terminé**, avec son heure :

| Couleur | Verdict | Sens |
|---|---|---|
| vert | Garantie respectée | toutes les vérifications sont passées ; le bandeau dit lesquelles |
| rouge | Garantie NON respectée | au moins une vérification a échoué ; les raisons sont listées |
| gris | Mesure non valide | une mesure manque ou n'est pas fiable : ni réussite, ni échec |
| bleu | Essai en cours / observation | le résultat n'est pas encore validé |

Pendant un essai, un **bandeau bleu** l'annonce, avec sa phase et les
mesures en direct, et le verdict de l'ancien essai est atténué. Si un essai
plus récent a été **interrompu** (Ctrl+C, panne), un **bandeau orange** le
dit : il n'a pas de verdict. Si le dernier essai est **invalide**, le bandeau
gris rappelle le dernier essai qui a un verdict valide. Un ancien résultat
n'est jamais présenté comme celui de l'essai en cours. La ligne de contexte
donne l'heure de lancement et l'heure de fin, la charge réellement appliquée
et, le cas échéant, « Essai de diagnostic » (limites différentes des limites
officielles).

Les six cartes :

| Carte | Question | Vert si |
|---|---|---|
| Paiements à enregistrer | combien la banque en a validé ? | (information) |
| Enregistrés en base | combien sont dans la base, avec les bonnes valeurs ? | tous |
| Paiements manquants | combien manquent ? | 0 |
| Doubles effets | un paiement est-il enregistré deux fois ? | 0 |
| Interruption | combien de temps rien n'a été écrit en base ? | sous la limite de l'essai (60 s) |
| Retour à la normale | combien de temps, depuis le lancement, avant que plus aucun paiement n'attende ? La carte donne aussi le temps de reprise (lancement → première écriture) et le temps de rattrapage (reprise → retour à la normale) | sous la limite de l'essai (120 s ; 180 s en panne brutale) |

Une interruption n'est pas un échec si elle reste sous la limite : la carte
est alors verte, et elle dit si l'interruption se distingue du rythme normal
du flux. Le générateur envoie les paiements par paquets, environ une fois par
seconde : une interruption plus courte que ce rythme ne se mesure pas.

« Non disponible » veut dire que la mesure n'existe pas pour cet essai
(par exemple, un essai ancien). Ce n'est jamais un zéro.

### 2. Déroulement de la mise à jour

Sept étapes, avec leur temps mesuré (en secondes après le lancement) :
fonctionnement normal, mise à jour lancée, arrêt de l'ancienne version,
redistribution du travail par Kafka (le « rebalance »), reprise par la
nouvelle version, traitement des paiements en attente, retour à la normale.
Une étape grise n'a pas été observée dans cet essai.

### 3. Intégrité des paiements

Des barres comparent les paiements envoyés, rejetés par la banque (normal,
pas une perte), validés, enregistrés avec les bonnes valeurs, manquants,
sans aucune décision, aux valeurs fausses et en double. Chaque paiement est
cherché par son identifiant dans la base : ce n'est pas un simple compteur.

### 4. Performance et continuité

- **Paiements en attente (en direct)** : orange = validés pas encore écrits en
  base, bleu = pas encore lus par le service. Les lignes violettes marquent
  les étapes de l'essai. Le sens des couleurs est écrit sous le titre de la
  section.
- **Instances en train de lire (en direct)** : 0 pendant la nouvelle
  répartition du travail.
- **Chaque essai face à sa limite** : une ligne par cas et par sémantique, un
  point par essai publié, et un trait rouge à **la limite utilisée par ces
  essais** (60 s pour l'interruption ; 120 s pour revenir à la normale, 180 s
  en panne brutale). Un point rouge a dépassé sa limite.

### 5. Comparaison des sémantiques

En haut, ce que dit la théorie. En bas, ce que nous avons **mesuré**, sur les
**seuls essais publiés dans `preuves/`** du code actuel (arrêt propre, heure
d'audit corrigée le 9 novembre) : ce sont les mêmes chiffres que les bilans et
les `resume.md`. Les essais invalides et les essais de diagnostic sont
écartés, et leur nombre est écrit sous le tableau, avec la liste des
campagnes. Une « mise à jour avec perte » est un essai où au moins un
paiement a été perdu.

### 6. Détails techniques (rangée repliée)

Pour les questions : lag du groupe Kafka, membres et partitions, écritures
par seconde, repères et phases, et **tous les essais enregistrés dans
InfluxDB**. Ce dernier tableau a un périmètre plus large que `preuves/` : il
contient aussi les essais isolés non publiés, les essais de l'ancien code et
les essais de diagnostic (colonne « bornes officielles »).

## D'où viennent les valeurs

| Partie | Source |
|---|---|
| Vue d'ensemble, déroulement, intégrité | page `/sujet11/synthese` de `service-health`, qui lit `runtime/sujet11/<essai>/resultat.json`, et pendant un essai `phase`, `compteurs.jsonl` et `lag.jsonl` |
| Chaque essai face à sa limite, comparaison | même page, vues `essais` et `comparaison`, qui lisent `preuves/sujet11/*/essais/*/` |
| Courbes en direct, détails techniques | InfluxDB : mesures `sujet11_groupe`, `sujet11_compteurs`, `sujet11_essai`, `sujet11_repere`, `sujet11_etat` |
| Valeur exacte de l'interruption | table d'audit de PostgreSQL (une ligne par écriture, heure `clock_timestamp()`) |

## Présenter le tableau de bord en 3 minutes

1. **30 s, l'en-tête.** « On remplace le programme qui enregistre les
   paiements pendant qu'ils arrivent. La question : en perd-on, en compte-t-on
   deux fois, et combien de temps s'arrête-t-on ? »
2. **45 s, la vue d'ensemble.** Lire le bandeau, puis les cartes de gauche à
   droite : attendus, enregistrés, manquants, doubles effets, interruption
   face à la limite, retard rattrapé.
3. **45 s, le déroulement.** Suivre les sept étapes. Insister sur l'étape 4 :
   en solution minimale, aucune version ne traite de paiement pendant la
   nouvelle répartition, mais les paiements attendent dans Kafka. En solution
   améliorée, l'ancienne version continue de traiter pendant ce temps.
4. **30 s, l'intégrité.** Montrer que la vérification se fait paiement par
   paiement, et qu'un rejet de la banque n'est pas une perte.
5. **30 s, la comparaison.** En arrêt propre, les sémantiques se valent. En
   panne brutale, at-most-once peut perdre le paiement en cours (8 pannes sur
   9), at-least-once le relit sans double effet.

Pour une démonstration sans essai en direct, chaque vue accepte un essai
terminé précis : `http://localhost:8083/sujet11/synthese?vue=ensemble&essai=<dossier>`,
avec un dossier de `preuves/sujet11/` ou de `runtime/sujet11/` (voir
`docs/sujet11/demonstration-soutenance.md`).

## Limite

Les boutons et les cadres demandent `GF_PANELS_DISABLE_SANITIZE_HTML=true`
dans `docker-compose.yml`, car Grafana retire par défaut les formulaires et
les cadres. C'est acceptable pour une plateforme locale de TP, pas pour un
Grafana exposé.
