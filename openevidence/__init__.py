"""
OpenEvidence Unofficial Python API Client

An unofficial Python client for interacting with OpenEvidence.com,
the leading medical information platform.

Uses Playwright headless browser to handle FingerprintJS authentication.
Supports multi-user SaaS integration via credential vault.
"""

from openevidence.client import OpenEvidenceClient, OpenEvidenceError
from openevidence.models import Article, ArticleStatus, Reference
from openevidence.vault import CredentialVault, OpenEvidenceVaultError

__version__ = "0.2.0"
__all__ = [
    "OpenEvidenceClient",
    "OpenEvidenceError",
    "CredentialVault",
    "OpenEvidenceVaultError",
    "Article",
    "ArticleStatus",
    "Reference",
]
