"""Data models for OpenEvidence API responses."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ArticleStatus(str, Enum):
    """Status of an article query."""
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    QUEUED = "queued"


@dataclass
class Reference:
    """A citation/reference from a medical source."""
    title: str
    journal: str = ""
    year: str = ""
    authors: str = ""
    url: str = ""
    doi: str = ""

    @classmethod
    def from_paragraph_refs(cls, refs: list[dict]) -> list["Reference"]:
        """Parse references from articleparagraph reference data."""
        results = []
        for ref in refs:
            results.append(cls(
                title=ref.get("title", ""),
                journal=ref.get("journal_name", ref.get("journal", "")),
                year=str(ref.get("year", "")),
                authors=ref.get("authors", ""),
                url=ref.get("url", ""),
                doi=ref.get("doi", ""),
            ))
        return results


@dataclass
class Section:
    """A section of the article response."""
    title: str = ""
    paragraphs: list[str] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)


@dataclass
class Article:
    """Represents a complete OpenEvidence article response."""
    id: str
    status: ArticleStatus
    title: str = ""
    question: str = ""
    text: str = ""
    clean_text: str = ""
    sections: list[Section] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)
    raw_response: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_api_response(cls, data: dict) -> "Article":
        """Parse an Article from the API response JSON."""
        article_id = data.get("id", "")
        status = ArticleStatus(data.get("status", "running"))
        title = data.get("title", "")
        question = data.get("inputs", {}).get("question", "")

        output = data.get("output") or {}
        raw_text = output.get("text", "")

        # Clean text: remove REACTCOMPONENT markers and HTML tags
        clean = cls._clean_text(raw_text)

        # Parse structured article
        structured = output.get("structured_article", {}) or {}
        sections = []
        all_refs = []

        for sec_data in structured.get("articlesection_set", []):
            sec = Section(title=sec_data.get("section_title", ""))
            for para in sec_data.get("articleparagraph_set", []):
                para_text = para.get("text", "")
                if para_text:
                    sec.paragraphs.append(para_text)
                # Extract references from paragraph
                for ref_data in para.get("references", []):
                    ref = Reference(
                        title=ref_data.get("title", ""),
                        journal=ref_data.get("journal_name", ""),
                        year=str(ref_data.get("year", "")),
                        authors=ref_data.get("authors", ""),
                        url=ref_data.get("url", ""),
                        doi=ref_data.get("doi", ""),
                    )
                    sec.references.append(ref)
                    all_refs.append(ref)
            if sec.paragraphs:
                sections.append(sec)

        follow_ups = structured.get("follow_up_questions", []) or []

        return cls(
            id=article_id,
            status=status,
            title=title,
            question=question,
            text=raw_text,
            clean_text=clean,
            sections=sections,
            follow_up_questions=follow_ups,
            references=all_refs,
            raw_response=data,
        )

    @staticmethod
    def _clean_text(raw: str) -> str:
        """Remove REACTCOMPONENT markers, HTML tags, and thinking blocks."""
        if not raw:
            return ""
        # Remove REACTCOMPONENT thinking blocks
        text = re.sub(
            r'REACTCOMPONENT!:!Thinking!:!\{.*?\}\n*',
            '',
            raw,
            flags=re.DOTALL,
        )
        # Remove HTML bold/strong tags but keep content
        text = re.sub(r'</?strong>', '', text)
        text = re.sub(r'</?b>', '', text)
        text = re.sub(r'</?em>', '', text)
        text = re.sub(r'</?i>', '', text)
        # Remove other HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Clean up extra whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()
