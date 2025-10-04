import os
import re
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def load_env():
    """
    Load environment variables from .env file with enhanced database URL handling.
    Supports both direct DATABASE_URL and Supabase individual environment variables.
    """
    try:
        with open('.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Handle both KEY=value and KEY="value with spaces" formats
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Remove quotes if present
                        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                            value = value[1:-1]
                            
                        os.environ[key] = value
        
        # Set default DATABASE_URL if individual Supabase variables are provided
        _setup_database_url()
        
    except FileNotFoundError:
        logger.warning(".env file not found - using existing environment variables")
    except Exception as e:
        logger.error(f"Error loading .env file: {e}")

def _setup_database_url():
    """
    Set up DATABASE_URL environment variable from individual Supabase variables
    if they exist but DATABASE_URL is not set.
    """
    if not os.environ.get('DATABASE_URL'):
        supabase_user = os.environ.get('SUPABASE_DB_USER')
        supabase_password = os.environ.get('SUPABASE_DB_PASSWORD')
        supabase_host = os.environ.get('SUPABASE_DB_HOST')
        supabase_name = os.environ.get('SUPABASE_DB_NAME')
        supabase_port = os.environ.get('SUPABASE_DB_PORT', '5432')
        
        if all([supabase_user, supabase_password, supabase_host, supabase_name]):
            database_url = f"postgresql://{supabase_user}:{supabase_password}@{supabase_host}:{supabase_port}/{supabase_name}"
            os.environ['DATABASE_URL'] = database_url
            logger.info("DATABASE_URL constructed from Supabase environment variables")
        else:
            logger.info("DATABASE_URL not set and Supabase variables incomplete - using SQLite fallback")

def get_database_url() -> str:
    """
    Get the database URL, preferring DATABASE_URL environment variable.
    Returns empty string if no database is configured.
    """
    return os.environ.get('DATABASE_URL', '')