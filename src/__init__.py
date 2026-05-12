# DF-HIVE-TEAM-SCORE [CRUX-MK]
"""Shannon-Entropy-basierte Team-Score-Engine fuer 10 AgentClasses."""

# LAZY-IMPORT-PATTERN (Dual-Import-Bug-Vermeidung per coding.md §1)
__all__ = [
    "ShannonEntropyCalculator",
    "TeamScoreEngine",
    "RoleDiversityTracker",
    "AdapterOrchestrator",
    "AuditLogger",
    "K16Mutex",
    "run_hive_audit",
]

def __getattr__(name: str):
    if name in __all__:
        from . import engine
        return getattr(engine, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
