## IN-11: Add Remember Me option to extend user session from 15 minutes to 30 days

**Jira Ticket:** [IN-11](https://anandinfinity0007.atlassian.net/browse/IN-11)

## Summary
Implement Remember Me functionality to extend user session from 15 minutes to 30 days with a checkbox on the login page

## Implementation Plan

**Step 1: Update Login Page UI**  
Add a 'Remember Me' checkbox to the login form, ensuring it's positioned appropriately and styled consistently with existing form elements
Files: `login_page.html`, `login_component.js`

**Step 2: Modify JWT Token Generation**  
Update auth/jwt_handler.py generate_tokens() method to support conditional token expiration based on remember_me flag. Implement logic to set token expiry to 30 days when remember_me=True, otherwise maintain 15-minute expiry
Files: `auth/jwt_handler.py`

**Step 3: Update Login Authentication Logic**  
Modify login authentication method to pass remember_me flag to token generation process. Ensure the flag is correctly captured from the login form
Files: `authentication_service.py`, `login_controller.py`

**Step 4: Implement Unit Tests**  
Create comprehensive unit tests to verify:
        1. Token generation with remember_me=True creates 30-day token
        2. Token generation with remember_me=False creates 15-minute token
        3. Login form checkbox correctly passes remember_me flag
Files: `tests/auth_tests.py`

**Step 5: Security Validation**  
Conduct a security review to ensure:
        1. Extended sessions do not compromise brute-force protection
        2. Token generation remains secure with longer expiry
        3. LoginGuard mechanisms are not negatively impacted

**Risk Level:** MEDIUM — Medium risk due to modifications to authentication token generation and potential security implications of extended sessions

**Deployment Notes:**
- Ensure backward compatibility with existing authentication flows
- Update authentication documentation to reflect new Remember Me feature
- Perform thorough testing across different authentication scenarios

## Proposed Code Changes

### `auth/jwt_handler.py` (modify)
Modify generate_tokens() to support conditional token expiration based on remember_me flag. When True, set expiry to 30 days; otherwise, maintain 15-minute expiry.
```python
@@ -1,10 +1,14 @@
from datetime import datetime, timedelta
import jwt

def generate_tokens(user_id, remember_me=False):
    # Base token payload
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + (timedelta(days=30) if remember_me else timedelta(minutes=15))
    }
    
    # Generate access token
    access_token = jwt.encode(payload, 'SECRET_KEY', algorithm='HS256')
    return access_token
```

### `authentication_service.py` (modify)
Update authentication service to accept and pass remember_me flag to token generation process.
```python
@@ -1,10 +1,12 @@
from auth.jwt_handler import generate_tokens

def authenticate_user(username, password, remember_me=False):
    # Validate user credentials
    user = validate_credentials(username, password)
    
    if user:
        # Generate token with remember_me flag
        access_token = generate_tokens(user.id, remember_me)
        return access_token
    
    return None
```

### `login_component.js` (modify)
Add Remember Me checkbox to login form, managing its state and passing the flag during login.
```javascript
@@ -1,15 +1,20 @@
function LoginComponent() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [rememberMe, setRememberMe] = useState(false);

    const handleLogin = async (e) => {
        e.preventDefault();
        try {
            const response = await authService.login({
                username,
                password,
                rememberMe
            });
            // Handle successful login
        } catch (error) {
            // Handle login error
        }
    }

    return (
        <form onSubmit={handleLogin}>
            {/* Existing username and password inputs */}
            <div>
                <input 
                    type="checkbox"
                    id="rememberMe"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                />
                <label htmlFor="rememberMe">Remember Me</label>
            </div>
            <button type="submit">Login</button>
        </form>
    );
}
```

### `tests/auth_tests.py` (modify)
Add unit tests to verify token generation with different remember_me flag settings.
```python
@@ -1,15 +1,30 @@
import unittest
from auth.jwt_handler import generate_tokens
from datetime import datetime, timedelta

class TestTokenGeneration(unittest.TestCase):
    def test_token_expiry_default(self):
        token = generate_tokens(user_id=1)
        decoded = jwt.decode(token, 'SECRET_KEY', algorithms=['HS256'])
        expiry = datetime.fromtimestamp(decoded['exp'])
        self.assertAlmostEqual(
            (expiry - datetime.utcnow()).total_seconds(), 
            15 * 60,  # 15 minutes
            delta=1  # Allow 1-second variance
        )

    def test_token_expiry_remember_me(self):
        token = generate_tokens(user_id=1, remember_me=True)
        decoded = jwt.decode(token, 'SECRET_KEY', algorithms=['HS256'])
        expiry = datetime.fromtimestamp(decoded['exp'])
        self.assertAlmostEqual(
            (expiry - datetime.utcnow()).total_seconds(), 
            30 * 24 * 60 * 60,  # 30 days
            delta=1  # Allow 1-second variance
        )

if __name__ == '__main__':
    unittest.main()
```

**New Dependencies:**
- `PyJWT library for token generation and decoding`

## Test Suggestions

Framework: `pytest`

- **test_generate_tokens_default_expiration** — Verify default token expiration is 15 minutes when remember_me is False
- **test_generate_tokens_extended_expiration** — Verify token expiration is 30 days when remember_me is True
- **test_authentication_service_remember_me_flag** — Verify authentication service passes remember_me flag to token generation
- **test_login_component_remember_me_state** — Verify login component correctly manages Remember Me checkbox state
- **test_generate_tokens_invalid_remember_me_type** *(edge case)* — Verify error handling for invalid remember_me type

## Confluence Documentation References

- [Authentication Security Standards - Brute Force Protection](https://anandinfinity0007.atlassian.net/wiki/spaces/INF/pages/2260994) — Contains authentication security standards that may impact session management and token generation

**Suggested Documentation Updates:**

- Authentication Security Standards - Brute Force Protection

## AI Confidence Scores
Plan: 80%, Code: 80%, Tests: 90%

---
> ⚠️ **This PR was generated by AI (Claude via AWS Bedrock) and requires thorough human review
> before merging. Verify all logic, test coverage, and edge cases independently.**
>
> _Generated by [AI Agentic SDLC Assistant](https://github.com/Telomere-techsupp/SDLCWorker) — by Telomere LLC_
> _© 2025-2026 Telomere LLC. All rights reserved._