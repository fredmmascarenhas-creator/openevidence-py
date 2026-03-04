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
        seen_ref_titles = set()  # Deduplicate references

        for sec_data in structured.get("articlesection_set", []):
            sec = Section(title=sec_data.get("section_title", ""))
            for para in sec_data.get("articleparagraph_set", []):
                para_text = para.get("text", "")
                if para_text:
                    sec.paragraphs.append(para_text)
                # Extract references from paragraph
                for ref_data in para.get("references", []):
                    ref = cls._parse_reference(ref_data)
                    if ref and ref.title and ref.title not in seen_ref_titles:
                        sec.references.append(ref)
                        all_refs.append(ref)
                        seen_ref_titles.add(ref.title)
            if sec.paragraphs:
                sections.append(sec)

        # Also check external_search_results for references
        for result in structured.get("external_search_results", []) or []:
            ref = cls._parse_reference(result)
            if ref and ref.title and ref.title not in seen_ref_titles:
                all_refs.append(ref)
                seen_ref_titles.add(ref.title)

        # Also check metadata for references
        metadata = structured.get("metadata", {}) or {}
        for ref_data in metadata.get("references", []) or []:
            ref = cls._parse_reference(ref_data)
            if ref and ref.title and ref.title not in seen_ref_titles:
                all_refs.append(ref)
                seen_ref_titles.add(ref.title)

        # Extract inline references from [[[$$$...$$$]]] markers in text
        if not all_refs:
            inline_refs = cls._extract_inline_references(raw_text)
            for ref in inline_refs:
                if ref.title not in seen_ref_titles:
                    all_refs.append(ref)
                    seen_ref_titles.add(ref.title)

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

    @classmethod
    def _parse_reference(cls, ref_data: dict) -> Optional[Reference]:
        """Parse a Reference from various API response formats."""
        if not ref_data:
            return None
        title = (
            ref_data.get("title", "") or
            ref_data.get("name", "") or
            ref_data.get("headline", "") or
            ""
        )
        if not title:
            return None
        return Reference(
            title=title,
            journal=(
                ref_data.get("journal_name", "") or
                ref_data.get("journal", "") or
                ref_data.get("source", "") or
                ref_data.get("publisher", "") or
                ""
            ),
            year=str(ref_data.get("year", "") or ref_data.get("date", "") or ""),
            authors=ref_data.get("authors", "") or ref_data.get("author", "") or "",
            url=ref_data.get("url", "") or ref_data.get("link", "") or "",
            doi=ref_data.get("doi", "") or "",
        )

    @staticmethod
    def _clean_text(raw: str) -> str:
        """Remove REACTCOMPONENT markers, HTML tags, thinking/search blocks, inline refs."""
        if not raw:
            return ""
        # Remove REACTCOMPONENT blocks (various formats)
        text = re.sub(
            r'REACTCOMPONENT!:!\w+!:!\{.*?\}\n*',
            '',
            raw,
            flags=re.DOTALL,
        )
        # Remove JSON array/object blocks (thinking/search/reasoning)
        # Matches patterns like [{"kind":"search",...},{"kind":"reasoning",...}]
        text = re.sub(
            r'\[(\s*\{[^]]*"kind"\s*:\s*"[^"]*"[^]]*\})\s*\]',
            '',
            text,
            flags=re.DOTALL,
        )
        # Remove standalone JSON thinking objects
        text = re.sub(
            r'\{[^}]*"kind"\s*:\s*"(search|reasoning|thinking)"[^}]*\}',
            '',
            text,
        )
        # Remove inline reference markers [[[$$$...$$$]]] but keep a [ref] marker
        text = re.sub(
            r'\[\[\[\$\$\$.*?\$\$\$\]\]\]',
            '',
            text,
            flags=re.DOTALL,
        )
        # Also handle [[[$$$...  without closing (truncated refs)
        text = re.sub(
            r'\[\[\[\$\$\$[^\]]*$',
            '',
            text,
            flags=re.MULTILINE,
        )
        # Remove HTML bold/strong tags but keep content
        text = re.sub(r'</?strong>', '', text)
        text = re.sub(r'</?b>', '', text)
        text = re.sub(r'</?em>', '', text)
        text = re.sub(r'</?i>', '', text)
        # Remove other HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Clean up leading garbage (commas, brackets, whitespace)
        text = re.sub(r'^[\s,\]\[}{]+', '', text)
        # Clean up extra whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'  +', ' ', text)
        return text.strip()

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove HTML tags from text, extract href URLs."""
        if not text:
            return ""
        return re.sub(r'<[^>]+>', '', text).strip()

    @staticmethod
    def _extract_url(text: str) -> str:
        """Extract URL from HTML anchor tag."""
        match = re.search(r'href="([^"]+)"', text)
        return match.group(1) if match else ""

    @classmethod
    def _extract_inline_references(cls, raw: str) -> list["Reference"]:
        """Extract references from [[[$$$...$$$]]] markers in the text."""
        refs = []
        seen = set()
        # Match [[[$$$content$$$]]]
        pattern = r'\[\[\[\$\$\$(.*?)\$\$\$\]\]\]'
        for match in re.finditer(pattern, raw, re.DOTALL):
            ref_text = match.group(1).strip()
            if not ref_text or ref_text in seen:
                continue
            seen.add(ref_text)

            # Extract URL from any <a href="..."> tags
            url = cls._extract_url(ref_text)

            # Strip HTML tags to get clean text
            clean_ref = cls._strip_html(ref_text)
            if not clean_ref:
                continue

            ref = Reference(title=clean_ref, url=url)

            # Try to parse "Author et al. Title. Journal. Year;..."
            parts = clean_ref.split('. ')
            if len(parts) >= 2:
                ref.authors = parts[0]
                ref.title = '. '.join(parts[1:3]) if len(parts) >= 3 else parts[1]
                if len(parts) >= 4:
                    ref.journal = parts[-2] if len(parts) > 4 else parts[3] if len(parts) > 3 else ""
                year_match = re.search(r'\b(19|20)\d{2}\b', clean_ref)
                if year_match:
                    ref.year = year_match.group(0)
            refs.append(ref)
        return refs
