"""Tests for the alerting engine."""

import pytest

from src.alerts import AlertEngine, AlertRule


def make_reading(**overrides):
    reading = {
        "station_id": "STN-001",
        "temperature_c": 30.0,
        "humidity_pct": 55.0,
        "co2_ppm": 415.0,
        "pm25": 40.0,
        "wind_speed_kph": 12.0,
        "rainfall_mm": 2.0,
        "sea_level_mm": 0.0,
    }
    reading.update(overrides)
    return reading


def test_default_rules_exist():
    engine = AlertEngine.default()
    names = {r.name for r in engine.rules}
    assert "temperature_c_high" in names
    assert "pm25_high" in names
    assert len(engine.rules) >= 10


def test_threshold_fires():
    engine = AlertEngine.default()
    alerts = engine.evaluate_reading(make_reading(temperature_c=55.0))
    hit = [a for a in alerts if a.metric == "temperature_c"]
    assert hit, "extreme heat must trigger an alert"
    assert hit[0].severity == "critical"
    assert "STN-001" in hit[0].message


def test_normal_reading_is_quiet():
    engine = AlertEngine.default()
    alerts = engine.evaluate_reading(make_reading())
    assert alerts == []


def test_low_threshold():
    engine = AlertEngine.default()
    alerts = engine.evaluate_reading(make_reading(temperature_c=-40.0))
    assert any(a.metric == "temperature_c" and a.rule_name.endswith("_low")
               for a in alerts)


def test_custom_rule_add_and_evaluate():
    engine = AlertEngine.default()
    engine.add_rule(AlertRule("co2_watch", "co2_ppm", "gt", 400.0, "warning"))
    alerts = engine.evaluate_reading(make_reading(co2_ppm=430.0))
    assert any(a.rule_name == "co2_watch" for a in alerts)


def test_rule_disable_enable_remove():
    engine = AlertEngine.default()
    engine.add_rule(AlertRule("temp_watch", "temperature_c", "gt", 10.0))
    assert engine.disable_rule("temp_watch")
    assert engine.evaluate_reading(make_reading(temperature_c=40.0)) == []
    assert engine.enable_rule("temp_watch")
    assert engine.evaluate_reading(make_reading(temperature_c=40.0))
    assert engine.remove_rule("temp_watch")
    assert not engine.remove_rule("temp_watch")


def test_missing_value_is_skipped():
    engine = AlertEngine.default()
    reading = make_reading()
    reading["temperature_c"] = None
    assert engine.evaluate_reading(reading) == []


def test_non_numeric_value_is_tolerated():
    engine = AlertEngine.default()
    reading = make_reading(temperature_c="not-a-number")
    assert engine.evaluate_reading(reading) == []


def test_history_and_stats():
    engine = AlertEngine.default()
    engine.evaluate_reading(make_reading(temperature_c=60.0, pm25=500.0))
    stats = engine.stats()
    assert stats["total"] >= 2
    assert stats["by_severity"]["critical"] >= 2

    recent = engine.recent(min_severity="critical")
    assert all(a["severity"] == "critical" for a in recent)


def test_custom_dispatcher_is_used():
    seen = []
    # Only the custom rule (no default rules) so the count is deterministic
    engine = AlertEngine(rules=[], dispatcher=seen.append)
    engine.add_rule(AlertRule("t", "temperature_c", "gt", 10.0))
    engine.evaluate_reading(make_reading(temperature_c=99.0))
    assert len(seen) == 1
    assert seen[0].value == 99.0
    assert seen[0].rule_name == "t"
