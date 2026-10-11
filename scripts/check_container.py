"""TASK-27 container check (TEST-33, NFR-10; TEST-31 readiness; TASK-26 log facet).

Usage (repository root, on a host with a container engine):
  python scripts/check_container.py [--engine docker] [--test-summary TEXT]

Builds the image, then runs it with a fresh named volume and a read-only root filesystem. It checks:
  - the process runs as a non-root UID (10001) and is not root;
  - the application layer is read-only (a write under /app fails) and the data volume is writable;
  - the service reaches /health/ready on a fresh volume;
  - structured events with ts and severity reach stdout (TASK-26, DEC-0062);
  - a stop and start on the same volume reaches ready again (restart; continuity is TASK-28);
  - the database written by the container passes the aged-item scan and yields a manifest that
    names the image digest and the exact commits (TASK-26 manifest, TEST-35).

Standard library only. Containers and the volume are removed at the end, pass or fail. Exit 0 means
every check passed on this host; the CI job runs it on the exact revision.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_UID = 10001
PORT = 8000
READY_TIMEOUT_S = 60
SPEC_VERSION = ROOT / "SPEC_VERSION"


class CheckFailed(Exception):
    pass


def container_failures(uid: str, app_write_rc: int, data_write_rc: int) -> list[str]:
    """The security decision of the container check, kept pure so it can be tested (TEST-33).

    uid is the process UID reported by the engine; app_write_rc and data_write_rc are the exit codes
    of a write to the application layer and to the data volume (0 means the write succeeded).
    """
    problems = []
    if uid != str(EXPECTED_UID):
        problems.append(f"process UID is {uid}, expected {EXPECTED_UID} (not root)")
    if app_write_rc == 0:
        problems.append("application layer is writable")
    if data_write_rc != 0:
        problems.append("data volume is not writable")
    return problems


def run(
    engine: str, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [engine, *args], capture_output=True, text=True, cwd=ROOT, check=False
    )
    if check and result.returncode != 0:
        raise CheckFailed(f"{engine} {args[0]} failed (exit {result.returncode})")
    return result


def wait_for(url: str, expect: int) -> None:
    deadline = time.monotonic() + READY_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == expect:
                    return
        except urllib.error.HTTPError as exc:
            if exc.code == expect:
                return
        except OSError:
            pass
        time.sleep(1)
    raise CheckFailed(f"{url} did not return {expect} in {READY_TIMEOUT_S}s")


def host_port(engine: str, name: str) -> int:
    out = run(engine, "port", name, str(PORT)).stdout.strip().splitlines()[0]
    return int(out.rsplit(":", 1)[1])


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailed(message)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--engine", default="docker")
    parser.add_argument(
        "--test-summary", default="container check only (no pytest summary given)"
    )
    args = parser.parse_args(argv)
    engine = args.engine
    if shutil.which(engine) is None:
        print(f"CONTAINER CHECK NOT RUN: '{engine}' is not on PATH")
        return 2

    tag = secrets.token_hex(4)
    image = f"abm-check:{tag}"
    volume = f"abm-check-data-{tag}"
    name = f"abm-check-{tag}"
    try:
        run(engine, "build", "-t", image, ".")
        run(engine, "volume", "create", volume)
        base = ["run", "-d", "--name", name, "--read-only", "-v", f"{volume}:/data"]
        env = [
            "-e", "ABM_MODE=demonstration",
            "-e", "ABM_TRUSTED_INGRESS=true",
            "-e", "ABM_CLOCK_MODE=system",
        ]  # fmt: skip
        run(engine, *base, *env, "-p", f"127.0.0.1::{PORT}", image)
        port = host_port(engine, name)
        base_url = f"http://127.0.0.1:{port}"
        wait_for(f"{base_url}/health/ready", 200)

        uid = run(engine, "exec", name, "id", "-u").stdout.strip()
        write_app = run(engine, "exec", name, "sh", "-c", "touch /app/x", check=False)
        write_data = run(
            engine, "exec", name, "sh", "-c", "touch /data/probe", check=False
        )
        problems = container_failures(uid, write_app.returncode, write_data.returncode)
        if problems:
            raise CheckFailed("; ".join(problems))

        urllib.request.urlopen(f"{base_url}/health/live", timeout=3).read()
        logs = run(engine, "logs", name).stdout
        events = [
            json.loads(line) for line in logs.splitlines() if line.startswith("{")
        ]
        expect(
            any("ts" in e and "severity" in e for e in events),
            "no structured event with ts and severity on stdout",
        )

        run(engine, "stop", name)
        run(engine, "start", name)
        port = host_port(engine, name)
        wait_for(f"http://127.0.0.1:{port}/health/ready", 200)

        with tempfile.TemporaryDirectory() as scratch:
            # the whole directory: WAL-mode writes may still sit in the -wal file
            run(engine, "cp", f"{name}:/data/.", scratch)
            db_copy = pathlib.Path(scratch) / "abm.sqlite3"
            digest = run(
                engine,
                "image",
                "inspect",
                image,
                "--format",
                "{{index .RepoDigests 0}}",
                check=False,
            ).stdout.strip()
            manifest = pathlib.Path(scratch) / "manifest.json"
            spec_pointer = dict(
                line.split("=", 1)
                for line in SPEC_VERSION.read_text(encoding="utf-8").splitlines()
                if "=" in line
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=ROOT,
                check=True,
            ).stdout.strip()
            scan = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "scan_aged_items.py"), str(db_copy),
                    "--older-than-hours", "24", "--manifest", str(manifest),
                    "--spec-version", spec_pointer["spec_version"],
                    "--spec-commit", spec_pointer["spec_commit"],
                    "--code-commit", head, "--test-summary", args.test_summary,
                ],
                capture_output=True, text=True, cwd=ROOT, check=False,
            )  # fmt: skip
            expect(
                scan.returncode == 0, "aged-item scan refused the container database"
            )
            data = json.loads(manifest.read_text(encoding="utf-8"))
            expect(
                data["code_commit"] == head, "manifest does not name the exact commit"
            )
            expect(bool(data["image_digest"]), "manifest has no image digest")
            print(
                f"manifest image_digest={data['image_digest']} repo_digest={digest or 'not reported'}"
            )
        print(
            "CONTAINER CHECK PASSED: non-root, read-only app layer, writable data volume, ready, restart"
        )
        return 0
    except CheckFailed as exc:
        print(f"CONTAINER CHECK FAILED: {exc}")
        return 1
    finally:
        run(engine, "rm", "-f", name, check=False)
        run(engine, "volume", "rm", volume, check=False)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
