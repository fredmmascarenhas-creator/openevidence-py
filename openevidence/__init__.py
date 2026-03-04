"""
OpenEvidence Unofficial Python API Client

An unofficial Python client for interacting with OpenEvidence.com,
the leading medical information platform.
"""

from openevidence.client import OpenEvidenceClient, OpenEvidenceError
from openevidence.models import Article, ArticleStatus, Reference

__version__ = "0.1.0"
__all__ = [
    "OpenEvidenceClient",
    "OpenEvidenceError",
    "Article",
    "ArticleStatus",
    "Reference",
]
