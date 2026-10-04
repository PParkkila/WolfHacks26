-- Backend-only, use a read-only Tiger role. Bind parameters instead of string interpolation.
-- $1 = session_id, initially submission-smoke-v1.
SELECT payload, published_at
FROM gold.dashboard_latest
WHERE session_id = $1
ORDER BY participant_key;

-- $1 = session_id; $2 = participant_key, e.g. demo:big_ideas:001.
-- Seven-day trend ending at the latest published simulated window.
SELECT payload, published_at
FROM gold.dashboard_windows
WHERE session_id = $1 AND participant_key = $2
  AND window_end > (
    SELECT max(window_end) - INTERVAL '7 days'
    FROM gold.dashboard_windows
    WHERE session_id = $1 AND participant_key = $2
  )
ORDER BY window_end;

-- Recording sanity check: 17 rows per hourly window; 170 windows after both test batches.
SELECT session_id, count(*) AS windows, count(DISTINCT participant_key) AS participants,
       min(window_end) AS first_window_end, max(window_end) AS latest_window_end
FROM gold.dashboard_windows
WHERE session_id = 'submission-smoke-v1'
GROUP BY session_id;
