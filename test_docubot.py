import unittest

from docubot import DocuBot


class RecordingLLM:
    """Small test double that records the context sent to RAG generation."""

    def __init__(self):
        self.last_query = None
        self.last_snippets = None

    def answer_from_snippets(self, query, snippets):
        self.last_query = query
        self.last_snippets = snippets
        return f"Grounded answer from {snippets[0][0]}"


class DocuBotTests(unittest.TestCase):
    def setUp(self):
        self.bot = DocuBot()

    def test_index_contains_document_terms(self):
        self.assertIn("token", self.bot.index)
        self.assertIn("AUTH.md", self.bot.index["token"])

    def test_retrieval_ranks_relevant_source_first(self):
        results = self.bot.retrieve("Where is the auth token generated?", top_k=2)
        self.assertEqual(results[0][0], "AUTH.md")

    def test_endpoint_retrieval_keeps_route_with_description(self):
        results = self.bot.retrieve("Which endpoint lists all users?", top_k=1)

        self.assertEqual(results[0][0], "API_REFERENCE.md")
        self.assertIn("GET /api/users", results[0][1])

    def test_refresh_retrieval_keeps_route_with_workflow(self):
        results = self.bot.retrieve(
            "How does a client refresh an access token?", top_k=2
        )

        combined = "\n".join(text for _, text in results)
        self.assertIn("/api/refresh", combined)

    def test_unrelated_question_triggers_refusal(self):
        answer = self.bot.answer_retrieval_only("How do I process payroll?")
        self.assertEqual(answer, "I do not know based on these docs.")

    def test_rag_sends_only_retrieved_snippets_to_llm(self):
        llm = RecordingLLM()
        bot = DocuBot(llm_client=llm)
        answer = bot.answer_rag("Which endpoint lists all users?", top_k=1)
        self.assertEqual(answer, "Grounded answer from API_REFERENCE.md")
        self.assertEqual(llm.last_query, "Which endpoint lists all users?")
        self.assertEqual(len(llm.last_snippets), 1)


if __name__ == "__main__":
    unittest.main()
