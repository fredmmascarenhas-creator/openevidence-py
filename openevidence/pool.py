"""
Session Pool for fast, persistent OpenEvidence connections.

Keeps browser sessions alive between requests so login happens only ONCE.
Subsequent queries reuse the existing browser — no startup overhead.

Usage (single user):
    pool = SessionPool()
    pool.login("user@email.com", "password")

    # All subsequent calls are fast (~5-10s instead of ~30s)
    article = pool.ask("What is metformin?")
    article2 = pool.ask("Side effects of ACE inhibitors?")

    pool.close()

Usage (multi-user SaaS):
    pool = SessionPool()
    pool.login("user_123", email="a@email.com", password="pass1")
    pool.login("user_456", email="b@email.com", password="pass2")

    # Each user's session stays alive
    article = pool.ask("Treatment for COPD?", user_id="user_123")
    article2 = pool.ask("Aspirin dosage?", user_id="user_456")

    pool.close()
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Optional

from openevidence.client import (
    BASE_URL,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_TIMEOUT,
    MAX_POLL_ATTEMPTS,
    OpenEvidenceClient,
    OpenEvidenceError,
)
from openevidence.models import Article, ArticleStatus


# Default user ID for single-user mode
_DEFAULT_USER = "__default__"

# Default state directory
DEFAULT_POOL_STATE_DIR = Path.home() / ".openevidence" / "pool"


class SessionPool:
    """
    Persistent session pool that keeps browsers alive between requests.

    Instead of opening/closing a browser for every query, the pool
    maintains live browser sessions. Login happens once per user,
    and all subsequent queries reuse that session instantly.

    Thread-safe: each user gets their own browser + lock.

    Performance comparison:
        Without pool (open/close each time):
            First query:  ~30s (launch browser + login + query)
            Each query:   ~25s (launch browser + restore session + query)

        With pool (browser stays alive):
            First query:  ~30s (launch browser + login + query)
            Each query:   ~5-10s (just the query!)
    """

    def __init__(
        self,
        headless: bool = True,
        base_url: str = BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        state_dir: Optional[Path] = None,
    ):
        self.headless = headless
        self.base_url = base_url
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.state_dir = Path(state_dir) if state_dir else DEFAULT_POOL_STATE_DIR

        # Active sessions: user_id -> OpenEvidenceClient (browser alive)
        self._sessions: dict[str, OpenEvidenceClient] = {}
        # Per-user locks for thread safety
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def _get_lock(self, user_id: str) -> threading.Lock:
        """Get or create a lock for a user."""
        with self._global_lock:
            if user_id not in self._locks:
                self._locks[user_id] = threading.Lock()
            return self._locks[user_id]

    def login(
        self,
        user_id: str = _DEFAULT_USER,
        *,
        email: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        """
        Login a user and keep their browser session alive.

        If the user has a saved session (from interactive_login), it will
        be restored automatically — no visible browser needed.

        For single-user mode, just call:
            pool.login(email="you@email.com", password="pass")

        For Google OAuth users (after interactive_login was done once):
            pool.login()  # uses saved session

        For multi-user SaaS:
            pool.login("user_123", email="a@email.com", password="pass1")

        Args:
            user_id: Unique user identifier (default: single-user mode).
            email: OpenEvidence email. Falls back to OPENEVIDENCE_EMAIL env var.
            password: OpenEvidence password. Falls back to OPENEVIDENCE_PASSWORD env var.
        """
        lock = self._get_lock(user_id)
        with lock:
            # Close existing session if any
            if user_id in self._sessions:
                try:
                    self._sessions[user_id].close()
                except Exception:
                    pass

            user_state_dir = self.state_dir / user_id
            client = OpenEvidenceClient(
                email=email,
                password=password,
                headless=self.headless,
                base_url=self.base_url,
                timeout=self.timeout,
                poll_interval=self.poll_interval,
                state_dir=user_state_dir,
            )

            # Start the browser and login (this is the slow part — only once!)
            client._start_browser()
            self._sessions[user_id] = client

    def interactive_login(
        self,
        user_id: str = _DEFAULT_USER,
        timeout: int = 120,
    ) -> None:
        """
        Open a VISIBLE browser for manual Google login.

        Call this ONCE per user. After login, the session is saved
        and all subsequent pool.login() calls will restore it in headless mode.

        Args:
            user_id: User to login (default: single-user mode).
            timeout: Max seconds to wait for login.
        """
        user_state_dir = self.state_dir / user_id
        client = OpenEvidenceClient(
            headless=False,  # Must be visible for Google login
            base_url=self.base_url,
            state_dir=user_state_dir,
        )
        client.interactive_login(timeout=timeout)

    def is_logged_in(self, user_id: str = _DEFAULT_USER) -> bool:
        """Check if a user has an active session."""
        return user_id in self._sessions and self._sessions[user_id]._page is not None

    def ask(
        self,
        question: str,
        *,
        user_id: str = _DEFAULT_USER,
        article_type: str = "Ask OpenEvidence Light with citations",
        original_article: Optional[str] = None,
    ) -> Article:
        """
        Ask a question using an existing session. Fast! (~5-10s)

        Args:
            question: Medical question to ask.
            user_id: Which user's session to use.
            article_type: Type of article to generate.
            original_article: UUID for follow-up questions.

        Returns:
            Article with text, references, etc.
        """
        lock = self._get_lock(user_id)
        with lock:
            client = self._get_session(user_id)
            return client.ask(
                question,
                article_type=article_type,
                original_article=original_article,
            )

    def ask_many(
        self,
        questions: list[str],
        *,
        user_id: str = _DEFAULT_USER,
        article_type: str = "Ask OpenEvidence Light with citations",
    ) -> list[Article]:
        """
        Ask multiple questions sequentially using the same session.

        Args:
            questions: List of medical questions.
            user_id: Which user's session to use.

        Returns:
            List of Article responses.
        """
        results = []
        for q in questions:
            article = self.ask(q, user_id=user_id, article_type=article_type)
            results.append(article)
        return results

    def logout(self, user_id: str = _DEFAULT_USER) -> None:
        """Close a specific user's session."""
        lock = self._get_lock(user_id)
        with lock:
            if user_id in self._sessions:
                try:
                    self._sessions[user_id].close()
                except Exception:
                    pass
                del self._sessions[user_id]

    def close(self) -> None:
        """Close ALL sessions and free resources."""
        with self._global_lock:
            for user_id in list(self._sessions.keys()):
                try:
                    self._sessions[user_id].close()
                except Exception:
                    pass
            self._sessions.clear()
            self._locks.clear()

    def active_users(self) -> list[str]:
        """List all users with active sessions."""
        return [
            uid for uid, client in self._sessions.items()
            if client._page is not None
        ]

    def _get_session(self, user_id: str) -> OpenEvidenceClient:
        """Get active session or raise error."""
        if user_id not in self._sessions:
            raise OpenEvidenceError(
                f"No active session for user '{user_id}'. "
                f"Call pool.login('{user_id}', email=..., password=...) first."
            )

        client = self._sessions[user_id]
        if client._page is None:
            raise OpenEvidenceError(
                f"Session for '{user_id}' was closed. Call pool.login() again."
            )

        return client

    def __enter__(self) -> "SessionPool":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def __del__(self):
        """Cleanup on garbage collection."""
        try:
            self.close()
        except Exception:
            pass
