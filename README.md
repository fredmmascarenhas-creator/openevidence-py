# openevidence-py

**Unofficial** Python client for [OpenEvidence.com](https://www.openevidence.com) — the leading medical information platform powered by AI with citations from NEJM, JAMA, NCCN, Cochrane, and more.

Uses **Playwright** (headless browser) to handle FingerprintJS authentication automatically. Includes **SessionPool** for fast repeated queries and **multi-user SaaS** integration.

> **Disclaimer**: This is an unofficial, community-driven project. Not affiliated with OpenEvidence Inc. Use responsibly and in accordance with OpenEvidence's Terms of Service.

---

## Table of Contents

- [Installation](#installation)
- [Login Setup (IMPORTANT - Read First!)](#login-setup)
  - [Google Login (most common)](#option-1-google-login-most-common)
  - [Email/Password Login](#option-2-emailpassword-login)
- [Quick Start](#quick-start)
- [SessionPool — Login Once, Query Fast](#sessionpool--login-once-query-fast)
- [Multi-User SaaS](#multi-user-saas)
- [OpenEvidence + NotebookLM Combo](#openevidence--notebooklm-combo)
- [CLI](#cli)
- [API Reference](#api-reference)
- [How It Works](#how-it-works)
- [Troubleshooting](#troubleshooting)
- [Production Deployment](#production-deployment)

---

## Installation

### Step 1: Install the package

```bash
pip install git+https://github.com/fredmmascarenhas-creator/openevidence-py.git
```

Or from source:

```bash
git clone https://github.com/fredmmascarenhas-creator/openevidence-py.git
cd openevidence-py
pip install -e .
```

> **Mac users**: If `pip` doesn't work, try `pip3` instead.

### Step 2: Install the browser (run once)

```bash
playwright install chromium
```

That's it! Now you need to set up your login.

---

## Login Setup

OpenEvidence requires authentication. Choose your login method:

### Option 1: Google Login (most common)

If you sign in to OpenEvidence using your Google account, follow these steps:

**Step 1 — Run the interactive login (only once!):**

```python
from openevidence import OpenEvidenceClient

client = OpenEvidenceClient()
client.interactive_login()
```

This will:

1. Open a **visible** Chrome browser
2. Navigate to openevidence.com
3. You click "Log In" → "Continue with Google" → choose your Google account
4. Once logged in, the session is saved to `~/.openevidence/browser_state.json`
5. Browser closes automatically

**Step 2 — Use normally (all subsequent times):**

```python
from openevidence import OpenEvidenceClient

# Now it runs headless and fast — no visible browser!
with OpenEvidenceClient() as client:
    article = client.ask("What is the treatment for type 2 diabetes?")
    print(article.clean_text)
```

The saved session includes your cookies and auth tokens. It will be reused automatically every time.

> **Session expired?** Just run `client.interactive_login()` again.

### Option 2: Email/Password Login

If you have a direct OpenEvidence account (not Google):

**Step 1 — Create a `.env` file:**

```bash
cp .env.example .env
```

Edit `.env`:

```env
OPENEVIDENCE_EMAIL=your_email@example.com
OPENEVIDENCE_PASSWORD=your_password
```

**Step 2 — Use normally:**

```python
from openevidence import OpenEvidenceClient

# Reads credentials from .env automatically
with OpenEvidenceClient() as client:
    article = client.ask("What is metformin used for?")
    print(article.clean_text)
```

---

## Quick Start

### Ask a question

```python
from openevidence import OpenEvidenceClient

with OpenEvidenceClient() as client:
    article = client.ask("What is the treatment for type 2 diabetes?")

    print(article.title)
    print(article.clean_text)

    # Show references
    for ref in article.references:
        print(f"  - {ref.title} ({ref.journal}, {ref.year})")

    # Show follow-up suggestions
    for q in article.follow_up_questions:
        print(f"  → {q}")
```

### Follow-up questions

```python
with OpenEvidenceClient() as client:
    article = client.ask("What is metformin?")

    # Use the article ID to ask follow-ups in context
    followup = client.ask(
        "What are the side effects?",
        original_article=article.id,
    )
    print(followup.clean_text)
```

### Get partial results (streaming)

```python
with OpenEvidenceClient() as client:
    for partial in client.ask_stream("What is aspirin used for?"):
        print(f"Status: {partial.status.value}")
        if partial.status.value == "success":
            print(partial.clean_text)
```

---

## SessionPool — Login Once, Query Fast

The **SessionPool** is the key to fast performance. It keeps the browser alive between requests, so login happens **once** and all queries are 3-5x faster.

```
Without pool:  Open browser → Load page → Query → Close  (~25-30s each time)
With pool:     [Browser already open] → Query             (~5-10s each time!)
```

### Single user with Google login

```python
from openevidence import SessionPool

# First time only: run interactive login
# pool = SessionPool()
# pool.interactive_login()

# Normal usage (after login saved):
pool = SessionPool()
pool.login()  # Restores saved Google session — headless, fast!

# All queries are fast now!
article1 = pool.ask("What is metformin used for?")
article2 = pool.ask("Side effects of ACE inhibitors?")
article3 = pool.ask("Treatment options for COPD?")
article4 = pool.ask("Latest guidelines for hypertension?")

for a in [article1, article2, article3, article4]:
    print(f"Q: {a.question}")
    print(f"A: {a.clean_text[:150]}...\n")

pool.close()
```

### Single user with email/password

```python
from openevidence import SessionPool

pool = SessionPool()
pool.login(email="you@email.com", password="your_password")

article = pool.ask("Aspirin dosage for secondary prevention?")
print(article.clean_text)

pool.close()
```

### Batch processing

```python
from openevidence import SessionPool

pool = SessionPool()
pool.login()

questions = [
    "What is the first-line treatment for hypertension?",
    "When should statins be prescribed?",
    "Guidelines for anticoagulation in atrial fibrillation?",
]

articles = pool.ask_many(questions)

for article in articles:
    print(f"\n{'='*60}")
    print(f"Q: {article.question}")
    print(f"A: {article.clean_text[:300]}...")
    print(f"References: {len(article.references)}")

pool.close()
```

---

## Multi-User SaaS

For SaaS platforms where multiple users each have their own OpenEvidence account.

### Architecture

```
Your SaaS Backend
├── CredentialVault (stores encrypted credentials on disk)
├── SessionPool (keeps live browser sessions per user)
│   ├── doctor_alice → [browser session alive, logged in]
│   ├── doctor_bob   → [browser session alive, logged in]
│   └── doctor_carol → [browser session alive, logged in]
└── FastAPI endpoints
    ├── POST /users/{id}/connect    → Login user (slow, once)
    ├── POST /search                → Query (fast, reuses session)
    └── DELETE /users/{id}/disconnect → Cleanup
```

### Setup users

```python
from openevidence import SessionPool, CredentialVault

# Store credentials encrypted on disk
vault = CredentialVault(encryption_key="your-secret-key")
vault.store_user("doctor_alice", "alice@hospital.com", "pass1")
vault.store_user("doctor_bob", "bob@clinic.com", "pass2")

# Create pool and login each user (slow, once per user)
pool = SessionPool()

for user_id in vault.list_users():
    email, password = vault.get_user_credentials(user_id)
    pool.login(user_id, email=email, password=password)

# Now queries are fast for all users!
article_a = pool.ask("Treatment for COPD?", user_id="doctor_alice")
article_b = pool.ask("Aspirin in ACS?", user_id="doctor_bob")

pool.close()
```

### Google login for SaaS users

For users who login via Google, each user does the interactive login once:

```python
pool = SessionPool()

# User does this once (opens visible browser on their machine)
pool.interactive_login("doctor_alice")

# From now on, their session is saved and works headless
pool.login("doctor_alice")
article = pool.ask("Treatment for diabetes?", user_id="doctor_alice")
```

### FastAPI Backend (production-ready)

```python
# Run with: uvicorn examples.saas_integration:app --reload

from fastapi import FastAPI, HTTPException
from openevidence import SessionPool, CredentialVault

app = FastAPI(title="Medical Evidence API")
vault = CredentialVault(encryption_key="your-secret-key")
pool = SessionPool()  # Lives for entire server lifetime

@app.post("/users/{user_id}/connect")
def connect(user_id: str, email: str, password: str):
    """Connect user's OpenEvidence account. Slow (~30s), done once."""
    vault.store_user(user_id, email, password)
    pool.login(user_id, email=email, password=password)
    return {"status": "connected"}

@app.post("/search")
def search(user_id: str, question: str):
    """Search medical evidence. Fast (~5-10s)!"""
    if not pool.is_logged_in(user_id):
        if vault.has_user(user_id):
            email, pw = vault.get_user_credentials(user_id)
            pool.login(user_id, email=email, password=pw)
        else:
            raise HTTPException(404, "User not connected")

    article = pool.ask(question, user_id=user_id)
    return {
        "title": article.title,
        "answer": article.clean_text,
        "references": [
            {"title": r.title, "journal": r.journal, "year": r.year}
            for r in article.references
        ],
    }

@app.on_event("shutdown")
def shutdown():
    pool.close()
```

See `examples/saas_integration.py` for the complete example with all endpoints.

---

## OpenEvidence + NotebookLM Combo

Combine both unofficial APIs for a full medical research pipeline:

```python
from openevidence import SessionPool

# 1. Get evidence from OpenEvidence
pool = SessionPool()
pool.login()  # Uses saved Google session

article = pool.ask("What are the treatment options for COPD?")

# 2. Send to NotebookLM for organization/audio
from notebooklm import NotebookLMClient

async with NotebookLMClient() as nb:
    notebook = await nb.notebooks.create(title=article.title)
    await nb.sources.add(
        notebook_id=notebook.id,
        content=article.clean_text,
        title=article.title,
    )
    # Now you have a NotebookLM notebook with cited medical evidence!

pool.close()
```

Requires: `pip install notebooklm-py`

---

## CLI

```bash
# Ask a question
openevidence ask "What is the treatment for hypertension?"

# JSON output
openevidence ask "Side effects of ACE inhibitors?" --json

# Streaming (partial results)
openevidence ask "What is aspirin?" --stream

# Get an existing article by UUID
openevidence get <article-uuid>
```

---

## API Reference

### `OpenEvidenceClient`

| Method | Description |
|--------|-------------|
| `interactive_login(timeout=120)` | Open visible browser for Google login (once) |
| `has_saved_session()` | Check if login session exists on disk |
| `ask(question)` | Ask a question, wait for complete response |
| `ask_stream(question)` | Ask and yield partial results |
| `get_article(article_id)` | Retrieve existing article by UUID |
| `close()` | Close browser and save session |

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `email` | `str` | env var | OpenEvidence email (Auth0 login) |
| `password` | `str` | env var | OpenEvidence password (Auth0 login) |
| `headless` | `bool` | `True` | Run browser headless |
| `timeout` | `float` | `120` | Request timeout in seconds |
| `poll_interval` | `float` | `2.0` | Seconds between polling |

### `SessionPool` (recommended for repeated queries / SaaS)

| Method | Description |
|--------|-------------|
| `interactive_login(user_id, timeout)` | Open visible browser for Google login |
| `login(user_id, email, password)` | Start session (restores saved session if available) |
| `ask(question, user_id)` | Query using live session (fast!) |
| `ask_many(questions, user_id)` | Multiple queries sequentially |
| `is_logged_in(user_id)` | Check if session is active |
| `logout(user_id)` | Close a user's session |
| `close()` | Close all sessions |

### `CredentialVault` (multi-user credential storage)

| Method | Description |
|--------|-------------|
| `store_user(user_id, email, password)` | Store encrypted credentials |
| `get_user_credentials(user_id)` | Retrieve (email, password) |
| `has_user(user_id)` | Check if user exists |
| `list_users()` | List all stored user IDs |
| `remove_user(user_id)` | Delete user data |

### `Article` Model

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Article UUID |
| `status` | `ArticleStatus` | `running`, `success`, `failed`, `queued` |
| `title` | `str` | Generated title |
| `question` | `str` | Original question |
| `clean_text` | `str` | Cleaned plain text response |
| `references` | `list[Reference]` | Citations from medical literature |
| `follow_up_questions` | `list[str]` | Suggested follow-up questions |

---

## How It Works

1. **Playwright** launches a headless Chromium browser
2. Visits openevidence.com — FingerprintJS runs and generates a `pizza` token
3. If logged in (via saved session), auth cookies are sent automatically
4. **POST `/api/article`** with the fingerprint token creates a query
5. **GET `/api/article/{uuid}`** polls until `status == "success"`
6. Response is parsed into structured `Article` with clean text and references
7. **SessionPool** keeps browser alive — login once, query many times fast

---

## Troubleshooting

### "429 Rate Limit" or "Weekly limit reached"
You're not logged in. Anonymous users have strict rate limits. Run `interactive_login()` to sign in with your account.

### "Session expired" or queries failing after some time
Google sessions expire after a while. Run `interactive_login()` again to refresh.

### "Playwright not found"
```bash
pip install playwright
playwright install chromium
```

### "pip not found" (Mac)
Use `pip3` instead of `pip`:
```bash
pip3 install git+https://github.com/fredmmascarenhas-creator/openevidence-py.git
```

### Browser opens but login not detected
Make sure you complete the full Google login flow and land back on openevidence.com while logged in. The system waits up to 120 seconds by default.

### "FingerprintJS token not found"
The browser needs a few seconds after page load for FingerprintJS to initialize. The client handles this automatically with a 5-second wait.

---

## Production Deployment

### Docker

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app
COPY . .
RUN pip install -e .
RUN playwright install chromium

CMD ["uvicorn", "examples.saas_integration:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Security Notes

- For production vault encryption, replace the built-in XOR with a proper secret manager (AWS Secrets Manager, HashiCorp Vault, etc.)
- Each user's browser session is isolated (separate cookies/fingerprint)
- Sessions are persisted to disk at `~/.openevidence/`
- Thread-safe: each user in the pool gets their own browser + lock
- Never commit `.env` files or `browser_state.json` to git

### Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENEVIDENCE_EMAIL` | Account email (Auth0 login) |
| `OPENEVIDENCE_PASSWORD` | Account password (Auth0 login) |
| `OPENEVIDENCE_VAULT_KEY` | Encryption key for credential vault |

---

## License

MIT License. See [LICENSE](LICENSE) for details.
