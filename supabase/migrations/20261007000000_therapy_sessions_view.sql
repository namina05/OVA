-- Data the recommendation engine needs that the initial schema does not capture yet.
-- pain_after: the pain level the user reports after the session (0-10). Together with
--   session_zones.pain_intensity (the pain marked before the session) it gives the
--   pain reduction the model learns from.
-- therapy_mode: how the heat was applied (e.g. 'continuous', 'pulse'). Allowed values are
--   enforced by the backend's configurable SafetyValidator, not by a check constraint here.
alter table public.sessions
  add column pain_after    smallint check (pain_after between 0 and 10),
  add column therapy_mode  text;

-- One row per session in the shape the recommender reads. A view, so no user data is copied.
-- zone:        the zone heated longest during the session
-- pain_zone:   the zone the user marked as most painful, pain_before its intensity
-- temperature_c is the average temperature measured on the heated zone.
-- security_invoker makes the underlying tables' row-level security apply to the caller.
create view public.therapy_sessions
with (security_invoker = true) as
select
  s.id                                                           as session_id,
  s.user_id,
  s.started_at,
  heated.zone                                                    as zone,
  heated.avg_temp_c                                              as temperature_c,
  round(coalesce(s.actual_duration_s, s.planned_duration_s) / 60.0, 1) as duration_min,
  s.therapy_mode,
  pain.zone                                                      as pain_zone,
  pain.pain_intensity                                            as pain_before,
  s.pain_after,
  s.cycle_day,
  s.end_reason
from public.sessions s
left join lateral (
  select z.zone, z.avg_temp_c
  from public.session_zones z
  where z.session_id = s.id and z.seconds_active > 0
  order by z.seconds_active desc, z.zone
  limit 1
) heated on true
left join lateral (
  select z.zone, z.pain_intensity
  from public.session_zones z
  where z.session_id = s.id and z.pain_intensity is not null
  order by z.pain_intensity desc, z.zone
  limit 1
) pain on true
where not s.is_simulated;
