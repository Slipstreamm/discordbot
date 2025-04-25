from flask import Flask, request, abort
import os
import hmac
import hashlib
import subprocess
import psutil
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

GITHUB_SECRET = os.getenv("GITHUB_SECRET").encode()
app = Flask(__name__)

def verify_signature(payload, signature):
    mac = hmac.new(GITHUB_SECRET, payload, hashlib.sha256)
    expected = "sha256=" + mac.hexdigest()
    return hmac.compare_digest(expected, signature)

def kill_main_process():
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        if proc.info['cmdline'] and 'main.py' in proc.info['cmdline']:
            print(f"Killing process {proc.info['pid']} running main.py")
            proc.terminate()
            proc.wait()

@app.route("/github-webhook-123", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Hub-Signature-256")
    if not signature or not verify_signature(request.data, signature):
        abort(404) # If its a 404, nobody will suspect theres a real endpoint here

    # Restart main.py logic
    print("Webhook received and verified. Restarting bot...")
    kill_main_process()
    subprocess.Popen(["python", "main.py"], cwd=os.path.dirname(__file__))
    return "Bot restarting."

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)