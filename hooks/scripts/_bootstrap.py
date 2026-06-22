"""Put the plugin root on sys.path so hook scripts can `from lib import ...`.

Hook scripts are launched by Claude Code as standalone processes (`python
.../hooks/scripts/foo.py`), so the plugin package isn't importable by default.
Each script imports this first. Kept as a side-effecting module rather than a
function so the import line alone does the work.
"""

import os
import sys

_PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
