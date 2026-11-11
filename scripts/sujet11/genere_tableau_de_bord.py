"""Génère infra/observability/grafana/dashboards/simul-pix-sujet11.json.

Le tableau est fait pour une présentation à quelqu'un qui ne connaît pas
Kafka, sur un écran 1920 × 1080. De haut en bas :

  0. ce qu'on teste, et les boutons pour lancer un essai ;
  1. vue d'ensemble : la garantie est-elle tenue ? ;
  2. déroulement de la mise à jour, étape par étape ;
  3. intégrité des paiements : attendus et enregistrés ;
  4. performance et continuité : courbes, avec la limite de 60 s ;
  5. comparaison des sémantiques : théorie, puis mesures ;
  6. détails techniques (rangée repliée), pour les questions.

Les sections 1 à 3 sont des cadres (iframe) de la page /sujet11/synthese de
service-health (services/service-health/sujet11_synthese.py) : Grafana ne
permet pas de choisir la taille du texte de ses tableaux, et cette page lit
directement les fichiers des essais. Les sections 4 à 6 lisent InfluxDB
(mesures écrites par scripts/sujet11/*.py).

Couleurs, les mêmes partout : vert = garantie tenue, rouge = perte ou limite
dépassée, orange = attention, bleu = information ou en cours, gris = non
disponible ou secondaire.

Usage : python3 scripts/sujet11/genere_tableau_de_bord.py infra/observability/grafana/dashboards/simul-pix-sujet11.json
"""
import json
import sys

DS = {"type": "influxdb", "uid": "simulpix-influxdb"}
BUCKET = 'from(bucket: "simulpix_observability")\n'
# Les courbes en direct suivent la période choisie en haut de Grafana...
B = BUCKET + '  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
# ...les résultats d'essais restent visibles quelle que soit cette période.
B90 = BUCKET + '  |> range(start: -90d)\n'

# Courbes et barres : teintes claires, lisibles sur le thème sombre de Grafana (contraste >= 6:1
# sur #181b1f, mesuré). Fonds pleins (boutons, légende) : teintes foncées, texte blanc >= 5:1.
VERT, ROUGE, ORANGE, BLEU, GRIS = "#4ade80", "#f87171", "#fb923c", "#60a5fa", "#a3adbf"
FOND_VERT, FOND_ROUGE, FOND_ORANGE, FOND_BLEU, FOND_GRIS = "#15803d", "#b91c1c", "#c2410c", "#1d4ed8", "#4b5563"
ND = "Non disponible"
POLICE = "font-family:Inter,Roboto,'Segoe UI',system-ui,sans-serif"
SYNTHESE = "http://localhost:8083/sujet11/synthese?vue="


def cible(q, ref="A"):
    return [{"datasource": DS, "query": q, "refId": ref}]


def nommer(champ, nom, couleur=None, **extra):
    props = [{"id": "displayName", "value": nom}]
    if couleur:
        props.append({"id": "color", "value": {"mode": "fixed", "fixedColor": couleur}})
    props += [{"id": k, "value": v} for k, v in extra.items()]
    return {"matcher": {"id": "byName", "options": champ}, "properties": props}


panels = []
y = 0
ident = iter(range(1, 1000))


def texte(contenu, h, w=24, x=0, transparent=True, titre=""):
    global y
    panels.append({"id": next(ident), "type": "text", "title": titre, "transparent": transparent,
                   "gridPos": {"h": h, "w": w, "x": x, "y": y},
                   "options": {"mode": "html", "content": contenu}})


def section(numero, titre, phrase):
    """Titre de section lisible au vidéoprojecteur (28 px), avec une phrase d'explication."""
    global y
    texte(f"<div style=\"{POLICE}\"><div style=\"font-size:28px;font-weight:700;line-height:1.2\">"
          f"{numero}. {titre}</div><div style=\"font-size:17px;opacity:.85;margin-top:4px\">{phrase}</div></div>", 3)
    y += 3


def cadre(vue, h, description):
    """Une vue de la page de synthèse, dans un cadre."""
    global y
    panels.append({"id": next(ident), "type": "text", "title": "", "transparent": True,
                   "description": description,
                   "gridPos": {"h": h, "w": 24, "x": 0, "y": y},
                   "options": {"mode": "html", "content":
                               f"<iframe src=\"{SYNTHESE}{vue}\" title=\"{vue}\" "
                               "style=\"width:100%;height:100%;border:0;border-radius:10px\"></iframe>"}})
    y += h


def courbe(titre, desc, q, pos, unite, overrides, seuils=None, escalier=False):
    defaults = {"unit": unite, "min": 0, "noValue": ND,
                "custom": {"lineInterpolation": "stepAfter" if escalier else "linear", "lineWidth": 3,
                           "fillOpacity": 10, "showPoints": "never", "spanNulls": False,
                           "axisLabel": "", "axisSoftMin": 0}}
    if seuils:
        defaults["thresholds"] = {"mode": "absolute", "steps": seuils}
        defaults["custom"]["thresholdsStyle"] = {"mode": "line+area"}
    return {"id": next(ident), "type": "timeseries", "title": titre, "description": desc, "datasource": DS,
            "gridPos": pos, "targets": cible(q),
            "fieldConfig": {"defaults": defaults, "overrides": overrides},
            "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                        "tooltip": {"mode": "multi"}}}


# ------------------------------------------------------------------ 0. En-tête et lancement
# Hauteurs des cadres (unités Grafana : h × 30 px + (h - 1) × 8 px), mesurées sur le contenu
# réel des vues à 1880 px de large, avec un bandeau d'essai en cours en plus (pire cas).
# Mesuré le 10 novembre, dans le pire cas (tous les cas d'essai, essai en cours et essai
# interrompu), à 1570 px de large : c'est la largeur réelle du cadre à 1920 px avec le menu
# de Grafana ouvert (vérifié dans Grafana connecté). Ensemble 730 px, déroulement 632,
# intégrité 546, essais 863, comparaison 707 ; marge de 24 px pour le cadre du panneau.
H = {"pilotage": 22, "ensemble": 21, "deroulement": 18, "integrite": 16, "essais": 24, "comparaison": 20}
# Légende des couleurs, visible en permanence (pas dans une infobulle). Les états ont
# toujours aussi un libellé écrit : la couleur n'est jamais le seul signal.
PASTILLE = ("display:inline-flex;align-items:center;gap:6px;margin-right:18px;font-size:17px;"
            "white-space:nowrap")
LEGENDE = "".join(
    f'<span style="{PASTILLE}"><span style="width:18px;height:18px;border-radius:4px;background:{c};'
    f'display:inline-block"></span><b>{nom}</b>&nbsp;{sens}</span>'
    for c, nom, sens in ((FOND_VERT, "Vert", ": objectif respecté"), (FOND_ROUGE, "Rouge", ": objectif non respecté"),
                         (FOND_ORANGE, "Orange", ": attention, à surveiller"),
                         (FOND_BLEU, "Bleu", ": information ou traitement en cours"),
                         (FOND_GRIS, "Gris", ": donnée non disponible")))
texte(f"""<div style="{POLICE}">
<div style="font-size:32px;font-weight:700;line-height:1.2">Mettre à jour un service sans perdre de paiement</div>
<div style="font-size:18px;margin:6px 0 8px;opacity:.9">On remplace le programme qui enregistre les paiements
dans la base (<b>persister-valid</b>) pendant que les paiements arrivent. On vérifie ensuite, paiement par
paiement, qu'aucun n'est perdu ni enregistré deux fois, que l'interruption reste sous sa limite et que le retard
est rattrapé à temps.</div>
<div style="margin:0 0 10px">{LEGENDE}</div>
</div>""", 5)
y += 5

# ------------------------------------------------------------------ 0. Contrôle des scénarios
section(0, "Contrôle des scénarios expérimentaux",
        "Choisir un scénario, vérifier le résumé, lancer, puis suivre l'essai. Il faut être connecté à Grafana "
        "avec le rôle Editor ou Admin ; la panne et l'arrêt demandent une confirmation.")
panels.append({"id": next(ident), "type": "text", "title": "", "transparent": True,
               "description": "Page /sujet11/pilotage de service-health. Le lancement réutilise le script "
                              "scripts/sujet11-maj.sh, avec ses paramètres fixés ; un seul essai à la fois.",
               "gridPos": {"h": H["pilotage"], "w": 24, "x": 0, "y": y},
               "options": {"mode": "html", "content":
                           "<iframe src=\"http://localhost:8083/sujet11/pilotage\" title=\"pilotage\" "
                           "style=\"width:100%;height:100%;border:0;border-radius:10px\"></iframe>"}})
y += H["pilotage"]

# ------------------------------------------------------------------ 1 à 3. Page de synthèse
section(1, "Vue d'ensemble", "Le résultat du dernier essai terminé. Chaque carte répond à une seule question, "
        "avec son libellé : Respecté, Non respecté, Information ou Non disponible.")
cadre("ensemble", H["ensemble"], "Dernier essai terminé. Pendant un essai, un bandeau bleu le dit et donne les mesures en direct.")
section(2, "Déroulement de la mise à jour", "Les étapes, dans l'ordre, avec les temps mesurés après le lancement "
        "de la mise à jour.")
cadre("deroulement", H["deroulement"], "Temps en secondes après le lancement de la mise à jour.")
section(3, "Intégrité des paiements", "Chaque paiement attendu est cherché dans la base, par son identifiant. "
        "Un rejet de la banque n'est pas une perte.")
cadre("integrite", H["integrite"], "Un rejet de la banque n'est pas une perte : il est enregistré dans la table des rejets.")

# ------------------------------------------------------------------ 4. Performance et continuité
section(4, "Performance et continuité",
        "En haut, en direct : <b style='color:#fb923c'>orange</b> = paiements validés pas encore écrits en base ; "
        "<b style='color:#60a5fa'>bleu</b> = paiements pas encore lus par le service ; lignes violettes = étapes "
        "de l'essai. En bas : chaque essai publié face à sa propre limite (trait rouge).")
panels.append(courbe(
    "Paiements en attente (en direct)",
    "Paiements validés pas encore écrits en base. La courbe monte pendant l'interruption, puis redescend à 0 "
    "quand la nouvelle version a rattrapé son retard. Sources : compteurs de la plateforme (toutes les 2 s) "
    "et groupe Kafka (chaque seconde).",
    B + '  |> filter(fn: (r) => (r._measurement == "sujet11_compteurs" and r._field == "ecart_topic_base")'
        ' or (r._measurement == "sujet11_groupe" and r._field == "lag"))\n'
        '  |> map(fn: (r) => ({_time: r._time, _value: float(v: r._value), '
        'serie: if r._measurement == "sujet11_groupe" then "lag" else "ecart"}))\n'
        '  |> group(columns: ["serie"])\n  |> aggregateWindow(every: v.windowPeriod, fn: max, createEmpty: false)\n'
        '  |> pivot(rowKey: ["_time"], columnKey: ["serie"], valueColumn: "_value")',
    {"h": 9, "w": 12, "x": 0, "y": y}, "short",
    [nommer("ecart", "pas encore écrits en base (paiements)", ORANGE),
     nommer("lag", "pas encore lus par le service (paiements)", BLEU)]))
panels.append(courbe(
    "Instances du service en train de lire (en direct)",
    "0 : plus personne ne lit les paiements, ils attendent dans la file d'attente. 1 : fonctionnement normal. "
    "2 : l'ancienne et la nouvelle version se partagent le travail (solution améliorée).",
    B + '  |> filter(fn: (r) => r._measurement == "sujet11_groupe" and r._field == "membres")\n'
        '  |> group(columns: ["_field"])\n  |> aggregateWindow(every: v.windowPeriod, fn: last, createEmpty: false)\n'
        '  |> keep(columns: ["_time", "_value"])\n  |> rename(columns: {_value: "membres"})',
    {"h": 9, "w": 12, "x": 12, "y": y}, "short",
    [nommer("membres", "instances en train de lire", BLEU)], escalier=True))
y += 9
cadre("essais", H["essais"], "Essais publiés dans preuves/ (code actuel). Un point = un essai ; trait rouge = sa limite.")

# ------------------------------------------------------------------ 5. Comparaison des sémantiques
section(5, "Comparaison des sémantiques de livraison",
        "Que change l'ordre « noter la lecture » / « écrire en base » quand le service s'arrête ? Seuls les "
        "essais publiés dans preuves/ sont comptés : mêmes chiffres que les bilans.")
cadre("comparaison", H["comparaison"], "Théorie à gauche, mesures à droite. Le périmètre est écrit sous le tableau.")

# ------------------------------------------------------------------ 6. Détails techniques (repliés)
details = []
dy = y + 1
details.append(courbe(
    "Lag du groupe Kafka (messages)",
    "Somme du lag des 6 partitions du topic validated pour le groupe persister-valid. Relevé par "
    "kafka-consumer-groups --describe, environ une fois par seconde (scripts/sujet11/mesure.py).",
    B + '  |> filter(fn: (r) => r._measurement == "sujet11_groupe" and r._field == "lag")\n'
        '  |> group(columns: ["_field"])\n  |> aggregateWindow(every: v.windowPeriod, fn: max, createEmpty: false)\n'
        '  |> keep(columns: ["_time", "_value"])\n  |> rename(columns: {_value: "lag"})',
    {"h": 8, "w": 8, "x": 0, "y": dy}, "short", [nommer("lag", "lag (messages)", BLEU)]))
details.append(courbe(
    "Membres et partitions lues",
    "Membres = consommateurs qui ont des partitions. Pendant un rebalance « eager », toutes les partitions "
    "sont rendues : le relevé voit alors 0 membre, même si les consommateurs restent dans le groupe.",
    B + '  |> filter(fn: (r) => r._measurement == "sujet11_groupe" and (r._field == "membres" or r._field == "partitions"))\n'
        '  |> group(columns: ["_field"])\n  |> aggregateWindow(every: v.windowPeriod, fn: last, createEmpty: false)\n'
        '  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")',
    {"h": 8, "w": 8, "x": 8, "y": dy}, "short",
    [nommer("membres", "membres actifs", BLEU, decimals=0), nommer("partitions", "partitions décrites", GRIS, decimals=0)],
    escalier=True))
details.append(courbe(
    "Écritures par seconde dans validated_transactions",
    "Dérivée du nombre de lignes, relevé toutes les 10 s par le collecteur de la plateforme. La valeur exacte "
    "de l'interruption vient de la table d'audit (une ligne par écriture, heure clock_timestamp()).",
    B + '  |> filter(fn: (r) => r._measurement == "postgres_runtime" and r._field == "validated_count")\n'
        '  |> aggregateWindow(every: v.windowPeriod, fn: last, createEmpty: false)\n'
        '  |> derivative(unit: 1s, nonNegative: true)',
    {"h": 8, "w": 8, "x": 16, "y": dy}, "short", [nommer("validated_count", "écritures / s", VERT)]))
dy += 8
details.append({
    "id": next(ident), "type": "table",
    "title": "Tous les essais enregistrés dans InfluxDB (y compris non publiés, anciens et de diagnostic)",
    "description": "Écrit par scripts/sujet11/bilan.py à la fin de chaque essai. Ce périmètre est plus large que "
                   "preuves/ : il contient les essais isolés, les essais « ancien code » (pause d'environ 44 s) et "
                   "les essais de diagnostic (officiel = false). La comparaison de la section 5 n'utilise que preuves/.",
    "datasource": DS, "gridPos": {"h": 10, "w": 24, "x": 0, "y": dy},
    "targets": cible(B90 + '  |> filter(fn: (r) => r._measurement == "sujet11_essai")\n'
                     '  |> map(fn: (r) => ({r with version: if exists r.version then r.version else "non-notee"}))\n'
                     '  |> pivot(rowKey: ["_time", "mode", "semantique", "charge", "version"], columnKey: ["_field"], valueColumn: "_value")\n'
                     '  |> group()\n  |> keep(columns: ["_time", "id", "version", "pause_s", "trou_normal_s", '
                     '"retard_max", "lag_zero_s", "perdus", "trous", "doubles_effets", "doublons_absorbes", "officiel", "verdict", "raisons"])\n'
                     '  |> sort(columns: ["_time"], desc: true)'),
    "fieldConfig": {"defaults": {"noValue": ND, "custom": {"align": "left"}}, "overrides": [
        nommer("_time", "fin", unit="time:DD/MM HH:mm"), nommer("id", "essai"),
        nommer("version", "persister-valid"), nommer("pause_s", "pause (s)", decimals=2),
        nommer("trou_normal_s", "trou normal (s)", decimals=2), nommer("retard_max", "lag max"),
        nommer("lag_zero_s", "lag à 0 (s)", decimals=1), nommer("perdus", "perdus"), nommer("trous", "trous"),
        nommer("doubles_effets", "doubles effets"), nommer("doublons_absorbes", "relectures"),
        nommer("officiel", "bornes officielles", mappings=[{"type": "value", "options": {
            "true": {"text": "oui"}, "false": {"text": "non (diagnostic)"}}}]),
        nommer("verdict", "verdict", mappings=[{"type": "value", "options": {
            "REUSSITE": {"text": "Réussite", "color": VERT}, "ECHEC": {"text": "Échec", "color": ROUGE},
            "OBSERVATION": {"text": "Observation", "color": BLEU}, "INVALIDE": {"text": "Invalide", "color": GRIS}}}],
               **{"custom.cellOptions": {"type": "color-background", "mode": "basic"}}),
        nommer("raisons", "raisons"),
    ]},
    "options": {"showHeader": True, "cellHeight": "sm"},
})
dy += 10
details.append({
    "id": next(ident), "type": "table", "title": "Repères et phases des essais (24 h)",
    "description": "Repères posés par scripts/sujet11-maj.sh, et phases (lance, mise_a_jour, drainage, collecte, "
                   "termine, interrompu). Un essai sans « termine » est encore en cours ou a été interrompu.",
    "datasource": DS, "gridPos": {"h": 8, "w": 24, "x": 0, "y": dy},
    "targets": cible(BUCKET + '  |> range(start: -24h)\n'
                     '  |> filter(fn: (r) => (r._measurement == "sujet11_repere" and r._field == "texte")'
                     ' or (r._measurement == "sujet11_etat" and r._field == "phase"))\n'
                     '  |> group()\n  |> sort(columns: ["_time"], desc: true)\n  |> limit(n: 30)\n'
                     '  |> keep(columns: ["_time", "_value", "essai"])\n  |> rename(columns: {_value: "evenement"})'),
    "fieldConfig": {"defaults": {"noValue": "Aucun repère sur 24 h"}, "overrides": [
        nommer("_time", "heure", unit="time:HH:mm:ss"), nommer("evenement", "repère ou phase"),
        nommer("essai", "essai")]},
    "options": {"showHeader": True, "cellHeight": "sm"},
})
panels.append({"id": next(ident), "type": "row", "title": "6. Détails techniques (pour les questions) : groupe Kafka, "
               "lag, écritures, essais, repères", "collapsed": True, "panels": details,
               "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}})
y += 1

tableau = {
    "uid": "simulpix-sujet11", "title": "Simul-Pix - Sujet 11 (mise à jour de persister-valid)",
    "description": "Mettre à jour un service sans perdre de paiement : lancer, suivre et comprendre les essais.",
    "tags": ["simulpix", "sujet11"], "timezone": "browser", "schemaVersion": 39, "version": 2,
    "editable": True, "refresh": "5s", "time": {"from": "now-15m", "to": "now"},
    "graphTooltip": 1,
    "annotations": {"list": [
        {"builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"}, "enable": True,
         "hide": True, "iconColor": "rgba(0, 211, 255, 1)", "name": "Annotations & Alerts", "type": "dashboard"},
        {"datasource": DS, "enable": True, "iconColor": "purple", "name": "Étapes de l'essai",
         "target": {"query": B + '  |> filter(fn: (r) => r._measurement == "sujet11_repere" and r._field == "texte")',
                    "refId": "Reperes"},
         "textColumn": "_value", "tagsColumn": "essai"},
    ]},
    "panels": panels,
}
json.dump(tableau, open(sys.argv[1], "w"), indent=2, ensure_ascii=False)
print("ok", len(panels), "panneaux")
