-- The name the app greets the user with, asked for during onboarding.
-- The hosted database already had this column, added by hand and nullable,
-- so it is only created where missing. No profiles exist yet, so the column
-- can be required from the start.
alter table public.profiles
  add column if not exists display_name text;

alter table public.profiles
  alter column display_name set not null,
  add constraint profiles_display_name_check
    check (char_length(btrim(display_name)) between 1 and 50);
