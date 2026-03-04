"""
OpenEvidence Unofficial Python API Client

An unofficial Python client for interacting with OpenEvidence.com,
the leading medical information platform.

Uses Playwright headless browser to handle FingerprintJS authentication.
Supports multi-user SaaS integration via credential vault.
"""

from openevidence.client import OpenEvidenceClient, OpenEvidenceError
from openevidence.models import Article, ArticleStatus, Reference
from openevidence.pool import SessionPool
from openevidence.vault import CredentialVault, OpenEvidenceVaultError

__version__ = "0.3.0"
__all__ = [
    "OpenEvidenceClient",
    "OpenEvidenceError",
    "SessionPool",
    "CredentialVault",
    "OpenEvidenceVaultError",
    "Article",
    "ArticleStatus",
    "Reference",
]
