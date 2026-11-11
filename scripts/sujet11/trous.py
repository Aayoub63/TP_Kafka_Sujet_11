"""Sujet 11, contrôle des trous de transaction_id en base.

Un essai envoie total paiements, numérotés tx-00000001 à tx-<total sur 8 chiffres>.
Chaque paiement finit dans validated_transactions ou rejected_transactions.
Un trou est un numéro entre 1 et total absent des deux tables à la fois.
"""
import re

MOTIF = re.compile(r"^tx-(\d{8})$")


def numero(transaction_id):
    """Numéro d'un identifiant tx-00000042, sinon None."""
    m = MOTIF.match(str(transaction_id))
    return int(m.group(1)) if m else None


def chercher(valides, rejetes, total):
    """Recense les numéros 1..total présents dans les deux tables, et les trous."""
    attendus = int(total)
    en_base = set()
    hors_plage = []
    for d in list(valides) + list(rejetes):
        n = numero(d.get("transaction_id"))
        if n is None or not 1 <= n <= attendus:
            hors_plage.append(d.get("transaction_id"))
        else:
            en_base.add(n)
    manquants = [n for n in range(1, attendus + 1) if n not in en_base]
    return {"attendus": attendus, "en_base": len(en_base), "trous": len(manquants),
            "exemples": ["tx-%08d" % n for n in manquants[:10]], "hors_plage": hors_plage}
