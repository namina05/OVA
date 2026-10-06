// Shows which knowledge chunks the chatbot would retrieve for a question.
//
// Usage: node --env-file=supabase/.env.local supabase/scripts/search.mjs "what helps with cramps?"
// Several questions can be given; add --full to print each chunk's whole text.

import { embed, request } from './client.mjs';

const full = process.argv.includes('--full');
const questions = process.argv.slice(2).filter((argument) => argument !== '--full');
if (!questions.length) {
  console.error('Usage: search.mjs [--full] "question" ["another question" ...]');
  process.exit(1);
}

for (const question of questions) {
  const matches = await request('/rest/v1/rpc/match_knowledge_chunks', {
    method: 'POST',
    body: { query_embedding: JSON.stringify(await embed(question)), match_count: 5 },
  });

  console.log(`\n${question}`);
  for (const match of matches) {
    // The first line of a chunk is its "Title > Heading" path.
    const [heading, ...rest] = match.content.split('\n');
    console.log(`  ${match.similarity.toFixed(3)}  ${heading}`);
    if (full) console.log(rest.join('\n').trim().replace(/^/gm, '         ') + '\n');
  }
}
