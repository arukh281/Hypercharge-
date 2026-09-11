"""CLI entry — fix sys.path when repo root contains a hypercharge/ folder."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_package_path() -> None:
    """Prefer the installed hypercharge package over a shadowing repo folder."""
    dist_root = Path(__file__).resolve().parent.parent
    if dist_root.name != "hypercharge":
        return

    # Drop parent paths whose hypercharge/ subfolder is this dist root (monorepo shadow).
    for entry in list(sys.path):
        if not entry:
            continue
        try:
            parent = Path(entry).resolve()
        except OSError:
            continue
        if parent == dist_root:
            continue
        if (parent / "hypercharge").resolve() == dist_root:
            sys.path.remove(entry)

    dist_s = str(dist_root)
    if dist_s in sys.path:
        sys.path.remove(dist_s)
    sys.path.insert(0, dist_s)

    cached = sys.modules.get("hypercharge")
    if cached is not None and not getattr(cached, "__version__", None):
        for name in list(sys.modules):
            if name == "hypercharge" or name.startswith("hypercharge."):
                if name != __name__:
                    del sys.modules[name]
        sys.modules.pop("hypercharge", None)


_ensure_package_path()

from hypercharge.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
