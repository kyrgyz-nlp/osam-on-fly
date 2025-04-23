import os
from dotenv import load_dotenv
from fastapi import FastAPI, Security, HTTPException, status
from fastapi.security import APIKeyHeader
from osam._server import app as original_app

# Load environment variables from a `.env` file if it exists in the current working directory.
# This is primarily useful for local development when running the script directly 
# (e.g., `python main.py`), allowing you to manage secrets/configs without setting
# system environment variables. 
# NOTE: When running this application inside a Docker container, environment variables
# are typically injected using `docker run --env-file .env` (preferred) or `docker run -e VAR=value`, 
# and this call might not find a `.env` file unless explicitly copied into the image (not recommended).
load_dotenv()

API_KEY = os.environ.get("API_KEY")
API_KEY_NAME = "X-API-Key"
APP_ENV = os.environ.get("APP_ENV", "production") # Default to production

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    """Dependency function to validate the API key."""
    if not API_KEY:
        if APP_ENV == "development":
            print("Warning: API_KEY environment variable not set. Authentication bypassed in development mode.")
            return # Bypass check in development if key is not set
        else:
            # Strictly enforce key presence in production (or any other env)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="API Key not configured on the server. Set API_KEY environment variable."
            )

    if not api_key_header:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Missing API Key"
        )
    if api_key_header != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Invalid API Key"
        )
    return api_key_header

# Create the main FastAPI app with the security dependency
app = FastAPI(dependencies=[Security(get_api_key)])

# Mount the original application
app.mount("/", original_app)
