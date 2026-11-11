"""Sujet 11 — pause de traitement mesurée dans PostgreSQL.

Définition retenue : la pause est le plus long intervalle sans nouvelle
écriture dans validated_transactions qui touche la fenêtre de l'opération
[t0, fin]. Les heures viennent de la table d'audit (une ligne par tentative
d'écriture, heure posée par PostgreSQL avec clock_timestamp() depuis le
9 novembre ; avec now() avant, voir preuves/sujet11/NOTE-heure-audit.md).

On mesure aussi le « trou normal » avant l'opération (référence), pour
savoir ce que la mise à jour ajoute vraiment. C'est aussi la résolution de
la mesure : le générateur émet par paquets, donc une pause plus courte que
ce trou est invisible (voir bilan.pause_distincte).
"""


def plus_long_trou(instants, debut, fin):
    """Plus long intervalle entre deux écritures consécutives qui chevauche [debut, fin].

    Renvoie (duree, derniere_ecriture_avant, premiere_ecriture_apres) ou None.
    Si plus rien n'est écrit après la dernière écriture, le trou reste ouvert
    jusqu'à `fin` et premiere_ecriture_apres vaut None : le service n'a pas repris.
    """
    meilleur = None
    for avant, apres in zip(instants, instants[1:]):
        if apres < debut or avant > fin:
            continue
        duree = apres - avant
        if meilleur is None or duree > meilleur[0]:
            meilleur = (duree, avant, apres)
    if instants and instants[-1] < fin:
        ouvert = (fin - max(instants[-1], debut), instants[-1], None)
        if meilleur is None or ouvert[0] > meilleur[0]:
            meilleur = ouvert
    return meilleur


def mesurer(audit, t0, fin, debut_reference):
    """Calcule la pause pendant l'opération et le trou normal avant t0.

    audit : liste de {"t": epoch} ; t0 : début de la mise à jour ;
    fin : fin de l'observation ; debut_reference : début de la fenêtre de
    référence (après la montée en charge).
    """
    instants = sorted(a["t"] for a in audit)
    avant_t0 = [t for t in instants if debut_reference <= t <= t0]
    reference = None
    if len(avant_t0) >= 2:
        reference = max(b - a for a, b in zip(avant_t0, avant_t0[1:]))
    operation = plus_long_trou([t for t in instants if t <= fin], t0, fin)
    resultat = {
        "ecritures": len(instants),
        "trou_normal_s": round(reference, 3) if reference is not None else None,
        "pause_s": None,
        "reprise": None,
        "derniere_ecriture_avant_s": None,
        "premiere_ecriture_apres_s": None,
    }
    if operation:
        duree, avant, apres = operation
        resultat.update({
            "pause_s": round(duree, 3),
            "reprise": apres is not None,
            # instants relatifs à t0, plus lisibles dans la chronologie
            "derniere_ecriture_avant_s": round(avant - t0, 3),
            "premiere_ecriture_apres_s": round(apres - t0, 3) if apres is not None else None,
        })
    return resultat
