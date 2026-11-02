-- Similarity search used by ai/retrieval/store.py when running on Postgres.
create or replace function match_kb_chunks(
  query_embedding vector(768),
  match_count int default 8,
  filter_area text default null
)
returns table (id text, document_id text, heading text, text text, meta jsonb, similarity float)
language sql stable as $$
  select c.id, c.document_id, c.heading, c.text, c.meta,
         1 - (c.embedding <=> query_embedding) as similarity
  from kb_chunks c
  join kb_documents d on d.id = c.document_id
  where filter_area is null or d.product_area in (filter_area, 'general')
  order by c.embedding <=> query_embedding
  limit match_count;
$$;
