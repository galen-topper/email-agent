#!/usr/bin/env python3
"""
Setup script for Email Agent MVP
"""

import os
import sys
import subprocess
import shutil

def run_command(cmd, description):
    """Run a command and handle errors."""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e}")
        print(f"Error output: {e.stderr}")
        return False

def main():
    """Main setup function."""
    print("🚀 Setting up Email Agent MVP...")
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        sys.exit(1)
    
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} detected")
    
    # Use Python 3.11 if available for better compatibility
    python_cmd = "python3.11" if sys.version_info >= (3, 11) else "python3"
    
    # Create virtual environment
    if not os.path.exists(".venv"):
        if not run_command(f"{python_cmd} -m venv .venv", "Creating virtual environment"):
            sys.exit(1)
    else:
        print("✅ Virtual environment already exists")
    
    # Install dependencies
    if not run_command(".venv/bin/pip install -r requirements.txt", "Installing dependencies"):
        sys.exit(1)
    
    # Create .env file if it doesn't exist
    if not os.path.exists(".env"):
        if os.path.exists("env.example"):
            shutil.copy("env.example", ".env")
            print("✅ Created .env file from template")
            print("⚠️  Please edit .env file with your email and OpenAI credentials")
        else:
            print("❌ env.example file not found")
            sys.exit(1)
    else:
        print("✅ .env file already exists")
    
    # Create necessary directories
    os.makedirs("raw", exist_ok=True)
    print("✅ Created raw directory for email storage")
    
    print("\n🎉 Setup complete!")
    print("\nNext steps:")
    print("1. Edit .env file with your email and OpenAI credentials")
    print("2. Run 'make dev' to start the API server")
    print("3. In another terminal, run 'python -m src.jobs.poll' to start email polling")
    print("4. Open http://localhost:8000 in your browser")

if __name__ == "__main__":
    main()
