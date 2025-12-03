# ============================================================================
# Momentum Trading System - Production Dockerfile
# ============================================================================
# Multi-stage build for optimized Python trading application
#
# Usage:
#   docker build -t momentum-backend .
#   docker run -p 8000:8000 --env-file .env momentum-backend
#
# For development:
#   docker build --target development -t momentum-dev .
# ============================================================================

# =============================================================================
# Stage 1: Base Python Image
# =============================================================================
FROM python:3.13-slim AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# =============================================================================
# Stage 2: Dependencies Builder
# =============================================================================
FROM base AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for layer caching)
COPY backend/requirements.txt /app/requirements.txt

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# =============================================================================
# Stage 3: Development Image
# =============================================================================
FROM base AS development

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install development dependencies
RUN pip install \
    pytest>=8.0.0 \
    pytest-asyncio>=0.23.0 \
    pytest-cov>=4.1.0 \
    pytest-mock>=3.12.0 \
    ruff>=0.1.0 \
    mypy>=1.7.0

# Copy application code
COPY backend/ /app/backend/
COPY pyproject.toml /app/

# Create directories for signals, orders, and logs
RUN mkdir -p /app/signals /app/orders /app/logs

# Create non-root user for security
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser && \
    chown -R appuser:appuser /app

USER appuser

# Default command for development (with auto-reload)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# =============================================================================
# Stage 4: Production Image
# =============================================================================
FROM base AS production

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy only necessary application code (no tests, no dev tools)
COPY backend/__init__.py /app/backend/
COPY backend/main.py /app/backend/
COPY backend/models.py /app/backend/
COPY backend/api/ /app/backend/api/
COPY backend/config/ /app/backend/config/
COPY backend/core/ /app/backend/core/
COPY backend/infrastructure/ /app/backend/infrastructure/
COPY backend/jobs/ /app/backend/jobs/
COPY backend/workers/ /app/backend/workers/
COPY backend/data/ /app/backend/data/

# Create directories for signals, orders, and logs
RUN mkdir -p /app/signals /app/orders /app/logs

# Create non-root user for security
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser && \
    chown -R appuser:appuser /app

USER appuser

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production command (no reload, multiple workers)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

# =============================================================================
# Stage 5: Test Runner Image
# =============================================================================
FROM development AS test

# Copy test files
COPY backend/tests/ /app/backend/tests/

# Run tests as the default command
CMD ["pytest", "backend/tests/", "-v", "--tb=short"]
