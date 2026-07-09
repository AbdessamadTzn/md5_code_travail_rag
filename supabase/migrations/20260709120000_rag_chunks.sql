-- RAG chunks for Code du travail (pgvector)
create extension if not exists vector with schema extensions;

create table if not exists public.rag_chunks (
  id text primary key,
  article_id text not null,
  num text,
  section_path text,
  source text,
  etat text,
  chunk_index integer not null default 0,
  chunk_count integer not null default 1,
  article_hash text,
  content text not null,
  embedding extensions.vector(512) not null,
  embedding_model text not null default 'distiluse-base-multilingual-cased-v2',
  created_at timestamptz not null default now()
);

-- Run after first data upload if you want faster semantic search:
-- create index rag_chunks_embedding_hnsw_idx
--   on public.rag_chunks using hnsw (embedding extensions.vector_cosine_ops);

create index if not exists rag_chunks_num_idx on public.rag_chunks (num);
create index if not exists rag_chunks_article_id_idx on public.rag_chunks (article_id);

alter table public.rag_chunks enable row level security;

create policy "rag_chunks_public_read"
  on public.rag_chunks
  for select
  to anon, authenticated
  using (true);

create or replace function public.match_rag_chunks(
  query_embedding extensions.vector(512),
  match_count integer default 5
)
returns table (
  id text,
  content text,
  article_id text,
  num text,
  section_path text,
  source text,
  etat text,
  chunk_index integer,
  chunk_count integer,
  article_hash text,
  similarity double precision
)
language sql
stable
as $$
  select
    rag_chunks.id,
    rag_chunks.content,
    rag_chunks.article_id,
    rag_chunks.num,
    rag_chunks.section_path,
    rag_chunks.source,
    rag_chunks.etat,
    rag_chunks.chunk_index,
    rag_chunks.chunk_count,
    rag_chunks.article_hash,
    1 - (rag_chunks.embedding <=> query_embedding) as similarity
  from public.rag_chunks
  order by rag_chunks.embedding <=> query_embedding
  limit match_count;
$$;

create or replace function public.search_rag_chunks_by_keyword(
  keyword text,
  match_count integer default 5
)
returns table (
  id text,
  content text,
  article_id text,
  num text,
  section_path text,
  source text,
  etat text,
  chunk_index integer,
  chunk_count integer,
  article_hash text
)
language sql
stable
as $$
  select
    rag_chunks.id,
    rag_chunks.content,
    rag_chunks.article_id,
    rag_chunks.num,
    rag_chunks.section_path,
    rag_chunks.source,
    rag_chunks.etat,
    rag_chunks.chunk_index,
    rag_chunks.chunk_count,
    rag_chunks.article_hash
  from public.rag_chunks
  where rag_chunks.content ilike '%' || keyword || '%'
  limit match_count;
$$;

grant usage on schema public to anon, authenticated;
grant select on public.rag_chunks to anon, authenticated;
grant execute on function public.match_rag_chunks(extensions.vector, integer) to anon, authenticated;
grant execute on function public.search_rag_chunks_by_keyword(text, integer) to anon, authenticated;
