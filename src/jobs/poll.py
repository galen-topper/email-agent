#!/usr/bin/env python3
"""
Email polling job - runs continuously to fetch and process new emails.
"""

import time
import logging
import signal
import sys
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ..config import settings
from ..models import Base
from ..imap_client import fetch_unseen_emails
from ..pipeline import process_new_emails
from ..utils import save_email_to_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database setup
engine = create_engine(settings.DB_URL, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
Base.metadata.create_all(engine)

class EmailPoller:
    """Email polling service."""
    
    def __init__(self):
        self.running = True
        self.db = SessionLocal()
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    def poll_once(self):
        """Perform one polling cycle."""
        try:
            logger.info("Starting email poll cycle...")
            
            # Fetch new emails
            def save_callback(email_data):
                save_email_to_db(self.db, email_data)
            
            fetched_emails = fetch_unseen_emails(save_callback)
            logger.info(f"Fetched {len(fetched_emails)} new emails")
            
            # Process new emails
            processed_count = process_new_emails(self.db)
            logger.info(f"Processed {processed_count} emails")
            
            return len(fetched_emails), processed_count
            
        except Exception as e:
            logger.error(f"Error in poll cycle: {e}")
            self.db.rollback()
            return 0, 0
    
    def run(self):
        """Run the polling loop."""
        logger.info(f"Starting email poller (interval: {settings.POLL_INTERVAL_SECONDS}s)")
        
        while self.running:
            try:
                fetched, processed = self.poll_once()
                
                if fetched > 0 or processed > 0:
                    logger.info(f"Poll cycle complete: {fetched} fetched, {processed} processed")
                else:
                    logger.debug("Poll cycle complete: no new emails")
                
                # Wait for next poll
                for _ in range(settings.POLL_INTERVAL_SECONDS):
                    if not self.running:
                        break
                    time.sleep(1)
                    
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt, shutting down...")
                break
            except Exception as e:
                logger.error(f"Unexpected error in polling loop: {e}")
                time.sleep(10)  # Wait a bit before retrying
        
        logger.info("Email poller stopped")
        self.db.close()

def main():
    """Main entry point for the polling job."""
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        # Run once and exit
        poller = EmailPoller()
        fetched, processed = poller.poll_once()
        print(f"Fetched {fetched} emails, processed {processed}")
        poller.db.close()
    else:
        # Run continuously
        poller = EmailPoller()
        poller.run()

if __name__ == "__main__":
    main()
