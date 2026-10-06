// Shared access to the hosted Supabase project for the knowledge-base scripts.
//
// Run scripts with: node --env-file=supabase/.env.local supabase/scripts/<name>.mjs

// Same project as app/lib/supabase_config.dart.
const SUPABASE_URL = 'https://fvbtqneiutwlutdeslvx.supabase.co';

// The secret key bypasses row-level security, which is what lets these scripts
// write to the knowledge tables. It must never be committed or put in the app.
const SECRET_KEY = process.env.SUPABASE_SECRET_KEY;
if (!SECRET_KEY) {
  console.error('SUPABASE_SECRET_KEY is not set. Run with --env-file=supabase/.env.local');
  process.exit(1);
}

export async function request(path, { method = 'GET', body, prefer } = {}) {
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
export async function embed(input) {
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
