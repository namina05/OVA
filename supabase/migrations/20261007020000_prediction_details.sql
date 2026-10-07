-- Extra outputs of the cycle model (FR-PRE): expected period length and a day-by-day pain
-- forecast for the predicted period. Written by the backend alongside predicted_start.
-- pain_forecast: [{"date": "2026-11-02", "day": -1, "expected_pain": 3.4, "low": 1.9, "high": 4.9}, ...]
-- where day is relative to the predicted start (0 = first day of the period).
alter table public.predictions
  add column predicted_period_length   smallint check (predicted_period_length between 1 and 15),
  add column period_length_range_days  smallint check (period_length_range_days >= 0),
  add column pain_forecast             jsonb;
