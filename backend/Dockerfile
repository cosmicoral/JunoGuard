# JunoGuard gateway.
#
# One process, one port, no local state worth keeping — see docs/deploy.md for
# the replica constraint. Pinned base image and pinned requirements, so two
# builds of the same commit produce the same thing.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# Dependencies first: this layer is cached until requirements change.
# requirements.txt is a hashed lock (see requirements.in); refuse anything else.
COPY requirements.txt ./
RUN pip install --require-hashes -r requirements.txt

COPY app ./app

# Never runs as root. Untrusted package code is delegated to the separately
# isolated sandbox container and never executes inside this FastAPI process.
RUN useradd --system --uid 10001 juno && chown -R juno:juno /srv
USER juno

EXPOSE 8000

# The platform's health check should use /ready, not /health: /health answers
# "the process is up", /ready answers "this deployment can do its job".
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=4).status == 200 else 1)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
