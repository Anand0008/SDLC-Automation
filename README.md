# SDLC-Automation Platform

A production-ready Python backend platform demonstrating **AI-assisted software development lifecycle (SDLC) automation**. The business logic modules (authentication, rate limiting, real-time WebSocket, analytics) in this repository were planned, proposed, and committed entirely by an autonomous 8-agent LangGraph pipeline — from Jira ticket to open pull request — with no human in the loop.

---

## Table of Contents

1. [Repository Structure](#repository-structure)
2. [Platform Modules](#platform-modules)
3. [How the AI Pipeline Works](#how-the-ai-pipeline-works)
4. [Agent Descriptions](#agent-descriptions)
5. [Confluence Integration](#confluence-integration)
6. [Pull Requests Created by the Pipeline](#pull-requests-created-by-the-pipeline)
7. [Known Limitations — LLM Parsing Error in CodeProposalAgent](#known-limitations--llm-parsing-error-in-codeproposalAgent)
8. [Environment Variables](#environment-variables)
9. [Quick Start](#quick-start)

---

## Repository Structure

```
auth/
  __init__.py
  jwt_handler.py              JWT RS256 token pair management

middleware/
  __init__.py
  rate_limiter.py             Redis sliding-window rate limiter

realtime/
  __init__.py
  websocket_manager.py        WebSocket + Redis Pub/Sub broadcast manager

analytics/
  __init__.py
  pipeline.py                 Buffered event pipeline with live streaming

tests/
  __init__.py
  test_rate_limiter.py        5 unit tests covering rate limiter core logic
  test_analytics_pipeline.py  6 unit tests covering analytics pipeline

README.md
```

---

## Platform Modules

### Authentication (`auth/`)

**`jwt_handler.py`**

- Generates RS256-signed access tokens (15-minute TTL) and refresh tokens (7-day TTL)
- Uses `python-jose` for signing and verification
- FastAPI `Depends`-compatible `get_current_user()` dependency
- All claims validated: `exp`, `iat`, `sub`, `type`
- Refresh token rotation: each use issues a new pair and invalidates the old token

### Rate Limiting (`middleware/`)

**`rate_limiter.py`**

- Redis sliding-window algorithm — counts only requests within the last 60 seconds
- Two independent limit tiers applied per request:
  - **Per-IP**: 100 requests/minute (configurable via `RATE_LIMIT_RPM`)
  - **Per-user**: 1000 requests/minute (authenticated users only)
- Returns HTTP 429 with mandatory `Retry-After` header and `X-RateLimit-*` diagnostic headers
- **Fail-open**: if Redis is unavailable, the request is allowed through rather than blocking all traffic
- FastAPI middleware class — drop-in addition to any app

### Real-Time (`realtime/`)

**`websocket_manager.py`**

- `ConnectionManager` — tracks all active WebSocket connections in memory
- Redis Pub/Sub subscription per connection group — enables broadcasting across multiple server instances (horizontal scaling)
- Heartbeat ping every 30 seconds; stale/disconnected sockets removed automatically
- `broadcast_to_group(group_id, message)` — fan-out to all subscribers of a logical group (e.g. all users watching order `#12345`)
- `send_personal_message(user_id, message)` — unicast to a single connected user

### Analytics (`analytics/`)

**`pipeline.py`**

- In-memory ring buffer (default 1000 events); flushes to PostgreSQL on size threshold or 5-second timer
- Async batch INSERT to `analytics_events` table — minimises DB round-trips
- Simultaneously publishes each batch to Redis channel `analytics:live` for real-time dashboard consumers
- Pre-built helpers: `track_page_view(user_id, path)`, `track_api_call(endpoint, status_code, latency_ms)`
- Graceful shutdown: `stop()` flushes the remaining buffer before exit

---

## How the AI Pipeline Works

The SDLC assistant is a **LangGraph state machine** with 8 specialist agents. Each agent reads the shared `WorkflowState`, does its work (calls an LLM, queries an MCP server, or runs a heuristic), and writes back a partial state update. LangGraph merges these updates and routes to the next node based on conditional edges.

```
Jira Ticket (DEV-30 / DEV-31 / DEV-32)
        |
        v
+------------------+
| TicketFetcher    |  Pulls ticket fields via mcp-atlassian Jira tools
+--------+---------+
         |
         v
+------------------+
| Completeness     |  Scores ticket quality (0-1).
| Agent            |  Rejects below COMPLETENESS_THRESHOLD (0.35)
+--------+---------+
         |
         v
+------------------+
| RepoScout        |  Walks the GitHub repo tree (mcp-github).
| Agent            |  Identifies relevant files; detects code style
+--------+---------+
         |
         v
+------------------+
| Confluence       |  Searches Confluence via mcp-atlassian.
| Agent            |  Retrieves design docs aligned to the ticket
+--------+---------+
         |
         v
+------------------+
| Planner          |  LLM generates a numbered implementation plan
| Agent            |  (step titles, affected files, complexity estimate)
+--------+---------+
         |
         v
+------------------+
| CodeProposal     |  LLM generates unified diffs / full file contents
| Agent            |  for every file in the plan  <- see Known Limitations
+--------+---------+
         |
         v
+------------------+
| Test             |  LLM proposes pytest test cases for the changes
| Agent            |
+--------+---------+
         |
         v
+------------------+
| PRComposer       |  Creates a GitHub branch, commits each file change,
| Agent            |  opens a Pull Request with the full plan + diff summary
+------------------+
        |
        v
  Open PR on GitHub
```

### Technology Stack

| Concern | Implementation |
|---|---|
| LLM | AWS Bedrock — `us.anthropic.claude-3-5-haiku-20241022-v1:0` |
| Orchestration | LangGraph (graph-based state machine) |
| Jira / Confluence | `uvx mcp-atlassian` (MCP server, 98 tools) |
| GitHub | `npx @modelcontextprotocol/server-github` |
| Persistence | SQLite (run history, LLM call log) |
| Structured output | LangChain `with_structured_output` + Pydantic schemas |
| Logging | Structured JSONL logs — activity log + LLM call log |

---

## Agent Descriptions

### TicketFetcherAgent
Calls `jira_get_issue` via the Atlassian MCP server. Extracts ticket ID, title, description, acceptance criteria, priority, labels, and story points into a typed `TicketContext` schema.

### CompletenessAgent
Runs a lightweight LLM call to score the ticket (0.0–1.0) on four dimensions: description clarity, acceptance criteria presence, scope definition, and technical detail. Tickets scoring below `COMPLETENESS_THRESHOLD` (default 0.35) are rejected early, preventing wasted LLM spend downstream.

### RepoScoutAgent
Uses `get_file_tree` and `get_file_contents` GitHub MCP tools to explore the repository. Selects up to `REPO_SCOUT_MAX_FILES` (default 20) files most relevant to the ticket keywords. Extracts function signatures, class names, and infers code style (indentation, naming convention, type-hint usage).

### ConfluenceAgent
Searches the configured Confluence space (`CONFLUENCE_SPACE_KEYS=SD`) via `confluence_search` MCP tool. Applies CQL space filter (`spaces_filter` param) to restrict results. Parses the MCP response format — `list[{type, text, id}]` — where each item's `text` field is a JSON array of page records. Fetches full page body for each result via `confluence_get_page`. Returns a `ConfluenceContext` with relevant excerpts attached to each page.

### PlannerAgent
Sends the ticket, repo analysis, and Confluence excerpts to Bedrock. Returns a structured `ImplementationPlan` with numbered steps, each specifying: title, description, affected files, and estimated complexity (1–5).

### CodeProposalAgent
Sends the implementation plan steps to Bedrock and requests file-level code changes. Returns a `CodeProposal` containing `FileDiff` objects (unified diff format or full file content). **See Known Limitations below** — this agent can fail on complex tickets.

### TestAgent
Given the `CodeProposal`, generates pytest test cases covering the new functions and classes. Returns a `TestProposal` with test file paths and test function stubs.

### PRComposerAgent
Creates a new branch (`ai/dev-{N}`), commits each `FileDiff` from the `CodeProposal`, and opens a Pull Request. The PR body contains: the ticket summary, Confluence pages referenced, implementation plan, list of changed files, and test suggestions.

---

## Confluence Integration

The pipeline is wired to a **Confluence Cloud** instance (Software Development space, key `SD`). The following design documents were authored to support the three feature tickets:

| Page | Ticket Relevance |
|---|---|
| System Architecture Overview | Platform-wide context |
| API Design Standards | DEV-30 — rate limiting standards, 429 response format, Redis sliding window |
| Database Schema and Migrations | DEV-32 — `analytics_events` partitioned table, DAU materialized view |
| Security and Authentication Guidelines | DEV-31 — WebSocket auth, JWT RS256, security headers |
| Real-Time Features and WebSocket Scaling | DEV-31 — `ConnectionManager` design, Redis Pub/Sub topology |

### How the Confluence Search Fix Works

Prior to the fix, `ConfluenceAgent` always returned `pages_found=0`. Three root causes were identified and resolved:

1. **Missing `spaces_filter`**: The MCP search tool accepts `spaces_filter` (comma-separated space keys), not `space_key`. The original code omitted this param, returning results from all spaces (none matching).

2. **Wrong response parsing**: `mcp-atlassian` returns `list[{type, text, id}]` — not a dict with a `results` key. The actual page array is a **JSON string inside `item["text"]`**. The old code called `result.get("results", [])` on the outer list, which always returned empty.

3. **Wrong space key format**: `.env` had `CONFLUENCE_SPACE_KEYS=Software Development` (display name). Confluence CQL requires the space **key** — `SD` — not the name.

---

## Pull Requests Created by the Pipeline

All three PRs were opened autonomously by `PRComposerAgent`:

| PR | Ticket | Branch | Feature |
|---|---|---|---|
| #1 | DEV-30 | `ai/dev-30` | Per-IP and per-user Redis rate limiting on `/api/users` |
| #2 | DEV-31 | `ai/dev-31` | Real-time order status WebSocket notifications with Redis Pub/Sub |
| #3 | DEV-32 | `ai/dev-32` | Analytics event pipeline with PostgreSQL persistence + live dashboard streaming |

---

## Known Limitations — LLM Parsing Error in CodeProposalAgent

### What the error looks like

In the pipeline logs you will see entries like:

```
agent_node_completed  agent=CodeProposalAgent  parsed_ok=false  latency_ms=124000
agent_node_failed     exc=LLM returned None for CodeProposal
current_phase=FAILED  errors=["code_proposal: LLM returned None for CodeProposal"]
```

### Root cause — token budget exhaustion truncates the tool call

`CodeProposalAgent` uses LangChain's `with_structured_output(CodeProposal, method="function_calling")`. This instructs Bedrock to emit the response as a **single JSON tool-call argument** matching the `CodeProposal` Pydantic schema.

The `CodeProposal` schema contains a `file_changes` list of `FileDiff` objects. Each `FileDiff` carries a `proposed_content` field — the complete source of a new or modified file. For complex tickets (e.g. DEV-31 with WebSocket manager + Redis Pub/Sub, DEV-32 with analytics pipeline + PostgreSQL migrations), the model needs to generate 4–6 full files, all serialised into a single JSON tool-call argument.

The Bedrock model output is capped at **`BEDROCK_MAX_TOKENS=4096`** (set in `.env`). When the total JSON for all `FileDiff` entries exceeds this budget, Bedrock **truncates the output mid-stream**. The tool-call argument is then syntactically invalid JSON — a missing closing brace or bracket is all it takes.

LangChain's `with_structured_output(..., include_raw=False)` catches the JSON parse failure internally and **silently returns `None`** instead of raising an exception. The `invoke_and_log` wrapper records `parsed_successfully=False` in `logs/llm_calls.jsonl`. Back in `CodeProposalAgent.run()`, the `None` check raises:

```python
if result is None:
    raise ValueError("LLM returned None for CodeProposal")
```

This is caught by the outer `except Exception`, which sets `should_stop=True` and `current_phase=FAILED`.

### Why the failure only appears on certain tickets

DEV-30 (rate limiter — 2 small files) produced a compact `CodeProposal` JSON that fit within 4096 tokens. DEV-31 and DEV-32 each required 4–6 new files whose combined proposed content exceeded the token budget.

The model still spends the full generation time (120–145 seconds observed) before the truncated response arrives — Bedrock streams until the token limit is hit. The latency does not indicate a timeout; it is normal generation time for large outputs.

### Why `parsed_ok=false` does not mean the LLM call failed

The LLM call itself **succeeded** — Bedrock received the prompt, ran inference, and returned a response. The failure happens at the **deserialisation step** on the client side. LangChain attempts to parse the response JSON into the `CodeProposal` Pydantic model; because the JSON is truncated, Pydantic validation fails and LangChain returns `None`. This distinction matters for debugging: the issue is not a network error, timeout, or model refusal — it is a response size problem.

### Possible mitigations

| Approach | Tradeoff |
|---|---|
| Increase `BEDROCK_MAX_TOKENS` to 8192 | Claude 3.5 Haiku supports up to 8192 output tokens; raises cost per call but reduces truncation |
| Process one implementation step per LLM call | Smaller per-call JSON; requires orchestration changes in `CodeProposalAgent` |
| Use `include_raw=True`, parse manually | Recover partial JSON from the truncated response; reconstruct as many `FileDiff` entries as possible before the cut-off |
| Switch to a model with higher reliable output capacity | Claude 3.5 Sonnet handles larger structured outputs more reliably |
| Compress `proposed_content` to diffs only | Unified diffs are much shorter than full file contents for modification tickets |

### Current resilience behaviour

The pipeline does not crash when `CodeProposalAgent` fails. `PRComposerAgent` still runs and opens a PR — the PR body contains the full numbered implementation plan and all Confluence pages referenced. A developer receives a detailed specification and can write the code manually, or re-run the pipeline after raising `BEDROCK_MAX_TOKENS`.

---

## Environment Variables

```env
# LLM
LLM_PROVIDER=bedrock
AWS_DEFAULT_REGION=us-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
BEDROCK_MODEL_ID=us.anthropic.claude-3-5-haiku-20241022-v1:0
BEDROCK_MAX_TOKENS=4096          # Increase to 8192 to reduce CodeProposal parse failures
BEDROCK_TEMPERATURE=0.1

# Jira
JIRA_URL=https://<instance>.atlassian.net
JIRA_USERNAME=...
JIRA_API_TOKEN=...
JIRA_PROJECTS_FILTER=DEV
JIRA_POLL_JQL=project in (DEV) AND status = "To Do" ORDER BY created DESC
JIRA_POLL_INTERVAL_SECONDS=300

# Confluence
CONFLUENCE_URL=https://<instance>.atlassian.net/wiki
CONFLUENCE_SPACE_KEYS=SD         # Comma-separated SPACE KEYS (not space names)
CONFLUENCE_MAX_PAGES=10

# GitHub
GITHUB_PERSONAL_ACCESS_TOKEN=...
GITHUB_REPO_OWNER=...
GITHUB_REPO_NAME=...
GITHUB_BASE_BRANCH=main

# Application
SQLITE_DB_PATH=data/sdlc_assistant.db
LOG_LEVEL=INFO
ACTIVITY_LOG_PATH=logs/activity.jsonl
LLM_LOG_PATH=logs/llm_calls.jsonl
REPO_SCOUT_MAX_FILES=20
COMPLETENESS_THRESHOLD=0.35
LLM_PARSE_RETRY_COUNT=3
DRY_RUN=false                    # true = skip Jira comments and GitHub PRs

# Runtime dependencies (for the platform modules in this repo)
RATE_LIMIT_RPM=100
REDIS_HOST=localhost
REDIS_PORT=6379
DATABASE_URL=postgresql://user:pass@localhost/db
```

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/Anand0008/SDLC-Automation.git
cd SDLC-Automation
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Start the server (requires Redis + PostgreSQL)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

*This repository and its code were generated by the AI Agentic SDLC Assistant — a LangGraph pipeline integrating AWS Bedrock, Jira, Confluence, and GitHub via Model Context Protocol (MCP) servers.*
