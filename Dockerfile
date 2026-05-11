FROM python:3.11-slim

WORKDIR /app

# Install system dependencies — Playwright Chromium needs these
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
    libgbm1 libasound2 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libpango-1.0-0 libcairo2 libcups2 libatspi2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install Python dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra all-adapters

# Install Playwright Chromium browser with system deps
RUN uv run playwright install --with-deps chromium

# Copy application code
COPY . .

# Runtime directories
RUN mkdir -p workspace skills archives

# Use venv directly
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uv", "run", "python", "main.py"]
