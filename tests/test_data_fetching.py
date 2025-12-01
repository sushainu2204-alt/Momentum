"""
Test Data Fetching

Validates that data fetching works correctly for:
- Historical data fetching
- Quote fetching
- Stock screening
- Candidate enrichment
"""

import sys
from datetime import datetime, timedelta

from backend.core.services.kite_service import KiteService
from backend.infrastructure.data_sources import ZerodhaDataSource
from backend.infrastructure.data_sources.universes import FnOUniverse
from backend.core.services.stock_screener_service import StockScreenerService, UniverseFactory
from backend.core.config import StrategyConfigFactory


def test_historical_data():
    """Test historical data fetching"""
    print("\n" + "="*70)
    print("TEST 1: Historical Data Fetching")
    print("="*70)
    
    # Initialize
    kite_service = KiteService()
    kite = kite_service.kite
    
    # Check if authenticated
    try:
        kite.profile()
    except Exception as e:
        print(f"❌ Kite not authenticated: {e}")
        print("Please run: python -m backend.main_new and visit http://localhost:8000/login")
        return False
    
    data_source = ZerodhaDataSource(kite)
    
    # Search for RELIANCE
    instruments = data_source.search_instruments("RELIANCE")
    
    if not instruments:
        print("❌ Could not find RELIANCE")
        return False
    
    instrument = instruments[0]
    print(f"✓ Found instrument: {instrument.tradingsymbol} (token: {instrument.instrument_token})")
    
    # Fetch 5-minute data for last 5 days
    from_date = datetime.now() - timedelta(days=5)
    to_date = datetime.now()
    
    print(f"\nFetching 5-minute data from {from_date.date()} to {to_date.date()}...")
    
    df = data_source.get_historical_data(
        instrument.instrument_token,
        from_date,
        to_date,
        interval='5minute'
    )
    
    if df is None or df.empty:
        print("❌ No data returned")
        return False
    
    print(f"✓ Received {len(df)} candles")
    print(f"\nSample data (last 5 rows):")
    print(df.tail())
    
    # Verify columns
    required_cols = ['open', 'high', 'low', 'close', 'volume']
    missing = [col for col in required_cols if col not in df.columns]
    
    if missing:
        print(f"❌ Missing columns: {missing}")
        return False
    
    print(f"✓ All required columns present: {required_cols}")
    
    return True


def test_quote_fetching():
    """Test quote fetching"""
    print("\n" + "="*70)
    print("TEST 2: Quote Fetching")
    print("="*70)
    
    # Initialize
    kite_service = KiteService()
    kite = kite_service.kite
    
    try:
        kite.profile()
    except Exception:
        print("❌ Kite not authenticated")
        return False
    
    data_source = ZerodhaDataSource(kite)
    
    # Search for multiple stocks
    symbols = ["RELIANCE", "TCS", "INFY"]
    tokens = []
    
    for symbol in symbols:
        instruments = data_source.search_instruments(symbol)
        if instruments:
            tokens.append(instruments[0].instrument_token)
    
    if not tokens:
        print("❌ Could not find any instruments")
        return False
    
    print(f"✓ Found {len(tokens)} instruments")
    print(f"Fetching quotes...")
    
    # Fetch quotes
    try:
        quotes = data_source.get_quotes(tokens)
    except Exception as e:
        print(f"❌ Error fetching quotes: {e}")
        return False
    
    if not quotes:
        print("❌ No quotes returned")
        print(f"Tried to fetch {len(tokens)} tokens: {tokens}")
        return False
    
    print(f"✓ Received {len(quotes)} quotes\n")
    
    for token, quote in quotes.items():
        print(f"{quote.symbol:12} | LTP: ₹{quote.last_price:8.2f} | "
              f"Change: {quote.change_pct:+6.2f}% | "
              f"Vol: {quote.volume:,}")
    
    return True


def test_stock_screening():
    """Test stock screening"""
    print("\n" + "="*70)
    print("TEST 3: Stock Screening")
    print("="*70)
    
    # Initialize
    kite_service = KiteService()
    kite = kite_service.kite
    
    try:
        kite.profile()
    except Exception:
        print("❌ Kite not authenticated")
        return False
    
    data_source = ZerodhaDataSource(kite)
    
    # Use a smaller universe for testing
    from backend.infrastructure.data_sources import CustomUniverse
    test_symbols = ["RELIANCE", "TCS", "INFY", "HDFC", "ICICIBANK", 
                    "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK", "LT"]
    
    universe = CustomUniverse(test_symbols)
    config = StrategyConfigFactory.create(
        'top_gainers_momentum',
        min_gain_pct=0.5,  # Lower threshold for testing
        max_gain_pct=10.0,
        max_open_gain_pct=15.0  # Must be > max_gain_pct
    )
    
    screener = StockScreenerService(data_source, universe, config)
    
    print(f"Universe size: {screener.get_universe_size()}")
    print(f"Screening for stocks with {config.min_gain_pct}% - {config.max_gain_pct}% gain...\n")
    
    # Screen
    candidates = screener.screen_top_gainers()
    
    if not candidates:
        print("⚠️  No candidates found (this is OK if market is flat)")
        return True
    
    print(f"\nTop {min(5, len(candidates))} candidates:")
    for i, candidate in enumerate(candidates[:5], 1):
        print(f"{i}. {candidate.symbol:12} | "
              f"Price: ₹{candidate.current_price:8.2f} | "
              f"Gain: {candidate.gain_pct:+6.2f}% | "
              f"Vol: {candidate.volume:,}")
    
    return True


def test_candidate_enrichment():
    """Test candidate enrichment with average volume"""
    print("\n" + "="*70)
    print("TEST 4: Candidate Enrichment")
    print("="*70)
    
    # Initialize
    kite_service = KiteService()
    kite = kite_service.kite
    
    try:
        kite.profile()
    except Exception:
        print("❌ Kite not authenticated")
        return False
    
    data_source = ZerodhaDataSource(kite)
    
    # Use custom universe
    from backend.infrastructure.data_sources import CustomUniverse
    universe = CustomUniverse(["RELIANCE", "TCS"])
    config = StrategyConfigFactory.create('top_gainers_momentum')
    
    screener = StockScreenerService(data_source, universe, config)
    
    print("Screening stocks...")
    candidates = screener.screen_top_gainers()
    
    if not candidates:
        print("⚠️  No candidates to enrich")
        return True
    
    print(f"Found {len(candidates)} candidates")
    print("\nEnriching with average volume...")
    
    for candidate in candidates:
        enriched = screener.enrich_candidate_with_volume(candidate, lookback_days=10)
        print(f"\n{enriched.symbol}:")
        print(f"  Current Volume:  {enriched.volume:,}")
        print(f"  Average Volume:  {enriched.avg_volume:,.0f}")
        
        if enriched.avg_volume > 0:
            multiplier = enriched.volume / enriched.avg_volume
            print(f"  Volume Multiple: {multiplier:.2f}x")
    
    return True


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("DATA FETCHING VALIDATION TESTS")
    print("="*70)
    
    tests = [
        ("Historical Data", test_historical_data),
        ("Quote Fetching", test_quote_fetching),
        ("Stock Screening", test_stock_screening),
        ("Candidate Enrichment", test_candidate_enrichment)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results[test_name] = result
        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
            results[test_name] = False
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} | {test_name}")
    
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ All tests passed! Data fetching is working correctly.")
    else:
        print("\n⚠️  Some tests failed. Please check the errors above.")
    
    print("="*70 + "\n")


if __name__ == '__main__':
    main()
