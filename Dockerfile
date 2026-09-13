# Two images from one file (DESIGN.md > 3. Deployment): `pipeline` runs etl.py as a batch job, `api` serves the database.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY src ./src
RUN uv sync --frozen --no-dev
COPY eval ./eval
COPY etl.py ./
ENV PATH="/app/.venv/bin:$PATH" RUNS_DIR=/data/runs DATA_DIR=/data DB_PATH=/data/risk.db

FROM base AS pipeline
# the report is mounted, not baked in: docker compose run pipeline --extract --pdf /reports/VestasAnnualReport2025.pdf
ENTRYPOINT ["python", "etl.py"]
CMD ["--list"]

FROM base AS api
EXPOSE 8000
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
