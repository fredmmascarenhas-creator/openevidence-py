# openevidence-py

**Unofficial** Python client for [OpenEvidence.com](https://www.openevidence.com) — the leading medical information platform powered by AI with citations from NEJM, JAMA, NCCN, Cochrane, and more.

> **Disclaimer**: This is an unofficial, community-driven project. It is not affiliated with, endorsed by, or associated with OpenEvidence Inc. Use responsibly and in accordance with OpenEvidence's Terms of Service.

## Installation

```bash
pip install openevidence-py
```

Or install from source:

```bash
git clone https://github.com/your-username/openevidence-py.git
cd openevidence-py
pip install -e .
```

## Quick Start

### Python API

```python
from openevidence import OpenEvidenceClient

# Synchronous usage (simplest)
client = OpenEvidenceClient()
article = client.ask_sync("What is the recommended treatment for type 2 diabetes?")

print(article.title)
print(article.clean_text)

for ref in article.references:
    print(f"  - {ref.title} ({ref.journal}, {ref.year})")

for q in article.follow_up_questions:
    print(f"  -> {q}")
```

### Async API

```python
import asyncio
from openevidence import OpenEvidenceClient

async def main():
    async with OpenEvidenceClient() as client:
        # Ask a question and wait for the full response
        article = await client.ask("What are the side effects of metformin?")
        print(article.clean_text)

        # Ask a follow-up question
        followup = await client.ask(
            "How does it compare to insulin?",
            original_article=article.id,
        )
        print(followup.clean_text)

asyncio.run(main())
```

### Streaming

```python
import asyncio
from openevidence import OpenEvidenceClient

async def main():
    async with OpenEvidenceClient() as client:
        async for partial in client.ask_stream("What is aspirin used for?"):
            print(f"Status: {partial.status.value}, Text length: {len(partial.text)}")

            if partial.status.value == "success":
                print(partial.clean_text)

asyncio.run(main())
```

### CLI

```bash
# Ask a question (pretty-printed output)
openevidence ask "What is the recommended treatment for hypertension?"

# Stream the response in real-time
openevidence ask "What is aspirin used for?" --stream

# Get JSON output (for piping/scripting)
openevidence ask "Side effects of ACE inhibitors?" --json

# Follow-up question using a previous article UUID
openevidence ask "How does it compare to ARBs?" --follow-up <uuid>

# Retrieve an existing article
openevidence get <article-uuid>
openevidence get <article-uuid> --json
```

## API Reference

### `OpenEvidenceClient`

| Parameter       | Type    | Default | Description                          |
|----------------|---------|---------|--------------------------------------|
| `base_url`     | `str`   | `https://www.openevidence.com` | Base URL        |
| `timeout`      | `float` | `120`   | Request timeout in seconds           |
| `poll_interval`| `float` | `1.5`   | Seconds between polling attempts     |

### Methods

#### `ask(question, **kwargs) -> Article`
Ask a question and wait for the complete response.

#### `ask_stream(question, **kwargs) -> AsyncIterator[Article]`
Ask a question and yield partial results as they arrive.

#### `get_article(article_id) -> Article`
Retrieve an existing article by UUID.

#### `ask_sync(question, **kwargs) -> Article`
Synchronous wrapper around `ask()`.

### `Article` Model

| Field                | Type              | Description                                  |
|---------------------|-------------------|----------------------------------------------|
| `id`                | `str`             | Article UUID                                 |
| `status`            | `ArticleStatus`   | `running`, `success`, `failed`, `queued`     |
| `title`             | `str`             | Generated title                              |
| `question`          | `str`             | Original question                            |
| `text`              | `str`             | Raw response text (with HTML/markers)        |
| `clean_text`        | `str`             | Cleaned plain text                           |
| `sections`          | `list[Section]`   | Structured sections with paragraphs          |
| `references`        | `list[Reference]` | Citations from medical literature            |
| `follow_up_questions`| `list[str]`      | Suggested follow-up questions                |

## How It Works

This library reverse-engineers the OpenEvidence web API:

1. **Session**: Establishes a browser-like HTTP session with cookies by visiting the homepage
2. **POST `/api/article`**: Submits a question with a generated anti-bot token (`pizza` header)
3. **GET `/api/article/{uuid}`**: Polls for the response until `status == "success"`
4. **Parsing**: Extracts clean text, structured sections, references, and follow-up questions

### Discovered Endpoints

| Endpoint                     | Method | Description                          |
|------------------------------|--------|--------------------------------------|
| `/api/article`               | POST   | Create a new article/query           |
| `/api/article/{uuid}`        | GET    | Get article status and content       |
| `/api/article/ct`            | GET    | List articles (requires auth)        |
| `/api/getTargetCampaign`     | POST   | Campaign targeting                   |
| `/api/events`                | POST   | Event tracking/analytics             |

### Request Payload Structure

```json
{
    "article_type": "Ask OpenEvidence Light with citations",
    "inputs": {
        "variant_configuration_file": "prod",
        "attachments": [],
        "question": "your question here",
        "use_gatekeeper": true
    },
    "original_article": null,
    "personalization_enabled": false,
    "disable_caching": false
}
```

## Limitations

- **No authentication**: Currently works without login (anonymous access), which may have rate limits
- **Polling-based**: Uses polling instead of streaming (the web app polls too)
- **Fragile**: As with any reverse-engineered API, endpoints may change without notice
- **Rate limits**: OpenEvidence may impose rate limits on anonymous usage
- **Not for production medical use**: This is a developer tool, not a medical device

## License

MIT License. See [LICENSE](LICENSE) for details.
