// The chatbot. Answers a signed-in user's question from the vetted knowledge
// base: finds the closest knowledge chunks, asks Gemini to answer using only
// those, and saves both sides of the exchange to chat_messages.
//
// Needs the GEMINI_API_KEY secret (supabase secrets set GEMINI_API_KEY=...).

// Setup type definitions for built-in Supabase Runtime APIs
import "@supabase/functions-js/edge-runtime.d.ts";
import { withSupabase } from "@supabase/server";

// Must be the model the knowledge chunks were embedded with.
const embedder = new Supabase.ai.Session("gte-small");

// Tried in order: when Google reports a model as overloaded or over its rate
// limit, the next one answers instead. Override with the GEMINI_MODELS secret.
const GEMINI_MODELS = (Deno.env.get("GEMINI_MODELS") ??
  "gemini-3.8-flash,gemini-3.7-flash,gemini-3.5-flash-lite").split(",");

// gte-small scores sit in a narrow band: on the test questions unrelated text
// scored up to 0.78 and questions the knowledge base cannot answer up to 0.82,
// while real matches started at 0.83.
const MIN_SIMILARITY = 0.82;
const MATCH_COUNT = 5;
const HISTORY_MESSAGES = 8;
const MAX_MESSAGE_LENGTH = 1000;

const SYSTEM_PROMPT =
  `You are the assistant in Ova, an app for a heat-therapy belt that eases period pain. You give general, educational information about menstrual health. You are not a doctor and you do not diagnose.

Rules:
- Answer only with information found in the numbered sources in the user's message. Do not add medical facts from your own knowledge.
- After each fact, cite the source it came from as [1], [2] and so on.
- If the sources do not answer the question, say you don't have vetted information on that and suggest asking a doctor, nurse or pharmacist. Do not guess. This includes questions about how to use the Ova belt.
- If the user describes something the sources flag as needing medical attention, say so clearly at the start of your answer.
- Never tell the user to start, stop or change a medicine or its dose; say what the sources say and refer them to a health professional.
- For greetings or thanks, reply briefly without sources. For anything unrelated to menstrual health, say what you can help with instead.
- Write in plain, kind language. Keep answers short: a few sentences or a short list. Use your own words rather than copying the sources.
- Write plain text only, with no Markdown such as ** or #. For a list, start each line with a hyphen.`;

type Match = {
  document_id: string;
  title: string;
  source: string;
  attribution: string;
  content: string;
  similarity: number;
};

type Source = Pick<Match, "document_id" | "title" | "source" | "attribution">;

type Turn = { role: "user" | "assistant"; content: string };

// Chunks from the same document share one source number, so a citation
// always points at a document the app can show.
function groupByDocument(matches: Match[]) {
  const sources: Source[] = [];
  const passages: string[][] = [];
  for (const match of matches) {
    let index = sources.findIndex((s) => s.document_id === match.document_id);
    if (index === -1) {
      index = sources.length;
      const { document_id, title, source, attribution } = match;
      sources.push({ document_id, title, source, attribution });
      passages.push([]);
    }
    passages[index].push(match.content);
  }
  return { sources, passages };
}

function buildQuestion(message: string, sources: Source[], passages: string[][]) {
  if (!sources.length) {
    return `Sources: none were found for this message.\n\nUser's message: ${message}`;
  }
  const blocks = sources.map((source, i) =>
    `[${i + 1}] ${source.title}\n${passages[i].join("\n\n")}`
  );
  return `Sources:\n\n${blocks.join("\n\n---\n\n")}\n\n---\n\nUser's message: ${message}`;
}

async function generate(history: Turn[], question: string): Promise<string> {
  const body = JSON.stringify({
    systemInstruction: { parts: [{ text: SYSTEM_PROMPT }] },
    contents: [
      ...history.map((turn) => ({
        role: turn.role === "assistant" ? "model" : "user",
        parts: [{ text: turn.content }],
      })),
      { role: "user", parts: [{ text: question }] },
    ],
    // The limit also covers the model's hidden reasoning, so it is set well
    // above the length of a reply.
    generationConfig: { temperature: 0.2, maxOutputTokens: 8192 },
  });

  let failure = "";
  for (const model of GEMINI_MODELS) {
    const response = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-goog-api-key": Deno.env.get("GEMINI_API_KEY") ?? "",
        },
        body,
      },
    );
    if (!response.ok) {
      failure = `${model} returned ${response.status}: ${await response.text()}`;
      // Busy or rate-limited: another model may still answer.
      if ([429, 500, 503].includes(response.status)) continue;
      break;
    }

    const result = await response.json();
    const candidate = result.candidates?.[0];
    const text = candidate?.content?.parts
      ?.map((part: { text?: string }) => part.text ?? "")
      .join("")
      .trim();
    // A blocked or cut-off reply is not shown: half an answer about health
    // is worse than none.
    if (!text || candidate.finishReason !== "STOP") {
      const reason = candidate?.finishReason ?? result.promptFeedback?.blockReason;
      throw new Error(`${model} gave no usable reply (${reason})`);
    }
    return text;
  }
  throw new Error(`Gemini failed: ${failure}`);
}

// Keeps only the sources the reply cites and renumbers the [n] markers to
// match, so "[1]" in the saved text is always the first saved source.
function cite(reply: string, sources: Source[]) {
  const cited: Source[] = [];
  const content = reply.replace(/\s*\[(\d+(?:\s*,\s*\d+)*)\]/g, (_, numbers: string) => {
    const renumbered = numbers.split(",").flatMap((number) => {
      const source = sources[Number(number) - 1];
      if (!source) return []; // a number the model made up
      if (!cited.includes(source)) cited.push(source);
      return [cited.indexOf(source) + 1];
    });
    return renumbered.length ? ` [${[...new Set(renumbered)].join(", ")}]` : "";
  });
  return { content, cited };
}

export default {
  fetch: withSupabase({ auth: "user" }, async (req, ctx) => {
    const body = await req.json().catch(() => ({}));
    const message = typeof body.message === "string" ? body.message.trim() : "";
    if (!message || message.length > MAX_MESSAGE_LENGTH) {
      return Response.json(
        { error: `message must be 1 to ${MAX_MESSAGE_LENGTH} characters` },
        { status: 400 },
      );
    }
    const askedAt = new Date().toISOString();

    try {
      // Row-level security limits this to the caller's own messages.
      const { data: recent, error: historyError } = await ctx.supabase
        .from("chat_messages")
        .select("role, content")
        .order("id", { ascending: false })
        .limit(HISTORY_MESSAGES);
      if (historyError) throw historyError;

      const embedding = await embedder.run(message, {
        mean_pool: true,
        normalize: true,
      });
      const { data: matches, error: matchError } = await ctx.supabase.rpc(
        "match_knowledge_chunks",
        { query_embedding: JSON.stringify(embedding), match_count: MATCH_COUNT },
      );
      if (matchError) throw matchError;

      const { sources, passages } = groupByDocument(
        (matches as Match[]).filter((m) => m.similarity >= MIN_SIMILARITY),
      );
      const { content, cited } = cite(
        await generate(
          (recent as Turn[]).reverse(),
          buildQuestion(message, sources, passages),
        ),
        sources,
      );

      // Users cannot insert chat messages themselves, so the admin client
      // writes both rows. They go in together: a question is only kept once
      // it has an answer.
      const { data: saved, error: saveError } = await ctx.supabaseAdmin
        .from("chat_messages")
        .insert([
          {
            user_id: ctx.userClaims!.id,
            role: "user",
            content: message,
            sources: null,
            created_at: askedAt,
          },
          {
            user_id: ctx.userClaims!.id,
            role: "assistant",
            content,
            sources: cited,
            created_at: new Date().toISOString(),
          },
        ])
        .select("id, role, content, sources, created_at")
        .order("id");
      if (saveError) throw saveError;

      return Response.json({ messages: saved });
    } catch (error) {
      console.error("chat failed:", error);
      return Response.json(
        { error: "The assistant could not answer just now." },
        { status: 502 },
      );
    }
  }),
};
