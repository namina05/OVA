// Returns the gte-small embedding (384 numbers) for one piece of text.
// Used by the knowledge-base ingestion script.

// Setup type definitions for built-in Supabase Runtime APIs
import "@supabase/functions-js/edge-runtime.d.ts";
import { withSupabase } from "@supabase/server";

// Created once per worker so the model is not reloaded on every request.
const session = new Supabase.ai.Session("gte-small");

// Secret key only: the publishable key ships inside the app, so allowing it
// would let anyone run embeddings on this project.
export default {
  fetch: withSupabase({ auth: ["secret"] }, async (req) => {
    const { input } = await req.json().catch(() => ({}));

    if (typeof input !== "string" || input.trim() === "") {
      return Response.json(
        { error: "input must be a non-empty string" },
        { status: 400 },
      );
    }

    const embedding = await session.run(input, {
      mean_pool: true,
      normalize: true,
    });

    return Response.json({ embedding });
  }),
};
