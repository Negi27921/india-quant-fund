-- Migration 022: Auto-expand dim_company when screener data is upserted
--
-- Every INSERT or UPDATE on fact_screener_fundamentals:
--   1. Updates existing dim_company row (price + market_cap) if ticker matches
--   2. Inserts a new dim_company row if ticker is not yet in universe
--
-- This replaces the manual /market/universe/sync endpoint for day-to-day ops.
-- The sync endpoint remains for emergency bulk repair only.
--
-- Run after 021_stock_snapshot_view.sql

CREATE OR REPLACE FUNCTION sync_dim_company_from_screener()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    -- Step 1: update existing row if ticker already in dim_company
    UPDATE dim_company
    SET
        market_cap_inr_cr = NEW.market_cap_cr,
        current_price_inr = NEW.current_price,
        updated_at        = NOW()
    WHERE ticker = NEW.ticker;

    -- Step 2: insert new row only if ticker was not found (UPDATE affected 0 rows)
    IF NOT FOUND THEN
        INSERT INTO dim_company (
            company_id,
            ticker,
            company_name,
            exchange,
            market_cap_inr_cr,
            current_price_inr,
            source,
            fetched_at,
            updated_at
        ) VALUES (
            NEW.ticker,                           -- company_id = ticker for screener-sourced rows
            NEW.ticker,
            NEW.ticker,                           -- company_name bootstrapped from ticker; enriched later
            'NSE',
            NEW.market_cap_cr,
            NEW.current_price,
            'screener',
            NOW(),
            NOW()
        )
        ON CONFLICT (company_id) DO NOTHING;      -- safety: ignore if company_id already taken
    END IF;

    RETURN NEW;
END;
$$;

-- Drop old trigger if it exists from a previous run
DROP TRIGGER IF EXISTS trg_sync_dim_company_from_screener ON fact_screener_fundamentals;

CREATE TRIGGER trg_sync_dim_company_from_screener
AFTER INSERT OR UPDATE ON fact_screener_fundamentals
FOR EACH ROW
EXECUTE FUNCTION sync_dim_company_from_screener();
