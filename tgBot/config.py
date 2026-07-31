import os
import sys

from dotenv import load_dotenv

load_dotenv()

REQUIRED_VARS = [
    "BOT_TOKEN",
    "ALLOWED_USER_ID",
    "WEBHOOK_SECRET",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REFRESH_TOKEN",
    "GDRIVE_ROOT_FOLDER_ID",
]

_missing = [name for name in REQUIRED_VARS if not os.environ.get(name)]
if _missing:
    sys.exit(
        "Missing required environment variables: "
        + ", ".join(_missing)
        + ". Copy .env.example to .env and fill in the values."
    )

BOT_TOKEN = os.environ["BOT_TOKEN"]
ALLOWED_USER_ID = int(os.environ["ALLOWED_USER_ID"])
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]

GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
GOOGLE_REFRESH_TOKEN = os.environ["GOOGLE_REFRESH_TOKEN"]
GDRIVE_ROOT_FOLDER_ID = os.environ["GDRIVE_ROOT_FOLDER_ID"]

PORT = int(os.environ.get("PORT", "8080"))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")

WEBHOOK_PATH = "/webhook"
