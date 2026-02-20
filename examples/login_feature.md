# User Login Feature

## User Story
As a registered user, I want to log in to the application using my email and password so that I can access my personalized dashboard.

## Acceptance Criteria
- Users can log in with valid email and password
- Invalid credentials show an appropriate error message
- Account locks after 5 consecutive failed attempts
- "Remember me" checkbox keeps the session active for 30 days
- Password field masks the input
- "Forgot password" link redirects to password reset page
- Session expires after 30 minutes of inactivity
- Successful login redirects to the user's dashboard

## Technical Notes
- REST API endpoint: POST /api/v1/auth/login
- Response includes JWT token on success
- Rate limiting: 10 requests per minute per IP
