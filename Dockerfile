FROM python:3.13-slim

# Install Poetry
RUN pip install poetry==2.2.1

WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install dependencies (no virtualenv inside Docker)
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# Copy source and config
COPY src/ ./src/
COPY config.md ./

# Volumes for credentials and logs
VOLUME ["/credentials", "/logs"]

CMD ["python", "src/scheduler.py"]
