# Google OAuth Setup Guide

To enable Google Sign-In for AgentMail, you'll need to create OAuth credentials in the Google Cloud Console.

## Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click "Select a project" → "New Project"
3. Name it "AgentMail" (or any name you prefer)
4. Click "Create"

## Step 2: Enable Required APIs

1. In your project, go to **APIs & Services** → **Library**
2. Search for and enable these APIs:
   - **Gmail API**
   - **Google+ API** (for user info)

## Step 3: Configure OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Choose **External** (unless you have a Google Workspace account)
3. Fill in the required fields:
   - **App name**: AgentMail
   - **User support email**: Your email
   - **Developer contact**: Your email
4. Click **Save and Continue**
5. On the "Scopes" page, click **Add or Remove Scopes** and add:
   - `.../auth/gmail.readonly`
   - `.../auth/gmail.send`
   - `.../auth/gmail.modify`
   - `.../auth/userinfo.email`
   - `.../auth/userinfo.profile`
6. Click **Save and Continue**
7. Add yourself as a test user (for development)
8. Click **Save and Continue**

## Step 4: Create OAuth Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. Choose **Web application**
4. Configure:
   - **Name**: AgentMail Web Client
   - **Authorized JavaScript origins**: 
     - `http://localhost:8000`
   - **Authorized redirect URIs**:
     - `http://localhost:8000/auth/callback`
5. Click **Create**
6. **SAVE** the **Client ID** and **Client Secret**

## Step 5: Update Your .env File

Add your OAuth credentials to `.env`:

```bash
GOOGLE_CLIENT_ID=your_client_id_here.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret_here
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback
SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')
```

## Step 6: Restart the Server

```bash
# Stop the current server
pkill -f uvicorn

# Start it again
make dev
# or
.venv/bin/uvicorn src.app:app --reload --host 0.0.0.0 --port 8000
```

## Step 7: Test the Login

1. Go to http://localhost:8000
2. You should be redirected to `/login`
3. Click "Sign in with Google"
4. Authorize the app
5. You'll be redirected back to `/inbox`

## Troubleshooting

### Error: "redirect_uri_mismatch"
- Make sure the redirect URI in Google Console exactly matches: `http://localhost:8000/auth/callback`
- No trailing slash
- Include the port number

### Error: "Access blocked: This app's request is invalid"
- Make sure you've added yourself as a test user in the OAuth consent screen
- Check that all required scopes are added

### Error: "OAuth not configured"
- Double-check your `.env` file has the correct values
- Make sure there are no extra spaces or quotes
- Restart the server after updating `.env`

## Production Deployment

For production:

1. Update `GOOGLE_REDIRECT_URI` to your production domain:
   ```bash
   GOOGLE_REDIRECT_URI=https://yourdomain.com/auth/callback
   ```

2. Add the production redirect URI in Google Console

3. Generate a secure `SECRET_KEY`:
   ```bash
   python -c 'import secrets; print(secrets.token_hex(32))'
   ```

4. Change OAuth consent screen to "In Production" (requires verification for > 100 users)

5. Use HTTPS in production (required by Google OAuth)

## Security Notes

- Never commit your `.env` file to version control
- Use different OAuth credentials for development and production
- Rotate your `SECRET_KEY` periodically
- Review the permissions you're requesting regularly
- Implement proper session management and CSRF protection in production
