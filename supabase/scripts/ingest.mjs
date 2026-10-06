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

// Same project as app/lib/supabase_config.dart.
const SUPABASE_URL = 'https://fvbtqneiutwlutdeslvx.supabase.co';

// The secret key bypasses row-level security, which is what lets this script
// write to the knowledge tables. It must never be committed or put in the app.
const SECRET_KEY = process.env.SUPABASE_SECRET_KEY;
if (!SECRET_KEY) {
  console.error('SUPABASE_SECRET_KEY is not set. Run with --env-file=supabase/.env.local');
  process.exit(1);
}

async function request(path, { method = 'GET', body, prefer } = {}) {
  const response = await fetch(SUPABASE_URL + path, {
    method,
    headers: {
      apikey: SECRET_KEY,
      'Content-Type': 'application/json',
      ...(prefer ? { Prefer: prefer } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`${method} ${path} failed (${response.status}): ${text}`);
  return text ? JSON.parse(text) : null;
}

// The first call after a quiet period can fail while the model loads.
async function embed(input) {
  for (let attempt = 1; ; attempt++) {
    try {
      const { embedding } = await request('/functions/v1/embed', { method: 'POST', body: { input } });
      if (embedding?.length !== 384) throw new Error(`expected 384 numbers, got ${embedding?.length}`);
      return embedding;
    } catch (error) {
      if (attempt === 3) throw error;
      await new Promise((resolve) => setTimeout(resolve, attempt * 2000));
    }
  }
}

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
