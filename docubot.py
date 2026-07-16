"""
Core DocuBot class responsible for:
- Loading documents from the docs/ folder
- Building a simple retrieval index (Phase 1)
- Retrieving relevant snippets (Phase 1)
- Supporting retrieval only answers
- Supporting RAG answers when paired with Gemini (Phase 2)
"""

import glob
import math
import os
import re
from collections import Counter, defaultdict


TOKEN_RE = re.compile(r"[a-z0-9]+")
STOP_WORDS = {
    "a", "all", "an", "and", "any", "are", "as", "at", "be", "by", "does",
    "docs", "documentation", "for", "from", "how", "i", "in", "is", "it",
    "mention", "of", "on", "or", "the", "there", "these", "to", "what",
    "where", "which", "with",
}


def normalize_token(token):
    """Apply a tiny, predictable stemmer for common documentation wording."""
    if token.endswith("ies") and len(token) > 4:
        return f"{token[:-3]}y"
    for suffix in ("ing", "ion", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) > len(suffix) + 3:
            return token[: -len(suffix)]
    return token


def tokenize(text):
    """Return useful normalized search terms from free-form text."""
    return [
        normalize_token(token)
        for token in TOKEN_RE.findall(text.lower())
        if token not in STOP_WORDS
    ]


def split_document_sections(text):
    """Keep each Markdown level-two section together for useful context."""
    sections = []
    current = []
    for line in text.splitlines():
        if line.startswith("## ") and current:
            section = "\n".join(current).strip()
            if section:
                sections.append(section)
            current = [line]
        else:
            current.append(line)

    final_section = "\n".join(current).strip()
    if final_section:
        sections.append(final_section)
    return sections

class DocuBot:
    def __init__(self, docs_folder="docs", llm_client=None):
        """
        docs_folder: directory containing project documentation files
        llm_client: optional Gemini client for LLM based answers
        """
        self.docs_folder = docs_folder
        self.llm_client = llm_client

        # Load documents into memory
        self.documents = self.load_documents()  # List of (filename, text)

        # Build a retrieval index (implemented in Phase 1)
        self.index = self.build_index(self.documents)

    # -----------------------------------------------------------
    # Document Loading
    # -----------------------------------------------------------

    def load_documents(self):
        """
        Loads all .md and .txt files inside docs_folder.
        Returns a list of tuples: (filename, text)
        """
        docs = []
        pattern = os.path.join(self.docs_folder, "*.*")
        for path in glob.glob(pattern):
            if path.endswith(".md") or path.endswith(".txt"):
                with open(path, "r", encoding="utf8") as f:
                    text = f.read()
                filename = os.path.basename(path)
                docs.append((filename, text))
        return docs

    # -----------------------------------------------------------
    # Index Construction (Phase 1)
    # -----------------------------------------------------------

    def build_index(self, documents):
        """
        TODO (Phase 1):
        Build a tiny inverted index mapping lowercase words to the documents
        they appear in.

        Example structure:
        {
            "token": ["AUTH.md", "API_REFERENCE.md"],
            "database": ["DATABASE.md"]
        }

        Keep this simple: split on whitespace, lowercase tokens,
        ignore punctuation if needed.
        """
        index = defaultdict(set)
        for filename, text in documents:
            for token in set(tokenize(text)):
                index[token].add(filename)
        return {token: sorted(filenames) for token, filenames in index.items()}

    # -----------------------------------------------------------
    # Scoring and Retrieval (Phase 1)
    # -----------------------------------------------------------

    def score_document(self, query, text):
        """
        TODO (Phase 1):
        Return a simple relevance score for how well the text matches the query.

        Suggested baseline:
        - Convert query into lowercase words
        - Count how many appear in the text
        - Return the count as the score
        """
        query_tokens = tokenize(query)
        if not query_tokens:
            return 0.0

        text_tokens = tokenize(text)
        frequencies = Counter(text_tokens)
        matched_terms = {token for token in query_tokens if frequencies[token]}
        if not matched_terms:
            return 0.0

        # Reward coverage first, then repeated evidence.  The logarithm prevents
        # a long document from winning only because it repeats a common word.
        coverage = len(matched_terms) / len(set(query_tokens))
        evidence = sum(1.0 + math.log(frequencies[token]) for token in matched_terms)
        phrase_bonus = 1.5 if " ".join(query_tokens) in " ".join(text_tokens) else 0.0
        return round((coverage * 4.0) + evidence + phrase_bonus, 4)

    def retrieve(self, query, top_k=3):
        """
        TODO (Phase 1):
        Use the index and scoring function to select top_k relevant document snippets.

        Return a list of (filename, text) sorted by score descending.
        """
        query_tokens = tokenize(query)
        if not query_tokens or top_k <= 0:
            return []

        candidate_files = set()
        for token in query_tokens:
            candidate_files.update(self.index.get(token, []))
        if not candidate_files:
            return []

        results = []
        unique_query_terms = set(query_tokens)
        minimum_document_matches = min(2, len(unique_query_terms))
        for filename, document_text in self.documents:
            if filename not in candidate_files:
                continue

            document_matches = unique_query_terms.intersection(tokenize(document_text))
            if len(document_matches) < minimum_document_matches:
                continue

            # Keep headings with their supporting details. Paragraph-only
            # splitting separated endpoint names from descriptions and made
            # otherwise-correct retrievals too weak for grounded generation.
            chunks = split_document_sections(document_text)
            scored_chunks = [
                (self.score_document(query, chunk), chunk) for chunk in chunks
            ]
            best_score, best_chunk = max(scored_chunks, default=(0.0, ""))
            if best_score > 0:
                results.append((best_score, filename, best_chunk))

        results.sort(key=lambda item: (-item[0], item[1]))
        return [(filename, text) for _, filename, text in results[:top_k]]

    # -----------------------------------------------------------
    # Answering Modes
    # -----------------------------------------------------------

    def answer_retrieval_only(self, query, top_k=3):
        """
        Phase 1 retrieval only mode.
        Returns raw snippets and filenames with no LLM involved.
        """
        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I do not know based on these docs."

        formatted = []
        for filename, text in snippets:
            formatted.append(f"[{filename}]\n{text}\n")

        return "\n---\n".join(formatted)

    def answer_rag(self, query, top_k=3):
        """
        Phase 2 RAG mode.
        Uses student retrieval to select snippets, then asks Gemini
        to generate an answer using only those snippets.
        """
        if self.llm_client is None:
            raise RuntimeError(
                "RAG mode requires an LLM client. Provide a GeminiClient instance."
            )

        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I do not know based on these docs."

        return self.llm_client.answer_from_snippets(query, snippets)

    # -----------------------------------------------------------
    # Bonus Helper: concatenated docs for naive generation mode
    # -----------------------------------------------------------

    def full_corpus_text(self):
        """
        Returns all documents concatenated into a single string.
        This is used in Phase 0 for naive 'generation only' baselines.
        """
        return "\n\n".join(text for _, text in self.documents)
