#!/bin/sh
#
# sujet11-maj.sh — mettre à jour persister-valid sous flux et mesurer la continuité.
#
# Déroulé :
#   1. installe l'audit des écritures (toggle-unique.sh) et le vide ;
#   2. lance un flux de paiements (run-scenario.sh) avec la sémantique choisie ;
#   3. relève le groupe persister-valid chaque seconde (scripts/sujet11/mesure.py) ;
#   4. après une période de référence, remplace le conteneur persister-valid
#      (docker compose up -d --build --force-recreate) ;
#   5. attend le retour du lag à 0, avec une limite de temps ;
#   6. collecte les données, applique l'oracle et calcule le bilan.
#
# Usage :
#   ./scripts/sujet11-maj.sh [--mode observee|minimale] [--semantique at_least_once|at_most_once]
#                            [--debit N] [--duree S] [--charge NOM] [--borne S]
#                            [--reference S] [--drainage-max S] [--sortie DOSSIER]
#
# Code de sortie (mode minimale) : 0 si la continuité est respectée, 1 sinon,
# 2 en cas d'erreur d'utilisation ou de plateforme indisponible.
#
set -eu

# Se placer à la racine du dépôt, quel que soit le répertoire d'appel.
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

MODE="minimale"
SEMANTIQUE="at_least_once"
DEBIT="20"
DUREE="150"
CHARGE="normale"
BORNE="${SUJET11_BORNE_S:-}"
REFERENCE="30"
DRAINAGE_MAX="120"
SORTIE=""

usage() {
  sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'
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
    --reference) REFERENCE="$2"; shift 2 ;;
    --drainage-max) DRAINAGE_MAX="$2"; shift 2 ;;
    --sortie) SORTIE="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "[sujet11] option inconnue : $1" >&2; usage ;;
  esac
done

case "$MODE" in observee|minimale) ;; *) echo "[sujet11] mode invalide : $MODE" >&2; exit 2 ;; esac
case "$SEMANTIQUE" in at_least_once|at_most_once) ;; *) echo "[sujet11] sémantique invalide : $SEMANTIQUE" >&2; exit 2 ;; esac
if [ "$MODE" = "minimale" ] && [ -z "$BORNE" ]; then
  echo "[sujet11] mode minimale : la borne de pause doit être fixée (--borne S ou SUJET11_BORNE_S)" >&2
  exit 2
fi
[ -n "$BORNE" ] || BORNE="0"

maintenant() { python3 -c 'import time; print(f"{time.time():.3f}")'; }

if ! curl -fsS "http://127.0.0.1:8082/health" >/dev/null 2>&1; then
  echo "[sujet11] plateforme indisponible : lancez ./start.sh" >&2
  exit 2
fi

TOTAL=$((DEBIT * DUREE))
ID="$(date +%Y%m%d-%H%M%S)-${MODE}-${SEMANTIQUE}-${CHARGE}"
[ -n "$SORTIE" ] || SORTIE="runtime/sujet11/$ID"
mkdir -p "$SORTIE"
echo "[sujet11] essai $ID : $TOTAL Pix à $DEBIT Pix/s, sortie $SORTIE"

# La sémantique est lue par persister-valid au moment de sa création : elle doit
# être présente pour run-scenario.sh ET pour la reconstruction, sinon le service
# reconstruit repart avec la valeur par défaut (at_least_once).
export SIMULPIX_KAFKA_CONSUMER_SEMANTICS="$SEMANTIQUE"

echo "[sujet11] 1/6 audit des écritures"
./scripts/toggle-unique.sh off >/dev/null
./scripts/toggle-unique.sh reset >/dev/null

echo "[sujet11] 2/6 lancement du flux (run-scenario.sh nominal)"
./scripts/run-scenario.sh nominal "$TOTAL" "$DEBIT" >"$SORTIE/run-scenario.txt" 2>&1
DEBUT_FLUX="$(maintenant)"
GROUPE="$(sed -n 's/^SIMULPIX_PERSISTER_VALID_GROUP=//p' runtime/current-run.env)"

echo "[sujet11] 3/6 relevé du groupe $GROUPE"
rm -f "$SORTIE/stop"
python3 scripts/sujet11/mesure.py "$GROUPE" "$SORTIE/lag.jsonl" "$SORTIE/stop" &
PID_MESURE=$!
# Les événements Docker sont écoutés en direct : l'historique du démon est
# limité et le relevé (un exec par seconde dans kafka-1) le remplit vite.
docker events --filter container=persister-valid --format '{{.TimeNano}} {{.Action}}' \
  >"$SORTIE/evenements.txt" 2>/dev/null &
PID_EVENEMENTS=$!
trap 'touch "$SORTIE/stop"; kill "$PID_EVENEMENTS" 2>/dev/null || true' EXIT INT TERM

sleep "$REFERENCE"
DEBUT_REFERENCE="$(python3 -c "print(f'{$DEBUT_FLUX + $REFERENCE / 3:.3f}')")"

echo "[sujet11] 4/6 mise à jour de persister-valid (rebuild + remplacement du conteneur)"
T0="$(maintenant)"
docker compose up -d --build --force-recreate --no-deps persister-valid >"$SORTIE/rebuild.txt" 2>&1
FIN_REBUILD="$(maintenant)"

echo "[sujet11] 5/6 attente du drainage (limite ${DRAINAGE_MAX} s)"
DRAINAGE_TERMINE="false"
LIMITE="$(python3 -c "print($T0 + $DRAINAGE_MAX)")"
sleep 5
while python3 -c "import sys,time; sys.exit(0 if time.time() < $LIMITE else 1)"; do
  if python3 - "$SORTIE/lag.jsonl" "$T0" <<'EOF'
import json, sys
lignes = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
t0 = float(sys.argv[2])
apres = [x for x in lignes if x["t"] > t0]
# drainé : un membre a repris les partitions et le lag est revenu à 0
sys.exit(0 if apres and apres[-1]["membres"] > 0 and apres[-1]["lag"] == 0
         and any(x["membres"] == 0 or x["lag"] > 0 for x in apres) else 1)
EOF
  then
    DRAINAGE_TERMINE="true"
    break
  fi
  sleep 2
done
sleep 3
FIN="$(maintenant)"

# L'oracle compare le topic et la base : il faut attendre la fin du flux et
# son dernier drainage, sinon les paiements encore en route compteraient
# comme perdus. La fenêtre de la pause, elle, s'arrête à FIN.
echo "[sujet11]     attente de la fin du flux ($TOTAL Pix) puis du lag à 0"
LIMITE_FLUX="$(python3 -c "print($DEBUT_FLUX + $DUREE + $DRAINAGE_MAX)")"
while python3 -c "import sys,time; sys.exit(0 if time.time() < $LIMITE_FLUX else 1)"; do
  if curl -fsS "http://127.0.0.1:8082/health/details" 2>/dev/null | python3 -c "
import json, sys
c = json.load(sys.stdin)['metrics']['counts']
sys.exit(0 if c.get('generated', 0) >= $TOTAL and c.get('db_validated_count', 0) + c.get('db_rejected_count', 0) >= c.get('generated', 0) else 1)
" && [ "$(tail -1 "$SORTIE/lag.jsonl" | python3 -c 'import json,sys; print(json.load(sys.stdin)["lag"])')" = "0" ]; then
    break
  fi
  sleep 3
done
FIN_FLUX="$(maintenant)"
touch "$SORTIE/stop"
wait "$PID_MESURE" 2>/dev/null || true
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
  "drainage_max_s": $DRAINAGE_MAX,
  "groupe": "$GROUPE",
  "debut_flux": $DEBUT_FLUX,
  "debut_reference": $DEBUT_REFERENCE,
  "t0": $T0,
  "fin_rebuild": $FIN_REBUILD,
  "fin": $FIN,
  "fin_flux": $FIN_FLUX,
  "drainage_termine": $DRAINAGE_TERMINE
}
EOF

echo "[sujet11] 6/6 collecte, oracle et bilan"
python3 scripts/sujet11/collecte.py "$SORTIE"
python3 scripts/sujet11/oracle.py "$SORTIE" >/dev/null
CODE=0
python3 scripts/sujet11/bilan.py "$SORTIE" || CODE=$?
exit "$CODE"
