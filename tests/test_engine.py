"""Tests fuer DF-HIVE-TEAM-SCORE Engine [CRUX-MK]."""
import math
from pathlib import Path

import pytest

from engine import (
    AGENT_CLASSES,
    AdapterOrchestrator,
    AuditLogger,
    H_MAX,
    HiveAuditResult,
    K16Mutex,
    RoleDiversityTracker,
    Severity,
    ShannonEntropyCalculator,
    TeamScoreEngine,
    run_hive_audit,
)


# ============================================================
# ShannonEntropyCalculator
# ============================================================

def test_shannon_entropy_uniform_distribution() -> None:
    """10 verschiedene Klassen gleichverteilt -> H ~ log2(10) = H_MAX."""
    calc = ShannonEntropyCalculator()
    items = list(AGENT_CLASSES)  # je 1x
    result = calc.calculate(items)
    assert result.total_count == 10
    assert math.isclose(result.h_raw, math.log2(10), abs_tol=0.01)
    assert math.isclose(result.h_normalized, 1.0, abs_tol=0.01)


def test_shannon_entropy_single_class() -> None:
    """Alle aus 1 Klasse -> H = 0, h_norm = 0."""
    calc = ShannonEntropyCalculator()
    items = ["REVENUE"] * 5
    result = calc.calculate(items)
    assert result.h_raw == 0.0
    assert result.h_normalized == 0.0
    assert result.total_count == 5


def test_shannon_entropy_empty() -> None:
    """Leere Liste -> Default-EntropyResult."""
    calc = ShannonEntropyCalculator()
    result = calc.calculate([])
    assert result.total_count == 0
    assert result.h_raw == 0.0
    assert result.h_normalized == 0.0


def test_shannon_entropy_two_classes_equal() -> None:
    """2 Klassen gleichverteilt -> H = 1 Bit."""
    calc = ShannonEntropyCalculator()
    items = ["REVENUE", "HOUSEKEEPING"]
    result = calc.calculate(items)
    assert math.isclose(result.h_raw, 1.0, abs_tol=0.01)


# ============================================================
# RoleDiversityTracker
# ============================================================

def test_diversity_tracker_full_coverage() -> None:
    """10/10 Klassen -> OK."""
    tracker = RoleDiversityTracker()
    dist = {cls: 1 for cls in AGENT_CLASSES}
    report = tracker.evaluate(dist)
    assert report.diversity_ratio == 1.0
    assert report.coverage_severity == Severity.OK
    assert len(report.classes_missing) == 0


def test_diversity_tracker_empty() -> None:
    """0/10 Klassen -> VETO."""
    tracker = RoleDiversityTracker()
    report = tracker.evaluate({})
    assert report.diversity_ratio == 0.0
    assert report.coverage_severity == Severity.VETO
    assert len(report.classes_missing) == 10


def test_diversity_tracker_partial() -> None:
    """5/10 Klassen -> CRITICAL (Ratio 0.5 zwischen 0.40-0.70)."""
    tracker = RoleDiversityTracker()
    dist = {cls: 1 for cls in AGENT_CLASSES[:5]}
    report = tracker.evaluate(dist)
    assert report.diversity_ratio == 0.5
    assert report.coverage_severity == Severity.CRITICAL


# ============================================================
# TeamScoreEngine
# ============================================================

def test_team_score_engine_full() -> None:
    """Voll-diverses Team -> hoher Composite-Score."""
    engine = TeamScoreEngine()
    result = engine.score("team-A", list(AGENT_CLASSES))
    assert result.team_id == "team-A"
    assert result.composite_score >= 0.85
    assert result.severity == Severity.OK


def test_team_score_engine_mono() -> None:
    """Mono-Klasse-Team -> niedriger Score."""
    engine = TeamScoreEngine()
    result = engine.score("team-mono", ["REVENUE"] * 10)
    assert result.composite_score < 0.4
    assert result.severity == Severity.VETO


def test_team_score_h_max_constant() -> None:
    """H_MAX = 3.32 per coding.md §10."""
    assert H_MAX == 3.32


# ============================================================
# AdapterOrchestrator
# ============================================================

def test_adapter_aggregate_empty() -> None:
    orch = AdapterOrchestrator()
    result = orch.aggregate({})
    assert result.teams_total == 0
    assert result.teams_audited == 0


def test_adapter_aggregate_mixed() -> None:
    orch = AdapterOrchestrator()
    teams = {
        "team-good": list(AGENT_CLASSES),
        "team-bad": ["REVENUE"] * 5,
    }
    result = orch.aggregate(teams)
    assert result.teams_total == 2
    assert result.veto_count == 1


# ============================================================
# K16-Mutex
# ============================================================

def test_k16_mutex(tmp_path: Path) -> None:
    """K16-Mutex blockt zweite Instanz."""
    lock = tmp_path / ".lock"
    m1 = K16Mutex(lock)
    assert m1.acquire() is True
    m2 = K16Mutex(lock)
    assert m2.acquire() is False
    m1.release()
    m3 = K16Mutex(lock)
    assert m3.acquire() is True
    m3.release()


# ============================================================
# AuditLogger
# ============================================================

def test_audit_logger_appends(tmp_path: Path) -> None:
    """JSONL append-only."""
    logger = AuditLogger(tmp_path / "audit.jsonl")
    logger.log({"r": 1})
    logger.log({"r": 2})
    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    assert len(lines) == 2


# ============================================================
# run_hive_audit Integration
# ============================================================

def test_run_hive_audit_full(tmp_path: Path) -> None:
    """Full Audit-Run mit 2 Teams."""
    config = {
        "paths": {"audit_log": "audit.jsonl"},
        "k16_concurrent_spawn_mutex": {"lock_dir": str(tmp_path / ".lock")},
    }
    teams = {
        "team-A": list(AGENT_CLASSES),
        "team-B": ["REVENUE", "HOUSEKEEPING"],
    }
    result = run_hive_audit(tmp_path, config, teams_input=teams)
    assert result.teams_total == 2
    assert result.teams_audited == 2
    assert (tmp_path / "audit.jsonl").exists()


def test_run_hive_audit_stop_flag(tmp_path: Path) -> None:
    """STOP.flag blockt Run."""
    config = {
        "paths": {"audit_log": "audit.jsonl"},
        "k16_concurrent_spawn_mutex": {"lock_dir": str(tmp_path / ".lock")},
    }
    stop = tmp_path / "STOP.flag"
    stop.write_text("stop")
    result = run_hive_audit(tmp_path, config, stop_flag=stop)
    assert result.skipped_due_to_stop_flag is True
