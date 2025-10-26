import os
import re
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def load_env():
    """
    Load environment variables from a .env file.
    """
    try:
        with open('.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Remove quotes if present
                        if (value.startswith('"') and value.endswith('"')) or \
                           (value.startswith("'") and value.endswith("'")):
                            value = value[1:-1]
                            
                        os.environ[key] = value
                        
    except FileNotFoundError:
        logger.warning(".env file not found - using existing environment variables.")
    except Exception as e:
        logger.error(f"Error loading .env file: {e}")

def get_database_url() -> str:
    """
    Get the database URL from the DATABASE_URL environment variable.
    Returns an empty string if not configured.
    """
    return os.environ.get('DATABASE_URL', '')