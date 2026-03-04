"""Tests for openevidence models."""

import unittest
from openevidence.models import Article, ArticleStatus, Reference


class TestPizzaToken(unittest.TestCase):
    def test_format(self):
        from openevidence.client import _generate_pizza_token
        token = _generate_pizza_token()
        parts = token.split(".")
        self.assertEqual(len(parts), 2)
        self.assertTrue(parts[0].isdigit())
        self.assertEqual(len(parts[1]), 6)

    def test_uniqueness(self):
        from openevidence.client import _generate_pizza_token
        tokens = {_generate_pizza_token() for _ in range(100)}
        self.assertGreater(len(tokens), 90)  # very likely all unique


class TestArticleModel(unittest.TestCase):
    def _make_response(self, **overrides):
        data = {
            "id": "abc-123",
            "status": "success",
            "title": "Test Title",
            "inputs": {"question": "test?"},
            "output": {
                "text": "Simple answer.",
                "structured_article": {
                    "articlesection_set": [],
                    "follow_up_questions": ["Q1?", "Q2?"],
                    "external_search_results": [],
                },
                "page_type": "ask_oe_light_with_citations",
            },
        }
        data.update(overrides)
        return data

    def test_basic_parse(self):
        article = Article.from_api_response(self._make_response())
        self.assertEqual(article.id, "abc-123")
        self.assertEqual(article.status, ArticleStatus.SUCCESS)
        self.assertEqual(article.title, "Test Title")
        self.assertEqual(article.question, "test?")
        self.assertEqual(article.clean_text, "Simple answer.")
        self.assertEqual(article.follow_up_questions, ["Q1?", "Q2?"])

    def test_running_status(self):
        data = self._make_response(status="running")
        article = Article.from_api_response(data)
        self.assertEqual(article.status, ArticleStatus.RUNNING)

    def test_clean_text_removes_react_component(self):
        data = self._make_response()
        data["output"]["text"] = (
            'REACTCOMPONENT!:!Thinking!:!{"done": true, "summary": "ok"}\n\n'
            "The answer is <strong>42</strong>."
        )
        article = Article.from_api_response(data)
        self.assertNotIn("REACTCOMPONENT", article.clean_text)
        self.assertNotIn("<strong>", article.clean_text)
        self.assertIn("42", article.clean_text)

    def test_sections_and_references(self):
        data = self._make_response()
        data["output"]["structured_article"]["articlesection_set"] = [
            {
                "section_title": "Sec 1",
                "articleparagraph_set": [
                    {
                        "text": "Paragraph text",
                        "references": [
                            {
                                "title": "Ref Title",
                                "journal_name": "JAMA",
                                "year": 2024,
                                "url": "https://example.com",
                                "doi": "10.1234/test",
                                "authors": "Smith J",
                            }
                        ],
                    }
                ],
                "articlefigureparagraph_set": [],
            }
        ]
        article = Article.from_api_response(data)
        self.assertEqual(len(article.sections), 1)
        self.assertEqual(article.sections[0].title, "Sec 1")
        self.assertEqual(len(article.references), 1)
        self.assertEqual(article.references[0].title, "Ref Title")
        self.assertEqual(article.references[0].journal, "JAMA")

    def test_empty_output(self):
        data = self._make_response(status="running")
        data["output"] = None
        article = Article.from_api_response(data)
        self.assertEqual(article.clean_text, "")
        self.assertEqual(article.sections, [])


class TestReference(unittest.TestCase):
    def test_from_paragraph_refs(self):
        refs = Reference.from_paragraph_refs([
            {"title": "A", "journal_name": "B", "year": 2023, "url": "", "doi": "", "authors": ""},
            {"title": "C", "journal_name": "D", "year": 2024, "url": "", "doi": "", "authors": ""},
        ])
        self.assertEqual(len(refs), 2)
        self.assertEqual(refs[0].title, "A")
        self.assertEqual(refs[1].journal, "D")


if __name__ == "__main__":
    unittest.main()
