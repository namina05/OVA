// Loads the knowledge-base Markdown files into Supabase: chunks each file,
// embeds every chunk with the `embed` Edge Function, and stores the result in
// knowledge_documents and knowledge_chunks.
//
// Safe to run again: a file that was ingested before is replaced, and the old
// version is only removed once the new one is fully stored.
//
// Usage: node --env-file=supabase/.env.local supabase/scripts/ingest.mjs

import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { chunkDocument } from './chunk.mjs';
import { embed, request } from './client.mjs';

async function ingest(file, markdown) {
  const { meta, chunks } = chunkDocument(markdown);

  // Embed everything before touching the database, so a failure here leaves
  // the stored version of this document as it was.
  const embeddings = [];
  for (const chunk of chunks) embeddings.push(await embed(chunk.content));

  const [document] = await request('/rest/v1/knowledge_documents', {
    method: 'POST',
    prefer: 'return=representation',
    body: {
      title: meta.title,
      source: meta.source,
      reviewed_at: meta.reviewed_at,
      attribution: meta.attribution,
    },
  });

  try {
    await request('/rest/v1/knowledge_chunks', {
      method: 'POST',
      body: chunks.map((chunk, i) => ({
        document_id: document.id,
        chunk_index: chunk.chunk_index,
        content: chunk.content,
        embedding: JSON.stringify(embeddings[i]),
      })),
    });
  } catch (error) {
    await request(`/rest/v1/knowledge_documents?id=eq.${document.id}`, { method: 'DELETE' });
    throw error;
  }

  // Remove earlier versions of the same source; their chunks go with them.
  const source = encodeURIComponent(meta.source);
  await request(`/rest/v1/knowledge_documents?source=eq.${source}&id=neq.${document.id}`, {
    method: 'DELETE',
  });

  console.log(`${file}: stored ${chunks.length} chunks`);
}

const knowledgeDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'knowledge');
const files = readdirSync(knowledgeDir).filter((name) => name.endsWith('.md')).sort();

for (const file of files) {
  await ingest(file, readFileSync(join(knowledgeDir, file), 'utf8'));
}
