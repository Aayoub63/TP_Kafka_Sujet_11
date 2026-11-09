#!/bin/sh
#
# sujet11-campagne.sh — enchaîner les essais de la solution minimale.
#
# Pour chaque répétition, chaque sémantique et chaque charge, lance
# scripts/sujet11-maj.sh en mode minimale, puis écrit le résumé dans
# preuves/sujet11/campagne-<date>/ (scripts/sujet11/resume.py).
#
# Usage : ./scripts/sujet11-campagne.sh [repetitions] [borne_s]
#   repetitions : 3 par défaut ; borne_s : 60 par défaut (décision du groupe).
# Réglages : SUJET11_DEBIT_NORMAL (20), SUJET11_DEBIT_FORT (60), SUJET11_DUREE (150).
#
# Un essai en échec ne stoppe pas la campagne : l'échec est un résultat.
#
set -eu

cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

REPETITIONS="${1:-3}"
BORNE="${2:-60}"
DEBIT_NORMAL="${SUJET11_DEBIT_NORMAL:-20}"
DEBIT_FORT="${SUJET11_DEBIT_FORT:-60}"
DUREE="${SUJET11_DUREE:-150}"
CAMPAGNE="campagne-$(date +%Y%m%d-%H%M%S)"
PREUVES="preuves/sujet11/$CAMPAGNE"
BRUT="runtime/sujet11/$CAMPAGNE"
mkdir -p "$BRUT"
ESSAIS=""

echo "[sujet11] $CAMPAGNE : $REPETITIONS répétition(s), borne $BORNE s, débits $DEBIT_NORMAL et $DEBIT_FORT Pix/s"
i=1
while [ "$i" -le "$REPETITIONS" ]; do
  for SEMANTIQUE in at_least_once at_most_once; do
    for CHARGE in normale forte; do
      if [ "$CHARGE" = "normale" ]; then DEBIT="$DEBIT_NORMAL"; else DEBIT="$DEBIT_FORT"; fi
      SORTIE="$BRUT/r${i}-${SEMANTIQUE}-${CHARGE}"
      echo "[sujet11] --- répétition $i : $SEMANTIQUE, charge $CHARGE ($DEBIT Pix/s)"
      CODE=0
      ./scripts/sujet11-maj.sh --mode minimale --semantique "$SEMANTIQUE" --charge "$CHARGE" \
        --debit "$DEBIT" --duree "$DUREE" --borne "$BORNE" --sortie "$SORTIE" \
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
