"""Sujet 11 — bilan d'un essai de mise à jour et verdict.

Rassemble, pour un dossier d'essai :
  - meta.json      : paramètres et instants (écrit par sujet11-maj.sh) ;
  - lag.jsonl      : relevés du groupe (mesure.py) ;
  - evenements.txt : événements Docker du conteneur persister-valid ;
  - oracle.json    : classement des identités (oracle.py) ;
  - donnees/audit.json : heures des écritures (pause.py) ;
  - donnees/topic_validated.json : position de chaque message (partitions.py) ;
  - compteurs.jsonl : compteurs de la plateforme avant, pendant et après.

Écrit resultat.json et bilan.txt. En modes « minimale », « amelioree » et « crash » :
  - REUSSITE (code 0) si : aucun paiement perdu, aucune valeur fausse, aucune
    ligne inattendue, aucun double effet, aucun paiement à la fois validé et
    rejeté, aucun trou de transaction_id, retard résorbé avant la limite,
    reprise des écritures et pause <= borne ;
  - ECHEC (code 1) dès qu'un de ces points n'est pas tenu ;
  - INVALIDE (code 1) si une mesure manque ou n'est pas fiable (horloge,
    sémantique, flux non terminé, audit ou relevé absent) : ni réussite, ni échec.
En mode « observee », le bilan est affiché sans verdict (code 0).

Usage : python3 scripts/sujet11/bilan.py <dossier-essai>
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pause  # noqa: E402
import influx  # noqa: E402
import partitions  # noqa: E402
import trous  # noqa: E402
import horloge  # noqa: E402

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def version_persister_valid(racine=RACINE):
    """Version de persister-valid mesurée : « arret-propre » si le code gère SIGTERM.

    Sans cette information, les essais de l'ancien code (pause d'environ 44 s) et
    ceux du code avec arrêt propre (environ 3 s) se mélangent dans les résultats.
    Le conteneur est reconstruit à partir de ce fichier au début de chaque essai.
    """
    try:
        code = open(os.path.join(racine, "services", "persister-valid", "main.py"), encoding="utf-8").read()
    except OSError:
        return "inconnue"
    return "arret-propre" if "STOP_REQUESTED" in code else "ancien-code"


def lire_json(dossier, nom):
    with open(os.path.join(dossier, nom)) as f:
        return json.load(f)


# Bornes officielles, par cas (décision du groupe, voir docs/sujet11/garantie.md) :
# pause maximale et délai pour revenir à 0 paiement en attente, comptés depuis le
# lancement de la mise à jour. La panne brutale est un contre-exemple à 10 Pix/s
# avec 80 ms de ralenti : la session Kafka seule dure environ 45 s et le service
# traite environ 12 Pix/s, d'où 180 s au lieu de 120 s.
# Même table dans services/service-health/sujet11_synthese.py (test d'égalité).
BORNES_OFFICIELLES = {"minimale": (60, 120), "amelioree": (60, 120), "observee": (60, 120), "crash": (60, 180)}


def essai_officiel(meta):
    """L'essai utilise-t-il les bornes officielles de son cas ? Sinon, c'est un essai de diagnostic."""
    attendu = BORNES_OFFICIELLES.get(meta.get("mode"))
    if meta.get("mode") == "observee":
        return None  # pas de verdict, pas de borne de pause
    return attendu is not None and (meta.get("borne_s"), meta.get("drainage_max_s")) == attendu


def charge_reelle(meta):
    """Charge décrite par ce qui a été appliqué (débit et ralenti), pas par l'étiquette."""
    if meta.get("ralenti_ms"):
        return f"ralentie ({meta.get('debit')} Pix/s, {meta['ralenti_ms']} ms entre lecture validée et écriture)"
    return f"{meta.get('charge')} ({meta.get('debit')} Pix/s)"


def lire_lignes(dossier, nom):
    with open(os.path.join(dossier, nom)) as f:
        return [json.loads(l) for l in f if l.strip()]


def lire_lag(dossier):
    return lire_lignes(dossier, "lag.jsonl")


def texte_compteurs(compteurs):
    """Trois lignes : avant, pire moment, après. « non mesuré » si absent."""
    if not compteurs:
        return ["   non mesuré (pas de compteurs.jsonl)"]
    lignes = []
    for nom, cle in (("avant la mise à jour", "avant"), ("pire moment", "pire"), ("après le flux", "apres")):
        x = compteurs.get(cle)
        if not x:
            lignes.append(f"   {nom} : non mesuré")
            continue
        lignes.append(f"   {nom} : {x.get('validated_topic_end_offsets')} / {x.get('db_validated_count')}"
                      f" / {x.get('ecart_topic_base')}")
    return lignes


def champs_influx(meta, resultat):
    """Champs de la mesure sujet11_essai. None n'est pas écrit : Grafana affiche alors
    « Non disponible », jamais un zéro inventé."""
    oc = resultat["oracle"]["continuite"]
    classes = oc["classes"]
    ch = resultat["chronologie"]
    p = resultat["pause"]
    trous_base = resultat["trous"] or {}
    compteurs = resultat.get("compteurs") or {}
    apres = compteurs.get("apres") or {}
    return {
        "id": meta["id"], "verdict": resultat["verdict"], "raisons": " ; ".join(resultat["raisons"]),
        "officiel": resultat.get("essai_officiel"), "ralenti_ms": meta.get("ralenti_ms"),
        "reussite": resultat["verdict"] == "REUSSITE",
        "debut_flux": meta.get("debut_flux"), "t0": meta.get("t0"), "fin_flux": meta.get("fin_flux"),
        "borne_s": float(meta["borne_s"]), "drainage_max_s": float(meta["drainage_max_s"]),
        "pause_s": p["pause_s"], "trou_normal_s": p["trou_normal_s"],
        "pause_distincte": resultat["pause_distincte"],
        "retard_max": resultat["retard_max_messages"],
        "attendus": oc["attendus"], "presents": classes["present"], "perdus": classes["perdu"],
        "valeurs_fausses": classes["valeur_fausse"], "rejets_metier": classes["rejet_metier"],
        "rejets_delai": classes["rejet_delai"], "inattendues": oc["lignes_inattendues"],
        "doubles_effets": oc.get("doubles_effets"), "incoherents": oc.get("incoherents"),
        "trous": trous_base.get("trous"), "en_base_total": apres.get("db_validated_count"),
        "doublons_absorbes": resultat["oracle"]["doublons"]["doublons_absorbes"],
        "drainage_termine": bool(resultat["drainage_termine"]),
        "debit_mesure": compteurs.get("debit_mesure"),
        # chronologie, en secondes après le lancement de la mise à jour
        "signal_arret_s": ch["signal_arret_s"], "conteneur_mort_s": ch["conteneur_mort_s"],
        "nouveau_conteneur_s": ch["nouveau_conteneur_s"], "sans_proprietaire_s": ch["groupe_vide_s"],
        "reattribuees_s": ch["partitions_reattribuees_s"], "lag_zero_s": ch["lag_revenu_a_zero_s"],
        "sans_proprietaire_duree_s": ch["groupe_vide_duree_s"],
        "derniere_ecriture_s": p["derniere_ecriture_avant_s"], "premiere_ecriture_s": p["premiere_ecriture_apres_s"],
    }


def lire_evenements(dossier, correction=0.0):
    """Lignes « <TimeNano> <action> [<conteneur> [<signal>]] » de `docker events`.

    Les anciens essais n'ont que l'heure et l'action : le conteneur vaut alors
    persister-valid et le signal est inconnu.
    """
    evenements = []
    chemin = os.path.join(dossier, "evenements.txt")
    if os.path.exists(chemin):
        for ligne in open(chemin):
            p = ligne.split()
            if len(p) >= 2 and p[0].isdigit():
                nom = p[2] if len(p) >= 3 else "persister-valid"
                signal = p[3] if len(p) >= 4 and p[3].isdigit() else None
                # heure du démon Docker, ramenée à l'horloge de la machine
                evenements.append((int(p[0]) / 1e9 - correction, p[1].rstrip(":"), nom, signal))
    return evenements


def chronologie(meta, lag, evenements):
    """Repères relatifs à t0, en secondes."""
    t0 = meta["t0"]
    ancien = "persister-valid"
    nouveau = "persister-valid-b" if meta["mode"] == "amelioree" else "persister-valid"
    rel = lambda t: round(t - t0, 3) if t is not None else None  # noqa: E731

    def premier(actions, nom):
        return next((t for t, a, n, _ in evenements if a in actions and n == nom and t >= t0 - 1), None)

    apres_t0 = [x for x in lag if x["t"] >= t0]
    deux_membres = next((x["t"] for x in apres_t0 if x["membres"] >= 2), None)
    vide = next((x["t"] for x in apres_t0 if x["membres"] == 0), None)
    reattribue = None
    if vide is not None:
        reattribue = next((x["t"] for x in apres_t0 if x["t"] > vide and x["membres"] > 0), None)
    fin_drainage = None
    if reattribue is not None:
        fin_drainage = next((x["t"] for x in apres_t0 if x["t"] >= reattribue and x["lag"] == 0), None)
    return {
        "signal_arret_s": rel(premier({"kill"}, ancien)),
        "signaux_recus": [[rel(t), s] for t, a, n, s in evenements if a == "kill" and n == ancien],
        "conteneur_mort_s": rel(premier({"die"}, ancien)),
        "nouveau_conteneur_s": rel(premier({"start"}, nouveau)),
        "deux_membres_s": rel(deux_membres),
        "arret_ancien_demande_s": rel(meta.get("t_arret")) if meta["mode"] == "amelioree" else None,
        "groupe_vide_s": rel(vide),
        "partitions_reattribuees_s": rel(reattribue),
        "lag_revenu_a_zero_s": rel(fin_drainage),
        "groupe_vide_duree_s": round(reattribue - vide, 3) if vide and reattribue else None,
    }


def anomalies_integrite(oracle, trous_base=None):
    """Écarts entre les paiements attendus et l'état de la base. Chacun empêche REUSSITE.

    Les identités attendues sont celles du topic validated : la banque les a
    validées. Un rejet métier légitime n'en fait pas partie (il est publié dans
    rejected, jamais dans validated) : il est compté à part (oracle « flux ») et
    ne fait pas échouer l'essai. Une identité validée retrouvée seulement dans les
    rejets est en revanche une anomalie : le client a reçu « validé », la base dit
    « rejeté ».
    """
    raisons = []
    c = oracle["continuite"]
    classes = c["classes"]
    if classes["perdu"]:
        raisons.append(f"{classes['perdu']} paiement(s) perdu(s)")
    rejetes_a_tort = classes.get("rejet_metier", 0) + classes.get("rejet_delai", 0)
    if rejetes_a_tort:
        raisons.append(f"{rejetes_a_tort} paiement(s) validé(s) retrouvé(s) seulement dans les rejets")
    if classes["valeur_fausse"]:
        raisons.append(f"{classes['valeur_fausse']} valeur(s) fausse(s)")
    if c["lignes_inattendues"]:
        raisons.append(f"{c['lignes_inattendues']} ligne(s) inattendue(s)")
    # anciens oracles : ces clés n'existent pas, la valeur vaut alors 0
    if c.get("doubles_effets"):
        raisons.append(f"{c['doubles_effets']} double(s) effet(s) en base")
    if c.get("incoherents"):
        raisons.append(f"{c['incoherents']} paiement(s) à la fois validé(s) et rejeté(s)")
    if c.get("conflits_topic"):
        raisons.append(f"{c['conflits_topic']} identité(s) publiée(s) avec des valeurs différentes")
    if trous_base is not None:
        # Recoupe la relecture du topic : un paiement absent des deux tables est
        # une perte, même si la relecture du topic l'a manqué.
        if trous_base["trous"]:
            raisons.append(f"{trous_base['trous']} paiement(s) sans décision en base (ni validé, ni rejeté)")
        if trous_base["hors_plage"]:
            raisons.append(f"{len(trous_base['hors_plage'])} identifiant(s) hors de l'essai en base")
    return raisons


def anomalies_temps(meta, mesure_pause, drainage_ok):
    """Écarts de continuité temporelle, mesurés contre les bornes de CET essai (meta.json)."""
    raisons = []
    if not drainage_ok:
        raisons.append(f"retard non résorbé en {meta['drainage_max_s']} s (drainage)")
    if mesure_pause["pause_s"] is None or not mesure_pause["reprise"]:
        raisons.append("pas de reprise des écritures")
    elif mesure_pause["pause_s"] > meta["borne_s"]:
        raisons.append(f"pause {mesure_pause['pause_s']} s > borne {meta['borne_s']} s")
    return raisons


def verdict(meta, oracle, mesure_pause, drainage_ok, trous_base=None):
    """Intégrité et temps seulement : REUSSITE si aucun écart, ECHEC sinon (raisons cumulées)."""
    raisons = anomalies_integrite(oracle, trous_base) + anomalies_temps(meta, mesure_pause, drainage_ok)
    return ("REUSSITE" if not raisons else "ECHEC"), raisons


def invalidites_par_type(meta, audit, lag, trous_base, topic_lus=None, compteurs=None):
    """Mesures manquantes ou douteuses, rangées selon ce qu'elles empêchent de conclure.

      - integrite : on ne peut pas affirmer que les paiements sont tous vérifiés ;
      - temps     : on ne peut pas affirmer la pause ou le drainage ;
      - scenario  : l'essai ne teste pas ce qu'il annonce.
    """
    inv = {"integrite": [], "temps": [], "scenario": []}
    if meta.get("flux_termine") is False:
        inv["integrite"].append("flux pas terminé avant la collecte : résultat indéterminé")
    if trous_base is None:
        inv["integrite"].append("tables PostgreSQL non relues : trous non vérifiables")
    if meta.get("base_stable") is False:
        inv["integrite"].append("base encore en écriture au moment de la collecte : une perte ne peut pas être conclue")
    fin_topic = ((compteurs or {}).get("apres") or {}).get("validated_topic_end_offsets")
    if topic_lus is not None and fin_topic is not None and topic_lus != fin_topic:
        inv["integrite"].append(f"relecture du topic incomplète : {topic_lus} messages lus sur {fin_topic}")
    if (horloge.derive(meta) or 0) > horloge.DERIVE_MAX_S:
        inv["temps"].append(f"horloge de Docker décalée de {meta['decalage_debut_s']} s puis {meta['decalage_fin_s']} s")
    if not audit:
        inv["temps"].append("audit des écritures vide : pause non mesurable")
    if not any(x.get("ok", True) and x.get("partitions") for x in lag):
        inv["temps"].append("aucun relevé du groupe : retard et chronologie non mesurables")
    for cle in ("semantique_effective", "semantique_effective_apres"):
        if meta.get(cle) not in (None, meta["semantique"]):
            quand = "après" if cle.endswith("apres") else "avant"
            inv["scenario"].append(f"persister-valid appliquait {meta[cle]} {quand} la mise à jour, pas {meta['semantique']}")
    return inv


def invalidites(meta, audit, lag, trous_base, topic_lus=None, compteurs=None):
    """Toutes les invalidités, à plat, dans l'ordre historique du bilan :
    horloge, sémantique, flux, audit, relevé, tables, relecture du topic."""
    inv = invalidites_par_type(meta, audit, lag, trous_base, topic_lus, compteurs)
    horloge_ = [x for x in inv["temps"] if x.startswith("horloge")]
    autres_temps = [x for x in inv["temps"] if not x.startswith("horloge")]
    flux = [x for x in inv["integrite"] if x.startswith("flux")]
    autres_integ = [x for x in inv["integrite"] if not x.startswith("flux")]
    return horloge_ + inv["scenario"] + flux + autres_temps + autres_integ


def decider(meta, oracle, mesure_pause, drainage_ok, trous_base, audit, lag, topic_lus=None, compteurs=None):
    """Verdict final, sans qu'aucune catégorie n'en efface une autre.

    Règle : une anomalie est démontrée quand les mesures dont elle dépend sont
    valides (une perte vient de la comparaison des identités, pas de l'horloge).
      - ECHEC    : au moins une anomalie démontrée ;
      - INVALIDE : aucune anomalie démontrée, mais une mesure manque ou est douteuse ;
      - REUSSITE : toutes les mesures sont valides et aucune anomalie.
    Les raisons gardent tout : anomalies démontrées, anomalies non confirmées
    (mesure douteuse) et invalidités.
    """
    inv = invalidites_par_type(meta, audit, lag, trous_base, topic_lus, compteurs)
    integ = anomalies_integrite(oracle, trous_base)
    temps = anomalies_temps(meta, mesure_pause, drainage_ok)
    integ_sure, temps_sur = not inv["integrite"], not inv["temps"]
    raisons = []
    raisons += integ if integ_sure else [f"{x} (non confirmé : mesure incomplète)" for x in integ]
    raisons += temps if temps_sur else [f"{x} (non confirmé : mesure du temps douteuse)" for x in temps]
    raisons += [f"mesure invalide : {x}" for x in inv["scenario"] + inv["integrite"] + inv["temps"]]
    demontrees = (integ if integ_sure else []) + (temps if temps_sur else [])
    if demontrees:
        statut = "ECHEC"
    elif any(inv.values()):
        statut = "INVALIDE"
    else:
        statut = "REUSSITE"
    anomalies = {"integrite": integ, "temps": temps, "mesure": inv,
                 "integrite_confirmee": integ_sure, "temps_confirme": temps_sur}
    return statut, raisons, anomalies


def pause_distincte(mesure_pause):
    """La pause se distingue-t-elle du rythme normal du flux ?

    Le générateur émet par paquets : sans mise à jour, il y a déjà des trous
    (trou normal, environ 1 s à 20 Pix/s). Une pause qui ne dépasse pas 1,5 fois
    ce trou ne peut pas être attribuée à la mise à jour. None si on ne sait pas.
    """
    p, t = mesure_pause.get("pause_s"), mesure_pause.get("trou_normal_s")
    if p is None or not t:
        return None
    return p > 1.5 * t


def resumer_compteurs(lignes):
    """Compteurs de la plateforme avant, au pire moment et après l'opération.

    lignes : contenu de compteurs.jsonl (phases avant, pendant, apres).
    Débit mesuré : paiements générés par seconde, entre le premier et le
    dernier relevé où le générateur produit encore. None si non mesurable.
    """
    if not lignes:
        return None
    par_phase = {p: [x for x in lignes if x.get("phase") == p] for p in ("avant", "pendant", "apres")}
    pendant = [x for x in par_phase["pendant"] if x.get("ecart_topic_base") is not None]
    pire = max(pendant, key=lambda x: x["ecart_topic_base"]) if pendant else None
    debit = None
    gen = sorted((x["t"], x["generated"]) for x in lignes if x.get("generated") is not None)
    actifs = [(t, g) for (t, g), (_, g_suivant) in zip(gen, gen[1:]) if g_suivant > g]
    if len(actifs) >= 2 and actifs[-1][0] > actifs[0][0]:
        debit = round((actifs[-1][1] - actifs[0][1]) / (actifs[-1][0] - actifs[0][0]), 1)
    return {"avant": (par_phase["avant"] or [None])[0], "pire": pire,
            "apres": (par_phase["apres"] or [None])[-1], "debit_mesure": debit}


def main():
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    dossier = sys.argv[1]
    meta = lire_json(dossier, "meta.json")
    oracle = lire_json(dossier, "oracle.json")
    lag = lire_lag(dossier)
    evenements = lire_evenements(dossier, horloge.decalage(meta))
    # Fichier absent = mesure absente : le bilan va jusqu'au bout et rend INVALIDE
    # (audit vide), au lieu de s'arrêter sur une erreur Python.
    try:
        audit = lire_json(dossier, os.path.join("donnees", "audit.json"))
    except OSError:
        audit = []
    # topic_lus : nombre de messages relus, même 0 (relecture impossible) ;
    # None seulement si le fichier n'existe pas (anciens essais).
    try:
        topic = lire_json(dossier, os.path.join("donnees", "topic_validated.json"))
        topic_lus = len(topic)
    except OSError:
        topic, topic_lus = [], None
    try:
        valides = lire_json(dossier, os.path.join("donnees", "db_validated.json"))
    except OSError:
        valides = None
    try:
        rejetes = lire_json(dossier, os.path.join("donnees", "db_rejected.json"))
    except OSError:
        rejetes = None
    # contrôle direct en base : recoupement de l'oracle, pas un critère du verdict
    trous_base = (trous.chercher(valides, rejetes, meta["total"])
                  if valides is not None and rejetes is not None else None)

    t0 = meta["t0"]
    mesure_pause = pause.mesurer(audit, t0, meta["fin"], meta["debut_reference"])
    apres = [x for x in lag if x["t"] >= t0]
    try:
        compteurs = resumer_compteurs(lire_lignes(dossier, "compteurs.jsonl"))
    except OSError:
        compteurs = None
    resultat = {
        "parametres": {k: meta.get(k) for k in ("mode", "semantique", "charge", "total", "debit",
                                                 "borne_s", "cible_metier_s", "drainage_max_s", "ralenti_ms")},
        "sous_cible_metier": (mesure_pause["pause_s"] is not None and meta.get("cible_metier_s") is not None
                              and mesure_pause["pause_s"] <= meta["cible_metier_s"]),
        "pause": mesure_pause,
        "pause_distincte": pause_distincte(mesure_pause),
        "retard_max_messages": max((x["lag"] for x in apres), default=None),
        "chronologie": chronologie(meta, lag, evenements),
        # les anciens essais n'ont pas de relevé par partition : liste vide
        "partitions": partitions.analyser(lag, topic, audit, t0),
        "trous": trous_base,
        "compteurs": compteurs,
        "essai_officiel": essai_officiel(meta),
        "charge_reelle": charge_reelle(meta),
        "bornes_officielles": BORNES_OFFICIELLES.get(meta["mode"]),
        "drainage_termine": meta["drainage_termine"],
        "version_persister_valid": version_persister_valid(),
        "oracle": oracle,
    }
    resultat["horloge"] = {"decalage_s": horloge.decalage(meta), "derive_s": horloge.derive(meta),
                           "flux_termine": meta.get("flux_termine")}
    statut, raisons, anomalies = decider(meta, oracle, mesure_pause, meta["drainage_termine"], trous_base,
                                         audit, lag, topic_lus=topic_lus, compteurs=compteurs)
    resultat["anomalies"] = anomalies
    if meta["mode"] in ("minimale", "amelioree", "crash"):
        resultat["verdict"], resultat["raisons"] = statut, raisons
    else:
        # observation : pas de verdict, mais les anomalies restent écrites
        resultat["verdict"], resultat["raisons"] = "OBSERVATION", raisons

    with open(os.path.join(dossier, "resultat.json"), "w") as f:
        json.dump(resultat, f, indent=2, ensure_ascii=False)

    # Une ligne par essai dans InfluxDB : le tableau de bord Grafana lit ces champs.
    influx.ecrire([influx.ligne(
        "sujet11_essai",
        {"mode": meta["mode"], "semantique": meta["semantique"], "charge": meta["charge"],
         "version": resultat["version_persister_valid"]},
        champs_influx(meta, resultat),
        t=meta.get("fin_flux", meta["fin"]))])

    c = oracle["continuite"]["classes"]
    oc = oracle["continuite"]
    ch = resultat["chronologie"]
    p = resultat["parametres"]
    distincte = resultat["pause_distincte"]
    texte = [
        "=" * 66,
        f" BILAN SUJET 11 — mode={p['mode']} sémantique={p['semantique']} charge={p['charge']}",
        "=" * 66,
        f" Flux : {p['total']} Pix à {p['debit']} Pix/s demandés"
        + (f", {compteurs['debit_mesure']} Pix/s mesurés" if compteurs and compteurs["debit_mesure"] else "")
        + f", persister-valid {resultat['version_persister_valid']}"
        + (f", ralenti {p['ralenti_ms']} ms" if p.get("ralenti_ms") else ""),
        f" Pause en base         : {mesure_pause['pause_s']} s (borne {p['borne_s']} s,"
        f" cible métier {p['cible_metier_s']} s : {'atteinte' if resultat['sous_cible_metier'] else 'non atteinte'})",
        f" Trou normal (référence): {mesure_pause['trou_normal_s']} s"
        + ("" if distincte is None else
           " : la pause dépasse le rythme normal du flux" if distincte else
           " : AUCUNE pause mesurable au-delà du rythme normal du flux"),
        f" Retard maximal        : {resultat['retard_max_messages']} messages",
        " Compteurs (topic validated / lignes en base / écart) :",
        *texte_compteurs(compteurs),
        " Chronologie (secondes après le lancement de la mise à jour) :",
        f"   signal d'arrêt {ch['signal_arret_s']} | conteneur mort {ch['conteneur_mort_s']}"
        f" | nouveau conteneur {ch['nouveau_conteneur_s']}",
        f"   signaux reçus par l'ancienne instance (instant, numéro) : {ch['signaux_recus']}",
        f"   deux membres dans le groupe {ch['deux_membres_s']}"
        f" | arrêt de l'ancienne demandé {ch['arret_ancien_demande_s']}",
        f"   aucune partition lue (groupe vide ou rebalance) {ch['groupe_vide_s']} | partitions réattribuées {ch['partitions_reattribuees_s']}"
        f" | lag à 0 {ch['lag_revenu_a_zero_s']}",
        f"   dernière écriture {mesure_pause['derniere_ecriture_avant_s']}"
        f" | première écriture après {mesure_pause['premiere_ecriture_apres_s']}",
        " Passations de partitions et message en cours :",
        *partitions.resume(resultat["partitions"], meta["semantique"]),
        f" Oracle : attendus={oc['attendus']} présents={c['present']}"
        f" perdus={c['perdu']} valeurs fausses={c['valeur_fausse']}"
        f" rejets délai={c['rejet_delai']} rejets métier={c['rejet_metier']}"
        f" lignes inattendues={oc['lignes_inattendues']}",
        f"   doubles effets={oc.get('doubles_effets', 'non mesuré')}"
        f" incohérents={oc.get('incoherents', 'non mesuré')}"
        f" conflits du topic={oc.get('conflits_topic', 'non mesuré')}"
        f" ; valeurs comparées : {', '.join(oc.get('champs_compares', [])) or 'non mesuré'}",
        (f" Trous de transaction_id en base : {trous_base['trous']} sur {trous_base['attendus']}"
         + (f" (exemples : {', '.join(trous_base['exemples'])})" if trous_base["exemples"] else "")
         if trous_base is not None else " Trous de transaction_id en base : non mesuré"),
        f" Doublons absorbés (audit) : {oracle['doublons']['doublons_absorbes']}"
        " (relectures sans second effet grâce à l'upsert)",
        f" Rejets pour délai sur tout le flux : {oracle.get('flux', {}).get('rejets_delai')}",
        f" Retard résorbé (drainage) en moins de {meta['drainage_max_s']} s :"
        f" {'oui' if meta['drainage_termine'] else 'NON'}",
        f" Horloge Docker - machine : décalage {resultat['horloge']['decalage_s']} s corrigé,"
        f" dérive pendant l'essai {resultat['horloge']['derive_s']} s",
        "-" * 66,
        f" VERDICT : {resultat['verdict']}" + (" — " + " ; ".join(resultat["raisons"])
                                             if resultat["raisons"] else ""),
        "=" * 66,
    ]
    with open(os.path.join(dossier, "bilan.txt"), "w") as f:
        f.write("\n".join(texte) + "\n")
    print("\n".join(texte))
    return 1 if resultat["verdict"] in ("ECHEC", "INVALIDE") else 0


if __name__ == "__main__":
    sys.exit(main())
