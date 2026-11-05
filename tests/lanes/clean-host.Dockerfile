FROM ubuntu:24.04 AS stage-a
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN apt-get update && apt-get install -y --no-install-recommends python3 pipx sudo && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --shell /bin/bash agentctl && printf 'agentctl ALL=(ALL) NOPASSWD: ALL\n' > /etc/sudoers.d/agentctl && chmod 0440 /etc/sudoers.d/agentctl
ENV PATH=/home/agentctl/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENV GHCUP_INSTALL_BASE_PREFIX=/home/agentctl
ENV PYTHONDONTWRITEBYTECODE=1
USER agentctl
WORKDIR /work/agentctl
COPY --chown=agentctl:agentctl . .
RUN python3 -c 'import os, platform, secrets; from pathlib import Path; from tests.harness.bootstrap_origin import capture; capture(Path.home() / ".local/state/agentctl/clean-host-stage-a", secrets.token_hex(16), platform.system(), os.environ, Path.home())'
RUN pipx install .
RUN agentctl --assume-yes list > /tmp/stage-a-output 2>&1; status=$?; test "$status" -eq 3 && python3 -c 'from pathlib import Path; text = Path("/tmp/stage-a-output").read_text(); assert "tmux" in text and "install" in text'

FROM stage-a AS stage-b
USER root
RUN apt-get update && apt-get install -y --no-install-recommends tmux git && rm -rf /var/lib/apt/lists/*
USER agentctl
RUN curl -fsSL https://claude.ai/install.sh | bash
RUN curl -fsSL https://chatgpt.com/codex/install.sh | sh
RUN pipx install --force --editable '.[dev]'
CMD ["agentctl", "check"]
