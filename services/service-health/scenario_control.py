from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any

from app_state import CONTROL_LOCK, CONTROL_STATE
from sujet11_etat import essai_en_cours
from config import (
    ALLOWED_CONSUMER_SEMANTICS,
    ALLOWED_PRODUCER_SEMANTICS,
    ALLOWED_SCENARIOS,
    ALLOWED_TRAFFIC_MODELS,
    NETWORK_PROFILES,
    SCENARIO_CATALOG,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_form_value(form: dict[str, list[str]], name: str, default: str) -> str:
    values = form.get(name)
    if not values:
        return default
    return values[0]


def sanitize_positive_int(raw_value: str, default: int, minimum: int = 1, maximum: int = 10000) -> int:
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


def get_scenario_config(name: str) -> dict[str, Any]:
    if str(name).startswith("football_match_peak"):
        name = "football_match_peak"
    return SCENARIO_CATALOG.get(name, SCENARIO_CATALOG["nominal"])


def normalize_scenario_name(name: str | None) -> str:
    scenario = str(name or "").strip()
    if scenario.startswith("football_match_peak"):
        return "football_match_peak"
    return scenario if scenario in ALLOWED_SCENARIOS else "nominal"


def grafana_dashboard_link(uid: str, slug: str) -> str:
    base_url = os.getenv("SIMULPIX_GRAFANA_PUBLIC_URL", "http://localhost:3000").rstrip("/")
    return f"{base_url}/d/{uid}/{slug}"


def is_scenario_port(port: int) -> bool:
    return port == int(os.getenv("SIMULPIX_SCENARIO_PORT", "8083"))


def build_control_job(form: dict[str, list[str]]) -> tuple[bool, str, list[str] | None, dict[str, str] | None]:
    action = read_form_value(form, "action", "")
    if action == "reset":
        return True, "reset_scenario", ["/bin/sh", "./scripts/reset-scenario.sh"], None

    if action == "stop_scenario":
        return True, "stop_scenario", ["/bin/sh", "./scripts/stop-scenario.sh"], None

    if action == "stop_platform":
        return True, "stop_platform", ["/bin/sh", "./scripts/stop-platform.sh"], None

    if action == "apply_network_profile":
        confirm_apply = read_form_value(form, "confirm_network_apply", "").strip().lower()
        if confirm_apply not in ("on", "1", "true", "yes"):
            CONTROL_STATE["status"] = "error"
            CONTROL_STATE["last_result"] = "error"
            CONTROL_STATE["last_output"] = ["network perturbation refused: explicit confirmation missing"]
            return False, "network_confirmation_missing", None, None
        profile = read_form_value(form, "network_profile", "kafka_latency")
        profile_config = NETWORK_PROFILES.get(profile)
        if profile_config is None:
            CONTROL_STATE["status"] = "error"
            CONTROL_STATE["last_result"] = "error"
            CONTROL_STATE["last_output"] = [f"unsupported network profile: {profile}"]
            return False, f"unsupported_network_profile:{profile}", None, None
        target_service = read_form_value(form, "network_target_service", str(profile_config["defaults"]["target_service"]))
        extra_env = {
            "SIMULPIX_NETWORK_DELAY_MS_OVERRIDE": read_form_value(form, "network_delay_ms", str(profile_config["defaults"]["delay_ms"])),
            "SIMULPIX_NETWORK_JITTER_MS_OVERRIDE": read_form_value(form, "network_jitter_ms", str(profile_config["defaults"]["jitter_ms"])),
            "SIMULPIX_NETWORK_LOSS_PERCENT_OVERRIDE": read_form_value(form, "network_loss_percent", str(profile_config["defaults"]["loss_percent"])),
            "SIMULPIX_NETWORK_RATE_KBIT_OVERRIDE": read_form_value(form, "network_rate_kbit", str(profile_config["defaults"]["rate_kbit"])),
        }
        return (
            True,
            f"apply_network_profile:{profile}:{target_service}",
            ["/bin/sh", "./scripts/network-perturb.sh", profile, target_service],
            extra_env,
        )

    if action == "reset_network_profile":
        return True, "reset_network_profile", ["/bin/sh", "./scripts/network-reset.sh"], None

    if action == "sujet11_essai":
        # Sujet 11 : mise à jour de persister-valid sous flux, lancée depuis Grafana.
        mode = read_form_value(form, "mode", "minimale").strip()
        semantique = read_form_value(form, "semantique", "at_least_once").strip()
        charge = read_form_value(form, "charge", "normale").strip()
        if mode not in {"observee", "minimale", "amelioree", "crash"} or semantique not in {"at_least_once", "at_most_once", "exactly_once_pg"} \
                or charge not in {"normale", "forte"}:
            CONTROL_STATE["status"] = "error"
            CONTROL_STATE["last_result"] = "error"
            CONTROL_STATE["last_output"] = [f"sujet11 : paramètres refusés ({mode}, {semantique}, {charge})"]
            return False, "sujet11_parametres_refuses", None, None
        # Débits de la campagne : 20 Pix/s en charge normale, 60 Pix/s en forte charge.
        debit_defaut = "60" if charge == "forte" else "20"
        debit = str(sanitize_positive_int(read_form_value(form, "debit", debit_defaut) or debit_defaut,
                                          int(debit_defaut), 1, 200))
        borne = str(sanitize_positive_int(read_form_value(form, "borne", "60"), 60, 1, 600))
        command = ["/bin/sh", "./scripts/sujet11-maj.sh", "--mode", mode, "--semantique", semantique,
                   "--charge", charge, "--debit", debit, "--borne", borne]
        if mode == "crash":
            # Panne : réglage fixe, celui du protocole. 80 ms entre commit et écriture
            # pour que le SIGKILL tombe dans la fenêtre ; à 80 ms par message
            # l'instance traite environ 12 Pix/s, d'où 10 Pix/s et 180 s de drainage.
            charge = "ralentie"
            command = ["/bin/sh", "./scripts/sujet11-maj.sh", "--mode", mode, "--semantique", semantique,
                       "--charge", charge, "--debit", "10", "--ralenti", "80",
                       "--drainage-max", "180", "--borne", borne]
        # Un essai dure environ 5 min : plus que la limite par défaut des actions (240 s).
        extra_env = {"SUJET11_INFLUX_URL": "http://influxdb:8086", "SIMULPIX_CONTROL_TIMEOUT_SECONDS": "900"}
        return True, f"sujet11_essai:{mode}:{semantique}:{charge}", command, extra_env

    if action == "run_scenario":
        scenario = read_form_value(form, "scenario", "nominal")
        raw_total = read_form_value(form, "total_messages", "").strip()
        raw_rate = read_form_value(form, "rate_per_second", "").strip()
        producer_semantics = read_form_value(form, "producer_semantics", "at_least_once").strip().lower() or "at_least_once"
        consumer_semantics = read_form_value(form, "consumer_semantics", "at_least_once").strip().lower() or "at_least_once"
        if producer_semantics not in ALLOWED_PRODUCER_SEMANTICS:
            producer_semantics = "at_least_once"
        if consumer_semantics not in ALLOWED_CONSUMER_SEMANTICS:
            consumer_semantics = "at_least_once"
        raw_consumer_commit_strategy = read_form_value(form, "consumer_commit_strategy", "after").strip().lower() or "after"
        raw_consumer_auto_commit = read_form_value(form, "consumer_auto_commit", "off").strip().lower() or "off"
        consumer_commit_strategy = raw_consumer_commit_strategy if raw_consumer_commit_strategy in {"before", "after"} else "after"
        consumer_auto_commit = "on" if raw_consumer_auto_commit in {"on", "1", "true", "yes"} else "off"
        consumer_max_poll_interval_ms = str(
            sanitize_positive_int(read_form_value(form, "consumer_max_poll_interval_ms", "300000"), 300000, 1000, 3600000)
        )
        consumer_commit_batch_size = str(
            sanitize_positive_int(read_form_value(form, "consumer_commit_batch_size", "1"), 1, 1, 1000000)
        )
        if consumer_semantics == "at_most_once":
            consumer_auto_commit = "off"
            consumer_commit_strategy = "before"
            consumer_commit_batch_size = "1"
        elif consumer_semantics == "at_least_once":
            consumer_auto_commit = "off"
            consumer_commit_strategy = "after"
            consumer_commit_batch_size = "1"
        elif consumer_semantics == "exactly_once_kafka":
            consumer_auto_commit = "off"
            consumer_commit_strategy = "after"
            consumer_commit_batch_size = "1"
        producer_acks = read_form_value(form, "producer_acks", "all").strip() or "all"
        producer_retries = str(sanitize_positive_int(read_form_value(form, "producer_retries", "0"), 0, 0, 1000000000))
        decision_sla_seconds = str(sanitize_positive_int(read_form_value(form, "decision_sla_seconds", "10"), 10, 3, 3600))
        validator_workers = str(
            sanitize_positive_int(read_form_value(form, "validator_workers", "1"), 1, 1, 64)
        )
        decision_engine_workers = str(
            sanitize_positive_int(read_form_value(form, "decision_engine_workers", "1"), 1, 1, 64)
        )
        traffic_model = read_form_value(form, "traffic_model", "bursty").strip().lower() or "bursty"
        if traffic_model not in ALLOWED_TRAFFIC_MODELS:
            traffic_model = "bursty"
        total = "" if raw_total == "" else str(sanitize_positive_int(raw_total, 100, 1, 1000000000))
        rate = "" if raw_rate == "" else str(sanitize_positive_int(raw_rate, 10, 0, 1000000000))
        if scenario not in ALLOWED_SCENARIOS:
            CONTROL_STATE["status"] = "error"
            CONTROL_STATE["last_result"] = "error"
            CONTROL_STATE["last_output"] = [f"unsupported scenario: {scenario}"]
            return False, f"unsupported_scenario:{scenario}", None, None
        extra_env = {
            "SIMULPIX_KAFKA_PRODUCER_SEMANTICS": producer_semantics,
            "SIMULPIX_KAFKA_CONSUMER_SEMANTICS": consumer_semantics,
            "SIMULPIX_KAFKA_CONSUMER_COMMIT_STRATEGY": consumer_commit_strategy,
            "SIMULPIX_KAFKA_CONSUMER_AUTO_COMMIT": consumer_auto_commit,
            "SIMULPIX_KAFKA_MAX_POLL_INTERVAL_MS": consumer_max_poll_interval_ms,
            "SIMULPIX_KAFKA_COMMIT_BATCH_SIZE": consumer_commit_batch_size,
            "SIMULPIX_KAFKA_ACKS": producer_acks,
            "SIMULPIX_KAFKA_RETRIES": producer_retries,
            "SIMULPIX_DECISION_SLA_SECONDS": decision_sla_seconds,
            "SIMULPIX_VALIDATOR_WORKERS": validator_workers,
            "SIMULPIX_DECISION_ENGINE_WORKERS": decision_engine_workers,
            "SIMULPIX_TRAFFIC_MODEL": traffic_model,
        }
        if scenario == "football_match_peak":
            extra_env |= {
                "SIMULPIX_MATCH_COUNT_OVERRIDE": str(sanitize_positive_int(read_form_value(form, "match_count", "10"), 10, 1, 1000)),
                "SIMULPIX_STADIUM_CAPACITY_OVERRIDE": str(
                    sanitize_positive_int(read_form_value(form, "stadium_capacity", "44000"), 44000, 1, 200000)
                ),
                "SIMULPIX_PIX_USAGE_RATE_OVERRIDE": read_form_value(form, "pix_usage_rate", "0.05"),
                "SIMULPIX_PEAK_SHARE_OVERRIDE": read_form_value(form, "peak_share", "0.30"),
                "SIMULPIX_PEAK_WINDOW_MINUTES_OVERRIDE": read_form_value(form, "peak_window_minutes", "15"),
                "SIMULPIX_TOTAL_WINDOW_MINUTES_OVERRIDE": read_form_value(form, "total_window_minutes", "240"),
                "SIMULPIX_TIME_COMPRESSION_FACTOR_OVERRIDE": read_form_value(form, "time_compression_factor", "10"),
            }
        return True, f"run_scenario:{scenario}", ["/bin/sh", "./scripts/run-scenario.sh", scenario, total, rate], extra_env

    if action == "replay_rejected":
        limit = sanitize_positive_int(read_form_value(form, "replay_limit", "10"), 10, 1, 500)
        return True, f"replay_rejected:{limit}", ["/bin/sh", "./scripts/replay-rejected.sh", str(limit)], None

    if action == "replay_corrected":
        limit = sanitize_positive_int(read_form_value(form, "corrected_limit", "5"), 5, 1, 500)
        return True, f"replay_corrected:{limit}", ["/bin/sh", "./scripts/replay-corrected.sh", str(limit)], None

    CONTROL_STATE["status"] = "error"
    CONTROL_STATE["last_result"] = "error"
    CONTROL_STATE["last_output"] = [f"unsupported action: {action}"]
    return False, f"unsupported_action:{action}", None, None


def run_control_command(command: list[str], workdir: str, extra_env: dict[str, str] | None = None) -> tuple[bool, list[str]]:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    CONTROL_STATE["status"] = "running"
    CONTROL_STATE["busy_message"] = "action en cours"
    CONTROL_STATE["last_started_at"] = utc_now_iso()
    try:
        completed = subprocess.run(
            command,
            cwd=workdir,
            env=env,
            capture_output=True,
            text=True,
            timeout=int(env.get("SIMULPIX_CONTROL_TIMEOUT_SECONDS", "240")),
            check=False,
        )
        lines = [line for line in (completed.stdout + "\n" + completed.stderr).splitlines() if line.strip()]
        output = lines[-20:] if lines else ["[simulpix] no output"]
        CONTROL_STATE["status"] = "ok" if completed.returncode == 0 else "error"
        CONTROL_STATE["last_result"] = "ok" if completed.returncode == 0 else "error"
        CONTROL_STATE["last_output"] = output
        return completed.returncode == 0, output
    except Exception as exc:
        output = [repr(exc)]
        CONTROL_STATE["status"] = "error"
        CONTROL_STATE["last_result"] = "error"
        CONTROL_STATE["last_output"] = output
        return False, output
    finally:
        CONTROL_STATE["busy_message"] = None
        CONTROL_STATE["last_finished_at"] = utc_now_iso()


def _apply_traffic_shaper_update(rate: str, traffic_model: str) -> tuple[bool, list[str]]:
    shaper_url = os.getenv("SIMULPIX_PIX_TRAFFIC_SHAPER_URL", "http://pix-traffic-shaper:8089/health")
    base_url = shaper_url.rsplit("/", 1)[0]
    update_url = base_url + "/update"
    payload: dict[str, Any] = {}
    if rate:
        payload["rate_per_second"] = float(rate)
    if traffic_model:
        payload["traffic_model"] = traffic_model
    if not payload:
        return True, ["[simulpix] rien à mettre à jour"]
    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(update_url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if result.get("status") == "ok":
            parts = [f"rate={rate}" if rate else "", f"model={traffic_model}" if traffic_model else ""]
            return True, [f"[simulpix] traffic shaper mis à jour : {', '.join(p for p in parts if p)}"]
        return False, [f"[simulpix] réponse inattendue : {result}"]
    except Exception as exc:
        return False, [f"[simulpix] erreur mise à jour traffic shaper : {exc}"]


def execute_control_action(form: dict[str, list[str]]) -> tuple[str, str]:
    action = read_form_value(form, "action", "")

    if action == "sujet11_essai":
        # Refus avant tout lancement si un essai tient le verrou, qu'il vienne
        # d'un bouton ou du terminal : le script le refuserait de toute façon.
        en_cours = essai_en_cours(os.getenv("SIMULPIX_WORKSPACE_DIR", "/workspace"))
        if en_cours is not None:
            CONTROL_STATE["status"] = "busy"
            CONTROL_STATE["last_result"] = "busy"
            CONTROL_STATE["busy_message"] = f"essai en cours : {en_cours['id']}"
            CONTROL_STATE["last_output"] = [f"[sujet11] un autre essai est en cours ({en_cours['id']})"]
            return "busy", "sujet11_occupe"

    if action == "update_scenario":
        raw_rate = read_form_value(form, "rate_per_second", "").strip()
        raw_model = read_form_value(form, "traffic_model", "").strip()
        rate = "" if raw_rate == "" else str(sanitize_positive_int(raw_rate, 10, 0, 1_000_000_000))
        model = raw_model if raw_model in ALLOWED_TRAFFIC_MODELS else ""
        ok, output = _apply_traffic_shaper_update(rate, model)
        CONTROL_STATE["status"] = "ok" if ok else "error"
        CONTROL_STATE["last_result"] = "ok" if ok else "error"
        CONTROL_STATE["last_action"] = "update_scenario"
        CONTROL_STATE["last_output"] = output
        CONTROL_STATE["last_finished_at"] = utc_now_iso()
        return ("ok" if ok else "error"), "update_scenario"

    if not CONTROL_LOCK.acquire(blocking=False):
        CONTROL_STATE["status"] = "busy"
        CONTROL_STATE["last_result"] = "busy"
        CONTROL_STATE["busy_message"] = "une autre action est deja en cours"
        CONTROL_STATE["last_output"] = ["[simulpix] another control action is already running"]
        return "busy", "busy"

    workspace = os.getenv("SIMULPIX_WORKSPACE_DIR", "/workspace")
    ok, action_label, command, extra_env = build_control_job(form)
    if not ok or command is None:
        CONTROL_LOCK.release()
        return "error", action_label

    CONTROL_STATE["status"] = "running"
    CONTROL_STATE["last_action"] = action_label
    CONTROL_STATE["last_result"] = "accepted"
    CONTROL_STATE["busy_message"] = "action en cours"
    CONTROL_STATE["last_started_at"] = utc_now_iso()
    CONTROL_STATE["last_finished_at"] = None
    CONTROL_STATE["last_output"] = [f"[simulpix] action queued: {action_label}"]

    def worker() -> None:
        try:
            if action_label.startswith("sujet11_essai"):
                # Sujet 11 : exécution arrêtable proprement, avec journal et historique
                # (sujet11_pilotage.py). Même commande, même liste blanche.
                from sujet11_pilotage import executer_essai
                env = os.environ.copy() | {"SIMULPIX_KEEP_HEALTH_RUNNING": "1"} | (extra_env or {})
                contexte = {"lancement": time.strftime("%Y%m%d-%H%M%S"), "qui": read_form_value(form, "_qui", "?"),
                            "scenario": read_form_value(form, "scenario", read_form_value(form, "mode", "")),
                            "semantique": read_form_value(form, "semantique", ""),
                            "charge": read_form_value(form, "charge", "")}
                CONTROL_STATE["last_started_at"] = utc_now_iso()
                ok, sortie = executer_essai(command, workspace, env, workspace, contexte,
                                            int(env.get("SIMULPIX_CONTROL_TIMEOUT_SECONDS", "900")))
                CONTROL_STATE["status"] = CONTROL_STATE["last_result"] = "ok" if ok else "error"
                CONTROL_STATE["last_output"] = sortie
                CONTROL_STATE["last_finished_at"] = utc_now_iso()
                CONTROL_STATE["busy_message"] = None
            else:
                run_control_command(
                    command,
                    workspace,
                    {"SIMULPIX_KEEP_HEALTH_RUNNING": "1"} | (extra_env or {}),
                )
        finally:
            CONTROL_LOCK.release()

    threading.Thread(target=worker, daemon=True).start()
    return "accepted", action_label
