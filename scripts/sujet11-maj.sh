#!/bin/sh
#
# sujet11-maj.sh — mettre à jour persister-valid sous flux et mesurer la continuité.
#
# Déroulé :
#   1. installe l'audit des écritures (toggle-unique.sh) et le vide ;
#   2. lance un flux de paiements (run-scenario.sh) avec la sémantique choisie ;
#   3. relève le groupe persister-valid chaque seconde (scripts/sujet11/mesure.py) ;
#   4. après une période de référence, remplace persister-valid :
#      - minimale : docker compose up -d --build --force-recreate (une instance) ;
#      - amelioree : démarre persister-valid-b dans le même groupe, attend qu'il
#        ait rejoint le groupe, puis arrête l'ancienne instance (SIGTERM) ;
#      - crash : ce n'est pas une solution mais une panne. docker kill (SIGKILL,
#        pas d'arrêt propre) puis redémarrage. Avec --ralenti, la fenêtre entre
#        commit et écriture s'élargit : on voit la différence entre sémantiques ;
#   5. attend le retour du lag à 0, avec une limite de temps ;
#   6. collecte les données, applique l'oracle et calcule le bilan.
#
# Usage :
#   ./scripts/sujet11-maj.sh [--mode observee|minimale|amelioree|crash] [--semantique at_least_once|at_most_once|exactly_once_pg]
#                            [--debit N] [--duree S] [--charge NOM] [--borne S] [--ralenti MS]
#                            [--cible S] [--reference S] [--drainage-max S] [--sortie DOSSIER]
#
# --ralenti MS : pause de persister-valid entre commit et écriture (SIMULPIX_PERSIST_DELAY_MS).
#
# Code de sortie (hors mode observee) : 0 si la continuité est respectée, 1 sinon,
# 2 en cas d'erreur d'utilisation ou de plateforme indisponible.
#
set -eu

# Se placer à la racine du dépôt, quel que soit le répertoire d'appel.
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

MODE="minimale"
SEMANTIQUE="at_least_once"
DEBIT="20"
DUREE="150"
CHARGE=""
BORNE="${SUJET11_BORNE_S:-}"
# Cible métier : délai de décision (10 s par défaut). Rapportée, sans faire échouer.
CIBLE="${SUJET11_CIBLE_S:-10}"
REFERENCE="30"
DRAINAGE_MAX=""
SORTIE=""
RALENTI="0"

usage() {
  sed -n '2,27p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --mode) MODE="$2"; shift 2 ;;
    --semantique) SEMANTIQUE="$2"; shift 2 ;;
    --debit) DEBIT="$2"; shift 2 ;;
    --duree) DUREE="$2"; shift 2 ;;
    --charge) CHARGE="$2"; shift 2 ;;
    --borne) BORNE="$2"; shift 2 ;;
    --cible) CIBLE="$2"; shift 2 ;;
    --reference) REFERENCE="$2"; shift 2 ;;
    --drainage-max) DRAINAGE_MAX="$2"; shift 2 ;;
    --sortie) SORTIE="$2"; shift 2 ;;
    --ralenti) RALENTI="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "[sujet11] option inconnue : $1" >&2; usage ;;
  esac
done

case "$MODE" in observee|minimale|amelioree|crash) ;; *) echo "[sujet11] mode invalide : $MODE" >&2; exit 2 ;; esac
case "$SEMANTIQUE" in at_least_once|at_most_once|exactly_once_pg) ;; *) echo "[sujet11] sémantique invalide : $SEMANTIQUE" >&2; exit 2 ;; esac
if [ "$MODE" != "observee" ] && [ -z "$BORNE" ]; then
  echo "[sujet11] mode $MODE : la borne de pause doit être fixée (--borne S ou SUJET11_BORNE_S)" >&2
  exit 2
fi
[ -n "$BORNE" ] || BORNE="0"
# Valeurs par défaut alignées sur les bornes officielles (scripts/sujet11/bilan.py,
# BORNES_OFFICIELLES) : 120 s pour revenir à la normale, 180 s en panne brutale.
if [ -z "$DRAINAGE_MAX" ]; then
  if [ "$MODE" = "crash" ]; then DRAINAGE_MAX="180"; else DRAINAGE_MAX="120"; fi
fi
# Étiquette de charge : « ralentie » dès qu'un ralenti est appliqué, sauf si l'appelant la donne.
if [ -z "$CHARGE" ]; then
  if [ "$RALENTI" != "0" ]; then CHARGE="ralentie"; else CHARGE="normale"; fi
fi
case "$RALENTI" in ''|*[!0-9]*) echo "[sujet11] --ralenti attend un nombre de millisecondes" >&2; exit 2 ;; esac

maintenant() { python3 -c 'import time; print(f"{time.time():.3f}")'; }
# Repère vertical dans le tableau de bord Grafana du sujet 11 (sans effet si InfluxDB ne répond pas).
repere() { python3 scripts/sujet11/influx.py repere "$ID" "$1" || true; }
# Phase de l'essai en cours, lue par le tableau de bord (lance, mise_a_jour, drainage, collecte, termine, interrompu).
# Aussi écrite dans $SORTIE/phase : la page de synthèse de service-health la lit.
etat() {
  if [ -d "$SORTIE" ]; then echo "$1" >"$SORTIE/phase"; fi
  python3 scripts/sujet11/influx.py etat "$ID" "$1" || true
}
TERMINE="false"
# Sortie du script : si l'essai n'est pas allé au bout, le tableau de bord le dit.
fin_essai() {
  [ "$TERMINE" = "true" ] || etat interrompu
  rm -rf "$VERROU"
}

# Python plutôt que curl : le conteneur service-health (boutons Grafana) n'a pas curl.
http_ok() { python3 -c "import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=5)" "$1" >/dev/null 2>&1; }
http_lire() { python3 -c "import sys, urllib.request; print(urllib.request.urlopen(sys.argv[1], timeout=5).read().decode())" "$1" 2>/dev/null; }

# Compteurs de la plateforme à un instant donné, ajoutés à compteurs.jsonl :
# avant la mise à jour, pendant le drainage, après le flux. L'écart entre le
# topic validated et la base est la « rupture de persistance » du protocole
# d'arrêt (docs/architecture/pix-validation-stop-protocol.md).
compteurs() {
  http_lire "http://127.0.0.1:8082/health/details" | python3 -c '
import json, sys, time
c = json.load(sys.stdin)["metrics"]["counts"]
cles = ("generated", "validated_topic_end_offsets", "db_validated_count", "db_rejected_count",
        "persister_valid_lag_total")
ligne = {"t": round(time.time(), 3), "phase": sys.argv[1]} | {k: c.get(k) for k in cles}
# un compteur absent donne un écart inconnu (null), jamais un zéro inventé
topic, base = c.get("validated_topic_end_offsets"), c.get("db_validated_count")
ligne["ecart_topic_base"] = topic - base if topic is not None and base is not None else None
print(json.dumps(ligne))
# même relevé dans InfluxDB : courbes « attendus / en base / en attente » du tableau de bord
sys.path.insert(0, "scripts/sujet11")
import influx
influx.ecrire([influx.ligne("sujet11_compteurs", {"essai": sys.argv[2]},
                            {k: v for k, v in ligne.items() if k not in ("t", "phase")}, t=ligne["t"])])
' "$1" "$ID" >>"$SORTIE/compteurs.jsonl" 2>/dev/null || true
}

if ! http_ok "http://127.0.0.1:8082/health"; then
  echo "[sujet11] plateforme indisponible : lancez ./start.sh" >&2
  exit 2
fi

TOTAL=$((DEBIT * DUREE))
ID="$(date +%Y%m%d-%H%M%S)-${MODE}-${SEMANTIQUE}-${CHARGE}"
[ -n "$SORTIE" ] || SORTIE="runtime/sujet11/$ID"
# Un seul essai à la fois sur la plateforme. Le verrou est un dossier :
# mkdir est atomique, et le dépôt est monté dans service-health, donc les
# essais lancés depuis le terminal et depuis Grafana voient le même verrou.
# Un verrou de plus de 20 min vient d'un essai interrompu : on le reprend.
VERROU="runtime/sujet11/verrou"
mkdir -p runtime/sujet11
if ! mkdir "$VERROU" 2>/dev/null; then
  if python3 -c "import os, sys, time; sys.exit(0 if time.time() - os.path.getmtime(sys.argv[1]) > 1200 else 1)" "$VERROU"; then
    rm -rf "$VERROU" && mkdir "$VERROU"
  else
    echo "[sujet11] un autre essai est en cours ($(cat "$VERROU/essai" 2>/dev/null)) : réessayez après sa fin" >&2
    exit 2
  fi
fi
echo "$ID" >"$VERROU/essai"
# dossier de l'essai, relatif au dépôt : la page de synthèse y lit le direct
echo "$SORTIE" >"$VERROU/sortie"
trap fin_essai EXIT
trap 'exit 130' INT TERM

mkdir -p "$SORTIE"

echo "[sujet11] essai $ID : $TOTAL Pix à $DEBIT Pix/s, sortie $SORTIE"
repere "essai démarré : $MODE, $SEMANTIQUE, $DEBIT Pix/s"

# La sémantique est lue par persister-valid au moment de sa création : elle doit
# être présente pour run-scenario.sh ET pour la reconstruction, sinon le service
# reconstruit repart avec la valeur par défaut (at_least_once).
export SIMULPIX_KAFKA_CONSUMER_SEMANTICS="$SEMANTIQUE"
# Même règle pour le ralenti, lu par docker-compose.yml (SIMULPIX_PERSIST_DELAY_MS).
export SIMULPIX_PERSIST_VALID_DELAY_MS="$RALENTI"

# Une seconde instance restée d'un essai précédent fausserait le groupe.
docker compose --profile roulant rm -sf persister-valid-b >/dev/null 2>&1 || true

# Décalage d'horloge entre la machine et Docker (scripts/sujet11/horloge.py).
DECALAGE_DEBUT="$(python3 scripts/sujet11/horloge.py | cut -d' ' -f1)"
echo "[sujet11] décalage d'horloge Docker - machine : $DECALAGE_DEBUT s"

echo "[sujet11] 1/6 audit des écritures"
./scripts/toggle-unique.sh off >/dev/null
./scripts/toggle-unique.sh reset >/dev/null
# now() donne l'heure de début de la transaction. persister-valid garde une
# transaction ouverte entre deux messages (comptage après chaque écriture) :
# la première écriture d'une nouvelle instance prenait l'heure de son
# démarrage, et la pause mesurée était trop courte. clock_timestamp() donne
# l'heure réelle de l'écriture.
docker compose exec -T postgres psql -U simulpix -d simulpix -v ON_ERROR_STOP=1 -q \
  -c "alter table tp_audit_attempts alter column attempted_at set default clock_timestamp()" >/dev/null

# L'image de persister-valid doit venir du code du dépôt : run-scenario.sh et
# le mode crash la démarrent sans la reconstruire. Une image ancienne qui ne
# connaît pas la sémantique demandée retombe sans le dire sur at_least_once.
docker compose build persister-valid >"$SORTIE/build.txt" 2>&1

echo "[sujet11] 2/6 lancement du flux (run-scenario.sh nominal)"
./scripts/run-scenario.sh nominal "$TOTAL" "$DEBIT" >"$SORTIE/run-scenario.txt" 2>&1
# Sémantique réellement appliquée par une instance, lue sur son /health.
semantique_de() {
  docker exec "$1" python3 -c '
import json, time, urllib.request
# vaut None tant que le service démarre : on réessaie 30 s
for _ in range(30):
    try:
        s = json.load(urllib.request.urlopen("http://127.0.0.1:8084/health", timeout=5)).get("consumer_semantics")
    except OSError:
        s = None
    if s:
        break
    time.sleep(1)
print(s or "inconnue")' 2>/dev/null || echo inconnue
}
SEMANTIQUE_EFFECTIVE="$(semantique_de persister-valid)"
echo "[sujet11]     sémantique appliquée par persister-valid : $SEMANTIQUE_EFFECTIVE"
etat lance
DEBUT_FLUX="$(maintenant)"
GROUPE="$(sed -n 's/^SIMULPIX_PERSISTER_VALID_GROUP=//p' runtime/current-run.env)"

echo "[sujet11] 3/6 relevé du groupe $GROUPE"
rm -f "$SORTIE/stop"
python3 scripts/sujet11/mesure.py "$GROUPE" "$SORTIE/lag.jsonl" "$SORTIE/stop" &
PID_MESURE=$!
# Les événements Docker sont écoutés en direct : l'historique du démon est
# limité et le relevé (un exec par seconde dans kafka-1) le remplit vite.
docker events --filter container=persister-valid --filter container=persister-valid-b \
  --format '{{.TimeNano}} {{.Action}} {{.Actor.Attributes.name}} {{index .Actor.Attributes "signal"}}' \
  >"$SORTIE/evenements.txt" 2>/dev/null &
PID_EVENEMENTS=$!
trap 'touch "$SORTIE/stop"; kill "$PID_EVENEMENTS" 2>/dev/null || true; fin_essai' EXIT

sleep "$REFERENCE"
DEBUT_REFERENCE="$(python3 -c "print(f'{$DEBUT_FLUX + $REFERENCE / 3:.3f}')")"

compteurs avant
T0="$(maintenant)"
# Pendant : un relevé toutes les 2 s, jusqu'au fichier d'arrêt du relevé du groupe.
( while [ ! -f "$SORTIE/stop" ]; do compteurs pendant; sleep 2; done ) &
PID_COMPTEURS=$!
repere "mise à jour lancée ($MODE, $SEMANTIQUE, $DEBIT Pix/s)"
etat mise_a_jour
if [ "$MODE" = "amelioree" ]; then
  echo "[sujet11] 4/6 mise à jour roulante : persister-valid-b démarre à côté de persister-valid"
  docker compose --profile roulant up -d --build --force-recreate --no-deps persister-valid-b \
    >"$SORTIE/rebuild.txt" 2>&1
  FIN_REBUILD="$(maintenant)"
  # On n'arrête l'ancienne instance que quand la nouvelle est dans le groupe :
  # sinon le groupe serait vide, comme dans la solution minimale.
  LIMITE_RELEVE="$(python3 -c "print($T0 + 60)")"
  while python3 -c "import sys,time; sys.exit(0 if time.time() < $LIMITE_RELEVE else 1)"; do
    if python3 - "$SORTIE/lag.jsonl" "$T0" <<'EOF'
import json, sys
lignes = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
sys.exit(0 if any(x["t"] > float(sys.argv[2]) and x["membres"] >= 2 for x in lignes) else 1)
EOF
    then
      break
    fi
    sleep 1
  done
  T_ARRET="$(maintenant)"
  repere "persister-valid-b dans le groupe, arrêt de l'ancienne instance"
  echo "[sujet11]     arrêt de l'ancienne instance (SIGTERM, arrêt propre)"
  docker compose stop persister-valid >"$SORTIE/arret-ancienne.txt" 2>&1
elif [ "$MODE" = "crash" ]; then
  echo "[sujet11] 4/6 panne : docker kill persister-valid (SIGKILL), puis redémarrage"
  # Pas de SIGTERM : l'instance ne finit pas son message, ne valide rien et
  # ne quitte pas le groupe. Le même conteneur redémarre aussitôt.
  docker kill persister-valid >"$SORTIE/rebuild.txt" 2>&1
  docker compose up -d --no-deps persister-valid >>"$SORTIE/rebuild.txt" 2>&1
  FIN_REBUILD="$(maintenant)"
  T_ARRET="$T0"
else
  echo "[sujet11] 4/6 mise à jour de persister-valid (rebuild + remplacement du conteneur)"
  docker compose up -d --build --force-recreate --no-deps persister-valid >"$SORTIE/rebuild.txt" 2>&1
  FIN_REBUILD="$(maintenant)"
  T_ARRET="$T0"
fi

echo "[sujet11] 5/6 attente du drainage (limite ${DRAINAGE_MAX} s)"
etat drainage
DRAINAGE_TERMINE="false"
LIMITE="$(python3 -c "print($T0 + $DRAINAGE_MAX)")"
sleep 5
while python3 -c "import sys,time; sys.exit(0 if time.time() < $LIMITE else 1)"; do
  if python3 - "$SORTIE/lag.jsonl" "$T_ARRET" "$MODE" <<'EOF'
import json, sys, time
lignes = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
t_arret, mode = float(sys.argv[2]), sys.argv[3]
apres = [x for x in lignes if x["t"] > t_arret]
fini = bool(apres) and apres[-1]["membres"] > 0 and apres[-1]["lag"] == 0
if mode == "amelioree":
    # le groupe peut ne jamais être vide : on attend seulement 3 s après l'arrêt
    fini = fini and time.time() > t_arret + 3
else:
    # une instance : il faut avoir vu la perturbation (groupe vide ou lag) avant de conclure
    fini = fini and any(x["membres"] == 0 or x["lag"] > 0 for x in apres)
sys.exit(0 if fini else 1)
EOF
  then
    DRAINAGE_TERMINE="true"
    break
  fi
  sleep 2
done
sleep 3
FIN="$(maintenant)"
if [ "$DRAINAGE_TERMINE" = "true" ]; then repere "drainage terminé"; else repere "drainage NON terminé"; fi
# La nouvelle instance applique-t-elle la sémantique demandée ? (même lecture qu'au début)
if [ "$MODE" = "amelioree" ]; then NOUVELLE="persister-valid-b"; else NOUVELLE="persister-valid"; fi
SEMANTIQUE_APRES="$(semantique_de "$NOUVELLE")"
echo "[sujet11]     sémantique appliquée par $NOUVELLE après la mise à jour : $SEMANTIQUE_APRES"

# L'oracle compare le topic et la base : il faut attendre la fin du flux et
# son dernier drainage, sinon les paiements encore en route compteraient
# comme perdus. La fenêtre de la pause, elle, s'arrête à FIN.
echo "[sujet11]     attente de la fin du flux ($TOTAL Pix) puis du lag à 0"
# Le générateur ralentit parfois (2 697 Pix sur 3 000 après 289 s, le
# 9 novembre) : on lui laisse deux fois la durée prévue, et on note s'il a fini.
FLUX_TERMINE="false"
LIMITE_FLUX="$(python3 -c "print($DEBUT_FLUX + 2 * $DUREE + $DRAINAGE_MAX)")"
while python3 -c "import sys,time; sys.exit(0 if time.time() < $LIMITE_FLUX else 1)"; do
  if http_lire "http://127.0.0.1:8082/health/details" | python3 -c "
import json, sys
c = json.load(sys.stdin)['metrics']['counts']
# Fini : tout est produit et chaque étage de la chaîne a tout lu. On n'exige pas
# que la base soit complète : une perte l'en empêcherait pour toujours.
lags = ('pix_validator_lag_total', 'pix_decision_engine_lag_total', 'pix_outcome_publisher_lag_total',
        'persister_valid_lag_total', 'persister_rejected_lag_total')
sys.exit(0 if c.get('generated', 0) >= $TOTAL and all(c.get(k) == 0 for k in lags) else 1)
" && [ "$(tail -1 "$SORTIE/lag.jsonl" | python3 -c 'import json,sys; print(json.load(sys.stdin)["lag"])')" = "0" ]; then
    FLUX_TERMINE="true"
    break
  fi
  sleep 3
done
# Lag à 0 ne veut pas dire « tout est écrit » en at-most-once : la lecture est
# validée AVANT l'écriture, une écriture peut encore être en cours. On attend que
# le nombre de lignes en base reste le même deux relevés de suite (3 s d'écart,
# 30 s au plus). Sinon, le bilan ne conclut pas à une perte : l'essai est INVALIDE.
BASE_STABLE="false"
nb_base() { http_lire "http://127.0.0.1:8082/health/details" | python3 -c 'import json,sys; print(json.load(sys.stdin)["metrics"]["counts"].get("db_validated_count"))' 2>/dev/null || echo none; }
AVANT_BASE="$(nb_base)"
ESSAIS_BASE=0
while [ "$ESSAIS_BASE" -lt 10 ]; do
  sleep 3
  APRES_BASE="$(nb_base)"
  if [ "$APRES_BASE" != "none" ] && [ "$APRES_BASE" = "$AVANT_BASE" ]; then BASE_STABLE="true"; break; fi
  AVANT_BASE="$APRES_BASE"
  ESSAIS_BASE=$((ESSAIS_BASE + 1))
done
FIN_FLUX="$(maintenant)"
touch "$SORTIE/stop"
wait "$PID_MESURE" 2>/dev/null || true
wait "$PID_COMPTEURS" 2>/dev/null || true
compteurs apres
DECALAGE_FIN="$(python3 scripts/sujet11/horloge.py | cut -d' ' -f1)"
kill "$PID_EVENEMENTS" 2>/dev/null || true

cat >"$SORTIE/meta.json" <<EOF
{
  "id": "$ID",
  "mode": "$MODE",
  "semantique": "$SEMANTIQUE",
  "charge": "$CHARGE",
  "total": $TOTAL,
  "debit": $DEBIT,
  "borne_s": $BORNE,
  "cible_metier_s": $CIBLE,
  "drainage_max_s": $DRAINAGE_MAX,
  "ralenti_ms": $RALENTI,
  "groupe": "$GROUPE",
  "debut_flux": $DEBUT_FLUX,
  "debut_reference": $DEBUT_REFERENCE,
  "t0": $T0,
  "t_arret": $T_ARRET,
  "fin_rebuild": $FIN_REBUILD,
  "fin": $FIN,
  "fin_flux": $FIN_FLUX,
  "drainage_termine": $DRAINAGE_TERMINE,
  "flux_termine": $FLUX_TERMINE,
  "base_stable": $BASE_STABLE,
  "semantique_effective": "$SEMANTIQUE_EFFECTIVE",
  "semantique_effective_apres": "$SEMANTIQUE_APRES",
  "decalage_debut_s": $DECALAGE_DEBUT,
  "decalage_fin_s": $DECALAGE_FIN
}
EOF

echo "[sujet11] 6/6 collecte, oracle et bilan"
etat collecte
python3 scripts/sujet11/collecte.py "$SORTIE"
python3 scripts/sujet11/oracle.py "$SORTIE" >/dev/null
CODE=0
python3 scripts/sujet11/bilan.py "$SORTIE" || CODE=$?
TERMINE="true"
etat termine
repere "essai terminé : $(python3 -c 'import json, sys; r = json.load(open(sys.argv[1])); print(r["verdict"], "- pause", r["pause"]["pause_s"], "s")' "$SORTIE/resultat.json" 2>/dev/null || echo "sans bilan")"

if [ "$MODE" = "amelioree" ]; then
  # Retour à la plateforme par défaut : une seule instance, persister-valid.
  docker compose --profile roulant rm -sf persister-valid-b >/dev/null 2>&1 || true
  docker compose up -d --no-deps persister-valid >/dev/null 2>&1 || true
fi
exit "$CODE"
