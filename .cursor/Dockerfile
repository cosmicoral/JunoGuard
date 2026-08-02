# Cloud agent base image for JunoGuard.
# Do not COPY the project — Cursor checks out the workspace at the correct commit.

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
      jq \
      build-essential \
      python3 \
      python3-pip \
      python3-venv \
      python3-dev \
      postgresql-client \
      docker.io \
      docker-compose-v2 \
      openssl \
    && rm -rf /var/lib/apt/lists/*

# Node.js 22 (matches local cloud agent runtime used for the dashboard / CLI package)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Use the distro pip as-is. Upgrading Debian's pip fails (no RECORD file).
WORKDIR /workspace
