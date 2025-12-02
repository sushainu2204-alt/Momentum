-- Trading System Database Schema
-- Tracks positions, orders, capital, and trade execution state
-- NOTE: All timestamps use TIMESTAMPTZ (timestamp with time zone) for proper IST handling

-- ================================================================
-- POSITIONS TABLE
-- Tracks all open and closed positions
-- ================================================================
CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    instrument_token BIGINT NOT NULL,
    strategy_name VARCHAR(50) NOT NULL,
    
    -- Entry details
    entry_price DECIMAL(10, 2) NOT NULL,
    entry_time TIMESTAMPTZ NOT NULL,
    quantity INTEGER NOT NULL,
    
    -- Risk management
    stop_loss DECIMAL(10, 2) NOT NULL,
    target DECIMAL(10, 2) NOT NULL,
    original_stop_loss DECIMAL(10, 2),   -- Original SL before trailing (NULL if no trailing)
    highest_price DECIMAL(10, 2),        -- Highest price reached (for trailing SL calculation)
    
    -- Current state
    current_price DECIMAL(10, 2),
    pnl DECIMAL(10, 2) DEFAULT 0,
    pnl_pct DECIMAL(5, 2) DEFAULT 0,
    
    -- Exit details
    exit_price DECIMAL(10, 2),
    exit_time TIMESTAMPTZ,
    exit_reason VARCHAR(50),
    status VARCHAR(20) DEFAULT 'OPEN',  -- OPEN, TARGET_HIT, SL_HIT, TIME_EXIT, MANUAL_EXIT, TRAILING_SL_HIT
    
    -- Metadata
    signal_id INTEGER,  -- Reference to signals table
    entry_order_id VARCHAR(50),  -- Kite order ID for entry
    exit_order_id VARCHAR(50),   -- Kite order ID for exit
    sl_order_id VARCHAR(50),     -- Kite order ID for SL order (for modification)
    target_order_id VARCHAR(50), -- Kite order ID for target order
    metadata JSONB,
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for positions table
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_strategy ON positions(strategy_name);
CREATE INDEX IF NOT EXISTS idx_positions_entry_time ON positions(entry_time);

-- ================================================================
-- ORDERS TABLE
-- Tracks all orders (pending, filled, rejected, cancelled)
-- ================================================================
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(50) UNIQUE NOT NULL,  -- Kite order ID
    symbol VARCHAR(20) NOT NULL,
    instrument_token BIGINT NOT NULL,
    strategy_name VARCHAR(50) NOT NULL,
    
    -- Order details
    order_type VARCHAR(20) NOT NULL,  -- MARKET, LIMIT, SL, SL-M
    transaction_type VARCHAR(10) NOT NULL,  -- BUY, SELL
    quantity INTEGER NOT NULL,
    price DECIMAL(10, 2),
    trigger_price DECIMAL(10, 2),
    
    -- Status
    status VARCHAR(20) NOT NULL,  -- PENDING, COMPLETE, REJECTED, CANCELLED, OPEN
    status_message TEXT,
    filled_quantity INTEGER DEFAULT 0,
    average_price DECIMAL(10, 2),
    
    -- Timestamps
    placed_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    filled_at TIMESTAMPTZ,
    
    -- Relationships
    position_id INTEGER REFERENCES positions(id),
    signal_id INTEGER,
    
    -- Metadata
    metadata JSONB
);

-- Indexes for orders table
CREATE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id);
CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_strategy ON orders(strategy_name);
CREATE INDEX IF NOT EXISTS idx_orders_placed_at ON orders(placed_at);

-- ================================================================
-- CAPITAL_STATE TABLE
-- Tracks available capital and risk limits
-- ================================================================
CREATE TABLE IF NOT EXISTS capital_state (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    
    -- Capital
    starting_capital DECIMAL(12, 2) NOT NULL,
    current_capital DECIMAL(12, 2) NOT NULL,
    available_capital DECIMAL(12, 2) NOT NULL,
    
    -- Allocations
    capital_in_positions DECIMAL(12, 2) DEFAULT 0,
    capital_in_pending_orders DECIMAL(12, 2) DEFAULT 0,
    
    -- Risk tracking
    total_risk DECIMAL(12, 2) DEFAULT 0,  -- SL distance * quantity
    max_risk_allowed DECIMAL(12, 2) NOT NULL,
    
    -- Position limits
    open_positions_count INTEGER DEFAULT 0,
    max_positions_allowed INTEGER NOT NULL,
    
    -- P&L
    realized_pnl DECIMAL(12, 2) DEFAULT 0,
    unrealized_pnl DECIMAL(12, 2) DEFAULT 0,
    total_pnl DECIMAL(12, 2) DEFAULT 0,
    
    -- Metadata
    metadata JSONB,
    
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for capital_state table
CREATE INDEX IF NOT EXISTS idx_capital_date ON capital_state(date);

-- ================================================================
-- TRADE_LOGS TABLE
-- Complete audit trail of all trading decisions
-- ================================================================
CREATE TABLE IF NOT EXISTS trade_logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    log_type VARCHAR(30) NOT NULL,  -- SIGNAL_GENERATED, SIGNAL_IGNORED, ORDER_PLACED, ORDER_FILLED, POSITION_OPENED, POSITION_CLOSED, ERROR
    
    -- Context
    symbol VARCHAR(20),
    strategy_name VARCHAR(50),
    
    -- Decision
    decision VARCHAR(20),  -- EXECUTE, IGNORE, ERROR
    reason TEXT,
    
    -- References
    signal_id INTEGER,
    order_id VARCHAR(50),
    position_id INTEGER,
    
    -- Data
    data JSONB
);

-- Indexes for trade_logs table
CREATE INDEX IF NOT EXISTS idx_trade_logs_timestamp ON trade_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_trade_logs_type ON trade_logs(log_type);
CREATE INDEX IF NOT EXISTS idx_trade_logs_symbol ON trade_logs(symbol);
CREATE INDEX IF NOT EXISTS idx_trade_logs_strategy ON trade_logs(strategy_name);

-- ================================================================
-- SIGNALS TABLE (Updated - add execution status)
-- ================================================================
CREATE TABLE IF NOT EXISTS signals (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    instrument_token BIGINT NOT NULL,
    strategy_name VARCHAR(50) NOT NULL,
    
    -- Signal details
    signal_type VARCHAR(10) NOT NULL,  -- BUY, SELL
    price DECIMAL(10, 2) NOT NULL,
    stop_loss DECIMAL(10, 2),
    target DECIMAL(10, 2),
    quantity INTEGER,
    reason TEXT,
    
    -- Execution status
    execution_status VARCHAR(20) DEFAULT 'PENDING',  -- PENDING, EXECUTED, IGNORED, FAILED
    execution_reason TEXT,
    executed_at TIMESTAMPTZ,
    
    -- References
    position_id INTEGER REFERENCES positions(id),
    order_id VARCHAR(50),
    
    -- Metadata
    metadata JSONB,
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for signals table
CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp);
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
CREATE INDEX IF NOT EXISTS idx_signals_strategy ON signals(strategy_name);
CREATE INDEX IF NOT EXISTS idx_signals_execution_status ON signals(execution_status);

-- ================================================================
-- COOLDOWN_TRACKER TABLE
-- Prevent re-entry on same symbol within cooldown period
-- ================================================================
CREATE TABLE IF NOT EXISTS cooldown_tracker (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    strategy_name VARCHAR(50) NOT NULL,
    last_entry_time TIMESTAMPTZ NOT NULL,
    cooldown_until TIMESTAMPTZ NOT NULL
);

-- Unique constraint for cooldown_tracker (symbol + strategy + exact timestamp)
CREATE UNIQUE INDEX IF NOT EXISTS idx_cooldown_unique 
ON cooldown_tracker(symbol, strategy_name, last_entry_time);

-- Indexes for cooldown_tracker table
CREATE INDEX IF NOT EXISTS idx_cooldown_symbol ON cooldown_tracker(symbol);
CREATE INDEX IF NOT EXISTS idx_cooldown_until ON cooldown_tracker(cooldown_until);

-- ================================================================
-- TRIGGERS
-- ================================================================

-- Update updated_at timestamp automatically
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_positions_updated_at BEFORE UPDATE ON positions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_orders_updated_at BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_capital_updated_at BEFORE UPDATE ON capital_state
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ================================================================
-- VIEWS
-- ================================================================

-- Active positions view
CREATE OR REPLACE VIEW active_positions AS
SELECT 
    p.*,
    o.filled_at as position_filled_at
FROM positions p
LEFT JOIN orders o ON p.entry_order_id = o.order_id
WHERE p.status = 'OPEN';

-- Pending orders view
CREATE OR REPLACE VIEW pending_orders AS
SELECT * FROM orders
WHERE status IN ('PENDING', 'OPEN')
ORDER BY placed_at DESC;

-- Today's trades view
CREATE OR REPLACE VIEW todays_trades AS
SELECT 
    p.*,
    DATE(p.entry_time) as trade_date
FROM positions p
WHERE DATE(p.entry_time) = CURRENT_DATE
ORDER BY p.entry_time DESC;

-- Daily P&L summary
CREATE OR REPLACE VIEW daily_pnl_summary AS
SELECT 
    DATE(entry_time) as date,
    strategy_name,
    COUNT(*) as total_trades,
    SUM(CASE WHEN status IN ('TARGET_HIT', 'SL_HIT', 'TIME_EXIT', 'MANUAL_EXIT') THEN 1 ELSE 0 END) as closed_trades,
    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winners,
    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losers,
    ROUND(AVG(CASE WHEN pnl > 0 THEN pnl END), 2) as avg_win,
    ROUND(AVG(CASE WHEN pnl < 0 THEN pnl END), 2) as avg_loss,
    ROUND(SUM(pnl), 2) as total_pnl,
    ROUND(AVG(pnl_pct), 2) as avg_pnl_pct
FROM positions
GROUP BY DATE(entry_time), strategy_name
ORDER BY date DESC, strategy_name;
