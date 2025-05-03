import os
import uvicorn
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get configuration from environment variables
host = os.getenv("API_HOST", "0.0.0.0")
port = int(os.getenv("API_PORT", "8000"))
data_dir = os.getenv("DATA_DIR", "data")

# Create data directory if it doesn't exist
os.makedirs(data_dir, exist_ok=True)

if __name__ == "__main__":
    print(f"Starting API server on {host}:{port}")
    print(f"Data directory: {data_dir}")
    uvicorn.run("api_server:app", host=host, port=port, reload=True)
