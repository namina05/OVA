-- How many times the user has been asked to rate a session (SRS FR-LOG-3).
-- Kept with the session so the "ask once more, then stop" rule holds across
-- reinstalls and devices.
alter table public.sessions
  add column relief_prompts smallint not null default 0 check (relief_prompts >= 0);
