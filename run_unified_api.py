import os
import sys
import threading
import uvicorn
from dotenv import load_dotenv

# Add the api_service directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'api_service'))

# Load environment variables
load_dotenv()

# Get configuration from environment variables
api_host = os.getenv("API_HOST", "0.0.0.0")
api_port = int(os.getenv("API_PORT", "443"))

# Set SSL certificate paths
ssl_cert = os.getenv("SSL_CERT_FILE", "/etc/letsencrypt/live/slipstreamm.dev/fullchain.pem")
ssl_key = os.getenv("SSL_KEY_FILE", "/etc/letsencrypt/live/slipstreamm.dev/privkey.pem")

def run_unified_api():
    """Run the unified API service"""
    try:
        print(f"Starting unified API service on {api_host}:{api_port}")

        # Check if SSL certificates exist and are configured
        ssl_available = ssl_cert and ssl_key and os.path.exists(ssl_cert) and os.path.exists(ssl_key)

        if ssl_available:
            print(f"Using SSL with certificates at {ssl_cert} and {ssl_key}")
            uvicorn.run(
                "api_server:app",
                host=api_host,
                port=api_port,
                log_level="debug", # Increase log level
                ssl_certfile=ssl_cert,
                ssl_keyfile=ssl_key
            )
        else:
            print("SSL certificates not found or not configured. Starting without SSL (development mode)")
            uvicorn.run(
                "api_server:app",
                host=api_host,
                port=api_port,
                log_level="debug" # Increase log level
            )
    except Exception as e:
        print(f"Error starting unified API service: {e}")

def start_api_in_thread():
    """Start the unified API service in a separate thread"""
    api_thread = threading.Thread(target=run_unified_api)
    api_thread.daemon = True
    api_thread.start()
    print("Unified API service started in background thread")
    return api_thread

if __name__ == "__main__":
    # Run the API directly if this script is executed
    run_unified_api()
