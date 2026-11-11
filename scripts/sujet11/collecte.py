"""Sujet 11 — collecte des données utilisées par l'oracle de continuité.

Le script lit, à la fin d'un essai :
  - les paiements réellement publiés dans le topic `validated` (identités attendues) ;
  - les lignes de `validated_transactions` et de `rejected_transactions` ;
  - la table d'audit `tp_audit_attempts` (une ligne par tentative d'écriture,
    installée par scripts/toggle-unique.sh off).

Chaque source est écrite dans <dossier>/donnees/ pour pouvoir rejouer l'analyse
sans relancer l'essai. Bibliothèque standard uniquement.

Usage : python3 scripts/sujet11/collecte.py <dossier-essai>
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import horloge  # noqa: E402

TOPIC_VALIDATED = "simulpix.transactions.validated"
# Valeurs comparées par l'oracle (mêmes noms dans le message et dans la table).
CHAMPS = ("amount", "currency", "emitter_account_id", "beneficiary_account_id")


def compose(*args, stdin=None):
    """Lance `docker compose ...` depuis la racine du dépôt et renvoie stdout."""
    racine = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    resultat = subprocess.run(
        ["docker", "compose", *args],
        cwd=racine, input=stdin, capture_output=True, text=True, check=False,
    )
    return resultat


def psql(requete):
    """Exécute une requête et renvoie les lignes, colonnes séparées par '|'."""
    r = compose("exec", "-T", "postgres", "psql", "-U", "simulpix", "-d", "simulpix",
                "-At", "-F", "|", "-v", "ON_ERROR_STOP=1", "-c", requete)
    if r.returncode != 0:
        raise RuntimeError(f"psql a échoué : {r.stderr.strip()}")
    return [ligne.split("|") for ligne in r.stdout.splitlines() if ligne.strip()]


def lire_topic_validated():
    """Relit tout le topic validated avec un consommateur jetable.

    read_committed : si un producteur transactionnel a annulé une transaction,
    ses messages ne doivent pas compter comme attendus.
    Le consommateur s'arrête après 15 s sans nouveau message.
    """
    r = compose(
        "exec", "-T", "kafka-1", "/opt/kafka/bin/kafka-console-consumer.sh",
        "--bootstrap-server", "kafka-1:29092",
        "--consumer.config", "/config/client.properties",
        "--topic", TOPIC_VALIDATED,
        "--from-beginning", "--timeout-ms", "15000",
        "--isolation-level", "read_committed",
        "--property", "print.partition=true", "--property", "print.offset=true",
    )
    messages = [lire_message(ligne) for ligne in r.stdout.splitlines()]
    return [m for m in messages if m is not None]


def lire_message(ligne):
    """Une ligne « Partition:3<TAB>Offset:120<TAB>{...} » du console consumer.

    La position (partition, offset) sert à savoir quel paiement était en cours
    quand le consommateur s'est arrêté. Renvoie None pour une ligne sans JSON.
    """
    position = re.match(r"\s*Partition:(\d+)\s+Offset:(\d+)\s+(\{.*)", ligne)
    texte = position.group(3) if position else ligne.strip()
    if not texte.startswith("{"):
        return None
    try:
        m = json.loads(texte)
    except json.JSONDecodeError:
        return None
    return {"transaction_id": m.get("transaction_id"),
            # seulement les champs présents : un champ absent n'est pas comparé
            **{champ: m[champ] for champ in CHAMPS if champ in m},
            "partition": int(position.group(1)) if position else None,
            "offset": int(position.group(2)) if position else None}


def main():
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    dossier = os.path.join(sys.argv[1], "donnees")
    os.makedirs(dossier, exist_ok=True)

    # L'audit est daté par PostgreSQL : on le ramène à l'horloge de la machine.
    try:
        meta = json.load(open(os.path.join(sys.argv[1], "meta.json")))
    except OSError:
        meta = {}
    correction = horloge.decalage(meta)
    topic = lire_topic_validated()
    valides = [dict(zip(("transaction_id", *CHAMPS), ligne))
               for ligne in psql(f"select transaction_id, {', '.join(CHAMPS)} from validated_transactions")]
    rejetes = [{"transaction_id": t, "rejection_type": ty, "rejection_reason": re}
               for t, ty, re in psql(
                   "select coalesce(transaction_id, ''), rejection_type, rejection_reason "
                   "from rejected_transactions")]
    audit_present = psql("select to_regclass('public.tp_audit_attempts') is not null")[0][0] == "t"
    audit = []
    if audit_present:
        # kind : INSERT à chaque livraison, puis UPDATE si l'upsert trouve la ligne
        audit = [{"transaction_id": t, "t": float(e) - correction, "kind": k}
                 for t, e, k in psql("select transaction_id, extract(epoch from attempted_at), attempt_kind "
                                     "from tp_audit_attempts order by attempted_at, attempt_id")]

    for nom, contenu in (("topic_validated", topic), ("db_validated", valides),
                         ("db_rejected", rejetes), ("audit", audit)):
        with open(os.path.join(dossier, f"{nom}.json"), "w") as f:
            json.dump(contenu, f)
    print(f"[sujet11] collecte : topic={len(topic)} db_validated={len(valides)} "
          f"db_rejected={len(rejetes)} audit={len(audit)} (audit actif : {audit_present})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
