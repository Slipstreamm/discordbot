from flask import Flask, request, abort
import os
import hmac
import hashlib
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

GITHUB_SECRET = os.getenv("GITHUB_SECRET").encode()
app = Flask(__name__)

def verify_signature(payload, signature):
    mac = hmac.new(GITHUB_SECRET, payload, hashlib.sha256)
    expected = "sha256=" + mac.hexdigest()
    return hmac.compare_digest(expected, signature)

@app.route("/github-webhook-123", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Hub-Signature-256")
    if not signature or not verify_signature(request.data, signature):
        abort(403)

    # Placeholder for reload_script logic
    print("Webhook received and verified.")
    return "OK"

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)