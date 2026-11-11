"""Proportions et intervalles de confiance pour la campagne d'essais.

Le nombre d'essais est limité : on raisonne en proportions avec une marge
d'incertitude (intervalle de Wilson), pas en valeurs absolues.
"""
import math


def wilson(k, n, z=1.96):
    """Intervalle de Wilson à 95 % pour la proportion k/n.

    Renvoie (bas, haut) borné à [0, 1], ou None si n vaut 0.
    """
    if n == 0:
        return None
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    demi = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return (max(0.0, centre - demi), min(1.0, centre + demi))


def synthese(lignes):
    """Résume une liste de lignes d'une même combinaison en proportions."""
    n = len(lignes)
    avec_perte = sum(1 for l in lignes if l["perdus"] > 0)
    sous_cible = sum(1 for l in lignes if l["sous_cible_metier"])
    paiements = sum(l["attendus"] for l in lignes)
    perdus = sum(l["perdus"] for l in lignes)
    doublons = sum(l["doublons_absorbes"] for l in lignes)
    return {
        "essais": n,
        "essais_avec_perte": avec_perte,
        "part_essais_avec_perte": avec_perte / n if n else None,
        "ic_essais_avec_perte": wilson(avec_perte, n),
        "paiements": paiements,
        "perdus": perdus,
        "taux_perte": perdus / paiements if paiements else None,
        "ic_taux_perte": wilson(perdus, paiements),
        "taux_doublons": doublons / paiements if paiements else None,
        "essais_sous_cible": sous_cible,
        "part_sous_cible": sous_cible / n if n else None,
        "ic_sous_cible": wilson(sous_cible, n),
    }


def pourcent(x):
    """Formate une proportion en pourcentage français, ou un tiret si None."""
    if x is None:
        return "-"
    # une borne de Wilson à k = 0 vaut 0 aux arrondis de calcul près
    if abs(x) < 1e-9:
        return "0 %"
    dec = 4 if abs(x) < 0.0001 else 2
    return f"{x * 100:.{dec}f}".replace(".", ",") + " %"
