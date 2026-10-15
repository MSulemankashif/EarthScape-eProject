"""
Alerting & notification engine
==============================
Implements the "Notifications and Alerts" functional requirement:

  * threshold rules per climate metric (hot / cold / pollution / storm ...)
  * anomaly-model alerts driven by the ML detector
  * configurable rules (add / remove / mute at runtime)
  * multi-channel dispatch: in-app + log file (email/webhook hooks included
    as stubs, since the eProject machine has no SMTP server)

Alerts are stored in the database layer and surfaced on the dashboard.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass, asdict
from datetime import datetime
from email.mime.text import MIMEText
from typing import Callable

from src.config import ALERT_THRESHOLDS
from src.utils.logger import get_logger

log = get_logger("earthscape.alerts")

SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


@dataclass
class Alert:
    """A single notification produced by the rule engine."""
    alert_id: str
    rule_name: str
    severity: str            # info | warning | critical
    station_id: str
    metric: str
    value: float
    threshold: float
    message: str
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AlertRule:
    """Configurable threshold rule."""
    name: str
    metric: str
    comparator: str          # "gt" or "lt"
    threshold: float
    severity: str = "warning"
    enabled: bool = True

    def evaluate(self, reading: dict) -> bool:
        if not self.enabled:
            return False
        value = reading.get(self.metric)
        if value is None:
            return False
        try:
            value = float(value)
        except (TypeError, ValueError):
            return False
        if self.comparator == "gt":
            return value > self.threshold
        if self.comparator == "lt":
            return value < self.threshold
        return False


class AlertEngine:
    """
    Evaluates readings against a rule set and dispatches notifications.

    Usage:
        engine = AlertEngine.default()
        alerts = engine.evaluate_reading(reading)
    """

    def __init__(self, rules: list[AlertRule] | None = None,
                 dispatcher: Callable[[Alert], None] | None = None):
        self.rules = rules if rules is not None else self.default_rules()
        self.dispatcher = dispatcher or self.log_dispatcher
        self.history: list[Alert] = []
        self._counter = 0

    # ------------------------------------------------------------------
    @staticmethod
    def default_rules() -> list[AlertRule]:
        """Rules derived from ALERT_THRESHOLDS in config.py."""
        rules: list[AlertRule] = []
        for metric, bounds in ALERT_THRESHOLDS.items():
            rules.append(AlertRule(
                name=f"{metric}_high",
                metric=metric,
                comparator="gt",
                threshold=bounds["high"],
                severity="critical" if metric in ("pm25", "temperature_c",
                                                  "wind_speed_kph") else "warning",
            ))
            rules.append(AlertRule(
                name=f"{metric}_low",
                metric=metric,
                comparator="lt",
                threshold=bounds["low"],
                severity="warning",
            ))
        return rules

    @classmethod
    def default(cls) -> "AlertEngine":
        return cls()

    # ------------------------------------------------------------------
    def add_rule(self, rule: AlertRule) -> None:
        self.rules = [r for r in self.rules if r.name != rule.name]
        self.rules.append(rule)
        log.info("Rule added: %s (%s %s %s, %s)",
                 rule.name, rule.metric, rule.comparator,
                 rule.threshold, rule.severity)

    def disable_rule(self, name: str) -> bool:
        for rule in self.rules:
            if rule.name == name:
                rule.enabled = False
                log.info("Rule disabled: %s", name)
                return True
        return False

    def enable_rule(self, name: str) -> bool:
        for rule in self.rules:
            if rule.name == name:
                rule.enabled = True
                return True
        return False

    def remove_rule(self, name: str) -> bool:
        before = len(self.rules)
        self.rules = [r for r in self.rules if r.name != name]
        return len(self.rules) != before

    def list_rules(self) -> list[dict]:
        return [asdict(r) for r in self.rules]

    # ------------------------------------------------------------------
    def evaluate_reading(self, reading: dict) -> list[Alert]:
        """Run every enabled rule against one reading, dispatch hits."""
        station = reading.get("station_id", "UNKNOWN")
        fired: list[Alert] = []
        for rule in self.rules:
            if not rule.evaluate(reading):
                continue
            self._counter += 1
            value = float(reading[rule.metric])
            word = "exceeded" if rule.comparator == "gt" else "dropped below"
            alert = Alert(
                alert_id=f"ALT-{self._counter:06d}",
                rule_name=rule.name,
                severity=rule.severity,
                station_id=station,
                metric=rule.metric,
                value=round(value, 2),
                threshold=rule.threshold,
                message=(f"{station}: {rule.metric} {word} threshold "
                         f"({value:.2f} vs {rule.threshold})"),
                timestamp=datetime.now().isoformat(timespec="seconds"),
            )
            self._dispatch(alert)
            fired.append(alert)
        return fired

    def evaluate_batch(self, readings: list[dict]) -> list[Alert]:
        out: list[Alert] = []
        for reading in readings:
            out.extend(self.evaluate_reading(reading))
        return out

    # ------------------------------------------------------------------
    def _dispatch(self, alert: Alert) -> None:
        self.history.append(alert)
        if len(self.history) > 2000:      # cap memory footprint
            del self.history[:500]
        try:
            self.dispatcher(alert)
        except Exception as exc:          # never break ingestion on alert failure
            log.error("Dispatcher failed for %s: %s", alert.alert_id, exc)

    # ------------------------------------------------------------------
    @staticmethod
    def log_dispatcher(alert: Alert) -> None:
        """Default channel: structured log line (always active)."""
        log.log(40 if alert.severity == "critical" else 30,
                "[%s] %s | %s | value=%s threshold=%s",
                alert.severity.upper(), alert.alert_id, alert.message,
                alert.value, alert.threshold)

    @staticmethod
    def email_dispatcher(to_addr: str, smtp_host: str = "localhost",
                         smtp_port: int = 25) -> Callable[[Alert], None]:
        """
        Optional SMTP channel. Provided for completeness per the requirement
        "configurable alerting mechanisms"; not exercised in the lab.
        """
        def _send(alert: Alert) -> None:
            msg = MIMEText(alert.message)
            msg["Subject"] = f"[EarthScape] {alert.severity.upper()} alert"
            msg["From"] = "earthscape-alerts@agency.local"
            msg["To"] = to_addr
            with smtplib.SMTP(smtp_host, smtp_port, timeout=5) as server:
                server.send_message(msg)
            log.info("Alert %s emailed to %s", alert.alert_id, to_addr)
        return _send

    @staticmethod
    def webhook_dispatcher(url: str) -> Callable[[Alert], None]:
        """Optional HTTP webhook channel (e.g. Slack / Teams incoming hook)."""
        import json
        import urllib.request

        def _send(alert: Alert) -> None:
            payload = json.dumps(asdict(alert)).encode("utf-8")
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5)
        return _send

    # ------------------------------------------------------------------
    def recent(self, limit: int = 50,
               min_severity: str = "info") -> list[dict]:
        """Newest-first alert history filtered by minimum severity."""
        threshold = SEVERITY_ORDER.get(min_severity, 0)
        items = [a for a in self.history
                 if SEVERITY_ORDER.get(a.severity, 0) >= threshold]
        return [a.to_dict() for a in reversed(items[-limit:])]

    def stats(self) -> dict:
        counts = {"info": 0, "warning": 0, "critical": 0}
        for alert in self.history:
            counts[alert.severity] = counts.get(alert.severity, 0) + 1
        return {"total": len(self.history), "by_severity": counts,
                "enabled_rules": sum(1 for r in self.rules if r.enabled),
                "total_rules": len(self.rules)}
