# AgentMail

Hey guys, this is Galen. This is a little portfolio project that I built to assist myself in my daily life. This handles emails through a priority system, making replying easy. The goal is to use an AI agent to make part of my daily life a little easier. 

## Quick Start

### 1. Setup

```bash
# Clone and setup
git clone <your-repo>
cd agentmail

# Create virtual environment and install dependencies
make setup

# Copy environment template and configure
cp env.example .env
# Edit .env with your email and OpenAI credentials
```

### 2. Configure Gmail

For Gmail, you'll need to:
1. Enable IMAP in your Gmail settings
2. Enable 2-factor authentication
3. Generate an App Password (not your regular password)
4. Use the App Password in your `.env` file

### 3. Run the Application

```bash
# Start the API server
make dev
# or
./run.sh

# In another terminal, start the email poller
python -m src.jobs.poll
```

### 4. Access the Web Interface

Open http://localhost:8000 in your browser to see the email dashboard.

## Configuration

Edit your `.env` file with the following settings:

```env
# Email Configuration
IMAP_HOST=imap.gmail.com
IMAP_USER=you@gmail.com
IMAP_PASS=your_app_password
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASS=your_app_password

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key
MODEL_NAME=gpt-4o-mini

# Application Settings
POLL_INTERVAL_SECONDS=120
DB_URL=sqlite:///./email_agent.db
FROM_DISPLAY="Your Name"
DEFAULT_SIGNATURE="\n\n— Your Name"
```

## API Endpoints

- `GET /` - Web dashboard
- `GET /health` - Health check
- `GET /stats` - Email statistics
- `GET /inbox?filter=needs_reply` - List emails with filtering
- `GET /email/{id}` - Get email details with AI analysis
- `POST /drafts/{id}/approve` - Approve and send a draft reply
- `POST /email/{id}/reclassify` - Force reclassification
- `POST /poll` - Manually trigger email fetch

## Architecture

```
src/
├── app.py              # FastAPI application
├── config.py           # Configuration management
├── models.py           # SQLAlchemy database models
├── imap_client.py      # Email fetching via IMAP
├── smtp_client.py      # Email sending via SMTP
├── llm.py              # OpenAI API wrapper
├── pipeline.py         # Email processing orchestration
├── rules.py            # Heuristic classification rules
├── utils.py            # Utility functions
└── jobs/
    └── poll.py         # Background email polling job