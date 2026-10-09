"""Static scan for value-formatted SQL (SEC-05, TEST-25 static half; specs/06-security.md)."""

from __future__ import annotations

import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCANNED = (ROOT / "src" / "abm", ROOT / "harness")
EXECUTE = {"execute", "executemany", "executescript"}
# Files whose execute() argument is reviewed, checksummed migration text, not request values.
# Formatted-SQL detection still applies to them; only the fixed-statement rule is waived.
DYNAMIC_EXECUTE_ALLOWED = {"src/abm/persistence/migrations.py"}
HOLE = "{}"  # stands in for every interpolated value; it counts as one non-space token
SQL_STATEMENT = re.compile(
    r"\s*(?:"
    r"select\s+(?:.*\bfrom\b|[\d*]|\{\})"
    r"|insert\s+(?:or\s+\w+\s+)?into\b"
    r"|update\s+\S+\s+set\b"
    r"|delete\s+from\b"
    r"|replace\s+into\b"
    r"|create\s+(?:(?:temp|temporary|unique|virtual)\s+)*(?:table|index|view|trigger)\b"
    r"|drop\s+(?:table|index|view|trigger)\b"
    r"|alter\s+table\b"
    r"|pragma\s+\S"
    r"|with\s+(?:recursive\s+)?\S+\s+as\s*\("
    r"|vacuum\b|reindex\b|analyze\b"
    r"|attach\s+(?:database\s+)?\S+\s+as\b"
    r"|explain\s+(?:query\s+plan\s+)?(?:select|insert|update|delete|\{\})"
    r"|begin\s+(?:immediate|exclusive|deferred|transaction)\b"
    r"|savepoint\s+\S"
    r")",
    re.IGNORECASE | re.DOTALL,
)


def _static_text(node: ast.expr) -> str | None:
    """Known text of a string expression with HOLE for values; None if it is not a string build."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        if not any(isinstance(v, ast.FormattedValue) for v in node.values):
            return None
        return "".join(
            str(v.value) if isinstance(v, ast.Constant) else HOLE for v in node.values
        )
    return None


def literal_constants(source: str) -> set[str]:
    """Module-level NAME = "plain string" assignments: the only names execute may receive."""
    names: set[str] = set()
    for node in ast.parse(source).body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def formatted_sql(
    source: str,
    constants: frozenset[str] | set[str] = frozenset(),
    allow_dynamic_execute: bool = False,
) -> list[int]:
    """Line numbers of SQL built from values, or passed to execute without a fixed statement."""
    constants = constants | literal_constants(source)
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.expr):
            continue
        text = None
        if isinstance(node, ast.JoinedStr):
            text = _static_text(node)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod | ast.Add):
            left = _static_text(node.left)
            text = None if left is None else left + HOLE
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "format"
        ):
            left = _static_text(node.func.value)
            text = None if left is None else left + HOLE
        built = text is not None and bool(SQL_STATEMENT.match(text))
        # a fixed statement is a string literal or a module-level string-literal constant
        unfixed = not allow_dynamic_execute and (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in EXECUTE
            and bool(node.args)
            and not (
                (
                    isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                )
                or (isinstance(node.args[0], ast.Name) and node.args[0].id in constants)
            )
        )
        if built or unfixed:
            lines.append(node.lineno)
    return sorted(set(lines))


def scanned_files() -> list[pathlib.Path]:
    return [p for root in SCANNED for p in sorted(root.rglob("*.py"))]


def test_source_tree_has_no_value_formatted_sql() -> None:
    files = scanned_files()
    assert files, "scan found no files; SCANNED paths are wrong"
    sources = {p: p.read_text(encoding="utf-8") for p in files}
    constants = set().union(*(literal_constants(s) for s in sources.values()))
    for path, source in sources.items():
        allowed = path.relative_to(ROOT).as_posix() in DYNAMIC_EXECUTE_ALLOWED
        assert formatted_sql(source, constants, allowed) == [], str(path)


def test_scan_rejects_formatted_sql() -> None:
    bad = [
        'cur.execute(f"SELECT * FROM t WHERE id = {x}")',
        'cur.execute("SELECT * FROM t WHERE id = " + x)',
        'cur.execute("SELECT * FROM t WHERE id = %s" % x)',
        'cur.execute("SELECT * FROM {}".format(t))',
        'cur.execute(f"UPDATE {t} SET a = ?", (1,))',
        'cur.execute(f"select {cols} from t")',
        "cur.execute(query)",
        'cur.executemany(f"INSERT INTO t VALUES ({x})", rows)',
        'q = f"DELETE FROM t WHERE id = {x}"',
        "q = f\"VACUUM INTO '{p}'\"",
        "q = f\"ATTACH DATABASE '{p}' AS d\"",
        'q = f"PRAGMA {name} = 1"',
        # a constant that is not a plain string literal is not a fixed statement
        'Q = f"{v} FROM t WHERE a = {x}"\ncur.execute(Q)',
        "Q = build(x)\ncur.execute(Q)",
        'Q = x + " WHERE"\ncur.execute(Q)',
        "cur.execute(OTHER_MODULE_CONSTANT)",
    ]
    for source in bad:
        assert formatted_sql(source), source


def test_scan_accepts_fixed_statements_and_unrelated_strings() -> None:
    good = [
        'cur.execute("SELECT * FROM t WHERE id = ?", (x,))',
        'INSERT_ENTRY = "INSERT INTO t VALUES (?)"\ncur.execute(INSERT_ENTRY, (x,))',
        'cur.executemany("INSERT INTO t VALUES (?)", rows)',
        'message = f"selected {count} rows"',
        'name = "update" + suffix',
        'log.info(f"update failed for {x}")',
        'raise ValueError(f"create request invalid: {x}")',
        'q = f"SELECT 1"',
        'x = """SELECT * FROM t""" ',
    ]
    for source in good:
        assert formatted_sql(source) == [], source


def test_known_constants_from_other_modules_are_accepted() -> None:
    assert formatted_sql("cur.execute(INSERT_ENTRY, (x,))", {"INSERT_ENTRY"}) == []


def test_dynamic_execute_allowance_is_narrow() -> None:
    assert DYNAMIC_EXECUTE_ALLOWED == {"src/abm/persistence/migrations.py"}
    # the allowance waives only the fixed-statement rule, never value-formatted SQL
    assert formatted_sql("cur.execute(statement)", allow_dynamic_execute=True) == []
    assert formatted_sql(
        'cur.execute(f"SELECT * FROM t WHERE a={x}")', allow_dynamic_execute=True
    )
