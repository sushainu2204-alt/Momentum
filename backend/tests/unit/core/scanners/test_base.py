"""
Unit Tests for Scanner Base Classes

Tests the scanner base interface, config, and result classes.
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

from backend.core.scanners.base import (
    IScanner,
    ScannerConfig,
    ScanResult
)
from backend.core.models import Candidate


class TestScannerConfig:
    """Test ScannerConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = ScannerConfig()
        
        assert config.name == "base_scanner"
        assert config.min_gain_pct == 0.0
        assert config.max_gain_pct == 100.0
        assert config.min_price == 20.0
        assert config.max_price == 50000.0
        assert config.min_volume == 0
        assert config.max_results == 50
        assert config.debug == False
    
    def test_custom_values(self):
        """Test custom configuration values."""
        config = ScannerConfig(
            name="custom_scanner",
            min_gain_pct=5.0,
            max_gain_pct=15.0,
            min_price=100.0,
            max_price=5000.0,
            min_volume=100000,
            max_results=20,
            debug=True
        )
        
        assert config.name == "custom_scanner"
        assert config.min_gain_pct == 5.0
        assert config.max_gain_pct == 15.0
        assert config.min_price == 100.0
        assert config.max_price == 5000.0
        assert config.min_volume == 100000
        assert config.max_results == 20
        assert config.debug == True


class TestScanResult:
    """Test ScanResult dataclass."""
    
    def test_empty_result(self):
        """Test empty scan result."""
        result = ScanResult()
        
        assert result.candidates == []
        assert result.scanner_name == ""
        assert result.total_scanned == 0
        assert result.total_passed == 0
        assert result.errors == []
        assert result.success == False
    
    def test_result_with_candidates(self, candidate_factory):
        """Test result with candidates."""
        candidates = [candidate_factory() for _ in range(3)]
        
        result = ScanResult(
            candidates=candidates,
            scanner_name="test_scanner",
            total_scanned=10,
            total_passed=3
        )
        
        assert len(result.candidates) == 3
        assert result.scanner_name == "test_scanner"
        assert result.total_scanned == 10
        assert result.total_passed == 3
        assert result.success == True
    
    def test_result_with_errors(self):
        """Test result with errors."""
        result = ScanResult(
            scanner_name="error_scanner",
            errors=["Connection failed", "Timeout"]
        )
        
        assert result.success == False
        assert len(result.errors) == 2
        assert "Connection failed" in result.errors
    
    def test_result_with_category_stats(self):
        """Test result with category statistics."""
        result = ScanResult(
            scanner_name="multi_category",
            category_stats={
                "FOSec": 50,
                "NIFTY": 25,
                "BANKNIFTY": 15
            }
        )
        
        assert result.category_stats["FOSec"] == 50
        assert result.category_stats["NIFTY"] == 25
        assert result.category_stats["BANKNIFTY"] == 15
    
    def test_result_str_representation(self, candidate_factory):
        """Test string representation."""
        candidates = [candidate_factory() for _ in range(5)]
        
        result = ScanResult(
            candidates=candidates,
            scanner_name="test",
            duration_ms=150.5
        )
        
        str_repr = str(result)
        assert "test" in str_repr
        assert "5 candidates" in str_repr
        assert "150ms" in str_repr or "151ms" in str_repr


class ConcreteScanner(IScanner):
    """Concrete scanner implementation for testing."""
    
    def __init__(self, config=None):
        super().__init__(config)
        self.scan_called = False
    
    async def scan(self) -> ScanResult:
        self.scan_called = True
        return ScanResult(scanner_name=self.get_name())
    
    def get_name(self) -> str:
        return "concrete_scanner"
    
    def get_description(self) -> str:
        return "A concrete scanner for testing"


class TestIScanner:
    """Test IScanner abstract base class."""
    
    def test_init_with_default_config(self):
        """Test scanner initialization with default config."""
        scanner = ConcreteScanner()
        
        assert scanner.config is not None
        assert scanner.config.name == "base_scanner"
    
    def test_init_with_custom_config(self):
        """Test scanner initialization with custom config."""
        config = ScannerConfig(name="custom", min_gain_pct=5.0)
        scanner = ConcreteScanner(config=config)
        
        assert scanner.config.name == "custom"
        assert scanner.config.min_gain_pct == 5.0
    
    @pytest.mark.asyncio
    async def test_scan_method(self):
        """Test scan method is called."""
        scanner = ConcreteScanner()
        
        result = await scanner.scan()
        
        assert scanner.scan_called == True
        assert result.scanner_name == "concrete_scanner"
    
    def test_get_name(self):
        """Test get_name returns correct name."""
        scanner = ConcreteScanner()
        
        assert scanner.get_name() == "concrete_scanner"
    
    def test_get_description(self):
        """Test get_description returns description."""
        scanner = ConcreteScanner()
        
        assert "concrete scanner" in scanner.get_description().lower()
    
    @pytest.mark.asyncio
    async def test_initialize_method(self):
        """Test initialize method (default does nothing)."""
        scanner = ConcreteScanner()
        
        # Should not raise
        await scanner.initialize()
    
    @pytest.mark.asyncio
    async def test_cleanup_method(self):
        """Test cleanup method (default does nothing)."""
        scanner = ConcreteScanner()
        
        # Should not raise
        await scanner.cleanup()
    
    def test_filter_candidates_price_filter(self, candidate_factory):
        """Test filter_candidates applies price filter."""
        config = ScannerConfig(min_price=100.0, max_price=500.0)
        scanner = ConcreteScanner(config)
        
        candidates = [
            candidate_factory(current_price=50.0),   # Too low
            candidate_factory(current_price=200.0),  # OK
            candidate_factory(current_price=600.0),  # Too high
            candidate_factory(current_price=300.0),  # OK
        ]
        
        filtered = scanner.filter_candidates(candidates)
        
        assert len(filtered) == 2
        assert all(100.0 <= c.current_price <= 500.0 for c in filtered)
    
    def test_filter_candidates_gain_filter(self, candidate_factory):
        """Test filter_candidates applies gain filter."""
        config = ScannerConfig(
            min_gain_pct=2.0,
            max_gain_pct=10.0,
            min_price=0,  # Disable price filter
            max_price=100000
        )
        scanner = ConcreteScanner(config)
        
        candidates = [
            candidate_factory(gain_pct=1.0, current_price=100),   # Too low
            candidate_factory(gain_pct=5.0, current_price=100),   # OK
            candidate_factory(gain_pct=15.0, current_price=100),  # Too high
            candidate_factory(gain_pct=8.0, current_price=100),   # OK
        ]
        
        filtered = scanner.filter_candidates(candidates)
        
        assert len(filtered) == 2
        assert all(2.0 <= c.gain_pct <= 10.0 for c in filtered)
    
    def test_filter_candidates_volume_filter(self, candidate_factory):
        """Test filter_candidates applies volume filter."""
        config = ScannerConfig(
            min_volume=50000,
            min_price=0,
            max_price=100000,
            min_gain_pct=-100,
            max_gain_pct=100
        )
        scanner = ConcreteScanner(config)
        
        candidates = [
            candidate_factory(volume=10000, current_price=100, gain_pct=5),   # Too low
            candidate_factory(volume=100000, current_price=100, gain_pct=5),  # OK
            candidate_factory(volume=75000, current_price=100, gain_pct=5),   # OK
        ]
        
        filtered = scanner.filter_candidates(candidates)
        
        assert len(filtered) == 2
        assert all(c.volume >= 50000 for c in filtered)
    
    def test_filter_candidates_max_results(self, candidate_factory):
        """Test filter_candidates limits results."""
        config = ScannerConfig(
            max_results=3,
            min_price=0,
            max_price=100000
        )
        scanner = ConcreteScanner(config)
        
        candidates = [candidate_factory(current_price=100) for _ in range(10)]
        
        filtered = scanner.filter_candidates(candidates)
        
        assert len(filtered) == 3
    
    def test_log_scan_start(self, caplog):
        """Test _log_scan_start logs correctly."""
        import logging
        caplog.set_level(logging.INFO)
        
        scanner = ConcreteScanner()
        scanner._log_scan_start()
        
        assert "concrete_scanner" in caplog.text
        assert "Starting scan" in caplog.text
    
    def test_log_scan_result_success(self, candidate_factory, caplog):
        """Test _log_scan_result logs success."""
        import logging
        caplog.set_level(logging.INFO)
        
        scanner = ConcreteScanner()
        result = ScanResult(
            scanner_name="concrete_scanner",
            candidates=[candidate_factory()],
            duration_ms=100
        )
        
        scanner._log_scan_result(result)
        
        assert "concrete_scanner" in caplog.text
        assert "1 candidates" in caplog.text
    
    def test_log_scan_result_no_candidates(self, caplog):
        """Test _log_scan_result logs warning when no candidates."""
        import logging
        caplog.set_level(logging.WARNING)
        
        scanner = ConcreteScanner()
        result = ScanResult(scanner_name="concrete_scanner")
        
        scanner._log_scan_result(result)
        
        assert "No candidates found" in caplog.text
    
    def test_log_scan_result_with_errors(self, caplog):
        """Test _log_scan_result logs errors."""
        import logging
        caplog.set_level(logging.ERROR)
        
        scanner = ConcreteScanner()
        result = ScanResult(
            scanner_name="concrete_scanner",
            errors=["API error", "Timeout"]
        )
        
        scanner._log_scan_result(result)
        
        assert "API error" in caplog.text
        assert "Timeout" in caplog.text
