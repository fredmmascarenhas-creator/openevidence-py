"""
OpenEvidence API Client

Unofficial Python client that interacts with OpenEvidence.com
using Playwright headless browser automation.

This approach handles FingerprintJS and session management automatically,
just like a real browser would.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Iterator, Optional

from openevidence.models import Article, ArticleStatus


# Default configuration
BASE_URL = "https://www.openevidence.com"
DEFAULT_ARTICLE_TYPE = "Ask OpenEvidence Light with citations"
DEFAULT_POLL_INTERVAL = 2.0  # seconds
DEFAULT_TIMEOUT = 120  # seconds
MAX_POLL_ATTEMPTS = 60

# Path to store browser session (cookies, localStorage, etc.)
DEFAULT_STATE_DIR = Path.home() / ".openevidence"


class OpenEvidenceClient:
    """
    Client for interacting with the OpenEvidence API via headless browser.

    Uses Playwright to automate a real browser, which handles FingerprintJS
    anti-bot protection automatically.

    Setup:
        1. pip install openevidence-py
        2. playwright install chromium
        3. Set OPENEVIDENCE_EMAIL and OPENEVIDENCE_PASSWORD in .env (optional)

    Usage:
        with OpenEvidenceClient() as client:
            article = client.ask("What is the treatment for diabetes?")
            print(article.clean_text)
    """

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        headless: bool = True,
        base_url: str = BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        state_dir: Optional[Path] = None,
    ):
        """
        Args:
            email: OpenEvidence account email. Falls back to OPENEVIDENCE_EMAIL env var.
            password: OpenEvidence account password. Falls back to OPENEVIDENCE_PASSWORD env var.
            headless: Run browser in headless mode (default: True for backend use).
            base_url: OpenEvidence base URL.
            timeout: Request timeout in seconds.
            poll_interval: Seconds between polling attempts.
            state_dir: Directory to store browser session state.
        """
        self.email = email or os.environ.get("OPENEVIDENCE_EMAIL")
        self.password = password or os.environ.get("OPENEVIDENCE_PASSWORD")
        self.headless = headless
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.state_dir = Path(state_dir) if state_dir else DEFAULT_STATE_DIR
        self._state_file = self.state_dir / "browser_state.json"

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self) -> "OpenEvidenceClient":
        self._start_browser()
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def _start_browser(self):
        """Launch the browser and set up the page."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise OpenEvidenceError(
                "Playwright is required. Install it with:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)

        # Try to restore previous session state
        if self._state_file.exists():
            try:
                self._context = self._browser.new_context(
                    storage_state=str(self._state_file),
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36"
                    ),
                )
            except Exception:
                self._context = self._new_context()
        else:
            self._context = self._new_context()

        self._page = self._context.new_page()

        # Navigate to homepage and wait for FingerprintJS to initialize
        self._page.goto(self.base_url, wait_until="networkidle")
        self._page.wait_for_timeout(2000)

        # Login if credentials are provided and not already logged in
        if self.email and self.password:
            self._ensure_logged_in()

        # Save session state for reuse
        self._save_state()

    def _new_context(self):
        """Create a fresh browser context."""
        return self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )

    def _ensure_logged_in(self):
        """Login to OpenEvidence if not already logged in."""
        page = self._page

        # Check if already logged in by looking for the "Log In" button
        login_btn = page.query_selector('text="Log In"')
        if not login_btn:
            return  # Already logged in

        login_btn.click()
        page.wait_for_timeout(2000)

        # Fill in email
        email_input = page.wait_for_selector('input[type="email"], input[name="email"]', timeout=10000)
        if email_input:
            email_input.fill(self.email)

        # Look for "Continue" or "Next" button
        continue_btn = page.query_selector('button:has-text("Continue")') or \
                       page.query_selector('button:has-text("Next")')
        if continue_btn:
            continue_btn.click()
            page.wait_for_timeout(1000)

        # Fill in password
        password_input = page.wait_for_selector('input[type="password"]', timeout=10000)
        if password_input:
            password_input.fill(self.password)

        # Submit
        submit_btn = page.query_selector('button[type="submit"]') or \
                     page.query_selector('button:has-text("Log In")') or \
                     page.query_selector('button:has-text("Sign In")')
        if submit_btn:
            submit_btn.click()

        # Wait for login to complete
        page.wait_for_timeout(3000)
        page.wait_for_load_state("networkidle")

        self._save_state()

    def _save_state(self):
        """Save browser state (cookies, localStorage) for session persistence."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._context.storage_state(path=str(self._state_file))
        except Exception:
            pass  # Not critical if save fails

    def close(self) -> None:
        """Close the browser and clean up resources."""
        if self._context:
            self._save_state()
        if self._page:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def ask(
        self,
        question: str,
        *,
        article_type: str = DEFAULT_ARTICLE_TYPE,
        original_article: Optional[str] = None,
    ) -> Article:
        """
        Ask a medical question and wait for the complete response.

        Args:
            question: The medical question to ask.
            article_type: Type of article to generate.
            original_article: UUID of a previous article (for follow-up questions).

        Returns:
            Article: The complete article response with text, references, etc.

        Raises:
            OpenEvidenceError: If the request fails or times out.
        """
        if not self._page:
            raise OpenEvidenceError("Client not initialized. Use 'with' statement.")

        page = self._page

        # Use the page's JavaScript context to make the API call
        # This way, the FingerprintJS token and cookies are handled by the browser
        create_script = """
        async ({question, article_type, original_article}) => {
            // Wait for FingerprintJS to be ready and get the requestId
            let pizza = null;

            // Check sessionStorage for FingerprintJS data
            for (let i = 0; i < sessionStorage.length; i++) {
                const key = sessionStorage.key(i);
                if (key.includes('fpjs')) {
                    try {
                        const data = JSON.parse(sessionStorage.getItem(key));
                        if (data.body && data.body.requestId) {
                            pizza = data.body.requestId;
                        }
                    } catch(e) {}
                }
            }

            if (!pizza) {
                // FingerprintJS hasn't run yet, wait a bit
                await new Promise(r => setTimeout(r, 3000));
                for (let i = 0; i < sessionStorage.length; i++) {
                    const key = sessionStorage.key(i);
                    if (key.includes('fpjs')) {
                        try {
                            const data = JSON.parse(sessionStorage.getItem(key));
                            if (data.body && data.body.requestId) {
                                pizza = data.body.requestId;
                            }
                        } catch(e) {}
                    }
                }
            }

            const payload = {
                article_type: article_type,
                inputs: {
                    variant_configuration_file: "prod",
                    attachments: [],
                    question: question,
                    use_gatekeeper: true,
                },
                personalization_enabled: false,
                disable_caching: false,
            };
            if (original_article) {
                payload.original_article = original_article;
            }

            const headers = {
                "Content-Type": "application/json",
            };
            if (pizza) {
                headers["pizza"] = pizza;
            }

            const response = await fetch("/api/article", {
                method: "POST",
                headers: headers,
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                const text = await response.text();
                return { error: true, status: response.status, body: text };
            }

            return await response.json();
        }
        """

        result = page.evaluate(
            create_script,
            {"question": question, "article_type": article_type, "original_article": original_article},
        )

        if isinstance(result, dict) and result.get("error"):
            raise OpenEvidenceError(
                f"Failed to create article: {result.get('status')} - {result.get('body')}"
            )

        article_id = result.get("id")
        if not article_id:
            raise OpenEvidenceError(f"No article ID in response: {result}")

        # Poll for completion
        return self._poll_article(article_id)

    def ask_stream(
        self,
        question: str,
        *,
        article_type: str = DEFAULT_ARTICLE_TYPE,
        original_article: Optional[str] = None,
    ) -> Iterator[Article]:
        """
        Ask a question and yield partial Article results as they stream in.

        Yields:
            Article: Partial/complete article as it streams.
        """
        if not self._page:
            raise OpenEvidenceError("Client not initialized. Use 'with' statement.")

        page = self._page

        # Create article using browser JS context
        create_script = """
        async ({question, article_type, original_article}) => {
            let pizza = null;
            for (let i = 0; i < sessionStorage.length; i++) {
                const key = sessionStorage.key(i);
                if (key.includes('fpjs')) {
                    try {
                        const data = JSON.parse(sessionStorage.getItem(key));
                        if (data.body && data.body.requestId) {
                            pizza = data.body.requestId;
                        }
                    } catch(e) {}
                }
            }

            const payload = {
                article_type: article_type,
                inputs: {
                    variant_configuration_file: "prod",
                    attachments: [],
                    question: question,
                    use_gatekeeper: true,
                },
                personalization_enabled: false,
                disable_caching: false,
            };
            if (original_article) {
                payload.original_article = original_article;
            }

            const headers = { "Content-Type": "application/json" };
            if (pizza) headers["pizza"] = pizza;

            const response = await fetch("/api/article", {
                method: "POST",
                headers: headers,
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                return { error: true, status: response.status, body: await response.text() };
            }
            return await response.json();
        }
        """

        result = page.evaluate(
            create_script,
            {"question": question, "article_type": article_type, "original_article": original_article},
        )

        if isinstance(result, dict) and result.get("error"):
            raise OpenEvidenceError(f"Failed: {result.get('status')} - {result.get('body')}")

        article_id = result.get("id")
        if not article_id:
            raise OpenEvidenceError(f"No article ID in response: {result}")

        # Poll and yield partial results
        attempts = 0
        while attempts < MAX_POLL_ATTEMPTS:
            time.sleep(self.poll_interval)
            attempts += 1

            data = page.evaluate(
                """async (id) => {
                    const r = await fetch('/api/article/' + id);
                    if (!r.ok) return null;
                    return await r.json();
                }""",
                article_id,
            )

            if not data:
                continue

            article = Article.from_api_response(data)
            yield article

            if article.status == ArticleStatus.SUCCESS:
                return
            if article.status == ArticleStatus.FAILED:
                raise OpenEvidenceError(f"Article failed: {data.get('user_error_msg')}")

        raise OpenEvidenceError("Polling timed out")

    def get_article(self, article_id: str) -> Article:
        """Retrieve an existing article by UUID."""
        if not self._page:
            raise OpenEvidenceError("Client not initialized. Use 'with' statement.")

        data = self._page.evaluate(
            """async (id) => {
                const r = await fetch('/api/article/' + id);
                if (!r.ok) return { error: true, status: r.status };
                return await r.json();
            }""",
            article_id,
        )

        if isinstance(data, dict) and data.get("error"):
            raise OpenEvidenceError(f"Failed to get article: {data.get('status')}")

        return Article.from_api_response(data)

    def _poll_article(self, article_id: str) -> Article:
        """Poll until completion."""
        page = self._page
        attempts = 0

        while attempts < MAX_POLL_ATTEMPTS:
            time.sleep(self.poll_interval)
            attempts += 1

            try:
                data = page.evaluate(
                    """async (id) => {
                        const r = await fetch('/api/article/' + id);
                        if (!r.ok) return null;
                        return await r.json();
                    }""",
                    article_id,
                )

                if not data:
                    continue

                status = data.get("status", "")
                if status == "success":
                    return Article.from_api_response(data)
                elif status == "failed":
                    raise OpenEvidenceError(
                        f"Article failed: {data.get('user_error_msg', 'Unknown error')}"
                    )

            except Exception as e:
                if "failed" in str(e).lower():
                    raise
                continue

        raise OpenEvidenceError(f"Timed out after {attempts} polling attempts")


class OpenEvidenceError(Exception):
    """Exception raised by OpenEvidence client operations."""
    pass
