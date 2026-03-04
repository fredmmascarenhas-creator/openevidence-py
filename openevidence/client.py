"""
OpenEvidence API Client

Unofficial Python client that interacts with OpenEvidence.com
by reverse-engineering its web API endpoints.
"""

from __future__ import annotations

import random
import string
import time
from typing import Iterator, Optional

import requests

from openevidence.models import Article, ArticleStatus


# Default configuration
BASE_URL = "https://www.openevidence.com"
DEFAULT_ARTICLE_TYPE = "Ask OpenEvidence Light with citations"
DEFAULT_POLL_INTERVAL = 1.5  # seconds
DEFAULT_TIMEOUT = 120  # seconds
MAX_POLL_ATTEMPTS = 80

# User-Agent to mimic a real browser
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def _generate_pizza_token() -> str:
    """
    Generate the 'pizza' anti-bot header token.

    Format: <unix_timestamp_ms>.<6_random_chars>
    The timestamp is milliseconds since epoch, followed by a dot
    and 6 random alphanumeric characters.
    """
    ts = int(time.time() * 1000)
    chars = string.ascii_letters + string.digits
    rand = ''.join(random.choice(chars) for _ in range(6))
    return f"{ts}.{rand}"


class OpenEvidenceClient:
    """
    Client for interacting with the OpenEvidence API.

    Usage:
        client = OpenEvidenceClient()
        article = client.ask("What is the treatment for diabetes?")
        print(article.clean_text)

    Or as a context manager:
        with OpenEvidenceClient() as client:
            article = client.ask("What is the treatment for diabetes?")
            print(article.clean_text)
    """

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._user_agent = user_agent
        self._session: Optional[requests.Session] = None
        self._initialized = False

    def _get_session(self) -> requests.Session:
        """Get or create the HTTP session with cookies."""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": self._user_agent,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/",
            })

        if not self._initialized:
            # Visit homepage to establish session cookies
            self._session.get(f"{self.base_url}/", timeout=30)
            self._initialized = True

        return self._session

    def __enter__(self) -> "OpenEvidenceClient":
        self._get_session()
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        """Close the HTTP session."""
        if self._session:
            self._session.close()
            self._session = None
            self._initialized = False

    def ask(
        self,
        question: str,
        *,
        article_type: str = DEFAULT_ARTICLE_TYPE,
        original_article: Optional[str] = None,
        personalization: bool = False,
        disable_cache: bool = False,
        use_gatekeeper: bool = True,
        variant: str = "prod",
    ) -> Article:
        """
        Ask a medical question and wait for the complete response.

        Args:
            question: The medical question to ask.
            article_type: Type of article to generate.
            original_article: UUID of a previous article (for follow-up questions).
            personalization: Whether to enable personalization.
            disable_cache: Whether to disable result caching.
            use_gatekeeper: Whether to use the gatekeeper.
            variant: Configuration variant (default: "prod").

        Returns:
            Article: The complete article response with text, references, etc.

        Raises:
            OpenEvidenceError: If the request fails or times out.
        """
        session = self._get_session()

        # Build the request payload
        payload = {
            "article_type": article_type,
            "inputs": {
                "variant_configuration_file": variant,
                "attachments": [],
                "question": question,
                "use_gatekeeper": use_gatekeeper,
            },
            "personalization_enabled": personalization,
            "disable_caching": disable_cache,
        }
        if original_article:
            payload["original_article"] = original_article

        # Generate the pizza anti-bot token
        headers = {
            "Content-Type": "application/json",
            "pizza": _generate_pizza_token(),
        }

        # Create the article
        try:
            response = session.post(
                f"{self.base_url}/api/article",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.HTTPError as e:
            raise OpenEvidenceError(
                f"Failed to create article: {e.response.status_code} - {e.response.text}"
            ) from e
        except requests.RequestException as e:
            raise OpenEvidenceError(f"Request failed: {e}") from e

        data = response.json()
        article_id = data.get("id")

        if not article_id:
            raise OpenEvidenceError(f"No article ID in response: {data}")

        # Poll for completion
        return self._poll_article(article_id)

    def ask_stream(
        self,
        question: str,
        *,
        article_type: str = DEFAULT_ARTICLE_TYPE,
        original_article: Optional[str] = None,
        poll_interval: Optional[float] = None,
    ) -> Iterator[Article]:
        """
        Ask a question and yield partial Article results as they stream in.

        Each yielded Article represents the current state, with status
        transitioning from RUNNING to SUCCESS.

        Args:
            question: The medical question to ask.
            article_type: Type of article to generate.
            original_article: UUID for follow-up questions.
            poll_interval: Override the default poll interval.

        Yields:
            Article: Partial/complete article as it streams.
        """
        session = self._get_session()

        payload = {
            "article_type": article_type,
            "inputs": {
                "variant_configuration_file": "prod",
                "attachments": [],
                "question": question,
                "use_gatekeeper": True,
            },
            "personalization_enabled": False,
            "disable_caching": False,
        }
        if original_article:
            payload["original_article"] = original_article

        headers = {
            "Content-Type": "application/json",
            "pizza": _generate_pizza_token(),
        }

        response = session.post(
            f"{self.base_url}/api/article",
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        article_id = data.get("id")

        interval = poll_interval or self.poll_interval
        attempts = 0

        while attempts < MAX_POLL_ATTEMPTS:
            time.sleep(interval)
            attempts += 1

            resp = session.get(
                f"{self.base_url}/api/article/{article_id}",
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                continue

            article_data = resp.json()
            article = Article.from_api_response(article_data)
            yield article

            if article.status == ArticleStatus.SUCCESS:
                return
            if article.status == ArticleStatus.FAILED:
                raise OpenEvidenceError(
                    f"Article generation failed: {article_data.get('user_error_msg', 'Unknown error')}"
                )

        raise OpenEvidenceError("Polling timed out waiting for article completion")

    def get_article(self, article_id: str) -> Article:
        """
        Retrieve an existing article by its UUID.

        Args:
            article_id: The UUID of the article.

        Returns:
            Article: The article data.
        """
        session = self._get_session()
        response = session.get(
            f"{self.base_url}/api/article/{article_id}",
            timeout=self.timeout,
        )
        response.raise_for_status()
        return Article.from_api_response(response.json())

    def _poll_article(self, article_id: str) -> Article:
        """Poll the article endpoint until completion or timeout."""
        session = self._get_session()
        attempts = 0

        while attempts < MAX_POLL_ATTEMPTS:
            time.sleep(self.poll_interval)
            attempts += 1

            try:
                response = session.get(
                    f"{self.base_url}/api/article/{article_id}",
                    timeout=self.timeout,
                )
                if response.status_code != 200:
                    continue

                data = response.json()
                status = data.get("status", "")

                if status == "success":
                    return Article.from_api_response(data)
                elif status == "failed":
                    error_msg = data.get("user_error_msg", "Unknown error")
                    raise OpenEvidenceError(f"Article generation failed: {error_msg}")
                # status == "running" or "queued" -> continue polling

            except requests.RequestException:
                continue  # Retry on network errors

        raise OpenEvidenceError(
            f"Timed out after {attempts} polling attempts for article {article_id}"
        )


class OpenEvidenceError(Exception):
    """Exception raised by OpenEvidence client operations."""
    pass
