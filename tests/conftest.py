from __future__ import annotations

import sys
from pathlib import Path

SUBMODULE_ROOT = Path(__file__).resolve().parents[1]
HOST_ROOT = SUBMODULE_ROOT.parents[1]
sys.path.insert(0, str(SUBMODULE_ROOT / "src"))
sys.path.insert(0, str(HOST_ROOT))
