# TASK-27: non-root service image with a read-only application layer and one writable data volume.
# The base image is pinned by digest (toolchain.toml); dependencies are installed only here, from the
# hash-verified runtime lock. Mode, ingress and secrets come from ABM_* at run time; the database path
# defaults into /data. The uvicorn access log is off: request paths carry account identifiers (SEC-09).
FROM python:3.12.15-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src \
    ABM_DB_PATH=/data/abm.sqlite3

WORKDIR /app

COPY requirements.lock ./
RUN python -m pip install --require-hashes --only-binary=:all: -r requirements.lock \
 && groupadd --system --gid 10001 abm \
 && useradd --system --uid 10001 --gid abm --no-create-home --shell /usr/sbin/nologin abm \
 && mkdir /data \
 && chown abm:abm /data

COPY src ./src
COPY migrations ./migrations

USER 10001:10001
VOLUME ["/data"]
EXPOSE 8000

# one worker: one shared SQLite connection behind one process-local lock (DEC-0055)
ENTRYPOINT ["python", "-m", "uvicorn", "--factory", "abm.main:app_from_environment", \
            "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
