# openevidence-py

**Unofficial** Python client for [OpenEvidence.com](https://www.openevidence.com) — the leading medical information platform powered by AI with citations from NEJM, JAMA, NCCN, Cochrane, and more.

Uses **Playwright** (headless browser) to handle FingerprintJS authentication automatically. Supports **multi-user SaaS** integration via credential vault.

> **Disclaimer**: This is an unofficial, community-driven project. Not affiliated with OpenEvidence Inc. Use responsibly.

## Installation

```bash
# Install the package
pip install git+https://github.com/fredmmascarenhas-creator/openevidence-py.git

# Install the browser (required, run once)
playwright install chromium
```

Or from source:

```bash
git clone https://github.com/fredmmascarenhas-creator/openevidence-py.git
cd openevidence-py
pip install -e .
playwright install chromium
```

## Setup (.env)

```bash
cp .env.example .env
# Edit .env with your credentials
```

```env
OPENEVIDENCE_EMAIL=your_email@example.com
OPENEVIDENCE_PASSWORD=your_password
OPENEVIDENCE_VAULT_KEY=your-secret-key-for-multi-user
```

## Quick Start

### Basic Usage

```python
from openevidence import OpenEvidenceClient

# With credentials from .env
with OpenEvidenceClient() as client:
    article = client.ask("What is the treatment for type 2 diabetes?")
    print(article.title)
    print(article.clean_text)

    for ref in article.references:
        print(f"  - {ref.title} ({ref.journal}, {ref.year})")
```

### Without Login (anonymous, may have rate limits)

```python
with OpenEvidenceClient() as client:
    article = client.ask("What is aspirin used for?")
    print(article.clean_text)
```

### Follow-up Questions

```python
with OpenEvidenceClient() as client:
    article = client.ask("What is metformin?")

    # Use the article ID for follow-ups
    followup = client.ask(
        "What are the side effects?",
        original_article=article.id,
    )
    print(followup.clean_text)
```

### Streaming (partial results)

```python
with OpenEvidenceClient() as client:
    for partial in client.ask_stream("What is aspirin used for?"):
        print(f"Status: {partial.status.value}")
        if partial.status.value == "success":
            print(partial.clean_text)
```

### CLI

```bash
openevidence ask "What is the treatment for hypertension?"
openevidence ask "Side effects of ACE inhibitors?" --json
openevidence ask "What is aspirin?" --stream
openevidence get <article-uuid>
```

## Multi-User SaaS Integration

For SaaS apps where each user has their own OpenEvidence account:

### Store User Credentials

```python
from openevidence import CredentialVault

vault = CredentialVault(encryption_key="your-secret-key")

# When a user connects their account in your SaaS
vault.store_user("user_123", "user@email.com", "their_password")
vault.store_user("user_456", "other@email.com", "other_password")
```

### Query on Behalf of a User

```python
# Each user gets isolated browser session + cookies
with vault.get_client("user_123") as client:
    article = client.ask("Treatment for hypertension?")
    print(article.clean_text)
```

### FastAPI Backend

```python
from fastapi import FastAPI
from openevidence import CredentialVault

app = FastAPI()
vault = CredentialVault(encryption_key="your-key")

@app.post("/search")
def search(user_id: str, question: str):
    with vault.get_client(user_id) as client:
        article = client.ask(question)
    return {
        "title": article.title,
        "answer": article.clean_text,
        "references": [
            {"title": r.title, "journal": r.journal}
            for r in article.references
        ],
    }
```

See `examples/saas_integration.py` for a complete FastAPI example with NotebookLM integration.

## OpenEvidence + NotebookLM Combo

Combine both unofficial APIs for a medical research pipeline:

```python
from openevidence import OpenEvidenceClient

# 1. Get evidence from OpenEvidence
with OpenEvidenceClient() as oe:
    article = oe.ask("Treatment options for COPD?")

# 2. Send to NotebookLM for organization
from notebooklm import NotebookLMClient

async with NotebookLMClient() as nb:
    notebook = await nb.notebooks.create(title=article.title)
    await nb.sources.add(
        notebook_id=notebook.id,
        content=article.clean_text,
        title=article.title,
    )
    # Now you have a NotebookLM notebook with cited medical evidence!
```

## API Reference

### `OpenEvidenceClient`

| Parameter       | Type    | Default | Description                          |
|----------------|---------|---------|--------------------------------------|
| `email`        | `str`   | env var | OpenEvidence email                   |
| `password`     | `str`   | env var | OpenEvidence password                |
| `headless`     | `bool`  | `True`  | Run browser headless                 |
| `timeout`      | `float` | `120`   | Request timeout in seconds           |
| `poll_interval`| `float` | `2.0`   | Seconds between polling              |

### `CredentialVault`

| Parameter        | Type   | Default              | Description                     |
|-----------------|--------|----------------------|---------------------------------|
| `vault_dir`     | `Path` | `~/.openevidence/vault` | Credential storage dir       |
| `encryption_key`| `str`  | env var              | Encryption key for credentials  |

### `Article` Model

| Field                | Type              | Description                                  |
|---------------------|-------------------|----------------------------------------------|
| `id`                | `str`             | Article UUID                                 |
| `status`            | `ArticleStatus`   | `running`, `success`, `failed`, `queued`     |
| `title`             | `str`             | Generated title                              |
| `question`          | `str`             | Original question                            |
| `clean_text`        | `str`             | Cleaned plain text response                  |
| `references`        | `list[Reference]` | Citations from medical literature            |
| `follow_up_questions`| `list[str]`      | Suggested follow-up questions                |

## How It Works

1. **Playwright** launches a headless Chromium browser
2. Visits openevidence.com — FingerprintJS runs and generates a `pizza` token
3. **POST `/api/article`** with the fingerprint token creates a query
4. **GET `/api/article/{uuid}`** polls until `status == "success"`
5. Response is parsed into structured `Article` with clean text and references
6. Browser session is persisted for reuse (faster subsequent calls)

## Production Notes

- For multi-user vault encryption, replace the built-in XOR encryption with a proper secret manager (AWS Secrets Manager, HashiCorp Vault, etc.)
- Each user's browser session is isolated (separate cookies/fingerprint)
- Sessions are persisted to disk, so subsequent calls skip the login flow
- Consider running Playwright in a Docker container for deployment

## License

MIT License. See [LICENSE](LICENSE) for details.
