# Multi-stage, non-root image for the triage engine.
# Mirrors the Chapter 10 container pattern from the TicketHub textbook:
# build in one stage, ship a minimal non-root runtime.

FROM python:3.12-slim AS build
WORKDIR /app
COPY pyproject.toml requirements.txt README.md ./
COPY src ./src
# Install the async API/worker path too so one image serves every role
# (batch `run`, API `serve`, queue `worker`).
RUN pip install --no-cache-dir --prefix=/install ".[serve]"

FROM python:3.12-slim
WORKDIR /app
# Unprivileged runtime user.
RUN useradd -u 10001 -r -g root -s /usr/sbin/nologin triage
COPY --from=build /install /usr/local
COPY examples ./examples
USER 10001

ENTRYPOINT ["triage"]
# Default: triage the baked-in sample logs so the image runs with zero wiring.
CMD ["run", "--reports", "/app/examples/sample_steplogs", "--format", "md", "--fail-under", "0.5"]
