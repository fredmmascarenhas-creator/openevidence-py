"""
Credential Vault for multi-user SaaS integration.

Stores encrypted OpenEvidence credentials per user, with isolated
browser sessions for each user.

Usage:
    vault = CredentialVault()
    vault.store_user("user_123", "user@email.com", "password123")

    with vault.get_client("user_123") as client:
        article = client.ask("What is aspirin?")
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Optional

from openevidence.client import OpenEvidenceClient


# Default storage paths
DEFAULT_VAULT_DIR = Path.home() / ".openevidence" / "vault"


class CredentialVault:
    """
    Manages OpenEvidence credentials for multiple SaaS users.

    Each user gets:
    - Encrypted credentials stored on disk
    - Isolated browser session (separate cookies/fingerprint)
    - Session persistence for faster subsequent requests

    For production, replace the simple encryption with a proper
    secret manager (AWS Secrets Manager, HashiCorp Vault, etc.).
    """

    def __init__(
        self,
        vault_dir: Optional[Path] = None,
        encryption_key: Optional[str] = None,
    ):
        """
        Args:
            vault_dir: Directory to store credential files.
            encryption_key: Key for encrypting credentials.
                Falls back to OPENEVIDENCE_VAULT_KEY env var.
                If not set, credentials are stored base64-encoded (NOT secure for production).
        """
        self.vault_dir = Path(vault_dir) if vault_dir else DEFAULT_VAULT_DIR
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self._key = encryption_key or os.environ.get("OPENEVIDENCE_VAULT_KEY")

    def store_user(self, user_id: str, email: str, password: str) -> None:
        """
        Store credentials for a user.

        Args:
            user_id: Unique identifier for the user in your SaaS.
            email: OpenEvidence account email.
            password: OpenEvidence account password.
        """
        data = json.dumps({"email": email, "password": password})
        encrypted = self._encrypt(data)

        user_dir = self._user_dir(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)

        cred_file = user_dir / "credentials.enc"
        cred_file.write_text(encrypted)

    def get_user_credentials(self, user_id: str) -> tuple[str, str]:
        """
        Retrieve credentials for a user.

        Returns:
            Tuple of (email, password).

        Raises:
            OpenEvidenceVaultError: If user not found.
        """
        cred_file = self._user_dir(user_id) / "credentials.enc"
        if not cred_file.exists():
            raise OpenEvidenceVaultError(f"No credentials found for user: {user_id}")

        encrypted = cred_file.read_text()
        decrypted = self._decrypt(encrypted)
        data = json.loads(decrypted)
        return data["email"], data["password"]

    def remove_user(self, user_id: str) -> None:
        """Remove all data for a user (credentials + session)."""
        import shutil
        user_dir = self._user_dir(user_id)
        if user_dir.exists():
            shutil.rmtree(user_dir)

    def list_users(self) -> list[str]:
        """List all stored user IDs."""
        if not self.vault_dir.exists():
            return []
        return [
            d.name for d in self.vault_dir.iterdir()
            if d.is_dir() and (d / "credentials.enc").exists()
        ]

    def has_user(self, user_id: str) -> bool:
        """Check if credentials exist for a user."""
        return (self._user_dir(user_id) / "credentials.enc").exists()

    def get_client(self, user_id: str, headless: bool = True) -> OpenEvidenceClient:
        """
        Get an OpenEvidenceClient configured for a specific user.

        Each user gets an isolated browser session with their own
        cookies, fingerprint, and authentication state.

        Args:
            user_id: The user to get a client for.
            headless: Run browser headless (default: True).

        Returns:
            OpenEvidenceClient configured for the user.
            Use as context manager: `with vault.get_client(user_id) as client:`
        """
        email, password = self.get_user_credentials(user_id)
        user_state_dir = self._user_dir(user_id)

        return OpenEvidenceClient(
            email=email,
            password=password,
            headless=headless,
            state_dir=user_state_dir,
        )

    def _user_dir(self, user_id: str) -> Path:
        """Get the storage directory for a user."""
        # Sanitize user_id for filesystem safety
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in user_id)
        return self.vault_dir / safe_id

    def _encrypt(self, plaintext: str) -> str:
        """
        Encrypt data. Uses simple XOR + base64 with the vault key.

        ⚠️  For production, replace with:
        - AWS Secrets Manager
        - HashiCorp Vault
        - Azure Key Vault
        - Google Secret Manager
        - Or at minimum: cryptography.fernet.Fernet
        """
        if self._key:
            key_bytes = hashlib.sha256(self._key.encode()).digest()
            data_bytes = plaintext.encode()
            encrypted = bytes(
                b ^ key_bytes[i % len(key_bytes)]
                for i, b in enumerate(data_bytes)
            )
            return base64.b64encode(encrypted).decode()
        else:
            # No key — just base64 encode (NOT secure, for dev only)
            return base64.b64encode(plaintext.encode()).decode()

    def _decrypt(self, encrypted: str) -> str:
        """Decrypt data."""
        if self._key:
            key_bytes = hashlib.sha256(self._key.encode()).digest()
            data_bytes = base64.b64decode(encrypted)
            decrypted = bytes(
                b ^ key_bytes[i % len(key_bytes)]
                for i, b in enumerate(data_bytes)
            )
            return decrypted.decode()
        else:
            return base64.b64decode(encrypted).decode()


class OpenEvidenceVaultError(Exception):
    """Exception raised by the credential vault."""
    pass
