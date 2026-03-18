## IN-7: Add /health and /readyz endpoints for Kubernetes liveness and readiness probes

**Jira Ticket:** [IN-7](https://anandinfinity0007.atlassian.net/browse/IN-7)

## Summary
Implement Kubernetes health and readiness probe endpoints (/health and /readyz) with SQLite connectivity check

## Implementation Plan

**Step 1: Create health.py with endpoint models**  
Define Pydantic models for /health and /readyz response schemas in routes/health.py. Include required fields: status, version (for /health), response_time_ms, and optional reason (for /readyz failure).
Files: `routes/health.py`

**Step 2: Implement /health endpoint**  
Create GET /health endpoint that always returns 200. Use os.getenv() to retrieve APP_VERSION, defaulting to 'unknown'. Measure response time using time.time() or similar.
Files: `routes/health.py`

**Step 3: Implement /readyz endpoint with database check**  
Create GET /readyz endpoint that performs a SQLite connectivity test using 'SELECT 1'. Return 200 on successful connection, 503 on failure. Include response time and failure reason.
Files: `routes/health.py`

**Step 4: Create health router**  
Create a FastAPI APIRouter for health endpoints. Add /health and /readyz routes to the router with appropriate response models and logic.
Files: `routes/health.py`

**Step 5: Update main.py to include health router**  
Import the health router in main.py and use include_router() to add it to the main FastAPI application. Add 'health' tag to the router.
Files: `main.py`

**Step 6: Write unit tests**  
Create unit tests in test_health.py to cover:
        1. /health endpoint always returns 200 with correct fields
        2. /readyz success path with working database
        3. /readyz failure path with database connection error
Files: `tests/test_health.py`

**Risk Level:** MEDIUM — Low risk implementation of standard Kubernetes probe endpoints. Minimal changes to existing codebase with clear requirements from Confluence documentation.

**Deployment Notes:**
- Ensure APP_VERSION environment variable is set in deployment configuration
- Verify SQLite database connection parameters are correctly configured
- Update Kubernetes deployment YAML to use new /health and /readyz probe endpoints

## Proposed Code Changes

### `routes/health.py` (create)
Implement health and readiness probe endpoints as specified in the ticket requirements. The /health endpoint always returns 200 with version and response time. The /readyz endpoint checks SQLite database connectivity and returns appropriate status codes.
```python
import os
import time
from typing import Optional

import sqlite3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

health_router = APIRouter()

class HealthResponse(BaseModel):
    status: str = 'ok'
    version: str
    response_time_ms: float

class ReadinessResponse(BaseModel):
    status: str
    response_time_ms: float
    reason: Optional[str] = None

@health_router.get('/health', response_model=HealthResponse)
async def health_check():
    start_time = time.time()
    version = os.getenv('APP_VERSION', 'unknown')
    
    response_time_ms = round((time.time() - start_time) * 1000, 2)
    return {
        'status': 'ok', 
        'version': version, 
        'response_time_ms': response_time_ms
    }

@health_router.get('/readyz', response_model=ReadinessResponse)
async def readiness_check():
    start_time = time.time()
    
    try:
        # Attempt to connect to SQLite database
        conn = sqlite3.connect('app.db')
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        cursor.close()
        conn.close()
        
        response_time_ms = round((time.time() - start_time) * 1000, 2)
        return {
            'status': 'ok', 
            'response_time_ms': response_time_ms
        }
    except sqlite3.Error as e:
        response_time_ms = round((time.time() - start_time) * 1000, 2)
        raise HTTPException(
            status_code=503, 
            detail={
                'status': 'error', 
                'response_time_ms': response_time_ms, 
                'reason': str(e)
            }
        )

```

### `main.py` (modify)
Add health router to the main FastAPI application with 'health' tag as specified in the implementation plan
```python
--- a/main.py
+++ b/main.py
@@ -1,6 +1,7 @@
 from fastapi import FastAPI
 
 # Import routers
+from routes.health import health_router
 
 app = FastAPI()
 
@@ -8,3 +9,5 @@ app = FastAPI()
 # Include other routers
 
 # Include health router
+app.include_router(health_router, tags=['health'])
+

```

**New Dependencies:**
- `sqlite3`
- `time`
- `os`

## Test Suggestions

Framework: `pytest`

- **test_health_endpoint_returns_correct_response** — Verify /health endpoint returns 200 with correct fields
- **test_readiness_probe_with_successful_db_connection** — Verify /readyz returns 200 when database is reachable
- **test_readiness_probe_with_failed_db_connection** *(edge case)* — Verify /readyz returns 503 when database is not reachable
- **test_health_endpoint_response_time_included** — Verify response_time_ms is present and is a number

## Confluence Documentation References

- [Health Check and Readiness Probe Design](https://anandinfinity0007.atlassian.net/wiki/spaces/INF/pages/2293761) — Directly defines the exact requirements for health check and readiness probe endpoints, including response schemas, purpose, and behavior

**Suggested Documentation Updates:**

- Health Check and Readiness Probe Design

## AI Confidence Scores
Plan: 95%, Code: 90%, Tests: 95%

---
> ⚠️ **This PR was generated by AI (Claude via AWS Bedrock) and requires thorough human review
> before merging. Verify all logic, test coverage, and edge cases independently.**
>
> _Generated by AI Agentic SDLC Assistant_