"""Sujet 11 : décalage entre l'horloge de la machine et celle de Docker.

L'audit est daté par PostgreSQL et les événements par le démon Docker, qui
tournent dans la machine virtuelle de Docker Desktop. Le relevé du groupe et
les instants du script sont datés par la machine. Après une mise en veille du
Mac, l'horloge de Docker peut prendre du retard (7 min mesurées le 9 novembre
2026) : les instants ne sont alors plus comparables.

Le décalage vaut : heure de PostgreSQL moins le milieu de l'aller-retour vu
par la machine. L'incertitude est la durée de cet aller-retour.

Usage : python3 scripts/sujet11/horloge.py   (affiche « décalage incertitude »)
"""
import os
import subprocess
import sys
import time

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def mesurer():
    avant = time.time()
    r = subprocess.run(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "simulpix", "-d", "simulpix",
                        "-tA", "-c", "select extract(epoch from clock_timestamp())"],
                       cwd=RACINE, capture_output=True, text=True, check=True)
    apres = time.time()
    return round(float(r.stdout.strip()) - (avant + apres) / 2, 3), round(apres - avant, 3)


# Au-delà, l'horloge de Docker a bougé pendant l'essai : la mesure est invalide.
DERIVE_MAX_S = 0.5


def derive(meta):
    """Écart entre le décalage du début et celui de la fin, ou None sans mesure."""
    if meta.get("decalage_debut_s") is None or meta.get("decalage_fin_s") is None:
        return None
    return round(abs(meta["decalage_fin_s"] - meta["decalage_debut_s"]), 3)


def decalage(meta):
    """Correction à retrancher aux heures de Docker : moyenne du début et de la fin
    de l'essai, ou 0 pour un essai sans mesure."""
    valeurs = [meta[k] for k in ("decalage_debut_s", "decalage_fin_s") if meta.get(k) is not None]
    return sum(valeurs) / len(valeurs) if valeurs else 0.0


if __name__ == "__main__":
    d, incertitude = mesurer()
    print(d, incertitude)
    sys.exit(0)
