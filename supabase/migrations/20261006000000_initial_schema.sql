-- Initial schema for the belt companion app (see SRS section 6).
-- Every user-owned table has row-level security: a user sees only their own rows.
-- Deleting a user from auth.users removes all of their data (FR-DAT-2).

create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- Profile and device
-- ---------------------------------------------------------------------------

create table public.profiles (
  id                     uuid primary key references auth.users (id) on delete cascade,
  date_of_birth          date not null,
  typical_cycle_length   smallint check (typical_cycle_length between 15 and 60),
  typical_period_length  smallint check (typical_period_length between 1 and 15),
  consent_at             timestamptz not null,
  -- FR-DAT-3: lets the user stop the chatbot reading their sessions and cycle logs
  chatbot_data_access    boolean not null default true,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);

create table public.devices (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null references auth.users (id) on delete cascade,
  ble_id            text not null,
  name              text,
  firmware_version  text,
  last_seen_at      timestamptz,
  created_at        timestamptz not null default now(),
  unique (user_id, ble_id)
);

-- ---------------------------------------------------------------------------
-- Therapy sessions
-- ---------------------------------------------------------------------------

-- The app generates the id, so a session logged offline keeps the same id when
-- it syncs and a retried upload cannot create a duplicate (NFR-REL-1).
create table public.sessions (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null references auth.users (id) on delete cascade,
  device_id           uuid references public.devices (id) on delete set null,
  started_at          timestamptz not null,
  planned_duration_s  integer not null check (planned_duration_s > 0),
  actual_duration_s   integer check (actual_duration_s >= 0),
  end_reason          text check (end_reason in ('completed', 'user_stopped', 'fault', 'connection_lost')),
  cycle_day           smallint check (cycle_day > 0),
  relief_score        smallint check (relief_score between 1 and 5),
  note                text,
  is_simulated        boolean not null default false,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

create index sessions_user_started_idx on public.sessions (user_id, started_at desc);

-- One row per zone: the summary the recommendation engine learns from.
-- level is the level held longest during the session.
-- pain_intensity is the body-map mark for the region this zone covers; null = no pain marked.
create table public.session_zones (
  session_id      uuid not null references public.sessions (id) on delete cascade,
  zone            smallint not null check (zone between 1 and 4),
  level           smallint not null check (level between 0 and 3),
  pain_intensity  smallint check (pain_intensity between 1 and 10),
  avg_temp_c      numeric(4, 1),
  peak_temp_c     numeric(4, 1),
  seconds_active  integer not null default 0 check (seconds_active >= 0),
  primary key (session_id, zone)
);

-- ---------------------------------------------------------------------------
-- Cycle tracking and prediction
-- ---------------------------------------------------------------------------

create table public.periods (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users (id) on delete cascade,
  start_date  date not null,
  end_date    date,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  check (end_date is null or end_date >= start_date),
  unique (user_id, start_date)
);

create table public.daily_logs (
  user_id     uuid not null references auth.users (id) on delete cascade,
  log_date    date not null,
  flow        text check (flow in ('none', 'spotting', 'light', 'medium', 'heavy')),
  pain        smallint check (pain between 0 and 10),
  symptoms    text[] not null default '{}',
  mood        text,
  note        text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  primary key (user_id, log_date)
);

-- Old rows are kept so predicted dates can be compared with what happened (FR-PRE-7).
create table public.predictions (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references auth.users (id) on delete cascade,
  predicted_start  date not null,
  range_days       smallint not null check (range_days >= 0),
  fertile_start    date,
  fertile_end      date,
  method           text not null check (method in ('onboarding_default', 'recent_average', 'model')),
  model_version    text,
  created_at       timestamptz not null default now()
);

create index predictions_user_created_idx on public.predictions (user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Chatbot
-- ---------------------------------------------------------------------------

create table public.chat_messages (
  id          bigint generated always as identity primary key,
  user_id     uuid not null references auth.users (id) on delete cascade,
  role        text not null check (role in ('user', 'assistant')),
  content     text not null,
  -- knowledge documents cited in an assistant reply: [{"document_id": ..., "title": ...}]
  sources     jsonb,
  created_at  timestamptz not null default now()
);

create index chat_messages_user_created_idx on public.chat_messages (user_id, created_at);

-- Vetted knowledge base. Shared by all users and holds no user data.
create table public.knowledge_documents (
  id           uuid primary key default gen_random_uuid(),
  title        text not null,
  source       text not null,
  reviewed_at  date not null,
  created_at   timestamptz not null default now()
);

-- 384 dimensions matches the gte-small embedding model built into Supabase Edge Functions.
create table public.knowledge_chunks (
  id           bigint generated always as identity primary key,
  document_id  uuid not null references public.knowledge_documents (id) on delete cascade,
  chunk_index  integer not null,
  content      text not null,
  embedding    extensions.vector(384) not null,
  unique (document_id, chunk_index)
);

create index knowledge_chunks_embedding_idx
  on public.knowledge_chunks using hnsw (embedding extensions.vector_cosine_ops);

create or replace function public.match_knowledge_chunks(
  query_embedding extensions.vector(384),
  match_count integer default 5
)
returns table (
  chunk_id     bigint,
  document_id  uuid,
  title        text,
  source       text,
  content      text,
  similarity   double precision
)
language sql
stable
set search_path = public, extensions
as $$
  select
    c.id,
    d.id,
    d.title,
    d.source,
    c.content,
    1 - (c.embedding <=> query_embedding)
  from knowledge_chunks c
  join knowledge_documents d on d.id = c.document_id
  order by c.embedding <=> query_embedding
  limit match_count;
$$;

-- ---------------------------------------------------------------------------
-- updated_at triggers
-- ---------------------------------------------------------------------------

create trigger profiles_set_updated_at before update on public.profiles
  for each row execute function public.set_updated_at();
create trigger sessions_set_updated_at before update on public.sessions
  for each row execute function public.set_updated_at();
create trigger periods_set_updated_at before update on public.periods
  for each row execute function public.set_updated_at();
create trigger daily_logs_set_updated_at before update on public.daily_logs
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Row-level security (NFR-SEC-1)
-- ---------------------------------------------------------------------------

alter table public.profiles               enable row level security;
alter table public.devices                enable row level security;
alter table public.sessions               enable row level security;
alter table public.session_zones          enable row level security;
alter table public.periods                enable row level security;
alter table public.daily_logs             enable row level security;
alter table public.predictions            enable row level security;
alter table public.chat_messages          enable row level security;
alter table public.knowledge_documents    enable row level security;
alter table public.knowledge_chunks       enable row level security;

-- Tables the user owns outright: full access to their own rows.
create policy "own profile" on public.profiles
  for all to authenticated
  using ((select auth.uid()) = id) with check ((select auth.uid()) = id);

create policy "own devices" on public.devices
  for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

create policy "own sessions" on public.sessions
  for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

create policy "own periods" on public.periods
  for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

create policy "own daily logs" on public.daily_logs
  for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

-- Access to a session's zone rows follows ownership of the parent session.
create policy "own session zones" on public.session_zones
  for all to authenticated
  using (exists (select 1 from public.sessions s
                 where s.id = session_id and s.user_id = (select auth.uid())))
  with check (exists (select 1 from public.sessions s
                      where s.id = session_id and s.user_id = (select auth.uid())));

-- Written by the backend (service role bypasses RLS); the user can read,
-- and can clear their chat history (FR-BOT-11).
create policy "read own predictions" on public.predictions
  for select to authenticated
  using ((select auth.uid()) = user_id);

create policy "read own chat messages" on public.chat_messages
  for select to authenticated
  using ((select auth.uid()) = user_id);

create policy "delete own chat messages" on public.chat_messages
  for delete to authenticated
  using ((select auth.uid()) = user_id);

-- Knowledge base: any signed-in user can read; only the backend can write.
create policy "read knowledge documents" on public.knowledge_documents
  for select to authenticated using (true);

create policy "read knowledge chunks" on public.knowledge_chunks
  for select to authenticated using (true);
