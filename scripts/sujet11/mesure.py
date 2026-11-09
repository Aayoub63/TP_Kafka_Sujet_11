"""Sujet 11 — relevé du groupe de consommateurs de persister-valid.

Toutes les secondes, interroge Kafka (kafka-consumer-groups.sh --describe) et
écrit une ligne JSON : heure, lag total, nombre de membres, partitions lues.
Ces lignes donnent le retard maximal et la chronologie du rebalance
(groupe vide, puis membre qui reçoit les partitions).

Usage : python3 scripts/sujet11/mesure.py <groupe> <fichier.jsonl> <fichier-stop>
Le relevé s'arrête quand <fichier-stop> existe (créé par sujet11-maj.sh).
"""
import json
import os
import subprocess
import sys
import time

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
    lag, membres, lignes = 0, set(), 0
    for ligne in r.stdout.splitlines():
        p = ligne.split()
        if len(p) >= 7 and p[0] == groupe:
            lignes += 1
            if p[5].isdigit():
                lag += int(p[5])
            if p[6] != "-":
                membres.add(p[6])
    return {"lag": lag, "membres": len(membres), "partitions": lignes, "ok": r.returncode == 0}


def main():
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    groupe, sortie, stop = sys.argv[1:]
    with open(sortie, "a") as f:
        while not os.path.exists(stop):
            debut = time.time()
            ligne = {"t": round(debut, 3)} | releve(groupe)
            f.write(json.dumps(ligne) + "\n")
            f.flush()
            time.sleep(max(0.0, 1.0 - (time.time() - debut)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
