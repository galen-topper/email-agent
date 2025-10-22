.PHONY: setup dev test clean

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt
	@echo "Setup complete! Copy env.example to .env and configure your settings."

dev:
	.venv/bin/uvicorn src.app:app --reload --host 0.0.0.0 --port 8000

test:
	.venv/bin/pytest tests/ -v

clean:
	rm -rf .venv
	rm -f email_agent.db
	rm -rf raw/
	rm -rf __pycache__/
	rm -rf src/__pycache__/
	rm -rf tests/__pycache__/

