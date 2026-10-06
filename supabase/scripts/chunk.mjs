// Splits the knowledge-base Markdown files into chunks for embedding.
//
// Rule: one chunk per heading section when it fits in MAX_WORDS; a longer
// section is split at its subsections, then at paragraph breaks. A list stays
// with the sentence that introduces it, and every chunk starts with its
// "Title > Heading" path so it makes sense on its own.
//
// Usage: node supabase/scripts/chunk.mjs   (writes supabase/chunks.json)

import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

// gte-small reads at most 512 tokens; 250 words of medical English plus the
// heading path stays under that.
const MAX_WORDS = 250;
const MIN_WORDS = 40;

const countWords = (text) => text.split(/\s+/).filter(Boolean).length;

export function parseDocument(markdown) {
  const [, frontMatter, body] = markdown.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
  const meta = {};
  for (const line of frontMatter.split('\n')) {
    const [, key, value] = line.match(/^(\w+):\s*(.*)$/);
    meta[key] = value.replace(/^"(.*)"$/, '$1');
  }
  return { meta, body };
}

// Turns the body into a tree of sections. Each section holds the blocks
// (paragraphs and lists) directly under its heading, plus its subsections.
function parseSections(body, title) {
  const root = { level: 1, path: [title], blocks: [], children: [] };
  const stack = [root];
  let list = null;

  for (const line of body.split('\n')) {
    const heading = line.match(/^(#{1,4}) (.*)$/);
    const item = line.match(/^(\s*)- /);
    if (!item) list = null;

    if (heading) {
      const level = heading[1].length;
      if (level === 1) continue; // repeats the document title
      while (stack.at(-1).level >= level) stack.pop();
      const parent = stack.at(-1);
      const section = { level, path: [...parent.path, heading[2]], blocks: [], children: [] };
      parent.children.push(section);
      stack.push(section);
    } else if (item) {
      if (!list) {
        list = { type: 'list', items: [] };
        stack.at(-1).blocks.push(list);
      }
      // A sub-bullet belongs to the top-level bullet above it.
      if (item[1] && list.items.length) list.items[list.items.length - 1] += '\n' + line;
      else list.items.push(line);
    } else if (line.trim()) {
      stack.at(-1).blocks.push({ type: 'paragraph', text: line.trim() });
    }
  }
  return root;
}

const blockText = (block) => (block.type === 'list' ? block.items.join('\n') : block.text);

// Text of a whole section, with subsection headings kept as plain lines.
function sectionText(section, withHeading = false) {
  const parts = withHeading ? [section.path.at(-1)] : [];
  parts.push(...section.blocks.map(blockText));
  parts.push(...section.children.map((child) => sectionText(child, true)));
  return parts.join('\n\n');
}

// Groups pieces of text into chunks of roughly equal size, none over MAX_WORDS.
function pack(pieces, separator, lead = '') {
  const budget = MAX_WORDS - countWords(lead);
  const total = pieces.reduce((sum, piece) => sum + countWords(piece), 0);
  const target = total / Math.ceil(total / budget);
  const groups = [[]];
  let size = 0;
  for (const piece of pieces) {
    const words = countWords(piece);
    if (size && (size >= target || size + words > budget)) {
      groups.push([]);
      size = 0;
    }
    groups.at(-1).push(piece);
    size += words;
  }
  return groups.map((group) => (lead ? lead + '\n\n' : '') + group.join(separator));
}

// Units are the smallest pieces that must not be separated: a paragraph, or a
// list together with the sentence that introduces it.
function toUnits(blocks) {
  const units = [];
  for (let i = 0; i < blocks.length; i++) {
    const block = blocks[i];
    const next = blocks[i + 1];
    if (block.type === 'paragraph' && block.text.endsWith(':') && next?.type === 'list') {
      const whole = block.text + '\n\n' + blockText(next);
      // A list too long for one chunk is split between bullets, and each part
      // repeats the introducing sentence.
      if (countWords(whole) <= MAX_WORDS) units.push(whole);
      else units.push(...pack(next.items, '\n', block.text));
      i++;
    } else if (block.type === 'list') {
      units.push(...pack(block.items, '\n'));
    } else if (countWords(block.text) > MAX_WORDS) {
      units.push(...pack(block.text.split(/(?<=[.?!])\s+(?=[A-Z])/), ' '));
    } else {
      units.push(block.text);
    }
  }
  return units;
}

function chunkSection(section) {
  const isRoot = section.level === 1;
  if (!isRoot && countWords(sectionText(section)) <= MAX_WORDS) {
    return [{ path: section.path, text: sectionText(section) }];
  }

  const own = pack(toUnits(section.blocks), '\n\n')
    .filter(Boolean)
    .map((text) => ({ path: section.path, text }));
  const fromChildren = section.children.flatMap(chunkSection);

  // A short fragment with no heading of its own joins the chunk beside it.
  const last = own.at(-1);
  if (last && countWords(last.text) < MIN_WORDS) {
    if (own.length > 1) {
      own.pop();
      own.at(-1).text += '\n\n' + last.text;
    } else if (fromChildren.length) {
      own.pop();
      fromChildren[0].text = last.text + '\n\n' + fromChildren[0].text;
    }
  }
  return [...own, ...fromChildren];
}

export function chunkDocument(markdown) {
  const { meta, body } = parseDocument(markdown);
  const chunks = chunkSection(parseSections(body, meta.title)).map((chunk, index) => {
    const heading = chunk.path.join(' > ');
    return {
      chunk_index: index,
      heading,
      words: countWords(chunk.text),
      content: heading + '\n\n' + chunk.text,
    };
  });
  return { meta, chunks };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const supabaseDir = join(dirname(fileURLToPath(import.meta.url)), '..');
  const knowledgeDir = join(supabaseDir, 'knowledge');
  const documents = readdirSync(knowledgeDir)
    .filter((name) => name.endsWith('.md'))
    .sort()
    .map((file) => ({ file, ...chunkDocument(readFileSync(join(knowledgeDir, file), 'utf8')) }));

  for (const { file, chunks } of documents) {
    const sizes = chunks.map((chunk) => chunk.words);
    console.log(`${file}: ${chunks.length} chunks, ${Math.min(...sizes)}-${Math.max(...sizes)} words`);
  }
  writeFileSync(join(supabaseDir, 'chunks.json'), JSON.stringify(documents, null, 2) + '\n');
}
