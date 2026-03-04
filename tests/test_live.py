"""
Live integration tests for OpenEvidence API.

These tests make real API calls to openevidence.com.
Run with: python -m pytest tests/test_live.py -v -s

NOTE: These tests may be slow (10-30s each) and may fail if:
- OpenEvidence is down or rate limiting
- Network connectivity issues
- API changes
"""

import unittest
import os

from openevidence import OpenEvidenceClient, ArticleStatus


@unittest.skipUnless(
    os.environ.get("OE_LIVE_TESTS", "").lower() in ("1", "true", "yes"),
    "Set OE_LIVE_TESTS=1 to run live integration tests",
)
class TestLiveAPI(unittest.TestCase):
    """Integration tests against the real OpenEvidence API."""

    def test_ask_simple_question(self):
        """Test asking a simple medical question."""
        with OpenEvidenceClient() as client:
            article = client.ask("What is aspirin?")

        self.assertEqual(article.status, ArticleStatus.SUCCESS)
        self.assertTrue(len(article.id) > 0)
        self.assertTrue(len(article.clean_text) > 50)
        self.assertTrue(len(article.title) > 0)
        print(f"\n  Title: {article.title}")
        print(f"  Text length: {len(article.clean_text)} chars")
        print(f"  References: {len(article.references)}")
        print(f"  Follow-ups: {len(article.follow_up_questions)}")

    def test_ask_stream(self):
        """Test streaming response."""
        with OpenEvidenceClient() as client:
            articles = list(client.ask_stream("What is ibuprofen?"))

        self.assertGreater(len(articles), 0)
        final = articles[-1]
        self.assertEqual(final.status, ArticleStatus.SUCCESS)
        print(f"\n  Polling steps: {len(articles)}")
        print(f"  Final text length: {len(final.clean_text)} chars")

    def test_get_article(self):
        """Test creating then retrieving an article."""
        with OpenEvidenceClient() as client:
            article = client.ask("What is paracetamol?")
            retrieved = client.get_article(article.id)

        self.assertEqual(retrieved.id, article.id)
        self.assertEqual(retrieved.status, ArticleStatus.SUCCESS)


if __name__ == "__main__":
    unittest.main()
