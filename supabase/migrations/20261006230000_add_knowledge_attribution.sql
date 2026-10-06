-- Credit line the source's licence requires to be shown with its content
-- (for example the Open Government Licence wording for NHS pages).
-- The table is still empty, so the column can be required from the start.
alter table public.knowledge_documents
  add column attribution text not null;

-- Return the attribution with each match so the chatbot can show it.
-- The return type changes, so the function has to be dropped and recreated.
drop function public.match_knowledge_chunks(extensions.vector, integer);

create function public.match_knowledge_chunks(
  query_embedding extensions.vector(384),
  match_count integer default 5
)
returns table (
  chunk_id     bigint,
  document_id  uuid,
  title        text,
  source       text,
  attribution  text,
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
    d.attribution,
    c.content,
    1 - (c.embedding <=> query_embedding)
  from knowledge_chunks c
  join knowledge_documents d on d.id = c.document_id
  order by c.embedding <=> query_embedding
  limit match_count;
$$;
