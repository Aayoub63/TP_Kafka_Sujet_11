"""Sujet 11 : quelles partitions changent de main, et quel message était en cours.

Entrées :
  - lag.jsonl : un relevé par seconde, avec pour chaque partition son
    propriétaire (CONSUMER-ID) et son offset validé (mesure.py) ;
  - donnees/topic_validated.json : chaque message avec sa partition et son
    offset (collecte.py) ;
  - donnees/audit.json : chaque tentative d'écriture en base, avec son heure.

Pour chaque passation (une partition passe d'une instance à une autre), on
donne l'offset où la nouvelle instance reprend, le paiement qui s'y trouve,
et on vérifie dans l'audit :
  - s'il était déjà écrit avant la passation : il sera relu, la base absorbe
    le doublon (cas at-least-once : écriture faite, commit pas encore fait) ;
  - si le paiement juste avant a bien été écrit : sinon il est perdu (cas
    at-most-once : commit fait, écriture pas faite).

Limite : le relevé a lieu environ une fois par seconde. L'offset de reprise
est celui du dernier relevé avant la passation. Il est sûr s'il a été lu
pendant que la partition n'avait plus de propriétaire : l'ancienne instance
ne pouvait plus le changer. Sinon (passation directe, sans trou), elle a pu
valider un offset de plus entre ce relevé et la passation.

Kafka n'affiche pas une partition sans propriétaire ni offset validé : une
partition absente d'un relevé compte comme « sans propriétaire ».
"""


def nommer_instances(lag):
    """CONSUMER-ID -> « instance 1 », « instance 2 »… dans l'ordre d'apparition."""
    noms = {}
    for releve in sorted(lag, key=lambda x: x["t"]):
        for partition in sorted(releve.get("parts", {}), key=int):
            proprietaire = releve["parts"][partition][0]
            if proprietaire != "-" and proprietaire not in noms:
                noms[proprietaire] = f"instance {len(noms) + 1}"
    return noms


def passations(lag, t0):
    """Changements de propriétaire après t0, partition par partition."""
    resultat = []
    releves = sorted(lag, key=lambda x: x["t"])
    partitions = sorted({p for r in releves for p in r.get("parts", {})}, key=int)
    for partition in partitions:
        # un relevé vide (commande en échec) ne dit rien : on l'ignore
        suite = [(r["t"], *r["parts"].get(partition, ["-", None])) for r in releves if r.get("parts")]
        dernier, offset_avant, sans_depuis, sur = None, None, None, False
        for t, proprietaire, offset in suite:
            if proprietaire == "-":
                if dernier is not None and sans_depuis is None:
                    sans_depuis = t
                sur = dernier is not None
                offset_avant = offset if offset is not None else offset_avant
                continue
            if dernier is not None and proprietaire != dernier and t >= t0:
                resultat.append({
                    "t": t, "partition": int(partition), "avant": dernier, "apres": proprietaire,
                    "sans_proprietaire_s": round(t - sans_depuis, 3) if sans_depuis else 0.0,
                    "offset_reprise": offset_avant, "sur": sur, "t_sans": sans_depuis,
                })
            dernier, sans_depuis, sur = proprietaire, None, False
            offset_avant = offset if offset is not None else offset_avant
    return sorted(resultat, key=lambda x: (x["t"], x["partition"]))


def analyser(lag, topic, audit, t0):
    """Passations avec le message repris et ce que l'audit en dit."""
    noms = nommer_instances(lag)
    position = {(m["partition"], m["offset"]): m["transaction_id"]
                for m in topic if m.get("partition") is not None}
    ecrit_a = {}
    for a in audit:
        if a.get("kind") == "UPDATE":  # suite d'une relecture, déjà comptée par son INSERT
            continue
        ecrit_a.setdefault(a["transaction_id"], []).append(a["t"])
    liste = []
    for p in passations(lag, t0):
        # « écrit avant » : avant que la partition perde son propriétaire. Le relevé
        # qui voit la nouvelle instance arrive jusqu'à une seconde après ses
        # premières écritures : le prendre comme limite les comptait comme
        # écritures de l'ancienne instance.
        limite = p["t_sans"] if p["t_sans"] is not None else p["t"]
        # le relevé après la passation peut déjà contenir les offsets de la
        # nouvelle instance : on garde celui d'avant
        offset = p["offset_reprise"]
        repris = position.get((p["partition"], offset)) if offset is not None else None
        precedent = position.get((p["partition"], offset - 1)) if offset else None
        liste.append({
            "t_s": round(p["t"] - t0, 3),
            "partition": p["partition"],
            "avant": noms.get(p["avant"], p["avant"]),
            "apres": noms.get(p["apres"], p["apres"]),
            "sans_proprietaire_s": p["sans_proprietaire_s"],
            "offset_reprise": offset,
            "offset_sur": p["sur"],
            "message_repris": repris,
            "deja_ecrit_avant": bool(repris) and any(t < limite for t in ecrit_a.get(repris, [])),
            "ecritures_du_message_repris": len(ecrit_a.get(repris, [])),
            "message_precedent": precedent,
            "precedent_ecrit": None if precedent is None else precedent in ecrit_a,
        })
    return {"instances": {v: k for k, v in noms.items()}, "passations": liste}


def resume(analyse, semantique=None):
    """Lignes de texte pour bilan.txt. En exactly_once_pg, un message déjà écrit et
    relu est écarté sans réécriture : une seule écriture est alors normale."""
    lignes = []
    for p in analyse["passations"]:
        if p["offset_reprise"] is None:
            message = "aucun offset validé (partition sans message)"
        elif p["message_repris"] is None:
            message = "aucun message à cet offset (rien en attente)"
        elif p["deja_ecrit_avant"] and p["ecritures_du_message_repris"] >= 2:
            message = (f"{p['message_repris']} déjà écrit avant, relu"
                       f" ({p['ecritures_du_message_repris']} écritures, doublon absorbé)")
        elif p["deja_ecrit_avant"] and semantique == "exactly_once_pg":
            message = (f"{p['message_repris']} déjà écrit avant, relu et écarté sans réécriture"
                       " (offset rangé dans PostgreSQL)")
        elif p["deja_ecrit_avant"]:
            message = f"{p['message_repris']} déjà écrit avant et pas relu (offset relevé en retard)"
        else:
            message = f"{p['message_repris']} pas encore écrit, lu par la nouvelle instance"
        if p["precedent_ecrit"] is False:
            message += f" ; ATTENTION {p['message_precedent']} jamais écrit"
        lignes.append(f"   {p['t_s']} s partition {p['partition']} : {p['avant']} -> {p['apres']}"
                      f" (sans propriétaire {p['sans_proprietaire_s']} s), reprise à l'offset"
                      f" {p['offset_reprise']}{'' if p['offset_sur'] else ' (à une seconde près)'} : {message}")
    return lignes or ["   aucune passation relevée"]
