import os
import logging

logger = logging.getLogger(__name__)

def load_env():
    """
    Load environment variables from a .env file for local development.
    Skips on Railway/containers and stays quiet if the file is missing.
    """
    if os.environ.get("RAILWAY_ENVIRONMENT"):
        # Deployed: env vars are injected by the platform.
        return

    try:
        path = ".env"
        if not os.path.exists(path):
            # Quietly skip to avoid noisy warnings
            return
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip().strip('"').strip("'")
                os.environ[key] = value
        logger.info("Loaded .env file.")
    except Exception as e:
        logger.info(f"Skipping .env load: {e}")

def get_database_url() -> str:
    return os.environ.get("DATABASE_URL", "")