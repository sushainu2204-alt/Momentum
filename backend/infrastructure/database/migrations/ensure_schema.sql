-- ================================================================
-- COMPREHENSIVE SCHEMA MIGRATION
-- ================================================================
-- Date: 2025-12-04
-- Purpose: Ensure all required columns exist for live trading
-- 
-- This migration is IDEMPOTENT - safe to run multiple times
-- It checks before adding columns and won't fail if they exist
--
-- Run with: psql -d your_database -f ensure_schema.sql
-- Or via Python: await db.execute(open('ensure_schema.sql').read())
-- ================================================================

-- ================================================================
-- ORDERS TABLE - Required Columns
-- ================================================================

-- modification_count: Tracks SL order modifications (Zerodha limit is 25)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'orders' AND column_name = 'modification_count'
    ) THEN
        ALTER TABLE orders ADD COLUMN modification_count INTEGER DEFAULT 0;
        RAISE NOTICE '✅ Added orders.modification_count column';
    ELSE
        RAISE NOTICE '✓ orders.modification_count already exists';
    END IF;
END $$;

-- ================================================================
-- POSITIONS TABLE - Required Columns
-- ================================================================

-- sl_order_id: Links position to its SL order for modification
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'positions' AND column_name = 'sl_order_id'
    ) THEN
        ALTER TABLE positions ADD COLUMN sl_order_id VARCHAR(50);
        RAISE NOTICE '✅ Added positions.sl_order_id column';
    ELSE
        RAISE NOTICE '✓ positions.sl_order_id already exists';
    END IF;
END $$;

-- highest_price: Tracks highest price for trailing SL calculation
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'positions' AND column_name = 'highest_price'
    ) THEN
        ALTER TABLE positions ADD COLUMN highest_price DECIMAL(10, 2);
        RAISE NOTICE '✅ Added positions.highest_price column';
    ELSE
        RAISE NOTICE '✓ positions.highest_price already exists';
    END IF;
END $$;

-- original_stop_loss: Original SL before trailing (for records)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'positions' AND column_name = 'original_stop_loss'
    ) THEN
        ALTER TABLE positions ADD COLUMN original_stop_loss DECIMAL(10, 2);
        RAISE NOTICE '✅ Added positions.original_stop_loss column';
    ELSE
        RAISE NOTICE '✓ positions.original_stop_loss already exists';
    END IF;
END $$;

-- target_order_id: Links position to its target order (optional)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'positions' AND column_name = 'target_order_id'
    ) THEN
        ALTER TABLE positions ADD COLUMN target_order_id VARCHAR(50);
        RAISE NOTICE '✅ Added positions.target_order_id column';
    ELSE
        RAISE NOTICE '✓ positions.target_order_id already exists';
    END IF;
END $$;

-- entry_order_id: Links position to its entry order
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'positions' AND column_name = 'entry_order_id'
    ) THEN
        ALTER TABLE positions ADD COLUMN entry_order_id VARCHAR(50);
        RAISE NOTICE '✅ Added positions.entry_order_id column';
    ELSE
        RAISE NOTICE '✓ positions.entry_order_id already exists';
    END IF;
END $$;

-- exit_order_id: Links position to its exit order
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'positions' AND column_name = 'exit_order_id'
    ) THEN
        ALTER TABLE positions ADD COLUMN exit_order_id VARCHAR(50);
        RAISE NOTICE '✅ Added positions.exit_order_id column';
    ELSE
        RAISE NOTICE '✓ positions.exit_order_id already exists';
    END IF;
END $$;

-- ================================================================
-- CLEANUP - Remove deprecated columns
-- ================================================================

-- Remove sl_modification_count from positions (now tracked on orders table)
DO $$ 
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'positions' AND column_name = 'sl_modification_count'
    ) THEN
        ALTER TABLE positions DROP COLUMN sl_modification_count;
        RAISE NOTICE '✅ Removed deprecated positions.sl_modification_count column';
    END IF;
END $$;

-- ================================================================
-- ADD COMMENTS FOR DOCUMENTATION
-- ================================================================

COMMENT ON COLUMN orders.modification_count IS 
    'Count of order modifications (Zerodha limit: 25, we recreate at 20)';

COMMENT ON COLUMN positions.sl_order_id IS 
    'Kite order ID for the SL-M order protecting this position';

COMMENT ON COLUMN positions.highest_price IS 
    'Highest price reached since entry (for trailing SL calculation)';

COMMENT ON COLUMN positions.original_stop_loss IS 
    'Original stop loss before any trailing (NULL if no trailing occurred)';

-- ================================================================
-- INDEXES - Prevent duplicates and improve performance
-- ================================================================

-- Unique partial index: Only one OPEN position per symbol allowed
-- This prevents race conditions during sync
CREATE UNIQUE INDEX IF NOT EXISTS idx_positions_symbol_open 
    ON positions (symbol) WHERE status = 'OPEN';

-- ================================================================
-- VERIFICATION QUERY
-- ================================================================

-- Run this to verify all columns exist:
DO $$
DECLARE
    missing_cols TEXT := '';
BEGIN
    -- Check orders.modification_count
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'orders' AND column_name = 'modification_count') THEN
        missing_cols := missing_cols || 'orders.modification_count, ';
    END IF;
    
    -- Check positions columns
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'positions' AND column_name = 'sl_order_id') THEN
        missing_cols := missing_cols || 'positions.sl_order_id, ';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'positions' AND column_name = 'highest_price') THEN
        missing_cols := missing_cols || 'positions.highest_price, ';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'positions' AND column_name = 'original_stop_loss') THEN
        missing_cols := missing_cols || 'positions.original_stop_loss, ';
    END IF;
    
    IF missing_cols = '' THEN
        RAISE NOTICE '';
        RAISE NOTICE '════════════════════════════════════════════════════════════';
        RAISE NOTICE '  ✅ ALL REQUIRED COLUMNS VERIFIED - READY FOR LIVE TRADING';
        RAISE NOTICE '════════════════════════════════════════════════════════════';
    ELSE
        RAISE EXCEPTION 'MISSING COLUMNS: %', missing_cols;
    END IF;
END $$;
