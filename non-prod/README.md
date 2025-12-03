# Non-Production Code

This folder contains all non-production code for the Momentum Trading System, separated from the main production codebase for clarity and organization.

## Folder Structure

```
non-prod/
├── tests/              # All test files
│   ├── unit/          # Unit tests (fast, isolated)
│   ├── integration/   # Integration tests (services working together)
│   ├── e2e/           # End-to-end tests (full system)
│   ├── conftest.py    # Shared pytest fixtures
│   └── pytest.ini     # Pytest configuration
│
├── scripts/           # Development and utility scripts
│   ├── debug/         # Debug and analysis scripts
│   ├── validation/    # Architecture/code validation scripts
│   ├── manual/        # Manual testing scripts
│   └── backend_scripts/ # Backend utility scripts
│
├── tools/             # Development tools
│   └── backtesting/   # Backtesting engine and runners
│
├── docs/              # Documentation files
│   └── *.md           # Architecture, guides, summaries
│
└── test_signals/      # Test signal data (for testing)
```

## Running Tests

```bash
# From project root
cd non-prod/tests

# Run all tests
pytest

# Run only unit tests
pytest unit/ -m unit

# Run only integration tests
pytest integration/ -m integration

# Run with coverage
pytest --cov=backend --cov-report=html
```

## Scripts

### Debug Scripts (`scripts/debug/`)
- `debug_vwap_filters.py` - Debug VWAP EMA filter analysis
- `manual_test_worker.py` - Interactive manual testing worker

### Validation Scripts (`scripts/validation/`)
- `validate_architecture.py` - Validate architecture compliance

### Manual Test Scripts (`scripts/manual/`)
- `test_sync_manual.py` - Manual sync job testing

## Backtesting Tools

The backtesting tools are in `tools/backtesting/`:

```bash
# Run backtest
python -m non-prod.tools.backtesting.runner --days 7

# Run specific backtest
python -m non-prod.tools.backtesting.run_backtest
```

## Documentation

Key documentation files are stored in `docs/`:
- `ARCHITECTURE.md` - Overall system architecture
- `SYSTEM_ARCHITECTURE.md` - Detailed system design
- `TESTING.md` - Testing guidelines
- `CLEANUP_SUMMARY.md` - Codebase cleanup notes
- `INTEGRATION_SUMMARY.md` - Integration details
