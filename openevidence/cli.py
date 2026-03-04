"""
Command-line interface for OpenEvidence.

Usage:
    openevidence ask "What is the treatment for hypertension?"
    openevidence ask "What is metformin?" --json
    openevidence get <article-uuid>
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap

from openevidence.client import OpenEvidenceClient, OpenEvidenceError
from openevidence.models import ArticleStatus


def _print_article_text(article, *, use_color: bool = True):
    """Pretty-print an article to stdout."""
    if use_color and sys.stdout.isatty():
        BOLD = "\033[1m"
        DIM = "\033[2m"
        ORANGE = "\033[38;5;208m"
        RESET = "\033[0m"
        GREEN = "\033[32m"
    else:
        BOLD = DIM = ORANGE = RESET = GREEN = ""

    print(f"\n{ORANGE}{'─' * 60}{RESET}")
    print(f"{BOLD}{article.title or article.question}{RESET}")
    print(f"{ORANGE}{'─' * 60}{RESET}\n")

    if article.clean_text:
        for paragraph in article.clean_text.split("\n\n"):
            wrapped = textwrap.fill(paragraph.strip(), width=80)
            if wrapped:
                print(wrapped)
                print()

    if article.references:
        print(f"\n{BOLD}References:{RESET}")
        seen = set()
        for i, ref in enumerate(article.references, 1):
            key = ref.title
            if key in seen:
                continue
            seen.add(key)
            print(f"  {DIM}{i}. {ref.title}{RESET}")
            if ref.journal:
                print(f"     {DIM}{ref.journal} ({ref.year}){RESET}")

    if article.follow_up_questions:
        print(f"\n{GREEN}Suggested follow-up questions:{RESET}")
        for q in article.follow_up_questions:
            print(f"  -> {q}")

    print()


def _article_to_dict(article):
    """Convert Article to a JSON-serializable dict."""
    return {
        "id": article.id,
        "title": article.title,
        "status": article.status.value,
        "question": article.question,
        "text": article.clean_text,
        "references": [
            {"title": r.title, "journal": r.journal, "year": r.year, "url": r.url}
            for r in article.references
        ],
        "follow_up_questions": article.follow_up_questions,
    }


def main():
    parser = argparse.ArgumentParser(
        prog="openevidence",
        description="Unofficial CLI for OpenEvidence - The leading medical information platform",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # ask command
    ask_parser = subparsers.add_parser("ask", help="Ask a medical question")
    ask_parser.add_argument("question", help="The medical question to ask")
    ask_parser.add_argument("--json", action="store_true", help="Output as JSON")
    ask_parser.add_argument("--stream", action="store_true", help="Stream the response")
    ask_parser.add_argument(
        "--follow-up", metavar="UUID",
        help="UUID of a previous article for follow-up questions"
    )

    # get command
    get_parser = subparsers.add_parser("get", help="Retrieve an existing article by UUID")
    get_parser.add_argument("article_id", help="The article UUID")
    get_parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        with OpenEvidenceClient() as client:
            if args.command == "ask":
                if args.stream:
                    last_text_len = 0
                    final_article = None
                    for article in client.ask_stream(
                        args.question,
                        original_article=getattr(args, 'follow_up', None),
                    ):
                        if not args.json:
                            if article.text and len(article.text) > last_text_len:
                                new_text = article.text[last_text_len:]
                                sys.stdout.write(new_text)
                                sys.stdout.flush()
                                last_text_len = len(article.text)
                        if article.status == ArticleStatus.SUCCESS:
                            final_article = article
                    if args.json and final_article:
                        print(json.dumps(_article_to_dict(final_article), indent=2, ensure_ascii=False))
                    elif final_article and not args.json:
                        print()
                        _print_article_text(final_article)
                else:
                    print("Querying OpenEvidence...", file=sys.stderr)
                    article = client.ask(
                        args.question,
                        original_article=getattr(args, 'follow_up', None),
                    )
                    if args.json:
                        print(json.dumps(_article_to_dict(article), indent=2, ensure_ascii=False))
                    else:
                        _print_article_text(article)

            elif args.command == "get":
                article = client.get_article(args.article_id)
                if args.json:
                    print(json.dumps(_article_to_dict(article), indent=2, ensure_ascii=False))
                else:
                    _print_article_text(article)

    except OpenEvidenceError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
