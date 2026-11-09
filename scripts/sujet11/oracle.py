"""Sujet 11 — oracle de continuité métier.

Compare les identités attendues (topic validated) avec la base, à partir des
fichiers écrits par collecte.py. Chaque identité attendue est classée :

  present          : une ligne dans validated_transactions, montant identique ;
  valeur_fausse    : une ligne, mais montant différent du message ;
  rejet_delai      : absente des validés, rejetée pour délai dépassé (TTL) ;
  rejet_metier     : absente des validés, rejetée pour une autre raison ;
  perdu            : absente partout. C'est la seule vraie perte.

L'oracle compte aussi :
  - les lignes en base sans message dans le topic (lignes inattendues) ;
  - les doublons absorbés : tentatives d'écriture en plus d'une par identité
    (table d'audit). Ils ne créent pas de second effet grâce à l'upsert.

Usage : python3 scripts/sujet11/oracle.py <dossier-essai>
Écrit <dossier>/oracle.json.
"""
import json
import os
import sys
from collections import Counter
from decimal import Decimal

REJETS_DELAI = {"processing_timeout", "TECHNICAL_TIMEOUT"}


def charger(dossier, nom):
    with open(os.path.join(dossier, "donnees", f"{nom}.json")) as f:
        return json.load(f)


def montant(valeur):
    """Normalise un montant (float JSON ou texte numeric PostgreSQL) à 2 décimales."""
    if valeur is None:
        return None
    return Decimal(str(valeur)).quantize(Decimal("0.01"))


def classer(topic, valides, rejetes):
    attendus = {}
    for m in topic:
        attendus.setdefault(m["transaction_id"], montant(m["amount"]))
    en_base = {v["transaction_id"]: montant(v["amount"]) for v in valides}
    rejets_par_id = {}
    for r in rejetes:
        rejets_par_id.setdefault(r["transaction_id"], []).append(r)

    classes = Counter()
    exemples = {}
    for tid, attendu in attendus.items():
        if tid in en_base:
            classe = "present" if en_base[tid] == attendu else "valeur_fausse"
        elif tid in rejets_par_id:
            motifs = {r["rejection_reason"] for r in rejets_par_id[tid]} | \
                     {r["rejection_type"] for r in rejets_par_id[tid]}
            classe = "rejet_delai" if motifs & REJETS_DELAI else "rejet_metier"
        else:
            classe = "perdu"
        classes[classe] += 1
        if classe != "present":
            exemples.setdefault(classe, []).append(tid)

    inattendues = sorted(set(en_base) - set(attendus))
    return {
        "attendus": len(attendus),
        "messages_topic": len(topic),
        "classes": {c: classes.get(c, 0) for c in
                    ("present", "valeur_fausse", "rejet_delai", "rejet_metier", "perdu")},
        "lignes_inattendues": len(inattendues),
        "exemples": {c: ids[:10] for c, ids in exemples.items()} |
                    ({"lignes_inattendues": inattendues[:10]} if inattendues else {}),
    }


def doublons_absorbes(audit, valides):
    """Tentatives d'écriture en trop, par rapport à une tentative par identité."""
    tentatives = Counter(a["transaction_id"] for a in audit)
    en_trop = {tid: n - 1 for tid, n in tentatives.items() if n > 1}
    return {
        "audit_actif": bool(audit),
        "tentatives": len(audit),
        "identites_ecrites": len(tentatives),
        "lignes_en_base": len(valides),
        "doublons_absorbes": sum(en_trop.values()),
        "exemples": sorted(en_trop, key=lambda t: -en_trop[t])[:10],
    }


def main():
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    dossier = sys.argv[1]
    topic = charger(dossier, "topic_validated")
    valides = charger(dossier, "db_validated")
    rejetes = charger(dossier, "db_rejected")
    audit = charger(dossier, "audit")

    resultat = {"continuite": classer(topic, valides, rejetes),
                "doublons": doublons_absorbes(audit, valides)}
    with open(os.path.join(dossier, "oracle.json"), "w") as f:
        json.dump(resultat, f, indent=2, ensure_ascii=False)

    c, d = resultat["continuite"], resultat["doublons"]
    print(f"[sujet11] oracle : attendus={c['attendus']} " +
          " ".join(f"{k}={v}" for k, v in c["classes"].items()) +
          f" inattendues={c['lignes_inattendues']} doublons_absorbes={d['doublons_absorbes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
