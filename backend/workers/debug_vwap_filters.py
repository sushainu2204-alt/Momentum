"""
Debug VWAP EMA Filters - Shows why each stock passes or fails filters

Usage:
    python -m backend.workers.debug_vwap_filters
"""

import asyncio
import logging
from datetime import datetime
import pandas as pd

from backend.infrastructure.data_sources.nse import NSEDataSource
from backend.infrastructure.data_sources.zerodha import ZerodhaDataSource
from backend.core.services.kite_service import KiteService
from backend.core.strategies.vwap_ema_breakout import VWAPEMABreakoutStrategy
from backend.core.config import VWAPEMABreakoutConfig
from backend.models import Candidate

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Main debug function"""
    logger.info("="*80)
    logger.info("  VWAP EMA FILTER DEBUG - Analyzing why stocks fail filters")
    logger.info("="*80)
    logger.info("")
    
    # Initialize data sources
    nse = NSEDataSource()
    
    kite_service = KiteService()
    kite = kite_service.kite
    zerodha = ZerodhaDataSource(kite) if kite and kite.access_token else None
    
    if not zerodha:
        logger.error("❌ Zerodha not available - need access token")
        return
    
    # Initialize strategy
    config = VWAPEMABreakoutConfig(
        min_gain_pct=2.0,
        max_gain_pct=4.0,
        ema_period=20,
        vwap_enabled=True,
        volume_multiplier=1.5,
        volume_lookback=20,
        breakout_previous_high=True,
        stop_loss_pct=0.7,
        target_pct=1.5,
        position_size_pct=0.10
    )
    strategy = VWAPEMABreakoutStrategy(config)
    
    logger.info(f"Strategy Configuration:")
    logger.info(f"  ├─ Gain Range: {config.min_gain_pct}% - {config.max_gain_pct}%")
    logger.info(f"  ├─ VWAP Enabled: {config.vwap_enabled}")
    logger.info(f"  ├─ EMA Period: {config.ema_period}")
    logger.info(f"  ├─ Volume Multiplier: {config.volume_multiplier}x")
    logger.info(f"  ├─ Breakout Previous High: {config.breakout_previous_high}")
    logger.info(f"  └─ Risk-Reward: 1:{config.target_pct/config.stop_loss_pct:.2f}")
    logger.info("")
    
    # Fetch top gainers from one category
    logger.info("📊 Fetching top gainers from SecGtr20...")
    gainers = nse.get_top_gainers(limit=10, category="SecGtr20")
    
    if not gainers:
        logger.error("❌ No gainers found")
        return
    
    logger.info(f"✅ Found {len(gainers)} gainers")
    logger.info("")
    
    # Test first 5 gainers
    passed_count = 0
    failed_count = 0
    
    for i, gainer in enumerate(gainers[:10], 1):
        logger.info("-" * 80)
        logger.info(f"[{i}] {gainer.symbol} - {gainer.pct_change:.2f}% gain, Volume: {gainer.volume:,}")
        logger.info("-" * 80)
        
        # Create candidate
        candidate = Candidate(
            symbol=gainer.symbol,
            instrument_token=0,  # Not needed for this debug
            current_price=gainer.last_price,
            gain_pct=gainer.pct_change,
            volume=gainer.volume,
            avg_volume=gainer.volume,
            timestamp=datetime.now()
        )
        
        # Fetch historical data
        logger.info("  📈 Fetching historical data...")
        try:
            df = zerodha.get_historical_data(
                symbol=gainer.symbol,
                interval="minute",
                from_date=datetime.now().replace(hour=9, minute=15, second=0, microsecond=0),
                to_date=datetime.now()
            )
            
            if df is None or df.empty:
                logger.info("  ❌ No historical data available")
                failed_count += 1
                logger.info("")
                continue
            
            logger.info(f"  ✅ Got {len(df)} candles")
            
            # Calculate indicators
            df = strategy.calculate_indicators(df)
            
            # Check each filter
            logger.info("")
            logger.info("  🔍 Filter Results:")
            
            # 1. Gain Range
            passed, info = strategy._check_price_range_detailed(candidate)
            status = "✅ PASS" if passed else "❌ FAIL"
            logger.info(f"    1. Gain Range: {status}")
            logger.info(f"       └─ {info}")
            
            # 2. VWAP Filter
            passed_vwap, info = strategy._check_vwap_filter_detailed(df)
            status = "✅ PASS" if passed_vwap else "❌ FAIL"
            logger.info(f"    2. VWAP Filter: {status}")
            logger.info(f"       └─ {info}")
            passed = passed and passed_vwap
            
            # 3. EMA Filter
            passed_ema, info = strategy._check_ema_filter_detailed(df)
            status = "✅ PASS" if passed_ema else "❌ FAIL"
            logger.info(f"    3. EMA Filter: {status}")
            logger.info(f"       └─ {info}")
            passed = passed and passed_ema
            
            # 4. Volume Surge
            passed_vol, info = strategy._check_volume_surge_detailed(df)
            status = "✅ PASS" if passed_vol else "❌ FAIL"
            logger.info(f"    4. Volume Surge: {status}")
            logger.info(f"       └─ {info}")
            passed = passed and passed_vol
            
            # 5. Breakout
            passed_bo, info = strategy._check_breakout_previous_high_detailed(df)
            status = "✅ PASS" if passed_bo else "❌ FAIL"
            logger.info(f"    5. Breakout Previous High: {status}")
            logger.info(f"       └─ {info}")
            passed = passed and passed_bo
            
            logger.info("")
            if passed:
                logger.info(f"  🎯 OVERALL: ✅ ALL FILTERS PASSED - SIGNAL GENERATED")
                passed_count += 1
            else:
                logger.info(f"  🎯 OVERALL: ❌ SOME FILTERS FAILED")
                failed_count += 1
            
        except Exception as e:
            logger.error(f"  ❌ Error processing {gainer.symbol}: {e}")
            failed_count += 1
        
        logger.info("")
    
    # Summary
    logger.info("="*80)
    logger.info("  SUMMARY")
    logger.info("="*80)
    logger.info(f"✅ Passed All Filters: {passed_count}")
    logger.info(f"❌ Failed Filters: {failed_count}")
    logger.info("")


if __name__ == '__main__':
    asyncio.run(main())
