-- Migration: Clean up sl_modification_count from positions table
-- Date: 2025-12-03
-- Purpose: modification_count belongs on orders table, not positions
--          Each SL order tracks its own modification count
--          When recreated, new order starts at 0

-- Remove the column from positions if it exists (it was incorrectly added there)
DO $$ 
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'positions' 
        AND column_name = 'sl_modification_count'
    ) THEN
        ALTER TABLE positions 
        DROP COLUMN sl_modification_count;
        
        RAISE NOTICE 'Column sl_modification_count removed from positions table';
    ELSE
        RAISE NOTICE 'Column sl_modification_count does not exist on positions - OK';
    END IF;
END $$;

-- Ensure modification_count exists on orders table (should already be there from schema)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'orders' 
        AND column_name = 'modification_count'
    ) THEN
        ALTER TABLE orders 
        ADD COLUMN modification_count INTEGER DEFAULT 0;
        
        RAISE NOTICE 'Column modification_count added to orders table';
    ELSE
        RAISE NOTICE 'Column modification_count already exists on orders - OK';
    END IF;
END $$;

-- Comment for documentation
COMMENT ON COLUMN orders.modification_count IS 'Count of order modifications (max 25 on Zerodha, we recreate at 20)';
