import os
import sys
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

# Ensure the project root directory (containing the 'discordbot' package) is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    print(f"Adding project root to sys.path: {project_root}")
    sys.path.insert(0, project_root)
else:
    print(f"Project root already in sys.path: {project_root}")


if __name__ == "__main__":
    import multiprocessing

    def run_uvicorn(bind_host):
        print(f"Starting API server on {bind_host}:{port}")
        uvicorn.run(
            "discordbot.api_service.api_server:app",
            host=bind_host,
            port=port
        )

    print(f"Data directory: {data_dir}")
    # Start both IPv4 and IPv6 servers
    processes = []
    for bind_host in ["0.0.0.0", "::"]:
        p = multiprocessing.Process(target=run_uvicorn, args=(bind_host,))
        p.start()
        processes.append(p)
    for p in processes:
        p.join()
