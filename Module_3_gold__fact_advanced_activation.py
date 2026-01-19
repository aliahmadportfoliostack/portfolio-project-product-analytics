import duckdb, os

con = duckdb.connect(
    os.path.join(os.path.dirname(__file__), "..", "..", "product_analytics_light.db")
)

con.execute("""
/*
================================================================================
gold__fact_advanced_activation
================================================================================

Context
- Many accounts sign up, but only some reach real product usage.
- This table defines a simple, explainable activation signal.

What this table does
- Looks at the first 14 days after an account is created
- Checks for two signals:
  1) Usage of core product functionality
  2) Evidence of deal creation / pipeline usage
- Combines these into activation and time-to-value
*/

CREATE OR REPLACE TABLE gold__fact_advanced_activation AS
WITH accounts AS (
    -- Base list of accounts with signup date
    SELECT
        AccountId,
        CAST(CreatedDate AS DATE) AS CreatedDate
    FROM gold__dim_accounts
),

core_events AS (
    -- First time an account uses core CRM functionality
    SELECT
        e.AccountId,
        MIN(CAST(e.EventDate AS DATE)) AS FirstCoreEventDate,
        COUNT(*) AS CoreEventsInFirst14Days
    FROM gold__fact_product_events e
    JOIN accounts a
      ON e.AccountId = a.AccountId
    WHERE e.HasDealContext = TRUE
      AND CAST(e.EventDate AS DATE)
          BETWEEN a.CreatedDate AND (a.CreatedDate + INTERVAL 14 DAY)
    GROUP BY 1
),

deals AS (
    -- First observed deal activity after signup
    SELECT
        d.AccountId,
        MIN(CAST(d.CreatedDate AS DATE)) AS FirstDealDate,
        COUNT(*) AS DealsInFirst14Days
    FROM gold__fact_deals d
    JOIN accounts a
      ON d.AccountId = a.AccountId
    WHERE CAST(d.CreatedDate AS DATE)
          BETWEEN a.CreatedDate AND (a.CreatedDate + INTERVAL 14 DAY)
    GROUP BY 1
)

SELECT
    a.AccountId,
    a.CreatedDate,

    -- Supporting timestamps for inspection
    e.FirstCoreEventDate,
    d.FirstDealDate,

    -- Activation happens once both signals are present
    CASE
        WHEN e.FirstCoreEventDate IS NOT NULL
         AND d.FirstDealDate IS NOT NULL
        THEN GREATEST(e.FirstCoreEventDate, d.FirstDealDate)
        ELSE NULL
    END AS ActivationDate,

    -- Simple activation flag
    CASE
        WHEN e.FirstCoreEventDate IS NOT NULL
         AND d.FirstDealDate IS NOT NULL
        THEN TRUE
        ELSE FALSE
    END AS IsActivated,

    -- Days from signup to activation
    CASE
        WHEN e.FirstCoreEventDate IS NOT NULL
         AND d.FirstDealDate IS NOT NULL
        THEN DATE_DIFF(
            'day',
            a.CreatedDate,
            GREATEST(e.FirstCoreEventDate, d.FirstDealDate)
        )
        ELSE NULL
    END AS TimeToValueDays,

    -- Diagnostic counts used for analysis and segmentation
    COALESCE(e.CoreEventsInFirst14Days, 0) AS CoreEventsInFirst14Days,
    COALESCE(d.DealsInFirst14Days, 0)      AS DealsInFirst14Days

FROM accounts a
LEFT JOIN core_events e
    ON a.AccountId = e.AccountId
LEFT JOIN deals d
    ON a.AccountId = d.AccountId
ORDER BY a.AccountId;
""")

print("✅ Created gold__fact_advanced_activation")

con.close()
