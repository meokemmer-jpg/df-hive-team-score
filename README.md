# DF-HIVE-TEAM-SCORE [CRUX-MK]

Shannon-Entropy-basierte Team-Score-Engine fuer 10 AgentClasses.

## Architektur

- `src/engine.py` — Shannon-Entropy + TeamScoreEngine + RoleDiversityTracker + AdapterOrchestrator + AuditLogger
- `tests/test_engine.py` — 14 Tests (Entropy + Diversity + Score + Mutex + Audit + Integration)
- `scripts/run-df-hive-team-score.sh` — K16-Mutex Wrapper

## SAE-v8 Integration

Per `coding.md` §10:
- `H_MAX = 3.32` (log2(10) fuer 10 AgentClasses)
- `Q_SCALE_INTEGRAL = 11.11` (referenziert)
- `F_CUM_DECAY = 0.98` (referenziert)

LAZY-IMPORT-PATTERN: Kein `from sae_v8.xxx` (Dual-Import-Bug-Vermeidung).

## Run

```bash
bash scripts/run-df-hive-team-score.sh
```

## Test

```bash
python3 -m pytest tests/ -q
```

[CRUX-MK]
