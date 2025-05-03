import uvicorn
import os
import sys
from fastapi.staticfiles import StaticFiles

# Ensure the parent directory (project root) is in the path
# so that 'discordbot' can be imported by the API
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the FastAPI app instance and settings AFTER adjusting path
from dashboard_api.main import app
from dashboard_api.config import settings

# Mount the static files directory (frontend)
# This assumes the 'dashboard_web' directory is inside 'discordbot'
# Adjust the path if the structure is different.
frontend_path = os.path.join(os.path.dirname(__file__), '..', 'discordbot', 'dashboard_web')

if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")
    print(f"Serving static files from: {frontend_path}")
else:
    print(f"Warning: Frontend directory not found at {frontend_path}. Static file serving disabled.")


if __name__ == "__main__":
    print(f"Starting Dashboard API server on {settings.API_HOST}:{settings.API_PORT}")
    uvicorn.run(
        "dashboard_api.main:app", # Reference the app instance correctly
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True # Enable auto-reload for development
        # Add SSL key/cert paths here if needed for HTTPS directly with uvicorn
        # ssl_keyfile=settings.SSL_KEY_FILE,
        # ssl_certfile=settings.SSL_CERT_FILE,
    )
