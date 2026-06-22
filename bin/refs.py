#!/usr/bin/env python3
"""CLI helper for /forge:reference — inspect available and installed references.

Subcommands:
  available            list references shipped in the plugin library
  installed            list references installed in the current project
  applicable <path>    list installed references that govern <path>

The plugin's own library lives at <plugin_root>/references/; a project's installed
references live at <cwd>/.forge/references/.
"""

import os
import sys

_PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _PLUGIN_ROOT)

from lib import references  # noqa: E402

_LIBRARY = os.path.join(_PLUGIN_ROOT, "references")


def _list(dir_path: str) -> int:
    found = False
    for name in sorted(os.listdir(dir_path)) if os.path.isdir(dir_path) else []:
        if not name.endswith(".md"):
            continue
        ref = references.load_one(os.path.join(dir_path, name))
        if ref:
            found = True
            scope = ", ".join(ref.applies_to) or "(unscoped)"
            print(
                f"  {ref.name} [{ref.enforcement}] — {ref.summary}\n"
                f"      governs: {scope}"
            )
    if not found:
        print("  (none)")
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "available"
    if cmd == "available":
        print(f"Available in library ({_LIBRARY}):")
        return _list(_LIBRARY)
    if cmd == "installed":
        print("Installed in this project:")
        return _list(references.refs_dir(os.getcwd()))
    if cmd == "applicable":
        if len(sys.argv) < 3:
            print("usage: refs.py applicable <path>", file=sys.stderr)
            return 2
        rel = os.path.relpath(sys.argv[2], os.getcwd())
        govs = references.for_file(os.getcwd(), rel)
        print(f"References governing {rel}:")
        if not govs:
            print("  (none)")
        for r in govs:
            print(f"  {r.name} [{r.enforcement}]")
        return 0
    print(f"unknown subcommand: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
