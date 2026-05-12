# DF-HIVE-TEAM-SCORE Engine [CRUX-MK]
"""
HIVE Team-Score basierend auf Shannon-Entropy (H = -sum(p*log2(p))).

H_MAX = log2(10) = 3.32 fuer 10 AgentClasses (per coding.md §10).

Architektur:
- ShannonEntropyCalculator: H = -sum(p_i * log2(p_i)) ueber Klassen-Verteilung
- TeamScoreEngine: Normalisiert H -> [0,1], aggregiert Team-Score
- RoleDiversityTracker: 10 AgentClasses Tracking
- AdapterOrchestrator: 5-Layer-Aggregat (HIVE-Layer)
- AuditLogger: JSONL append-only
"""
from __future__ import annotations

import json
import math
import os
import time
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


# Per coding.md §10: H_MAX = log2(10) fuer 10 AgentClasses
H_MAX: float = 3.32

# 10 AgentClasses (per SAE v8.1)
AGENT_CLASSES: tuple[str, ...] = (
    "REVENUE",
    "HOUSEKEEPING",
    "FRONT_DESK",
    "FOOD_BEVERAGE",
    "MAINTENANCE",
    "SECURITY",
    "RESEARCH",
    "GOVERNANCE",
    "COSMOS",
    "META",
)


class Severity(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    VETO = "VETO"


# ============================================================
# K16-Mutex (Pattern-Reuse aus DF-COSMOS)
# ============================================================

class K16Mutex:
    """Atomic mkdir-Mutex fuer K16 Concurrent-Spawn-Protection."""

    def __init__(self, lock_dir: Path) -> None:
        self.lock_dir = Path(lock_dir)

    def acquire(self) -> bool:
        try:
            self.lock_dir.mkdir(parents=False, exist_ok=False)
            (self.lock_dir / "pid").write_text(str(os.getpid()))
            return True
        except FileExistsError:
            return False

    def release(self) -> None:
        try:
            for child in self.lock_dir.iterdir():
                child.unlink()
            self.lock_dir.rmdir()
        except FileNotFoundError:
            pass


# ============================================================
# Audit-Logger
# ============================================================

class AuditLogger:
    """JSONL append-only Audit-Logger."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, record: dict[str, Any]) -> None:
        record_with_ts = {"ts": datetime.now(timezone.utc).isoformat(), **record}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record_with_ts, ensure_ascii=False) + "\n")


# ============================================================
# Shannon-Entropy-Calculator
# ============================================================

@dataclass(frozen=True)
class EntropyResult:
    """Resultat einer Shannon-Entropy-Berechnung."""

    h_raw: float       # Shannon-Entropy (Bits)
    h_normalized: float  # H / H_MAX, in [0,1]
    total_count: int
    class_distribution: dict[str, int]
    h_max: float


class ShannonEntropyCalculator:
    """Berechnet H = -sum(p * log2(p)) fuer eine Klassen-Verteilung."""

    def __init__(self, h_max: float = H_MAX) -> None:
        self.h_max = h_max

    def calculate(self, items: Iterable[str]) -> EntropyResult:
        """Berechnet Shannon-Entropy fuer eine Liste von Klassen-Labels.

        Pre: items ist iterable[str]
        Post: 0 <= h_normalized <= 1 (bei N>0)
        """
        counter: Counter[str] = Counter(items)
        total = sum(counter.values())
        if total == 0:
            return EntropyResult(
                h_raw=0.0,
                h_normalized=0.0,
                total_count=0,
                class_distribution={},
                h_max=self.h_max,
            )
        h_raw = 0.0
        for cls, count in counter.items():
            p = count / total
            if p > 0:
                h_raw -= p * math.log2(p)
        # Normalize
        h_normalized = min(h_raw / self.h_max, 1.0) if self.h_max > 0 else 0.0
        return EntropyResult(
            h_raw=h_raw,
            h_normalized=h_normalized,
            total_count=total,
            class_distribution=dict(counter),
            h_max=self.h_max,
        )


# ============================================================
# Role-Diversity-Tracker (10 AgentClasses)
# ============================================================

@dataclass(frozen=True)
class DiversityReport:
    classes_present: tuple[str, ...]
    classes_missing: tuple[str, ...]
    diversity_ratio: float   # classes_present / len(AGENT_CLASSES)
    coverage_severity: Severity


class RoleDiversityTracker:
    """Trackt welche AgentClasses im Team vertreten sind."""

    def __init__(self, all_classes: tuple[str, ...] = AGENT_CLASSES) -> None:
        self.all_classes = all_classes

    def evaluate(self, distribution: dict[str, int]) -> DiversityReport:
        present_set = {cls for cls, count in distribution.items() if count > 0 and cls in self.all_classes}
        missing = tuple(sorted(set(self.all_classes) - present_set))
        ratio = len(present_set) / len(self.all_classes) if self.all_classes else 0.0
        if ratio >= 0.85:
            sev = Severity.OK
        elif ratio >= 0.70:
            sev = Severity.WARNING
        elif ratio >= 0.40:
            sev = Severity.CRITICAL
        else:
            sev = Severity.VETO
        return DiversityReport(
            classes_present=tuple(sorted(present_set)),
            classes_missing=missing,
            diversity_ratio=ratio,
            coverage_severity=sev,
        )


# ============================================================
# Team-Score-Engine
# ============================================================

@dataclass(frozen=True)
class TeamScoreResult:
    team_id: str
    entropy_result: EntropyResult
    diversity_report: DiversityReport
    composite_score: float   # blended (h_norm + diversity_ratio) / 2
    severity: Severity


class TeamScoreEngine:
    """Aggregiert Shannon-Entropy + Diversity zu Team-Score."""

    def __init__(
        self,
        entropy: ShannonEntropyCalculator | None = None,
        diversity: RoleDiversityTracker | None = None,
    ) -> None:
        self.entropy = entropy or ShannonEntropyCalculator()
        self.diversity = diversity or RoleDiversityTracker()

    def score(self, team_id: str, agent_classes: Iterable[str]) -> TeamScoreResult:
        ent = self.entropy.calculate(agent_classes)
        div = self.diversity.evaluate(ent.class_distribution)
        composite = (ent.h_normalized + div.diversity_ratio) / 2.0
        if composite >= 0.85:
            sev = Severity.OK
        elif composite >= 0.70:
            sev = Severity.WARNING
        elif composite >= 0.40:
            sev = Severity.CRITICAL
        else:
            sev = Severity.VETO
        return TeamScoreResult(
            team_id=team_id,
            entropy_result=ent,
            diversity_report=div,
            composite_score=composite,
            severity=sev,
        )


# ============================================================
# Adapter-Orchestrator
# ============================================================

@dataclass(frozen=True)
class HiveAuditResult:
    teams_total: int
    teams_audited: int
    average_composite: float
    average_h_normalized: float
    veto_count: int
    skipped_due_to_stop_flag: bool = False


class AdapterOrchestrator:
    """Adapter zwischen TeamScoreEngine und Audit-Pipeline."""

    def __init__(self, engine: TeamScoreEngine | None = None) -> None:
        self.engine = engine or TeamScoreEngine()

    def aggregate(self, teams: dict[str, list[str]]) -> HiveAuditResult:
        if not teams:
            return HiveAuditResult(0, 0, 0.0, 0.0, 0)
        results = [self.engine.score(tid, agents) for tid, agents in teams.items()]
        avg_comp = sum(r.composite_score for r in results) / len(results)
        avg_h = sum(r.entropy_result.h_normalized for r in results) / len(results)
        vetos = sum(1 for r in results if r.severity == Severity.VETO)
        return HiveAuditResult(
            teams_total=len(teams),
            teams_audited=len(results),
            average_composite=avg_comp,
            average_h_normalized=avg_h,
            veto_count=vetos,
        )


# ============================================================
# run_hive_audit
# ============================================================

def run_hive_audit(
    repo_root: Path,
    config: dict[str, Any],
    stop_flag: Path | None = None,
    teams_input: dict[str, list[str]] | None = None,
) -> HiveAuditResult:
    """Full HIVE-Audit-Run.

    Pre: config enthaelt 'paths' + 'k16_concurrent_spawn_mutex'
    Post: AuditLog gesetzt, HiveAuditResult zurueck
    """
    if stop_flag is not None and stop_flag.exists():
        return HiveAuditResult(0, 0, 0.0, 0.0, 0, skipped_due_to_stop_flag=True)

    lock_dir = Path(config.get("k16_concurrent_spawn_mutex", {}).get("lock_dir", "/tmp/df-hive-team-score.lock"))
    mutex = K16Mutex(lock_dir)
    if not mutex.acquire():
        return HiveAuditResult(0, 0, 0.0, 0.0, 0)

    try:
        audit_log_path = Path(repo_root) / config.get("paths", {}).get("audit_log", "audit.jsonl")
        logger = AuditLogger(audit_log_path)
        orchestrator = AdapterOrchestrator()
        teams = teams_input or {}
        result = orchestrator.aggregate(teams)
        logger.log({"event": "hive-audit-complete", "result": asdict(result)})
        return result
    finally:
        mutex.release()
