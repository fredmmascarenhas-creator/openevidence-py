"""
SaaS Integration Example

Shows how to use OpenEvidence + NotebookLM together in a backend,
with multi-user credential management.

Architecture:
    User Request → Your SaaS Backend
        → OpenEvidence (medical search with citations)
        → NotebookLM (organize into notebook, generate audio, etc.)
        → Return enriched response to user
"""

import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()


# ──────────────────────────────────────────────
# 1. SINGLE USER (simple .env approach)
# ──────────────────────────────────────────────

def simple_medical_search(question: str) -> dict:
    """
    Simple single-user medical search.

    .env file:
        OPENEVIDENCE_EMAIL=your@email.com
        OPENEVIDENCE_PASSWORD=your_password
    """
    from openevidence import OpenEvidenceClient

    with OpenEvidenceClient() as client:
        article = client.ask(question)

    return {
        "title": article.title,
        "answer": article.clean_text,
        "references": [
            {"title": r.title, "journal": r.journal, "year": r.year}
            for r in article.references
        ],
        "follow_up_questions": article.follow_up_questions,
    }


# ──────────────────────────────────────────────
# 2. MULTI-USER (vault approach for SaaS)
# ──────────────────────────────────────────────

def setup_user(user_id: str, email: str, password: str):
    """
    Called when a user connects their OpenEvidence account in your SaaS.
    Store their credentials securely.
    """
    from openevidence.vault import CredentialVault

    vault = CredentialVault(
        encryption_key=os.environ.get("OPENEVIDENCE_VAULT_KEY", "change-me-in-production")
    )
    vault.store_user(user_id, email, password)
    print(f"Credentials stored for user {user_id}")


def medical_search_for_user(user_id: str, question: str) -> dict:
    """
    Medical search on behalf of a specific SaaS user.
    Uses their OpenEvidence account.
    """
    from openevidence.vault import CredentialVault

    vault = CredentialVault(
        encryption_key=os.environ.get("OPENEVIDENCE_VAULT_KEY")
    )

    with vault.get_client(user_id) as client:
        article = client.ask(question)

    return {
        "title": article.title,
        "answer": article.clean_text,
        "references": [
            {"title": r.title, "journal": r.journal, "year": r.year}
            for r in article.references
        ],
        "follow_up_questions": article.follow_up_questions,
        "article_id": article.id,  # Save for follow-ups
    }


# ──────────────────────────────────────────────
# 3. COMBO: OpenEvidence + NotebookLM
# ──────────────────────────────────────────────

async def medical_research_pipeline(user_id: str, question: str) -> dict:
    """
    Full pipeline:
    1. Search OpenEvidence for medical evidence
    2. Send results to NotebookLM for organization
    3. Return enriched response

    Requires:
        pip install openevidence-py notebooklm-py
    """
    from openevidence.vault import CredentialVault

    # Step 1: Get medical evidence from OpenEvidence
    vault = CredentialVault(
        encryption_key=os.environ.get("OPENEVIDENCE_VAULT_KEY")
    )

    with vault.get_client(user_id) as oe_client:
        article = oe_client.ask(question)

    # Step 2: Send to NotebookLM for deeper analysis
    # (requires notebooklm-py to be installed and configured)
    notebook_result = None
    try:
        from notebooklm import NotebookLMClient

        async with NotebookLMClient() as nb_client:
            # Create a notebook with the medical evidence
            notebook = await nb_client.notebooks.create(
                title=f"Medical Research: {article.title}"
            )

            # Add the OpenEvidence response as a source
            source_text = f"""
            # {article.title}

            ## Question
            {article.question}

            ## Evidence-Based Answer
            {article.clean_text}

            ## References
            """
            for ref in article.references:
                source_text += f"- {ref.title} ({ref.journal}, {ref.year})\n"

            await nb_client.sources.add(
                notebook_id=notebook.id,
                content=source_text,
                title=article.title,
            )

            notebook_result = {
                "notebook_id": notebook.id,
                "notebook_url": f"https://notebooklm.google.com/notebook/{notebook.id}",
            }

    except ImportError:
        notebook_result = {"note": "notebooklm-py not installed, skipping notebook creation"}
    except Exception as e:
        notebook_result = {"error": str(e)}

    # Step 3: Return combined result
    return {
        "question": question,
        "openevidence": {
            "title": article.title,
            "answer": article.clean_text,
            "references": [
                {"title": r.title, "journal": r.journal, "year": r.year}
                for r in article.references
            ],
            "follow_up_questions": article.follow_up_questions,
            "article_id": article.id,
        },
        "notebooklm": notebook_result,
    }


# ──────────────────────────────────────────────
# 4. FASTAPI EXAMPLE (ready for deployment)
# ──────────────────────────────────────────────

def create_fastapi_app():
    """
    Create a FastAPI app with medical search endpoints.

    Run with: uvicorn examples.saas_integration:app --reload

    Endpoints:
        POST /users/{user_id}/connect    - Connect OpenEvidence account
        POST /search                     - Search medical evidence
        GET  /article/{article_id}       - Get existing article
    """
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel

    app = FastAPI(title="Medical Evidence SaaS API")

    class ConnectRequest(BaseModel):
        email: str
        password: str

    class SearchRequest(BaseModel):
        user_id: str
        question: str
        follow_up_of: str | None = None

    @app.post("/users/{user_id}/connect")
    def connect_account(user_id: str, req: ConnectRequest):
        """Connect a user's OpenEvidence account."""
        from openevidence.vault import CredentialVault
        vault = CredentialVault(
            encryption_key=os.environ.get("OPENEVIDENCE_VAULT_KEY")
        )
        vault.store_user(user_id, req.email, req.password)
        return {"status": "connected", "user_id": user_id}

    @app.post("/search")
    def search(req: SearchRequest):
        """Search medical evidence for a user."""
        from openevidence.vault import CredentialVault
        vault = CredentialVault(
            encryption_key=os.environ.get("OPENEVIDENCE_VAULT_KEY")
        )
        if not vault.has_user(req.user_id):
            raise HTTPException(404, "User not found. Connect account first.")

        with vault.get_client(req.user_id) as client:
            article = client.ask(
                req.question,
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

    return app


# Create app instance for uvicorn
try:
    app = create_fastapi_app()
except ImportError:
    app = None  # FastAPI not installed


# ──────────────────────────────────────────────
# MAIN: Run examples
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Simple Medical Search ===")
    result = simple_medical_search("What is the treatment for hypertension?")
    print(f"Title: {result['title']}")
    print(f"Answer (first 200 chars): {result['answer'][:200]}...")
    print(f"References: {len(result['references'])}")
    print(f"Follow-ups: {result['follow_up_questions']}")
