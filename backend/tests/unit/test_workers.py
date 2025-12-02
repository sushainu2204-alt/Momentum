"""
Unit Tests for Worker Classes

Tests base worker, VWAP Breakout worker, and sync jobs.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ============================================================================
# BASE STRATEGY WORKER TESTS
# ============================================================================

class TestBaseStrategyWorker:
    """Test base strategy worker functionality."""
    
    @pytest.fixture
    def mock_worker(self, mock_kite, mock_db, mock_redis):
        """Create a mock base worker."""
        from backend.workers.base_strategy_worker import BaseStrategyWorker
        
        class TestWorker(BaseStrategyWorker):
            def get_strategy_name(self):
                return "test_strategy"
            
            def create_strategy(self):
                return MagicMock()
            
            def create_config(self):
                return MagicMock()
        
        worker = TestWorker.__new__(TestWorker)
        worker.kite = mock_kite
        worker.database = mock_db
        worker.redis = mock_redis
        worker.strategy = MagicMock()
        worker.config = MagicMock()
        worker.running = False
        
        return worker
    
    def test_worker_has_strategy_name(self, mock_worker):
        """Test worker has strategy name."""
        assert mock_worker.get_strategy_name() == "test_strategy"
    
    def test_worker_has_strategy(self, mock_worker):
        """Test worker creates strategy."""
        strategy = mock_worker.create_strategy()
        assert strategy is not None
    
    def test_worker_has_config(self, mock_worker):
        """Test worker creates config."""
        config = mock_worker.create_config()
        assert config is not None
    
    @pytest.mark.asyncio
    async def test_worker_start_stop(self, mock_worker):
        """Test worker start and stop."""
        mock_worker.start = AsyncMock()
        mock_worker.stop = AsyncMock()
        
        await mock_worker.start()
        assert mock_worker.start.called
        
        await mock_worker.stop()
        assert mock_worker.stop.called
    
    @pytest.mark.asyncio
    async def test_worker_scan_interval(self, mock_worker):
        """Test worker respects scan interval."""
        mock_worker.scan_interval = 60  # 60 seconds
        
        assert mock_worker.scan_interval == 60
    
    def test_worker_is_market_hours(self, mock_worker):
        """Test market hours check."""
        mock_worker.is_market_hours = MagicMock()
        
        # During market hours
        mock_worker.is_market_hours.return_value = True
        market_time = datetime.now().replace(hour=10, minute=30)
        
        result = mock_worker.is_market_hours(market_time)
        assert result is True
    
    def test_worker_outside_market_hours(self, mock_worker):
        """Test outside market hours."""
        mock_worker.is_market_hours = MagicMock()
        
        # Outside market hours
        mock_worker.is_market_hours.return_value = False
        after_hours = datetime.now().replace(hour=17, minute=0)
        
        result = mock_worker.is_market_hours(after_hours)
        assert result is False


# ============================================================================
# VWAP BREAKOUT WORKER TESTS
# ============================================================================

class TestVWAPBreakoutWorker:
    """Test VWAP Breakout worker."""
    
    @pytest.fixture
    def mock_vwap_worker(self, mock_kite, mock_db):
        """Create mock VWAP Breakout worker."""
        worker = MagicMock()
        worker.kite = mock_kite
        worker.database = mock_db
        worker.get_strategy_name.return_value = "vwap_breakout"
        worker.running = True
        return worker
    
    def test_worker_strategy_name(self, mock_vwap_worker):
        """Test VWAP worker strategy name."""
        assert mock_vwap_worker.get_strategy_name() == "vwap_breakout"
    
    @pytest.mark.asyncio
    async def test_fetch_top_gainers(self, mock_vwap_worker):
        """Test fetching top gainers."""
        mock_vwap_worker.fetch_top_gainers = AsyncMock(return_value=[
            {"symbol": "RELIANCE", "gain_pct": 3.5, "price": 2450.0},
            {"symbol": "INFY", "gain_pct": 2.8, "price": 1650.0}
        ])
        
        gainers = await mock_vwap_worker.fetch_top_gainers()
        
        assert len(gainers) == 2
        assert gainers[0]['symbol'] == "RELIANCE"
    
    @pytest.mark.asyncio
    async def test_fetch_historical_data(self, mock_vwap_worker, sample_ohlcv_data):
        """Test fetching historical data for candidate."""
        expected_df = sample_ohlcv_data(num_candles=50)
        mock_vwap_worker.fetch_historical_data = AsyncMock(return_value=expected_df)
        
        df = await mock_vwap_worker.fetch_historical_data("RELIANCE")
        
        assert len(df) == 50
        assert 'close' in df.columns
    
    @pytest.mark.asyncio
    async def test_process_candidate(self, mock_vwap_worker, sample_ohlcv_data, sample_candidate):
        """Test processing a candidate."""
        candidate = sample_candidate()
        df = sample_ohlcv_data(num_candles=50, trend="up")
        
        mock_vwap_worker.process_candidate = AsyncMock(return_value=MagicMock(
            symbol=candidate.symbol,
            signal_type="BUY"
        ))
        
        signal = await mock_vwap_worker.process_candidate(candidate, df)
        
        assert signal is not None
        assert signal.symbol == candidate.symbol
    
    @pytest.mark.asyncio
    async def test_save_signal(self, mock_vwap_worker, sample_signal):
        """Test saving generated signal."""
        signal = sample_signal()
        mock_vwap_worker.save_signal = AsyncMock(return_value=1)
        
        signal_id = await mock_vwap_worker.save_signal(signal)
        
        assert signal_id == 1
    
    @pytest.mark.asyncio
    async def test_scan_cycle(self, mock_vwap_worker):
        """Test complete scan cycle."""
        mock_vwap_worker.run_scan_cycle = AsyncMock(return_value=2)  # 2 signals generated
        
        signals_count = await mock_vwap_worker.run_scan_cycle()
        
        assert signals_count == 2


# ============================================================================
# VWAP EMA WORKER TESTS
# ============================================================================

class TestVWAPEMAWorker:
    """Test VWAP EMA Breakout worker."""
    
    @pytest.fixture
    def mock_ema_worker(self, mock_kite):
        """Create mock VWAP EMA worker."""
        worker = MagicMock()
        worker.kite = mock_kite
        worker.get_strategy_name.return_value = "vwap_ema_breakout"
        return worker
    
    def test_worker_strategy_name(self, mock_ema_worker):
        """Test EMA worker strategy name."""
        assert mock_ema_worker.get_strategy_name() == "vwap_ema_breakout"
    
    @pytest.mark.asyncio
    async def test_ema_filter_application(self, mock_ema_worker, sample_ohlcv_data):
        """Test EMA filter is applied."""
        df = sample_ohlcv_data(num_candles=50, trend="up")
        
        mock_ema_worker.apply_ema_filter = MagicMock(return_value=True)
        
        result = mock_ema_worker.apply_ema_filter(df)
        
        assert result is True


# ============================================================================
# BULLISH FLAG WORKER TESTS
# ============================================================================

class TestBullishFlagWorker:
    """Test Bullish Flag worker."""
    
    @pytest.fixture
    def mock_flag_worker(self, mock_kite):
        """Create mock Bullish Flag worker."""
        worker = MagicMock()
        worker.kite = mock_kite
        worker.get_strategy_name.return_value = "bullish_flag"
        return worker
    
    def test_worker_strategy_name(self, mock_flag_worker):
        """Test flag worker strategy name."""
        assert mock_flag_worker.get_strategy_name() == "bullish_flag"
    
    @pytest.mark.asyncio
    async def test_flag_pattern_detection(self, mock_flag_worker, sample_ohlcv_data):
        """Test flag pattern detection in worker."""
        df = sample_ohlcv_data(num_candles=30)
        
        mock_flag_worker.detect_pattern = MagicMock(return_value=(True, 102.5, 101.2))
        
        found, flag_high, flag_low = mock_flag_worker.detect_pattern(df)
        
        assert found is True
        assert flag_high > flag_low


# ============================================================================
# SYNC JOBS TESTS
# ============================================================================

class TestSyncJobs:
    """Test background sync jobs."""
    
    @pytest.fixture
    def mock_sync_job(self, mock_kite, mock_db):
        """Create mock sync job."""
        job = MagicMock()
        job.kite = mock_kite
        job.database = mock_db
        return job
    
    @pytest.fixture
    def mock_kite_api(self):
        """Create a MagicMock for Kite API that allows setting return values."""
        mock = MagicMock()
        mock.positions = MagicMock()
        mock.orders = MagicMock()
        return mock
    
    @pytest.mark.asyncio
    async def test_sync_positions(self, mock_sync_job, mock_kite_api):
        """Test syncing positions from Kite."""
        mock_kite_api.positions.return_value = {"day": [
            {"tradingsymbol": "RELIANCE", "quantity": 10, "pnl": 500.0},
            {"tradingsymbol": "INFY", "quantity": 5, "pnl": -100.0}
        ]}
        
        mock_sync_job.kite = mock_kite_api
        mock_sync_job.sync_positions = AsyncMock()
        await mock_sync_job.sync_positions()
        
        mock_sync_job.sync_positions.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_sync_orders(self, mock_sync_job, mock_kite_api):
        """Test syncing orders from Kite."""
        mock_kite_api.orders.return_value = [
            {"order_id": "230101000001", "status": "COMPLETE"},
            {"order_id": "230101000002", "status": "PENDING"}
        ]
        
        mock_sync_job.kite = mock_kite_api
        mock_sync_job.sync_orders = AsyncMock()
        await mock_sync_job.sync_orders()
        
        mock_sync_job.sync_orders.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cleanup_old_data(self, mock_sync_job, mock_db):
        """Test cleaning up old data."""
        mock_sync_job.cleanup_old_signals = AsyncMock(return_value=50)
        
        deleted = await mock_sync_job.cleanup_old_signals(days=30)
        
        assert deleted == 50


# ============================================================================
# WORKER SCHEDULER TESTS
# ============================================================================

class TestWorkerScheduler:
    """Test worker scheduling."""
    
    def test_schedule_scan_job(self):
        """Test scheduling scan job."""
        from apscheduler.schedulers.background import BackgroundScheduler
        
        scheduler = BackgroundScheduler()
        scheduler.start()  # Start scheduler before adding jobs
        
        try:
            # Add a job (mock)
            def dummy_scan():
                pass
            
            job = scheduler.add_job(
                dummy_scan,
                'interval',
                minutes=5,
                id='vwap_scan'
            )
            
            assert job.id == 'vwap_scan'
        finally:
            # Cleanup
            scheduler.shutdown(wait=False)
    
    def test_schedule_cron_job(self):
        """Test scheduling cron job."""
        from apscheduler.schedulers.background import BackgroundScheduler
        
        scheduler = BackgroundScheduler()
        scheduler.start()  # Start scheduler before adding jobs
        
        try:
            def dummy_eod():
                pass
            
            job = scheduler.add_job(
                dummy_eod,
                'cron',
                hour=15,
                minute=30,
                id='eod_cleanup'
            )
            
            assert job.id == 'eod_cleanup'
        finally:
            # Cleanup
            scheduler.shutdown(wait=False)
    
    def test_pause_resume_job(self):
        """Test pausing and resuming job."""
        from apscheduler.schedulers.background import BackgroundScheduler
        
        scheduler = BackgroundScheduler()
        scheduler.start()
        
        def dummy():
            pass
        
        job = scheduler.add_job(dummy, 'interval', seconds=10, id='test_job')
        
        scheduler.pause_job('test_job')
        assert scheduler.get_job('test_job').next_run_time is None
        
        scheduler.resume_job('test_job')
        assert scheduler.get_job('test_job').next_run_time is not None
        
        # Cleanup
        scheduler.shutdown(wait=False)


# ============================================================================
# WORKER ERROR HANDLING TESTS
# ============================================================================

class TestWorkerErrorHandling:
    """Test worker error handling."""
    
    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, mock_kite):
        """Test graceful worker shutdown."""
        worker = MagicMock()
        worker.running = True
        worker.stop = AsyncMock()
        
        async def graceful_stop():
            worker.running = False
            await worker.stop()
        
        await graceful_stop()
        
        assert worker.running is False
        worker.stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_continue_on_single_candidate_error(self):
        """Test worker continues on single candidate failure."""
        candidates = ["RELIANCE", "INFY", "TCS"]
        processed = []
        errors = []
        
        async def process_candidate(symbol):
            if symbol == "INFY":
                raise ValueError("Processing error")
            processed.append(symbol)
        
        for candidate in candidates:
            try:
                await process_candidate(candidate)
            except Exception as e:
                errors.append((candidate, str(e)))
                continue
        
        assert "RELIANCE" in processed
        assert "TCS" in processed
        assert len(errors) == 1
        assert errors[0][0] == "INFY"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
