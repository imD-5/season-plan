"""Dependency rule: inner layers never import outer ones."""

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "season"

FORBIDDEN = {
    "domain": ("season.application", "season.adapters", "season.interfaces", "season.container",
               "season.config", "sqlite3", "typesafe_sdk", "http", "urllib", "subprocess"),
    "application": ("season.adapters", "season.interfaces", "season.container", "season.config",
                    "sqlite3", "typesafe_sdk", "http", "urllib", "subprocess"),
    "adapters": ("season.interfaces", "season.container"),
}


def imports(path: Path) -> set[str]:
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module)
    return out


class LayerTest(unittest.TestCase):
    def test_dependency_rule(self):
        for layer, banned in FORBIDDEN.items():
            for f in (ROOT / layer).rglob("*.py"):
                for name in imports(f):
                    with self.subTest(file=str(f.relative_to(ROOT)), imports=name):
                        self.assertFalse(any(name == b or name.startswith(b + ".") for b in banned))


if __name__ == "__main__":
    unittest.main()
