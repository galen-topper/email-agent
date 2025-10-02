#!/bin/bash
# Start the Email Agent API server

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Start the FastAPI server
uvicorn src.app:app --reload --host 0.0.0.0 --port 8000

