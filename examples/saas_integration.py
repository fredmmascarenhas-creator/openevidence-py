"""
SaaS Integration Example

Shows how to use OpenEvidence + NotebookLM together in a backend,
with multi-user credential management.

Architecture:
    User Request → Your SaaS Backend
        → OpenEvidence (medical search with citations)
        → NotebookLM (organize into notebook, generate audio, etc.)
        → Return enriched response to user

KEY CONCEPT - SessionPool:
    Login happens ONCE. All subsequent queries reuse the live browser.
    This makes repeated searches 3-5x faster than opening/closing each time.
"""

import os

# Try loading .env (optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ──────────────────────────────────────────────
# 1. SINGLE USER — Simplest approach
# ──────────────────────────────────────────────

def simple_single_query():
    """
    One question, one answer. Opens and closes the browser.
    Good for: scripts, CLI tools, one-off queries.

    .env file:
        OPENEVIDENCE_EMAIL=your@email.com
        OPENEVIDENCE_PASSWORD=your_password
    """
    from openevidence import OpenEvidenceClient

    with OpenEvidenceClient() as client:
        article = client.ask("What is the treatment for type 2 diabetes?")
        print(article.title)
        print(article.clean_text)


# ──────────────────────────────────────────────
# 2. SINGLE USER — Fast repeated queries with pool
# ──────────────────────────────────────────────

def fast_multiple_queries():
    """
    Login ONCE, ask MANY questions quickly.
    Good for: research sessions, batch processing.

    Performance:
        First query:  ~30s (login + query)
        Each after:   ~5-10s (query only!)
    """
    from openevidence import SessionPool

    pool = SessionPool()

    # Login once (slow, ~20s)
    pool.login(
        email=os.environ.get("OPENEVIDENCE_EMAIL"),
        password=os.environ.get("OPENEVIDENCE_PASSWORD"),
    )

    # All subsequent queries are fast!
    questions = [
        "What is metformin used for?",
        "Side effects of ACE inhibitors?",
        "Treatment options for COPD?",
        "Latest guidelines for hypertension?",
    ]

    for q in questions:
        article = pool.ask(q)
        print(f"\n{'='*60}")
        print(f"Q: {q}")
        print(f"A: {article.clean_text[:200]}...")
        print(f"   [{len(article.references)} references]")

    pool.close()


# ──────────────────────────────────────────────
# 3. MULTI-USER SAAS — Each user logs in once
# ──────────────────────────────────────────────

def multi_user_saas():
    """
    Multiple users, each with their own OpenEvidence account.
    Each user logs in ONCE, then all their queries are fast.

    Good for: SaaS backends, multi-tenant platforms.
    """
    from openevidence import SessionPool

    pool = SessionPool()

    # Each user logs in once (e.g., when they connect their account)
    pool.login("doctor_alice", email="alice@hospital.com", password="pass1")
    pool.login("doctor_bob", email="bob@clinic.com", password="pass2")

    # Now queries are fast for both users
    article_a = pool.ask("Treatment for hypertension?", user_id="doctor_alice")
    article_b = pool.ask("Aspirin dosage for ACS?", user_id="doctor_bob")

    # More queries — still fast, browser stays alive
    article_a2 = pool.ask("Side effects of losartan?", user_id="doctor_alice")

    print(f"Alice got: {article_a.title}")
    print(f"Bob got: {article_b.title}")
    print(f"Alice follow-up: {article_a2.title}")

    pool.close()


# ──────────────────────────────────────────────
# 4. MULTI-USER with Credential Vault (persistent)
# ──────────────────────────────────────────────

def multi_user_with_vault():
    """
    For production SaaS: credentials stored encrypted on disk.
    Vault manages credentials, Pool manages live sessions.

    Good for: production deployments where credentials persist
    across server restarts.
    """
    from openevidence import CredentialVault, SessionPool

    vault = CredentialVault(
        encryption_key=os.environ.get("OPENEVIDENCE_VAULT_KEY", "change-me")
    )

    # Step 1: Store credentials (usually via your SaaS onboarding UI)
    vault.store_user("user_123", "user@email.com", "password123")

    # Step 2: Create pool and login users from vault
    pool = SessionPool()
    email, password = vault.get_user_credentials("user_123")
    pool.login("user_123", email=email, password=password)

    # Step 3: Fast queries!
    article = pool.ask("What is the role of statins?", user_id="user_123")
    print(article.clean_text)

    pool.close()


# ──────────────────────────────────────────────
# 5. COMBO: OpenEvidence + NotebookLM pipeline
# ──────────────────────────────────────────────

async def medical_research_pipeline(question: str) -> dict:
    """
    Full pipeline:
    1. Search OpenEvidence for medical evidence with citations
    2. Send results to NotebookLM for organization/audio
    3. Return enriched response

    Requires:
        pip install openevidence-py notebooklm-py
    """
    from openevidence import SessionPool

    # Step 1: Get evidence (fast if pool already has session)
    pool = SessionPool()
    pool.login(
        email=os.environ.get("OPENEVIDENCE_EMAIL"),
        password=os.environ.get("OPENEVIDENCE_PASSWORD"),
    )
    article = pool.ask(question)

    # Step 2: Send to NotebookLM
    notebook_result = None
    try:
        from notebooklm import NotebookLMClient

        async with NotebookLMClient() as nb_client:
            notebook = await nb_client.notebooks.create(
                title=f"Medical Research: {article.title}"
            )

            source_text = f"# {article.title}\n\n"
            source_text += f"## Question\n{article.question}\n\n"
            source_text += f"## Evidence-Based Answer\n{article.clean_text}\n\n"
            source_text += "## References\n"
            for ref in article.references:
                source_text += f"- {ref.title} ({ref.journal}, {ref.year})\n"

            await nb_client.sources.add(
                notebook_id=notebook.id,
                content=source_text,
                title=article.title,
            )

            notebook_result = {
                "notebook_id": notebook.id,
                "url": f"https://notebooklm.google.com/notebook/{notebook.id}",
            }
    except ImportError:
        notebook_result = {"note": "notebooklm-py not installed"}
    except Exception as e:
        notebook_result = {"error": str(e)}

    pool.close()

    return {
        "question": question,
        "evidence": {
            "title": article.title,
            "answer": article.clean_text,
            "references": [
                {"title": r.title, "journal": r.journal, "year": r.year}
                for r in article.references
            ],
        },
        "notebook": notebook_result,
    }


# ──────────────────────────────────────────────
# 6. FASTAPI — Production-ready SaaS API
# ──────────────────────────────────────────────

def create_fastapi_app():
    """
    FastAPI app with SessionPool for fast responses.

    Run: uvicorn examples.saas_integration:app --reload

    KEY: The pool is created ONCE at startup. Users login once,
    then all /search calls are fast (~5-10s instead of ~30s).
    """
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel

    app = FastAPI(
        title="Medical Evidence SaaS API",
        description="OpenEvidence + NotebookLM backend with fast session pooling",
    )

    # Credential vault for persistent storage
    vault = CredentialVault(
        encryption_key=os.environ.get("OPENEVIDENCE_VAULT_KEY", "change-me")
    )

    # Session pool — lives for the entire server lifetime
    pool = SessionPool()

    class ConnectRequest(BaseModel):
        email: str
        password: str

    class SearchRequest(BaseModel):
        user_id: str
        question: str
        follow_up_of: str | None = None

    @app.post("/users/{user_id}/connect")
    def connect_account(user_id: str, req: ConnectRequest):
        """
        Connect a user's OpenEvidence account.
        Stores credentials and creates a live session.
        This is the SLOW call (~30s) — happens once per user.
        """
        # Store credentials for persistence
        vault.store_user(user_id, req.email, req.password)

        # Create live session (login + browser)
        pool.login(user_id, email=req.email, password=req.password)

        return {"status": "connected", "user_id": user_id}

    @app.post("/search")
    def search(req: SearchRequest):
        """
        Search medical evidence. FAST (~5-10s) because session is alive.
        """
        if not pool.is_logged_in(req.user_id):
            # Try to restore from vault
            if vault.has_user(req.user_id):
                email, password = vault.get_user_credentials(req.user_id)
                pool.login(req.user_id, email=email, password=password)
            else:
                raise HTTPException(404, "User not connected. POST /users/{id}/connect first.")

        article = pool.ask(
            req.question,
            user_id=req.user_id,
            original_article=req.follow_up_of,
        )

        return {
            "article_id": article.id,
            "title": article.title,
            "answer": article.clean_text,
            "references": [
                {"title": r.title, "journal": r.journal, "year": r.year}
                for r in article.references
            ],
            "follow_up_questions": article.follow_up_questions,
        }

    @app.get("/users")
    def list_active_users():
        """List users with active browser sessions."""
        return {"active_users": pool.active_users()}

    @app.delete("/users/{user_id}/disconnect")
    def disconnect_user(user_id: str):
        """Close a user's session (free resources)."""
        pool.logout(user_id)
        return {"status": "disconnected", "user_id": user_id}

    @app.on_event("shutdown")
    def shutdown():
        """Close all sessions when server stops."""
        pool.close()

    return app


# Import vault here for use in create_fastapi_app
try:
    from openevidence import CredentialVault
except ImportError:
    CredentialVault = None

# Create app instance for uvicorn
try:
    app = create_fastapi_app()
except Exception:
    app = None


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Fast Multiple Queries Demo ===")
    fast_multiple_queries()
