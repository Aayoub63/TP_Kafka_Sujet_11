"""Sujet 11 — oracle de continuité métier.

Compare les identités attendues (topic validated) avec la base, à partir des
fichiers écrits par collecte.py. Chaque identité attendue est classée :

  present          : une ligne dans validated_transactions, valeurs identiques ;
  valeur_fausse    : une ligne, mais une valeur comparée diffère du message ;
  rejet_delai      : absente des validés, rejetée pour délai dépassé (TTL) ;
  rejet_metier     : absente des validés, rejetée pour une autre raison ;
  perdu            : absente partout. C'est la seule vraie perte.

Valeurs comparées : montant, devise, compte émetteur et compte bénéficiaire
(CHAMPS). Les anciens essais n'ont que le montant : on compare alors les
champs présents des deux côtés, et le résultat le dit (champs_compares).

L'oracle compte aussi, et chacun de ces cas fait échouer l'essai :
  - les lignes en base sans message dans le topic (lignes inattendues) ;
  - les doubles effets : plusieurs lignes en base pour une même identité ;
  - les incohérents : une identité à la fois validée et rejetée en base ;
  - les conflits du topic : une même identité publiée avec des valeurs
    différentes (on ne saurait pas laquelle attendre).
Il compte enfin les doublons absorbés : tentatives d'écriture en plus d'une
par identité (table d'audit). Ils ne créent pas de second effet grâce à
l'upsert : ce sont des relectures, pas des erreurs.

Usage : python3 scripts/sujet11/oracle.py <dossier-essai>
Écrit <dossier>/oracle.json.
"""
import json
import os
import sys
from collections import Counter
from decimal import Decimal

REJETS_DELAI = {"processing_timeout", "TECHNICAL_TIMEOUT"}
# Valeurs métier comparées entre le message et la ligne en base.
CHAMPS = ("amount", "currency", "emitter_account_id", "beneficiary_account_id")


def charger(dossier, nom):
    with open(os.path.join(dossier, "donnees", f"{nom}.json")) as f:
        return json.load(f)


def montant(valeur):
    """Normalise un montant (float JSON ou texte numeric PostgreSQL) à 2 décimales."""
    if valeur is None:
        return None
    return Decimal(str(valeur)).quantize(Decimal("0.01"))


def valeurs(ligne):
    """Valeurs comparables d'un message ou d'une ligne : seulement les champs présents."""
    v = {}
    for champ in CHAMPS:
        if champ in ligne and ligne[champ] is not None:
            v[champ] = montant(ligne[champ]) if champ == "amount" else str(ligne[champ])
    return v


def classer(topic, valides, rejetes):
    attendus, conflits = {}, set()
    for m in topic:
        tid, v = m["transaction_id"], valeurs(m)
        if tid in attendus and attendus[tid] != v:
            conflits.add(tid)
        attendus.setdefault(tid, v)
    lignes_par_id = {}
    for ligne in valides:
        lignes_par_id.setdefault(ligne["transaction_id"], []).append(valeurs(ligne))
    # une identité a au plus une ligne (clé primaire) : sinon, c'est un double effet
    doubles = {tid: len(l) - 1 for tid, l in lignes_par_id.items() if len(l) > 1}
    rejets_par_id = {}
    for r in rejetes:
        rejets_par_id.setdefault(r["transaction_id"], []).append(r)
    incoherents = sorted(set(lignes_par_id) & set(rejets_par_id))

    classes = Counter()
    exemples = {}
    champs_compares, champs_faux = set(), Counter()
    for tid, attendu in attendus.items():
        if tid in lignes_par_id:
            en_base = lignes_par_id[tid][0]
            communs = set(attendu) & set(en_base)
            champs_compares |= communs
            faux = sorted(c for c in communs if attendu[c] != en_base[c])
            champs_faux.update(faux)
            classe = "valeur_fausse" if faux or not communs else "present"
        elif tid in rejets_par_id:
            motifs = {r["rejection_reason"] for r in rejets_par_id[tid]} | \
                     {r["rejection_type"] for r in rejets_par_id[tid]}
            classe = "rejet_delai" if motifs & REJETS_DELAI else "rejet_metier"
        else:
            classe = "perdu"
        classes[classe] += 1
        if classe != "present":
            exemples.setdefault(classe, []).append(tid)

    inattendues = sorted(set(lignes_par_id) - set(attendus))
    autres = {"lignes_inattendues": inattendues, "doubles_effets": sorted(doubles),
              "incoherents": incoherents, "conflits_topic": sorted(conflits)}
    return {
        "attendus": len(attendus),
        "messages_topic": len(topic),
        "classes": {c: classes.get(c, 0) for c in
                    ("present", "valeur_fausse", "rejet_delai", "rejet_metier", "perdu")},
        "lignes_inattendues": len(inattendues),
        "doubles_effets": sum(doubles.values()),
        "incoherents": len(incoherents),
        "conflits_topic": len(conflits),
        "champs_compares": sorted(champs_compares),
        "champs_faux": dict(champs_faux),
        "exemples": {c: ids[:10] for c, ids in exemples.items()} |
                    {k: v[:10] for k, v in autres.items() if v},
    }


def livraisons(audit):
    """Lignes d'audit qui correspondent à une livraison du message.

    Une relecture déclenche deux lignes : INSERT (la tentative), puis UPDATE
    (l'upsert trouve la ligne existante). On ne garde que les INSERT. Les
    anciens essais n'ont pas le type : toutes les lignes comptent.
    """
    return [a for a in audit if a.get("kind", "INSERT") != "UPDATE"]


def doublons_absorbes(audit, valides):
    """Livraisons en trop, par rapport à une livraison par identité."""
    tentatives = Counter(a["transaction_id"] for a in livraisons(audit))
    en_trop = {tid: n - 1 for tid, n in tentatives.items() if n > 1}
    return {
        "audit_actif": bool(audit),
        "tentatives": len(livraisons(audit)),
        "identites_ecrites": len(tentatives),
        "lignes_en_base": len(valides),
        "doublons_absorbes": sum(en_trop.values()),
        "exemples": sorted(en_trop, key=lambda t: -en_trop[t])[:10],
    }


def rejets_du_flux(rejetes):
    """Rejets sur tout le flux, y compris ceux faits avant le topic validated.

    Un paiement rejeté pour délai par pix-decision-engine n'arrive jamais dans
    validated : l'oracle de persister-valid ne le voit pas. On le compte à part
    pour distinguer un effet de la surcharge d'un effet de la mise à jour.
    """
    delai = sum(1 for r in rejetes
                if {r["rejection_reason"], r["rejection_type"]} & REJETS_DELAI)
    return {"rejets_total": len(rejetes), "rejets_delai": delai}


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
                "doublons": doublons_absorbes(audit, valides),
                "flux": rejets_du_flux(rejetes)}
    with open(os.path.join(dossier, "oracle.json"), "w") as f:
        json.dump(resultat, f, indent=2, ensure_ascii=False)

    c, d = resultat["continuite"], resultat["doublons"]
    print(f"[sujet11] oracle : attendus={c['attendus']} " +
          " ".join(f"{k}={v}" for k, v in c["classes"].items()) +
          f" inattendues={c['lignes_inattendues']} doubles_effets={c['doubles_effets']}"
          f" incoherents={c['incoherents']} conflits_topic={c['conflits_topic']}"
          f" doublons_absorbes={d['doublons_absorbes']}"
          f" rejets_delai_flux={resultat['flux']['rejets_delai']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
