"""
Backend Test Suite

Test organization mirrors the backend source structure:
- tests/unit/core/models/      ← tests for backend/core/models/
- tests/unit/core/strategies/  ← tests for backend/core/strategies/
- tests/unit/core/indicators/  ← tests for backend/core/indicators/
- tests/unit/config/           ← tests for backend/config/
- tests/integration/           ← component integration tests
- tests/e2e/                   ← end-to-end system tests

Run all tests:
    pytest

Run by category:
    pytest -m unit
    pytest -m integration

Run with coverage:
    pytest --cov=backend --cov-report=html
"""
