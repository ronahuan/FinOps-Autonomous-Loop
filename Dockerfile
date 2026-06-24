# Multi-target Dockerfile: observer, actor, approval
# Build: docker build --target <target> -t <tag> .

# ---- shared base ----
FROM python:3.11-slim AS base
RUN pip install --no-cache-dir httpx pydantic>=2 python-dotenv

# ---- observer ----
FROM base AS observer
WORKDIR /app/observer
COPY observer/pyproject.toml .
COPY observer/observer/ observer/
COPY observer/tests/fixtures/ tests/fixtures/
RUN pip install --no-cache-dir kubernetes \
    && pip install --no-cache-dir . \
    && mkdir -p /app/observer/out/proposals \
    && chmod -R 777 /app/observer/out
CMD ["python", "-m", "observer.main"]

# ---- actor ----
FROM base AS actor
ENV HOME=/app
RUN pip install --no-cache-dir ansible-core kubernetes \
    && ansible-galaxy collection install kubernetes.core \
    && mkdir -p /app/.ansible/tmp /app/out/backups \
    && chmod -R 777 /app/.ansible /app/out
WORKDIR /app
COPY actor/playbooks/ playbooks/
COPY actor/inventory/ inventory/
COPY actor/collections/ collections/
CMD ["ansible-playbook", "playbooks/remediate-safe.yml"]

# ---- approval ----
FROM base AS approval
RUN pip install --no-cache-dir kubernetes slack-bolt flask
WORKDIR /app
COPY approval/server.py .
EXPOSE 8085
CMD ["python", "server.py"]
