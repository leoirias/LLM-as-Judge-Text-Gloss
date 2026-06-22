FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /workspace

ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

CMD ["uv", "run", "python", "src/main.py", "--experiment", "experiments/qwen3_8b_baseline/config.yaml"]
