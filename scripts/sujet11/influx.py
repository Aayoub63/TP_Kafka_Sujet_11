"""Sujet 11 — écriture des mesures dans InfluxDB pour le tableau de bord Grafana.

Format « line protocol » d'InfluxDB 2, envoyé à /api/v2/write. Les valeurs
par défaut sont celles de docker-compose.yml (organisation, bucket et jeton
locaux de la plateforme). Depuis un conteneur, SUJET11_INFLUX_URL vaut
http://influxdb:8086.

L'observation ne doit jamais faire échouer un essai : en cas d'erreur, on
affiche un seul avertissement et on continue.

Usage en ligne de commande :
  python3 scripts/sujet11/influx.py repere <essai> <texte>   (repère affiché dans Grafana)
  python3 scripts/sujet11/influx.py etat <essai> <phase>     (phase de l'essai en cours)

Phases : lance, mise_a_jour, drainage, collecte, termine, interrompu. Le
tableau de bord s'en sert pour ne jamais présenter le résultat d'un ancien
essai comme celui de l'essai en cours.
"""
PHASES = ("lance", "mise_a_jour", "drainage", "collecte", "termine", "interrompu")
import os
import sys
import time
import urllib.request

URL = os.getenv("SUJET11_INFLUX_URL", "http://127.0.0.1:8086")
ORG = os.getenv("SUJET11_INFLUX_ORG", "simulpix")
BUCKET = os.getenv("SUJET11_INFLUX_BUCKET", "simulpix_observability")
JETON = os.getenv("SUJET11_INFLUX_TOKEN", "simulpix-observability-token")
_averti = False


def echapper_tag(valeur):
    return str(valeur).replace("\\", "\\\\").replace(",", "\\,").replace("=", "\\=").replace(" ", "\\ ")


def champ(valeur):
    """Valeur de champ : entier (suffixe i), réel, booléen ou texte entre guillemets."""
    if isinstance(valeur, bool):
        return "true" if valeur else "false"
    if isinstance(valeur, int):
        return f"{valeur}i"
    if isinstance(valeur, float):
        return repr(valeur)
    return '"' + str(valeur).replace("\\", "\\\\").replace('"', '\\"') + '"'


def ligne(mesure, tags, champs, t=None):
    tags_txt = "".join(f",{k}={echapper_tag(v)}" for k, v in tags.items() if v not in (None, ""))
    champs_txt = ",".join(f"{k}={champ(v)}" for k, v in champs.items() if v is not None)
    instant = int((t if t is not None else time.time()) * 1e9)
    return f"{mesure}{tags_txt} {champs_txt} {instant}"


def ecrire(lignes):
    global _averti
    corps = "\n".join(lignes).encode()
    requete = urllib.request.Request(
        f"{URL}/api/v2/write?org={ORG}&bucket={BUCKET}&precision=ns",
        data=corps, method="POST",
        headers={"Authorization": f"Token {JETON}", "Content-Type": "text/plain; charset=utf-8"},
    )
    try:
        urllib.request.urlopen(requete, timeout=2).close()
        return True
    except Exception as exc:  # observation seulement : on n'interrompt pas l'essai
        if not _averti:
            print(f"[sujet11] InfluxDB indisponible, le tableau de bord ne sera pas alimenté : {exc}",
                  file=sys.stderr)
            _averti = True
        return False


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "repere":
        ecrire([ligne("sujet11_repere", {"essai": sys.argv[2]}, {"texte": sys.argv[3]})])
        return 0
    if len(sys.argv) == 4 and sys.argv[1] == "etat" and sys.argv[3] in PHASES:
        ecrire([ligne("sujet11_etat", {}, {"essai": sys.argv[2], "phase": sys.argv[3]})])
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
