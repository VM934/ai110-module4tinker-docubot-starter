# DocuBot Model Card

## 1. System Overview

DocuBot is a documentation assistant that answers developer questions using a
small local collection of Markdown files. Its goal is to make answers easier to
verify by retrieving relevant evidence before generating or displaying a
response.

Inputs are a user question, the files in `docs/`, and an optional
`GEMINI_API_KEY`. Retrieval-only mode returns cited snippets. Naive mode asks
Gemini to answer from the whole corpus, while RAG mode sends only the most
relevant retrieved snippets to Gemini.

## 2. Retrieval Design

DocuBot normalizes lowercase words with a small predictable stemmer and builds
an inverted index from each term to the files that contain it. A document must
match at least two meaningful query terms (or the single term in a one-word
query) before it is considered. Paragraphs are scored using query coverage,
term frequency with logarithmic damping, and an exact-phrase bonus. The best
paragraph from each matching file is ranked, then the top `k` snippets are
returned with filenames.

This design favors clarity and low dependency cost over semantic recall. It is
fast and easy to inspect, but synonyms such as `credential` and `password` will
not match unless the same normalized terms appear.

## 3. Use of Gemini

- **Naive LLM mode:** sends the full documentation corpus to Gemini with the
  question. It can produce fluent answers, but the large context makes the
  evidence harder to audit.
- **Retrieval only mode:** does not call Gemini. It returns filenames and raw
  paragraphs selected by deterministic search logic.
- **RAG mode:** retrieves first, refuses when no evidence is found, and then
  sends only the selected snippets and the question to Gemini.

The RAG prompt instructs Gemini to use only the supplied snippets, say it does
not know when the snippets are insufficient, avoid inventing APIs or behavior,
and cite source filenames.

## 4. Experiments and Comparisons

The retrieval evaluation found the expected source for all seven answerable
sample questions. The harness reports `0.88` because its eighth query is an
intentional no-answer case and empty expected-source lists count as a miss. The
system correctly returned no result for that question.

| Query | Naive LLM | Retrieval only | RAG | Notes |
|---|---|---|---|---|
| Where is the auth token generated? | Pending approved Gemini run | `AUTH.md`: `generate_access_token` in `auth_utils.py` | Pending approved Gemini run | Retrieval found the exact implementation detail. |
| How do I connect to the database? | Pending approved Gemini run | `DATABASE.md` first, then `SETUP.md` | Pending approved Gemini run | Stemming connected `connect` with `connection`. |
| Which endpoint lists all users? | Pending approved Gemini run | `API_REFERENCE.md` first | Pending approved Gemini run | The top source contains `GET /api/users`. |
| How does a client refresh an access token? | Pending approved Gemini run | `AUTH.md` and `API_REFERENCE.md` | Pending approved Gemini run | Both workflow and endpoint evidence are available. |

Retrieval-only output is less conversational than an LLM response, but its
evidence is visible and reproducible. RAG should improve readability without
giving up grounding; the live Gemini comparison remains intentionally pending
until API-key creation and prompt transmission are authorized.

## 5. Failure Cases and Guardrails

1. **Question:** “How do I process payroll?” The first implementation matched a
   generic word and returned a setup paragraph. It should have refused. The
   document-level minimum-match guardrail now returns: “I do not know based on
   these docs.”
2. **Question:** “How do I connect to the database?” Exact word matching initially
   ranked the general setup guide but missed `connection` in `DATABASE.md`. A
   small normalizer now maps `connection` to `connect`, ranking the database
   guide first.

DocuBot should refuse when no file matches enough meaningful query terms or when
the retrieved context cannot support the requested claim. It also limits the
number and size of snippets and never calls Gemini when retrieval returns no
evidence.

## 6. Limitations and Future Improvements

Current limitations:

1. Lexical search does not understand many synonyms or intent.
2. The tiny stemmer may merge or shorten some words imperfectly.
3. Relevance is based on document text, not freshness or source authority.
4. Only the best paragraph per file is returned, which can omit nearby context.

Future improvements:

1. Add BM25 or embeddings and compare them against the lexical baseline.
2. Preserve headings with paragraphs and add a minimum confidence score.
3. Track document versions and show exact citations or line ranges.

## 7. Responsible Use

Careless use could expose secrets from private documentation or cause developers
to trust an outdated or incomplete answer. A wrong authentication or database
instruction could create outages or security defects.

- Verify important answers against the cited file before changing production
  code or infrastructure.
- Keep secrets and unrelated private files outside the indexed folder.
- Refresh the index when documentation changes.
- Treat a refusal as a safety feature, not a reason to bypass retrieval.
