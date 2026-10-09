"""Import-boundary tests for the modular monolith (DEC-0001; specs/03-architecture.md section 4)."""

from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

LAYERS = ("api", "application", "domain", "persistence", "ports", "observability")
# layer -> abm layers it may import (itself is always allowed)
ALLOWED = {
    "domain": set(),
    "ports": {"domain"},
    "application": {"domain", "ports"},
    "persistence": {"domain", "ports"},
    "api": {"application", "domain"},
    "observability": {"application", "domain"},
    "config": set(),
    "main": set(LAYERS) | {"config"},
}
# the monetary domain has no FastAPI or SQLite dependency; sqlite3 is stdlib, so ban it explicitly.
# _sqlite3 is the C module behind sqlite3. importlib and the builtins below are dynamic imports
# that the static import scan cannot see, so the domain may not use them at all.
DOMAIN_BANNED_STDLIB = {"sqlite3", "_sqlite3", "importlib"}
DOMAIN_BANNED_BUILTINS = {"__import__", "exec", "eval"}


def layer_of(module: str) -> str | None:
    parts = module.split(".")
    return parts[1] if parts[0] == "abm" and len(parts) > 1 else None


def imported_modules(source: str, module: str, is_package: bool) -> list[str]:
    package = module if is_package else module.rpartition(".")[0]
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = package.split(".")
                anchor = anchor[: len(anchor) - (node.level - 1)]
                base = ".".join(anchor + ([base] if base else []))
            found.append(base)
            # `from abm import domain` imports a submodule, not just the package
            found += [f"{base}.{alias.name}" for alias in node.names]
    return found


def violations(files: dict[str, str]) -> list[str]:
    """files maps dotted module name -> source; a name ending in `.__init__` is a package."""
    problems: list[str] = []
    for name, source in files.items():
        is_package = name.endswith(".__init__")
        module = name.removesuffix(".__init__")
        layer = layer_of(module) or ("root" if module == "abm" else None)
        if layer is None:
            continue
        if layer == "domain":
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.Name) and node.id in DOMAIN_BANNED_BUILTINS:
                    problems.append(f"domain module {module} uses {node.id}")
        for target in imported_modules(source, module, is_package):
            top = target.split(".")[0]
            if top == "harness":
                problems.append(f"{module} imports harness")
            elif top == "abm":
                target_layer = layer_of(target)
                if target_layer and target_layer != layer and target_layer not in ALLOWED.get(layer, set()):
                    problems.append(f"{module} imports {target}")
            elif layer == "domain" and (
                top not in sys.stdlib_module_names or top in DOMAIN_BANNED_STDLIB
            ):
                problems.append(f"domain module {module} imports {target}")
    return problems


def project_modules() -> dict[str, str]:
    files = {}
    for path in (SRC / "abm").rglob("*.py"):
        name = ".".join(path.relative_to(SRC).with_suffix("").parts)
        files[name] = path.read_text(encoding="utf-8")
    return files


def test_layout_matches_target_tree() -> None:
    for layer in LAYERS:
        assert (SRC / "abm" / layer / "__init__.py").is_file(), layer
    for name in ("main.py", "config.py"):
        assert (SRC / "abm" / name).is_file(), name
    assert (ROOT / "harness" / "__init__.py").is_file()
    for kind in ("unit", "integration", "contract", "security", "e2e"):
        assert (ROOT / "tests" / kind).is_dir(), kind


def test_project_respects_dependency_rules() -> None:
    assert violations(project_modules()) == []


def test_every_abm_module_belongs_to_a_known_layer() -> None:
    known = set(LAYERS) | {"main", "config", "__init__"}
    assert {layer_of(name.removesuffix(".__init__")) or "__init__" for name in project_modules()} <= known


def test_checker_rejects_forbidden_imports() -> None:
    bad = {
        "abm.domain.money": "import sqlite3\nimport _sqlite3\nimport importlib\nx = __import__('os')\nexec('1')\nimport fastapi\nfrom abm.api import x\nfrom .. import persistence",
        "abm.application.svc": "from abm.persistence import repo\nfrom abm import api",
        "abm.api.routes": "from ..persistence import db",
        "abm.observability.logs": "import abm.persistence.db",
        "abm.ports.__init__": "from . import sibling\nfrom ..application import svc",
        "abm.main": "import harness",
        "abm.__init__": "import harness\nfrom abm import api\nfrom . import persistence",
    }
    problems = violations(bad)
    for expected in (
        "domain module abm.domain.money imports sqlite3",
        "domain module abm.domain.money imports importlib",
        "domain module abm.domain.money imports _sqlite3",
        "domain module abm.domain.money uses __import__",
        "domain module abm.domain.money uses exec",
        "domain module abm.domain.money imports fastapi",
        "abm.domain.money imports abm.api",
        "abm.domain.money imports abm.persistence",
        "abm.application.svc imports abm.persistence",
        "abm.application.svc imports abm.api",
        "abm.api.routes imports abm.persistence.db",
        "abm.observability.logs imports abm.persistence.db",
        "abm.ports imports abm.application",
        "abm.main imports harness",
        "abm imports harness",
        "abm imports abm.api",
        "abm imports abm.persistence",
    ):
        assert any(p.startswith(expected) for p in problems), expected


def test_checker_accepts_permitted_imports() -> None:
    good = {
        "abm.domain.money": "import dataclasses\nfrom decimal import Decimal\nfrom . import other",
        "abm.application.svc": "from abm.domain import money\nfrom abm.ports import clock\nfrom . import helper",
        "abm.persistence.repo": "from ..domain import money",
        "abm.api.routes": "import fastapi\nfrom abm.application import svc",
        "abm.main": "from abm import persistence, api, config",
    }
    assert violations(good) == []
