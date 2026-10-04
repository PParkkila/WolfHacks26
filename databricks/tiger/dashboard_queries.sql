-- Backend-only, use a read-only Tiger role. Bind parameters instead of string interpolation.
-- $1 = session_id: continuous-oct4-v1 (66 people); submission-smoke-v1 remains the 17-person fallback.
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

-- Recording sanity check: 66 rows per hourly window in continuous-oct4-v1.
SELECT session_id, count(*) AS windows, count(DISTINCT participant_key) AS participants,
       min(window_end) AS first_window_end, max(window_end) AS latest_window_end
FROM gold.dashboard_windows
WHERE session_id = $1
GROUP BY session_id;

-- Prediction availability. A scored session should have no pending/null scores.
SELECT count(*) AS windows,
       count(*) FILTER (WHERE payload->>'wearable_risk_indicator' IS NOT NULL) AS scored_windows,
       min((payload->>'wearable_risk_indicator')::double precision) AS minimum_score,
       max((payload->>'wearable_risk_indicator')::double precision) AS maximum_score
FROM gold.dashboard_windows
WHERE session_id = $1;
