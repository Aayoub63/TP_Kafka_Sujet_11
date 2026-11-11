#!/bin/sh
#
# sujet11-campagne.sh — enchaîner les essais d'une solution (minimale ou améliorée)
# ou de la panne (crash).
#
# Pour chaque répétition, chaque sémantique et chaque charge, lance
# scripts/sujet11-maj.sh dans le mode choisi, puis écrit le résumé dans
# preuves/sujet11/campagne-<date>/ (scripts/sujet11/resume.py).
#
# Usage : ./scripts/sujet11-campagne.sh [repetitions] [borne_s] [mode]
#   repetitions : 3 par défaut ; borne_s : 60 par défaut (décision du groupe) ;
#   mode : minimale (défaut), amelioree ou crash.
# En mode crash, une seule charge « ralentie » : 10 Pix/s, 80 ms entre commit et
# écriture, 180 s de drainage (voir docs/sujet11/protocole-essai.md).
# Réglages : SUJET11_DEBIT_NORMAL (20), SUJET11_DEBIT_FORT (60), SUJET11_DUREE (150),
# SUJET11_SEMANTIQUES ("at_least_once at_most_once"), SUJET11_CHARGES ("normale forte",
# hors mode crash).
#
# Un essai en échec ne stoppe pas la campagne : l'échec est un résultat.
#
set -eu

cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

REPETITIONS="${1:-3}"
BORNE="${2:-60}"
MODE="${3:-minimale}"
case "$MODE" in minimale|amelioree|crash) ;; *) echo "[sujet11] mode invalide : $MODE" >&2; exit 2 ;; esac
DEBIT_NORMAL="${SUJET11_DEBIT_NORMAL:-20}"
DEBIT_FORT="${SUJET11_DEBIT_FORT:-60}"
DUREE="${SUJET11_DUREE:-150}"
# exactly_once_pg : offsets rangés dans PostgreSQL (persister-valid), à ajouter ici.
SEMANTIQUES="${SUJET11_SEMANTIQUES:-at_least_once at_most_once}"
CAMPAGNE="campagne-${MODE}-$(date +%Y%m%d-%H%M%S)"
PREUVES="preuves/sujet11/$CAMPAGNE"
BRUT="runtime/sujet11/$CAMPAGNE"
mkdir -p "$BRUT"
ESSAIS=""

echo "[sujet11] $CAMPAGNE : mode $MODE, $REPETITIONS répétition(s), borne $BORNE s, débits $DEBIT_NORMAL et $DEBIT_FORT Pix/s"
i=1
while [ "$i" -le "$REPETITIONS" ]; do
  for SEMANTIQUE in $SEMANTIQUES; do
    if [ "$MODE" = "crash" ]; then CHARGES="ralentie"; else CHARGES="${SUJET11_CHARGES:-normale forte}"; fi
    for CHARGE in $CHARGES; do
      OPTIONS=""
      case "$CHARGE" in
        normale) DEBIT="$DEBIT_NORMAL" ;;
        forte) DEBIT="$DEBIT_FORT" ;;
        ralentie) DEBIT="10"; OPTIONS="--ralenti 80 --drainage-max 180" ;;
      esac
      SORTIE="$BRUT/r${i}-${SEMANTIQUE}-${CHARGE}"
      echo "[sujet11] --- répétition $i : $SEMANTIQUE, charge $CHARGE ($DEBIT Pix/s)"
      CODE=0
      ./scripts/sujet11-maj.sh --mode "$MODE" --semantique "$SEMANTIQUE" --charge "$CHARGE" \
        --debit "$DEBIT" --duree "$DUREE" --borne "$BORNE" --sortie "$SORTIE" $OPTIONS \
        >"$SORTIE.log" 2>&1 || CODE=$?
      grep "VERDICT" "$SORTIE.log" || echo "[sujet11] pas de verdict (code $CODE), voir $SORTIE.log"
      ESSAIS="$ESSAIS $SORTIE"
    done
  done
  i=$((i + 1))
done

# shellcheck disable=SC2086
python3 scripts/sujet11/resume.py "$PREUVES" $ESSAIS
echo "[sujet11] résumé écrit dans $PREUVES"
