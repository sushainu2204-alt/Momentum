from backend.core.services import KiteService, MarketDataService

# Initialize services
kite_service = KiteService()
market_service = MarketDataService(kite_service=kite_service)

# Fetch data (will cache)
print("Fetching data (first call - should hit API)...")
df1 = market_service.fetch_intraday_data(
    instrument_token=256265,  # NIFTY 50
    days=5,
    interval="5minute"
)
print(f"✓ Fetched {len(df1)} candles")

# Fetch again (should use cache)
print("\nFetching data (second call - should use cache)...")
df2 = market_service.fetch_intraday_data(
    instrument_token=256265,
    days=5,
    interval="5minute"
)
print(f"✓ Fetched {len(df2)} candles from cache")

# Check they're identical
assert len(df1) == len(df2), "Cache mismatch!"
print("\n✅ Cache working correctly!")
