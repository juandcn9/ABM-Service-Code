"""Static scan for value-formatted SQL (SEC-05, TEST-25 static half; specs/06-security.md)."""

from __future__ import annotations

import ast
import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[2] / "src"
EXECUTE = {"execute", "executemany", "executescript"}
SQL_START = re.compile(
    r"\s*(select|insert|update|delete|create|drop|alter|pragma|replace|with)\s+\S",
    re.IGNORECASE,
)


def _starts_like_sql(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and bool(SQL_START.match(node.value))
    )


def formatted_sql(source: str) -> list[int]:
    """Line numbers of SQL built from values, or passed to execute without a fixed literal."""
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        built = (
            (
                isinstance(node, ast.JoinedStr)
                and node.values
                and _starts_like_sql(node.values[0])
            )
            or (
                isinstance(node, ast.BinOp)
                and isinstance(node.op, ast.Mod | ast.Add)
                and _starts_like_sql(node.left)
            )
            or (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "format"
                and _starts_like_sql(node.func.value)
            )
        )
        # a fixed statement is a string literal or an ALL_CAPS module constant
        unfixed = (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in EXECUTE
            and node.args
            and not (
                (
                    isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                )
                or (isinstance(node.args[0], ast.Name) and node.args[0].id.isupper())
            )
        )
        if (built or unfixed) and isinstance(node, ast.expr):
            lines.append(node.lineno)
    return sorted(set(lines))


def test_source_tree_has_no_value_formatted_sql() -> None:
    for path in (SRC / "abm").rglob("*.py"):
        assert formatted_sql(path.read_text(encoding="utf-8")) == [], str(path)


def test_scan_rejects_formatted_sql() -> None:
    bad = [
        'cur.execute(f"SELECT * FROM t WHERE id = {x}")',
        'cur.execute("SELECT * FROM t WHERE id = " + x)',
        'cur.execute("SELECT * FROM t WHERE id = %s" % x)',
        'cur.execute("SELECT * FROM {}".format(t))',
        "cur.execute(query)",
        'cur.executemany(f"INSERT INTO t VALUES ({x})", rows)',
        'q = f"DELETE FROM t WHERE id = {x}"',
    ]
    for source in bad:
        assert formatted_sql(source) == [1], source


def test_scan_accepts_fixed_statements_and_unrelated_strings() -> None:
    good = [
        'cur.execute("SELECT * FROM t WHERE id = ?", (x,))',
        "cur.execute(INSERT_ENTRY, (x,))",
        'cur.executemany("INSERT INTO t VALUES (?)", rows)',
        'message = f"selected {count} rows"',
        'name = "update" + suffix',
    ]
    for source in good:
        assert formatted_sql(source) == [], source
