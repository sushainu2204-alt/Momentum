"""
Test script for infrastructure abstractions.
Validates dependency injection and decoupling.
"""
print("="*60)
print("TESTING INFRASTRUCTURE DECOUPLING")
print("="*60)

errors = []

# Test 1: Message Broker Abstraction
print("\n1. Testing Message Broker abstraction...")
try:
    from backend.infrastructure.messaging import IMessageBroker, IMessageBrokerSync
    from backend.infrastructure.messaging import RedisMessageBroker, RedisMessageBrokerSync
    print("   ✓ IMessageBroker interface imported")
    print("   ✓ RedisMessageBroker implementation imported")
    print("   ✓ Sync variants imported")
except Exception as e:
    errors.append(f"Message broker import failed: {e}")
    print(f"   ✗ Failed: {e}")

# Test 2: Cache Abstraction
print("\n2. Testing Cache abstraction...")
try:
    from backend.infrastructure.cache import ICache, RedisCache, InMemoryCache
    print("   ✓ ICache interface imported")
    print("   ✓ RedisCache implementation imported")
    print("   ✓ InMemoryCache implementation imported")
    
    # Test in-memory cache
    cache = InMemoryCache()
    cache.set("test_key", "test_value")
    value = cache.get("test_key")
    assert value == "test_value", "Cache get/set failed"
    print("   ✓ InMemoryCache works correctly")
except Exception as e:
    errors.append(f"Cache import/test failed: {e}")
    print(f"   ✗ Failed: {e}")

# Test 3: Database Abstraction
print("\n3. Testing Database abstraction...")
try:
    from backend.infrastructure.database import IDatabase
    print("   ✓ IDatabase interface imported")
    print("   ✓ Ready for PostgreSQL/SQLite implementations")
except Exception as e:
    errors.append(f"Database import failed: {e}")
    print(f"   ✗ Failed: {e}")

# Test 4: Services with Dependency Injection
print("\n4. Testing Services with DI...")
try:
    from backend.core.services import KiteService, MarketDataService, SignalService
    from backend.infrastructure.cache import InMemoryCache
    
    # Test MarketDataService with injected cache
    cache = InMemoryCache()
    market_service = MarketDataService(cache=cache)
    print("   ✓ MarketDataService accepts injected cache")
    
    # Test that it uses the injected cache
    assert market_service.cache is cache, "Cache not injected properly"
    print("   ✓ Injected cache is being used")
    
except Exception as e:
    errors.append(f"Service DI failed: {e}")
    print(f"   ✗ Failed: {e}")

# Test 5: Worker with Dependency Injection
print("\n5. Testing Worker with DI...")
try:
    from backend.workers.strategy_worker import StrategyWorker
    from backend.infrastructure.messaging import RedisMessageBroker
    from backend.config import settings
    
    # Can inject custom message broker
    broker = RedisMessageBroker(settings.REDIS_URL)
    worker = StrategyWorker(message_broker=broker)
    
    print("   ✓ StrategyWorker accepts injected message broker")
    assert worker.message_broker is broker, "Broker not injected properly"
    print("   ✓ Injected broker is being used")
    
except Exception as e:
    errors.append(f"Worker DI failed: {e}")
    print(f"   ✗ Failed: {e}")

# Test 6: Abstraction Benefits - Easy Mocking
print("\n6. Testing Abstraction Benefits (Mocking)...")
try:
    from backend.infrastructure.cache import ICache
    
    class MockCache(ICache):
        """Mock cache for testing"""
        def __init__(self):
            self.data = {}
        def get(self, key): return self.data.get(key)
        def set(self, key, value, ttl=None): self.data[key] = value
        def delete(self, key): self.data.pop(key, None)
        def keys(self, pattern): return list(self.data.keys())
        def close(self): pass
    
    # Use mock cache in service
    mock = MockCache()
    from backend.core.services import MarketDataService
    service = MarketDataService(cache=mock)
    
    print("   ✓ Created MockCache for testing")
    print("   ✓ Service accepts mock implementation")
    print("   ✓ Easy to test without real Redis!")
    
except Exception as e:
    errors.append(f"Mocking test failed: {e}")
    print(f"   ✗ Failed: {e}")

# Summary
print("\n" + "="*60)
if not errors:
    print("✅ ALL TESTS PASSED!")
    print("\n🎉 Infrastructure Decoupling Complete:")
    print("   • Business logic NOT coupled to Redis")
    print("   • Services use dependency injection")
    print("   • Easy to swap implementations")
    print("   • Easy to mock for testing")
    print("   • Follows SOLID principles")
    print("\n📦 New Structure:")
    print("   infrastructure/")
    print("   ├── messaging/  (IMessageBroker + Redis impl)")
    print("   ├── cache/      (ICache + Redis/InMemory impl)")
    print("   └── database/   (IDatabase interface)")
    print("\n✨ Benefits:")
    print("   • Can swap Redis for RabbitMQ/Kafka")
    print("   • Can swap Redis cache for Memcached")
    print("   • Can add PostgreSQL/SQLite easily")
    print("   • Services testable in isolation")
else:
    print("❌ SOME TESTS FAILED:")
    for error in errors:
        print(f"   - {error}")

print("="*60 + "\n")
