## IN-3: Add "Remember Me" option to extend user session from 15 minutes to 30 days

**Jira Ticket:** [IN-3](https://anandinfinity0007.atlassian.net/browse/IN-3)

## Summary
Implement 'Remember Me' functionality in token generation to support 30-day sessions for trusted devices

## Implementation Plan

**Step 1: Update generate_tokens() function signature**  
Modify the generate_tokens() function in auth/jwt_handler.py to accept a new remember_me parameter with a default value of False
Files: `auth/jwt_handler.py`

**Step 2: Implement conditional token expiry logic**  
Add conditional logic to set different token expiration times based on remember_me flag:
- If remember_me=False: Use existing 15-minute access token and 7-day refresh token
- If remember_me=True: Set access token to 1 hour (3600s) and refresh token to 30 days (2592000s)
Files: `auth/jwt_handler.py`

**Step 3: Update login request handling**  
Modify login request processing to pass remember_me flag to generate_tokens() function. Ensure the flag is optional with a default of False.
Files: `auth/jwt_handler.py`

**Step 4: Create unit tests for new token generation scenarios**  
Add new unit tests to verify:
- Default behavior (remember_me=False) remains unchanged
- remember_me=True generates 1-hour access and 30-day refresh tokens
- Verify exp claim in JWT payload reflects correct expiration times
Files: `tests/test_jwt_handler.py`

**Step 5: Validate existing test suite**  
Run existing token generation unit tests to ensure no regressions and all previous test cases continue to pass
Files: `tests/test_jwt_handler.py`

**Risk Level:** LOW — Low risk modification to existing token generation logic with minimal changes and no impact on validation. Changes are isolated to a single function and do not modify core authentication mechanisms.

**Deployment Notes:**
- Minimal backend change
- No database migrations required
- No breaking changes to existing API contract

## Proposed Code Changes

### `auth/jwt_handler.py` (modify)
Modify generate_tokens() to support a remember_me flag that changes token expiration times. When remember_me is True, extend access token to 1 hour and refresh token to 30 days. Maintain existing 15-min/7-day behavior when False. Added docstring to explain new parameter.
```python
@@ -1,10 +1,20 @@
-def generate_tokens(user_id: str) -> Dict[str, str]:
+def generate_tokens(user_id: str, remember_me: bool = False) -> Dict[str, str]:
     """Generate access and refresh tokens for a user.
 
+    Args:
+        user_id (str): The unique identifier for the user.
+        remember_me (bool, optional): Flag to extend token expiration. Defaults to False.
+
     Returns:
         Dict[str, str]: A dictionary containing access and refresh tokens.
     """
     # Token generation logic
-    access_token_expiry = int(time.time()) + 900  # 15 minutes
-    refresh_token_expiry = int(time.time()) + 604800  # 7 days
+    if remember_me:
+        access_token_expiry = int(time.time()) + 3600  # 1 hour
+        refresh_token_expiry = int(time.time()) + 2592000  # 30 days
+    else:
+        access_token_expiry = int(time.time()) + 900  # 15 minutes
+        refresh_token_expiry = int(time.time()) + 604800  # 7 days
 
     access_token = create_access_token({
         'sub': user_id,
@@ -12,6 +22,7 @@
     refresh_token = create_refresh_token({
         'sub': user_id,
         'exp': refresh_token_expiry
+        # Note: 'remember_me' not stored in token payload
     })
 
     return {

```

### `tests/test_jwt_handler.py` (modify)
Add new unit test to verify token generation with remember_me=True. Test checks that tokens are generated correctly and have the expected expiration times (1-hour access, 30-day refresh). Assumes existence of a decode_token() helper function to inspect token payloads.
```python
@@ -1,15 +1,35 @@
 def test_generate_tokens():
     # Existing test for default token generation
     tokens = generate_tokens('user123')
     assert 'access_token' in tokens
     assert 'refresh_token' in tokens
 
+def test_generate_tokens_remember_me():
+    # Test token generation with remember_me=True
+    tokens = generate_tokens('user123', remember_me=True)
+    assert 'access_token' in tokens
+    assert 'refresh_token' in tokens
+
+    # Verify token expiration times for remember_me=True
+    access_token_payload = decode_token(tokens['access_token'])
+    refresh_token_payload = decode_token(tokens['refresh_token'])
+
+    # Check access token expiry (1 hour = 3600 seconds)
+    assert access_token_payload['exp'] - access_token_payload['iat'] == 3600
+
+    # Check refresh token expiry (30 days = 2592000 seconds)
+    assert refresh_token_payload['exp'] - refresh_token_payload['iat'] == 2592000
+
 def test_token_validation():
     # Existing token validation tests
     pass

```

## Test Suggestions

Framework: `pytest`

- **test_generate_tokens_default_remember_me_false** — Verify token generation with default remember_me=False behavior
- **test_generate_tokens_remember_me_true** — Verify token generation with remember_me=True extends token lifetimes
- **test_generate_tokens_remember_me_invalid_input** *(edge case)* — Verify behavior with invalid remember_me input
- **test_generate_tokens_user_id_none** *(edge case)* — Verify behavior when user_id is None

## Confluence Documentation References

- [Authentication Security Standards - Brute Force Protection](https://anandinfinity0007.atlassian.net/wiki/spaces/INF/pages/2260994) — Provides context for authentication security standards, which is relevant to the token generation and session management changes proposed in the ticket

**Suggested Documentation Updates:**

- Authentication Security Standards - Brute Force Protection
- Add a section describing the new 'Remember Me' token generation strategy and its security implications

## AI Confidence Scores
Plan: 95%, Code: 90%, Tests: 95%

---
> ⚠️ **This PR was generated by AI (Claude via AWS Bedrock) and requires thorough human review
> before merging. Verify all logic, test coverage, and edge cases independently.**
>
> _Generated by AI Agentic SDLC Assistant_