import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from app_state import CONTROL_STATE
from formatting import render_network_warning_banner
from payloads import build_fallback_payload, build_health_payload, emit_periodic_health_logs, utc_now_iso
from probes import safe_int
from scenario_control import (
    execute_control_action,
    get_scenario_config,
    is_scenario_port,
    read_form_value,
)
from sujet11_etat import essai_en_cours, rendre_etat
from sujet11_synthese import rendre_synthese
from sujet11_pilotage import (arreter, autoriser, lire_utilisateur, rendre_pilotage, rendre_statut,
                              reprise_au_demarrage, traduire_scenario)
from views_dashboard import render_dashboard_html
from views_scenario import render_scenario_html as render_scenario_view


def render_sparkline(history: list[dict[str, Any]], key: str, stroke: str, width: int = 240, height: int = 64) -> str:
    values = [float(item.get(key, 0.0) or 0.0) for item in history[-12:]]
    if not values:
        return "<div class='sparkline-empty'>n/a</div>"
    minimum = min(values)
    maximum = max(values)
    spread = maximum - minimum
    if spread == 0:
        spread = 1.0
    points = []
    count = max(len(values) - 1, 1)
    for index, value in enumerate(values):
        x = round((index / count) * (width - 8) + 4, 2)
        normalized = (value - minimum) / spread
        y = round(height - 6 - normalized * (height - 12), 2)
        points.append(f"{x},{y}")
    polyline = " ".join(points)
    return (
        f"<svg viewBox='0 0 {width} {height}' class='sparkline' aria-hidden='true'>"
        f"<polyline fill='none' stroke='{stroke}' stroke-width='3' points='{polyline}' />"
        "</svg>"
    )


def render_html(payload: dict[str, Any]) -> str:
    return render_dashboard_html(
        payload,
        safe_int=safe_int,
        render_sparkline=render_sparkline,
        render_network_warning_banner=render_network_warning_banner,
        format_control_message=format_control_message,
    )


def render_scenario_html(payload: dict[str, Any]) -> str:
    return render_scenario_view(
        payload,
        safe_int=safe_int,
        read_form_value=read_form_value,
        get_scenario_config=get_scenario_config,
        render_network_warning_banner=render_network_warning_banner,
        format_control_message=format_control_message,
    )


def format_control_message(action: str, result: str, control: dict[str, Any]) -> tuple[str, str]:
    if not action and not result:
        return "", "info"
    if action == "network_confirmation_missing":
        return "Perturbation réseau refusée : cochez la case « je confirme » avant de cliquer sur Appliquer.", "warning"
    if result == "accepted":
        return f"Action {action} lancee. La page se mettra a jour automatiquement.", "success"
    if result == "ok":
        return f"Action {action} terminee avec succes.", "success"
    if action == "busy" or result == "busy":
        busy_message = str(control.get("busy_message") or "une autre action est deja en cours")
        return busy_message.capitalize() + ".", "warning"
    return f"Action {action or 'inconnue'} en erreur. Voir la sortie ci-dessous.", "error"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        route = urlsplit(self.path).path
        query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        current_port = int(self.server.server_address[1])
        if route in ("/sujet11/pilotage", "/sujet11/pilotage/statut"):
            # Contrôle des scénarios expérimentaux (cadre du tableau de bord Grafana).
            workspace = os.getenv("SIMULPIX_WORKSPACE_DIR", "/workspace")
            utilisateur = lire_utilisateur(self.headers.get("Cookie", ""))
            if route == "/sujet11/pilotage":
                page = rendre_pilotage(workspace, utilisateur, read_form_value(query, "message", ""),
                                       read_form_value(query, "genre", ""))
            else:
                try:
                    services = build_health_payload().get("services")
                except Exception:
                    services = None
                page = rendre_statut(workspace, utilisateur, services)
            corps = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)
            return
        if route == "/sujet11/synthese":
            # Cadres « Vue d'ensemble », « Déroulement » et « Intégrité » du tableau de bord.
            workspace = os.getenv("SIMULPIX_WORKSPACE_DIR", "/workspace")
            page = rendre_synthese(read_form_value(query, "vue", "ensemble"), workspace,
                                   essai_en_cours(workspace), read_form_value(query, "essai", "")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
            return
        if route == "/sujet11/etat":
            # Cadre du panneau « Pilotage » de Grafana (sujet 11).
            page = rendre_etat(
                essai_en_cours(os.getenv("SIMULPIX_WORKSPACE_DIR", "/workspace")),
                resultat=read_form_value(query, "resultat", ""),
                mode=read_form_value(query, "mode", ""),
                semantique=read_form_value(query, "semantique", ""),
                charge=read_form_value(query, "charge", ""),
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
            return
        allowed_routes = {"/", "/ui", "/scenario", "/health", "/health/services", "/health/details"}
        if route not in allowed_routes:
            self.send_response(404)
            self.end_headers()
            return
        try:
            body = build_health_payload()
        except Exception as exc:
            body = build_fallback_payload(exc, route)
        body["ui"] = {
            "message": read_form_value(query, "result", ""),
            "action": read_form_value(query, "control_action", ""),
            "scenario": read_form_value(query, "scenario", ""),
            "total_messages": read_form_value(query, "total_messages", ""),
            "rate_per_second": read_form_value(query, "rate_per_second", ""),
            "decision_sla_seconds": read_form_value(query, "decision_sla_seconds", "10"),
            "validator_workers": read_form_value(query, "validator_workers", "1"),
            "decision_engine_workers": read_form_value(query, "decision_engine_workers", "1"),
            "producer_semantics": read_form_value(query, "producer_semantics", ""),
            "consumer_semantics": read_form_value(query, "consumer_semantics", ""),
            "consumer_commit_strategy": read_form_value(query, "consumer_commit_strategy", ""),
            "consumer_auto_commit": read_form_value(query, "consumer_auto_commit", ""),
            "consumer_max_poll_interval_ms": read_form_value(query, "consumer_max_poll_interval_ms", ""),
            "consumer_commit_batch_size": read_form_value(query, "consumer_commit_batch_size", ""),
            "producer_acks": read_form_value(query, "producer_acks", ""),
            "producer_retries": read_form_value(query, "producer_retries", ""),
            "traffic_model": read_form_value(query, "traffic_model", ""),
            "match_count": read_form_value(query, "match_count", ""),
            "stadium_capacity": read_form_value(query, "stadium_capacity", ""),
            "pix_usage_rate": read_form_value(query, "pix_usage_rate", ""),
            "peak_share": read_form_value(query, "peak_share", ""),
            "peak_window_minutes": read_form_value(query, "peak_window_minutes", ""),
            "total_window_minutes": read_form_value(query, "total_window_minutes", ""),
            "time_compression_factor": read_form_value(query, "time_compression_factor", ""),
            "network_profile": read_form_value(query, "network_profile", ""),
            "network_target_service": read_form_value(query, "network_target_service", ""),
            "network_delay_ms": read_form_value(query, "network_delay_ms", ""),
            "network_jitter_ms": read_form_value(query, "network_jitter_ms", ""),
            "network_loss_percent": read_form_value(query, "network_loss_percent", ""),
            "network_rate_kbit": read_form_value(query, "network_rate_kbit", ""),
        }
        if route == "/scenario" or (route == "/" and is_scenario_port(current_port)):
            payload = render_scenario_html(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if route in ("/", "/ui"):
            payload = render_html(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        route = urlsplit(self.path).path
        if route != "/control":
            self.send_response(404)
            self.end_headers()
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length).decode("utf-8")
            form = parse_qs(body, keep_blank_values=True)
            action = read_form_value(form, "action", "")
            if action.startswith("sujet11_"):
                # Sujet 11 : origine, session Grafana (Editor ou Admin) et confirmation
                # sont vérifiées pour toute demande, d'où qu'elle vienne.
                self._sujet11(action, form)
                return
            result, action_label = execute_control_action(form)
        except Exception as exc:
            CONTROL_STATE["status"] = "error"
            CONTROL_STATE["last_result"] = "error"
            CONTROL_STATE["last_finished_at"] = utc_now_iso()
            CONTROL_STATE["last_output"] = [repr(exc)]
            action_label = "control_exception"
            result = "error"
            form = {}
        scenario = read_form_value(form, "scenario", "")
        return_view = read_form_value(form, "return_view", "")
        if return_view == "sujet11":
            # Le formulaire Grafana vise le cadre de l'état : on y affiche le résultat du clic.
            query = urlencode({
                "resultat": result,
                "mode": read_form_value(form, "mode", ""),
                "semantique": read_form_value(form, "semantique", ""),
                "charge": read_form_value(form, "charge", ""),
            })
            self.send_response(303)
            self.send_header("Location", "/sujet11/etat?" + query)
            self.end_headers()
            return
        if return_view == "scenario":
            query = urlencode(
                {
                    "control_action": action_label,
                    "result": result,
                    "total_messages": read_form_value(form, "total_messages", ""),
                    "rate_per_second": read_form_value(form, "rate_per_second", ""),
                    "decision_sla_seconds": read_form_value(form, "decision_sla_seconds", "10"),
                    "validator_workers": read_form_value(form, "validator_workers", "1"),
                    "decision_engine_workers": read_form_value(form, "decision_engine_workers", "1"),
                    "producer_semantics": read_form_value(form, "producer_semantics", ""),
                    "consumer_semantics": read_form_value(form, "consumer_semantics", ""),
                    "consumer_commit_strategy": read_form_value(form, "consumer_commit_strategy", ""),
                    "consumer_auto_commit": read_form_value(form, "consumer_auto_commit", ""),
                    "consumer_max_poll_interval_ms": read_form_value(form, "consumer_max_poll_interval_ms", ""),
                    "consumer_commit_batch_size": read_form_value(form, "consumer_commit_batch_size", ""),
                    "producer_acks": read_form_value(form, "producer_acks", ""),
                    "producer_retries": read_form_value(form, "producer_retries", ""),
                    "traffic_model": read_form_value(form, "traffic_model", ""),
                    "match_count": read_form_value(form, "match_count", ""),
                    "stadium_capacity": read_form_value(form, "stadium_capacity", ""),
                    "pix_usage_rate": read_form_value(form, "pix_usage_rate", ""),
                    "peak_share": read_form_value(form, "peak_share", ""),
                    "peak_window_minutes": read_form_value(form, "peak_window_minutes", ""),
                    "total_window_minutes": read_form_value(form, "total_window_minutes", ""),
                    "time_compression_factor": read_form_value(form, "time_compression_factor", ""),
                    "network_profile": read_form_value(form, "network_profile", ""),
                    "network_target_service": read_form_value(form, "network_target_service", ""),
                    "network_delay_ms": read_form_value(form, "network_delay_ms", ""),
                    "network_jitter_ms": read_form_value(form, "network_jitter_ms", ""),
                    "network_loss_percent": read_form_value(form, "network_loss_percent", ""),
                    "network_rate_kbit": read_form_value(form, "network_rate_kbit", ""),
                }
            )
            target = "/scenario" + (f"?{query}" if query else "")
        else:
            target = "/?control_action=" + action_label + "&result=" + result
        self.send_response(303)
        self.send_header("Location", target)
        self.end_headers()

    def _sujet11(self, action: str, form: dict) -> None:
        workspace = os.getenv("SIMULPIX_WORKSPACE_DIR", "/workspace")
        ok, message = traduire_scenario(form)
        utilisateur = None
        if ok:
            ok, message, utilisateur = autoriser(action, form, {k: v for k, v in self.headers.items()})
        if ok and action == "sujet11_arreter":
            resultat, message = arreter(workspace)
            genre = "info" if resultat == "stop" else "erreur"
        elif ok and action == "sujet11_essai":
            form["_qui"] = [utilisateur["login"]]
            resultat, _ = execute_control_action(form)
            message, genre = {
                "accepted": ("Essai lancé. Le suivi apparaît à droite dans quelques secondes.", "ok"),
                "busy": ("Refusé : un essai est déjà en cours. Attendez sa fin.", "erreur"),
            }.get(resultat, ("Refusé : paramètres non acceptés ou erreur au lancement.", "erreur"))
        elif ok:
            message, genre = "Refusé : action inconnue.", "erreur"
        else:
            genre = "erreur"
        if read_form_value(form, "return_view", "") == "sujet11":
            # ancien formulaire du tableau de bord : réponse dans le petit cadre d'état
            cible = "/sujet11/etat?" + urlencode({"resultat": "accepted" if genre == "ok" else "error"})
        else:
            cible = "/sujet11/pilotage?" + urlencode({"message": message, "genre": genre})
        self.send_response(303)
        self.send_header("Location", cible)
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> int:
    port = int(os.getenv("SIMULPIX_PORT", "8082"))
    scenario_port = int(os.getenv("SIMULPIX_SCENARIO_PORT", "8083"))
    threading.Thread(target=emit_periodic_health_logs, daemon=True).start()
    # Un essai lancé par ce service avant un redémarrage n'a pas pu finir : on le dit.
    repris = reprise_au_demarrage(os.getenv("SIMULPIX_WORKSPACE_DIR", "/workspace"))
    if repris:
        print(json.dumps({"event": "sujet11_essai_interrompu_par_redemarrage", "sortie": repris}), flush=True)
    if scenario_port != port:
        threading.Thread(
            target=lambda: ThreadingHTTPServer(("0.0.0.0", scenario_port), Handler).serve_forever(),
            daemon=True,
        ).start()
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
