# AgentMail

Hey guys, this is Galen. This is a little portfolio project that I built to assist myself in my daily life. This handles emails through a priority system, making replying easy. The goal is to use an AI agent to make part of my daily life a little easier. 

<img width="1434" height="676" alt="Screenshot 2025-10-21 at 7 07 04 PM" src="https://github.com/user-attachments/assets/4bb90c73-72f1-4edd-acb2-1d3c30416010" />
(Emails are blocked out since I'd rather not leak my whole inbox to the general public)

## APP IS STILL IN DEVELOPMENT AND NOT AVAILABLE FOR PUBLIC USE, MESSAGE ME @ gtopper@stanford.edu if you want access

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
```
