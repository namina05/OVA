-- Clinical knowledge graph: symptoms, warning signs, conditions, therapies, belt zones and
-- cycle patterns, linked by relations that each cite a vetted knowledge document.
-- Shared by all users and holds no user data. The source of truth is
-- backend/knowledge_graph/clinical_graph.json; `python -m knowledge_graph.sync` loads it here.
--
-- The personal graph is not stored: the backend derives it on request from the user's own
-- sessions, periods and daily_logs rows, so no user data is copied.

create table public.kg_nodes (
  id          text primary key check (id ~ '^[a-z_]+:[a-z0-9_]+$'),
  type        text not null check (type in (
                'symptom', 'condition', 'therapy', 'care_level', 'cycle_phase', 'body_zone', 'cycle_pattern')),
  label       text not null,
  properties  jsonb not null default '{}',
  updated_at  timestamptz not null default now()
);

create table public.kg_edges (
  id               bigint generated always as identity primary key,
  source_id        text not null references public.kg_nodes (id) on delete cascade,
  relation         text not null check (relation ~ '^[A-Z_]+$'),
  target_id        text not null references public.kg_nodes (id) on delete cascade,
  properties       jsonb not null default '{}',
  -- URL of the knowledge document (knowledge_documents.source) and the exact sentence relied on
  evidence_source  text not null,
  evidence_quote   text not null,
  unique (source_id, relation, target_id)
);

create index kg_edges_target_idx on public.kg_edges (target_id);

create trigger kg_nodes_set_updated_at before update on public.kg_nodes
  for each row execute function public.set_updated_at();

alter table public.kg_nodes enable row level security;
alter table public.kg_edges enable row level security;

-- Any signed-in user (and the chatbot acting for them) can read; only the backend writes.
create policy "read kg nodes" on public.kg_nodes for select to authenticated using (true);
create policy "read kg edges" on public.kg_edges for select to authenticated using (true);
