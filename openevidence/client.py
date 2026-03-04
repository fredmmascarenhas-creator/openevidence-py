"""
OpenEvidence API Client

Unofficial Python client that interacts with OpenEvidence.com
using Playwright browser automation.

Supports Google OAuth login:
  1. First time: browser opens VISIBLE, you login manually via Google
  2. Session is saved in a persistent Chrome profile (keeps ALL cookies)
  3. All subsequent queries run headless and fast — session persists!

Usage:
    # First time — will open a visible browser for Google login
    client = OpenEvidenceClient()
    client.interactive_login()  # Opens browser, you login via Google

    # From now on — headless and fast!
    with OpenEvidenceClient() as client:
        article = client.ask("What is metformin?")
        print(article.clean_text)
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

# Path to store browser profile (persistent Chrome profile)
DEFAULT_STATE_DIR = Path.home() / ".openevidence"


class OpenEvidenceClient:
    """
    Client for interacting with the OpenEvidence API via browser.

    Uses a persistent Chrome profile to keep Google login alive across sessions.

    Setup:
        1. pip install openevidence-py
        2. playwright install chromium
        3. Run interactive_login() once to save your Google session

    Usage (after login saved):
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
        self._load_dotenv()
        self.email = email or os.environ.get("OPENEVIDENCE_EMAIL")
        self.password = password or os.environ.get("OPENEVIDENCE_PASSWORD")
        self.headless = headless
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.state_dir = Path(state_dir) if state_dir else DEFAULT_STATE_DIR
        # Persistent Chrome profile directory (keeps ALL cookies, localStorage, etc.)
        self._profile_dir = self.state_dir / "chrome_profile"

        self._playwright = None
        self._context = None  # persistent context IS the browser
        self._page = None

    @staticmethod
    def _load_dotenv():
        """Load .env file without requiring python-dotenv."""
        try:
            from dotenv import load_dotenv
            load_dotenv()
            return
        except ImportError:
            pass

        for env_path in [Path(".env"), Path(__file__).parent.parent / ".env"]:
            if env_path.exists():
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key and value:
                            os.environ.setdefault(key, value)
                break

    def __enter__(self) -> "OpenEvidenceClient":
        self._start_browser()
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def has_saved_session(self) -> bool:
        """Check if a persistent Chrome profile exists from a previous login."""
        return self._profile_dir.exists() and any(self._profile_dir.iterdir())

    def interactive_login(self, timeout: int = 120) -> None:
        """
        Open a VISIBLE browser for manual login (Google OAuth, etc.).

        The browser will open openevidence.com — click "Log In" and
        sign in with your Google account. Once logged in, the session
        is saved in a persistent Chrome profile automatically.

        This only needs to be done ONCE. After that, all queries
        can run headless because the Chrome profile retains everything.

        Args:
            timeout: Max seconds to wait for login (default: 120).
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise OpenEvidenceError(
                "Playwright is required. Install it with:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

        print("\n" + "=" * 60)
        print("  OPENEVIDENCE - LOGIN INTERATIVO")
        print("=" * 60)
        print("\nUm navegador vai abrir. Siga estes passos:")
        print("  1. Clique em 'Log In'")
        print("  2. Clique em 'Continue with Google'")
        print("  3. Escolha sua conta Google e faça login")
        print("  4. Quando voltar ao OpenEvidence logado,")
        print("     a sessão será salva automaticamente.")
        print(f"\nVocê tem {timeout} segundos para completar o login.")
        print("=" * 60 + "\n")

        # Ensure profile directory exists
        self._profile_dir.mkdir(parents=True, exist_ok=True)

        pw = sync_playwright().start()
        try:
            # Use persistent context = real Chrome profile that saves EVERYTHING
            context = pw.chromium.launch_persistent_context(
                user_data_dir=str(self._profile_dir),
                headless=False,  # ALWAYS visible for interactive login
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
            )

            page = context.new_page()

            # Hide automation indicators
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
            """)

            # Navigate to OpenEvidence
            page.goto(self.base_url, wait_until="domcontentloaded", timeout=60000)

            # Wait for user to complete login
            print("Aguardando login... (faça login no navegador)")

            start_time = time.time()
            logged_in = False

            while time.time() - start_time < timeout:
                time.sleep(2)

                try:
                    # Check if "Log In" button is gone = logged in
                    login_btn = page.query_selector('text="Log In"')
                    if login_btn is None:
                        url = page.url
                        if "openevidence.com" in url and "auth" not in url.lower():
                            logged_in = True
                            break
                except Exception:
                    pass

            if logged_in:
                # Wait for cookies to settle
                page.wait_for_timeout(3000)

                print("\n✅ Login salvo com sucesso!")
                print(f"   Perfil Chrome salvo em: {self._profile_dir}")
                print("   Agora você pode usar o client em modo headless.")
                print("   Todas as buscas serão rápidas!\n")
            else:
                print("\n❌ Timeout! Login não foi detectado.")
                print("   Tente novamente com: client.interactive_login()")

            page.close()
            # Closing the persistent context saves everything to disk
            context.close()

        finally:
            pw.stop()

    def _start_browser(self):
        """Launch the browser with persistent profile."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise OpenEvidenceError(
                "Playwright is required. Install it with:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

        self._profile_dir.mkdir(parents=True, exist_ok=True)

        self._playwright = sync_playwright().start()

        # Use persistent context — this IS the browser + context combined
        # It loads the Chrome profile with all saved cookies, localStorage, etc.
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self._profile_dir),
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )

        self._page = self._context.new_page()

        # Hide automation indicators
        self._page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        """)

        # Navigate to OpenEvidence
        self._page.goto(self.base_url, wait_until="domcontentloaded", timeout=60000)
        # Wait for FingerprintJS to initialize
        self._page.wait_for_timeout(5000)

        # Check if session is still valid
        if not self._is_logged_in():
            if self.email and self.password:
                self._auth0_login()
            else:
                print(
                    "\n⚠️  Não logado! Execute primeiro:\n"
                    "    from openevidence import OpenEvidenceClient\n"
                    "    client = OpenEvidenceClient()\n"
                    "    client.interactive_login()\n"
                )

    def _is_logged_in(self) -> bool:
        """Check if currently logged in to OpenEvidence."""
        try:
            login_btn = self._page.query_selector('text="Log In"')
            return login_btn is None
        except Exception:
            return False

    def _auth0_login(self):
        """Login via Auth0 email/password (non-Google flow)."""
        page = self._page

        login_btn = page.query_selector('text="Log In"')
        if not login_btn:
            return

        login_btn.click()
        page.wait_for_timeout(3000)

        email_input = page.wait_for_selector('#username', timeout=15000)
        if email_input:
            email_input.click()
            email_input.fill(self.email)
            page.wait_for_timeout(500)

        page.keyboard.press("Enter")
        page.wait_for_timeout(2000)

        password_input = page.query_selector('input[type="password"]')
        if not password_input:
            password_input = page.wait_for_selector('input[type="password"]', timeout=10000)

        if password_input:
            password_input.click()
            password_input.fill(self.password)
            page.wait_for_timeout(500)
            page.keyboard.press("Enter")

        page.wait_for_timeout(5000)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass

    def close(self) -> None:
        """Close the browser and clean up resources."""
        if self._page:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None
        if self._context:
            try:
                # Closing persistent context saves everything to disk
                self._context.close()
            except Exception:
                pass
            self._context = None
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
            Article with text, references, etc.

        Raises:
            OpenEvidenceError: If the request fails or times out.
        """
        if not self._page:
            raise OpenEvidenceError("Client not initialized. Use 'with' statement.")

        page = self._page

        # Use the page's JavaScript context to make the API call
        # Browser handles FingerprintJS token and cookies automatically
        create_script = """
        async ({question, article_type, original_article}) => {
            // Get FingerprintJS requestId from sessionStorage
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

            if (!pizza) {
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
                return {
                    error: true,
                    status: response.status,
                    body: text,
                    page_url: window.location.href,
                    has_pizza: !!pizza,
                };
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
                f"\n  Page URL: {result.get('page_url')}"
                f"\n  Has pizza token: {result.get('has_pizza')}"
            )

        article_id = result.get("id")
        if not article_id:
            raise OpenEvidenceError(f"No article ID in response: {result}")

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
        """
        if not self._page:
            raise OpenEvidenceError("Client not initialized. Use 'with' statement.")

        page = self._page

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

        attempts = 0
        while attempts < MAX_POLL_ATTEMPTS:
            time.sleep(self.poll_interval)
            attempts += 1

            data = self._page.evaluate(
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
