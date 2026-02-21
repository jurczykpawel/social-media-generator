FROM python:3.12-slim

# Playwright/Chromium system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk-bridge2.0-0 libdrm2 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2 \
    libatspi2.0-0 libcups2 libxkbcommon0 libxfixes3 \
    fonts-noto-color-emoji fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install chromium

# Create non-root user
RUN useradd -m -s /bin/bash appuser

COPY --chown=appuser:appuser . .

RUN mkdir -p /app/data/user_brands && chown -R appuser:appuser /app/data

USER appuser

EXPOSE 8000

# Default: run API server. Override for CLI usage.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
