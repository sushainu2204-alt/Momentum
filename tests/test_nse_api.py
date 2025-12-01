"""
Test NSE API Integration

Quick test to verify NSE top gainers API works.
"""

from backend.infrastructure.data_sources import NSEDataSource

def test_nse_api():
    """Test NSE API for top gainers"""
    print("="*70)
    print("TESTING NSE API INTEGRATION")
    print("="*70)
    
    nse = NSEDataSource()
    
    # Test top gainers
    print("\n📈 Fetching Top Gainers from NSE...")
    gainers = nse.get_top_gainers(limit=10)
    
    if gainers:
        print(f"\n✓ Successfully fetched {len(gainers)} top gainers\n")
        print(f"{'Symbol':<15} {'LTP':>10} {'Change %':>10} {'Volume':>15}")
        print("-" * 52)
        
        for gainer in gainers:
            print(f"{gainer.symbol:<15} {gainer.last_price:>10.2f} {gainer.pct_change:>10.2f}% {gainer.volume:>15,}")
    else:
        print("❌ Failed to fetch top gainers")
    
    print("\n" + "="*70)

if __name__ == "__main__":
    test_nse_api()
