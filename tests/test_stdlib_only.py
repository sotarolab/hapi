"""The referee does not import the player: the root scripts use only the standard library and each other,
so they run on bare Python in the hourly job and never depend on caudal."""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPTS = sorted(ROOT.glob("*.py"))


def imported(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_root_scripts_import_only_the_standard_library():
    assert len(SCRIPTS) >= 7
    local = {p.stem for p in SCRIPTS}
    for p in SCRIPTS:
        extra = imported(p) - sys.stdlib_module_names - local
        assert not extra, f"{p.name} imports {sorted(extra)}: the referee does not import the player"
