"""Pytest conftest fuer DF-HIVE-TEAM-SCORE."""
import sys
from pathlib import Path

# Add src/ to sys.path (KEIN sae_v8.xxx Import, coding.md §1)
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
