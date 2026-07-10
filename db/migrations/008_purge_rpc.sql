-- Migration 008: Purge RPC and entity coverage tracking

-- Purge old bids (soft-delete) — retention in days
CREATE OR REPLACE FUNCTION purge_old_bids(p_retention_days INT DEFAULT 400)
RETURNS TABLE (
    purged_count INT,
    remaining_count INT
) LANGUAGE plpgsql AS $$
DECLARE
    cutoff_date DATE;
    v_purged INT;
BEGIN
    cutoff_date := CURRENT_DATE - p_retention_days;

    -- Soft-delete old inactive records
    UPDATE pncp_raw_bids
    SET is_active = FALSE
    WHERE is_active = TRUE
      AND data_publicacao < cutoff_date;

    GET DIAGNOSTICS v_purged = ROW_COUNT;

    RETURN QUERY
    SELECT
        v_purged,
        COUNT(*)::INT
    FROM pncp_raw_bids
    WHERE is_active = TRUE;
END;
$$;
