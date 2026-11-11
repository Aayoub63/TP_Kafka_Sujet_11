"""Sujet 11 — relevé du groupe de consommateurs de persister-valid.

Toutes les secondes, interroge Kafka (kafka-consumer-groups.sh --describe) et
écrit une ligne JSON : heure, lag total, nombre de membres, partitions lues,
et pour chaque partition son propriétaire et son offset validé.
Ces lignes donnent le retard maximal et la chronologie du rebalance
(groupe vide, puis membre qui reçoit les partitions).

Chaque relevé est aussi écrit dans InfluxDB (mesure sujet11_groupe), pour
suivre persister-valid à la seconde dans Grafana.

Usage : python3 scripts/sujet11/mesure.py <groupe> <fichier.jsonl> <fichier-stop>
Le relevé s'arrête quand <fichier-stop> existe (créé par sujet11-maj.sh).
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import influx  # noqa: E402

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def releve(groupe):
    """Un relevé du groupe. Une ligne de données a 9 colonnes :
    GROUP TOPIC PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG CONSUMER-ID HOST CLIENT-ID.
    """
    r = subprocess.run(
        ["docker", "compose", "exec", "-T", "kafka-1", "/opt/kafka/bin/kafka-consumer-groups.sh",
         "--bootstrap-server", "kafka-1:29092", "--command-config", "/config/client.properties",
         "--describe", "--group", groupe],
        cwd=RACINE, capture_output=True, text=True, check=False,
    )
    return lire_describe(r.stdout, groupe) | {"ok": r.returncode == 0}


def lire_describe(sortie, groupe):
    """Analyse la sortie de --describe. CURRENT-OFFSET vaut « - » avant le
    premier commit et CONSUMER-ID vaut « - » si personne ne lit la partition."""
    lag, membres, lignes, parts = 0, set(), 0, {}
    for ligne in sortie.splitlines():
        p = ligne.split()
        if len(p) >= 7 and p[0] == groupe:
            lignes += 1
            if p[5].isdigit():
                lag += int(p[5])
            if p[6] != "-":
                membres.add(p[6])
            # propriétaire et offset validé de chaque partition : on saura quelles
            # partitions changent de main, et à quel offset la relève reprend
            parts[p[2]] = [p[6], int(p[3]) if p[3].isdigit() else None]
    return {"lag": lag, "membres": len(membres), "partitions": lignes, "parts": parts}


def main():
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    groupe, sortie, stop = sys.argv[1:]
    with open(sortie, "a") as f:
        while not os.path.exists(stop):
            debut = time.time()
            r = releve(groupe)
            # La commande démarre une JVM (environ 1 s) avant d'interroger Kafka :
            # l'état lu est celui de la fin de la commande, pas de son début.
            fin = time.time()
            ligne = {"t": round(fin, 3)} | r
            f.write(json.dumps(ligne) + "\n")
            f.flush()
            influx.ecrire([influx.ligne(
                "sujet11_groupe", {"groupe": groupe},
                {"lag": ligne["lag"], "membres": ligne["membres"], "partitions": ligne["partitions"]},
                t=fin)])
            time.sleep(max(0.0, 1.0 - (time.time() - debut)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
