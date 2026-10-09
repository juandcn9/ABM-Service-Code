from __future__ import annotations

import hashlib
import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_PYTHON = "3.12.15"
EXPECTED_RUNTIME = {
    "fastapi": "0.143.0",
    "pydantic": "2.14.0",
    "uvicorn": "0.54.0",
}
EXPECTED_DEV = {
    "httpx": "0.28.1",
    "mypy": "2.4.0",
    "pip-tools": "7.6.2",
    "pytest": "9.1.1",
    "ruff": "0.16.10",
}
EXPECTED_IMAGE = (
    "python:3.12.15-slim-bookworm@"
    "sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258"
)
EXPECTED_LOCK_DIGESTS = {
    "requirements.lock": "2e8d3b9afafc28630cc9e463c8700ee0514f80c5608d7623d1c7e662dfea8337",
    "requirements-dev.lock": "8e8231ddd8f72f7de296bb698806756ac110e17b597d9ff53ba5dfc46486ebd8",
}
FAILURES: list[str] = []


def fail(message: str) -> None:
    FAILURES.append(message)


def normalized_pins(values: list[str]) -> dict[str, str]:
    pins: dict[str, str] = {}
    for value in values:
        match = re.fullmatch(r"([a-z0-9-]+)==([A-Za-z0-9._+-]+)", value)
        if not match:
            fail(f"direct dependency is not an exact plain pin: {value}")
            continue
        pins[match.group(1)] = match.group(2)
    return pins


def validate_metadata() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject.get("project", {})
    if project.get("requires-python") != ">=3.12,<3.13":
        fail("pyproject Python series is not exactly 3.12")
    if normalized_pins(project.get("dependencies", [])) != EXPECTED_RUNTIME:
        fail("runtime direct pins differ from the reviewed set")
    optional = project.get("optional-dependencies", {})
    if set(optional) != {"dev"}:
        fail("only the explicit dev dependency group is permitted")
    if normalized_pins(optional.get("dev", [])) != EXPECTED_DEV:
        fail("development direct pins differ from the reviewed set")

    version = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    if version != EXPECTED_PYTHON:
        fail(f".python-version mismatch: {version}")

    toolchain = tomllib.loads((ROOT / "toolchain.toml").read_text(encoding="utf-8"))
    if toolchain.get("schema_version") != 1:
        fail("toolchain schema version is not supported")
    if toolchain.get("python") != EXPECTED_PYTHON:
        fail("toolchain Python patch does not match .python-version")
    if toolchain.get("python_series") != "3.12":
        fail("toolchain Python series is not 3.12")
    if toolchain.get("container_image") != EXPECTED_IMAGE:
        fail("container base tag/digest differs from the reviewed official image")
    if toolchain.get("lock_generator") != "pip-tools==7.6.2":
        fail("lock generator is not exact-pinned")
    if toolchain.get("runtime_lock") != "requirements.lock":
        fail("runtime lock path differs from the approved repository path")
    if toolchain.get("development_lock") != "requirements-dev.lock":
        fail("development lock path differs from the approved repository path")
    for key in ("generator_install", "runtime_install", "development_install"):
        command = toolchain.get(key, "")
        if "--require-hashes" not in command or "--only-binary=:all:" not in command:
            fail(f"{key} does not enforce hashes and binary artifacts")


def lock_pins(path: pathlib.Path) -> dict[str, str]:
    body = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(body.replace("\r\n", "\n").encode("utf-8")).hexdigest()
    if digest != EXPECTED_LOCK_DIGESTS.get(path.name):
        fail(f"{path.name} content digest differs from the reviewed lock")
    if "http://" in body or "https://" in body or "git+" in body:
        fail(f"{path.name} contains a remote or VCS source")
    for line in body.splitlines():
        stripped_line = line.strip()
        if stripped_line.startswith("-") and not stripped_line.startswith(
            "--hash=sha256:"
        ):
            fail(f"{path.name} contains an unexpected requirement directive")
    blocks = re.split(r"\n(?=[a-zA-Z0-9])", body)
    pins: dict[str, str] = {}
    for block in blocks:
        stripped = block.strip()
        if not stripped or stripped.startswith("#"):
            continue
        first = stripped.splitlines()[0]
        match = re.match(r"([a-zA-Z0-9_.-]+)==([^\s\\]+)", first)
        if not match:
            fail(f"{path.name} has a non-exact requirement block: {first}")
            continue
        name = match.group(1).lower().replace("_", "-")
        if name in pins:
            fail(f"{path.name} duplicates {name}")
        pins[name] = match.group(2)
        hashes = re.findall(r"--hash=sha256:([0-9a-f]{64})(?=\s|$)", block)
        if not hashes:
            fail(f"{path.name} lacks a valid SHA-256 hash for {name}")
        if len(hashes) != block.count("--hash="):
            fail(f"{path.name} contains a malformed or non-SHA-256 hash for {name}")
        if len(hashes) != len(set(hashes)):
            fail(f"{path.name} contains a duplicate hash for {name}")
    if not pins:
        fail(f"{path.name} contains no resolved packages")
    return pins


def validate_locks() -> None:
    runtime = lock_pins(ROOT / "requirements.lock")
    development = lock_pins(ROOT / "requirements-dev.lock")
    for name, version in EXPECTED_RUNTIME.items():
        if runtime.get(name) != version:
            fail(f"runtime lock mismatch for {name}")
        if development.get(name) != version:
            fail(f"development lock mismatch for runtime dependency {name}")
    for name, version in EXPECTED_DEV.items():
        if name in runtime:
            fail(f"runtime lock contains development-only dependency {name}")
        if development.get(name) != version:
            fail(f"development lock mismatch for {name}")


def validate_example_configuration() -> None:
    body = (ROOT / ".env.example").read_text(encoding="utf-8")
    expected = {
        "ABM_MODE": "development",
        "ABM_DB_PATH": "/var/lib/abm/abm.sqlite3",
        "ABM_LOG_LEVEL": "INFO",
        "ABM_BUSY_TIMEOUT_MS": "5000",
        "ABM_TRUSTED_INGRESS": "false",
        "ABM_CLOCK_MODE": "system",
    }
    parsed = dict(line.split("=", 1) for line in body.splitlines() if line.strip())
    if parsed != expected:
        fail(".env.example differs from the approved safe configuration")
    if re.search(r"(?i)(password|passwd|api[_-]?key|secret|token)", body):
        fail(".env.example contains a secret-bearing field")


def main() -> int:
    try:
        validate_metadata()
        validate_locks()
        validate_example_configuration()
    except (FileNotFoundError, OSError, tomllib.TOMLDecodeError) as error:
        fail(f"toolchain input cannot be read: {error}")
    if FAILURES:
        print("TASK-02 VALIDATION FAILED")
        for item in FAILURES:
            print(f"- {item}")
        return 1
    print("TASK-02 VALIDATION PASSED")
    print(f"- Python: {EXPECTED_PYTHON}")
    print(f"- runtime packages: {len(lock_pins(ROOT / 'requirements.lock'))}")
    print(f"- development packages: {len(lock_pins(ROOT / 'requirements-dev.lock'))}")
    print(
        "- exact direct pins, SHA-256 locks, container digest, and safe example: passed"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
