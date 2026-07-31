"""
Разовый локальный скрипт для получения GOOGLE_REFRESH_TOKEN.

Требует GOOGLE_CLIENT_ID и GOOGLE_CLIENT_SECRET в .env (см. .env.example
и README.md, раздел про Google Cloud Console). Не деплоится вместе с ботом,
запускается один раз локально.
"""

import os

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

# Полный доступ к Drive нужен, т.к. бот работает с папкой, созданной
# пользователем вручную (не самим приложением) — узкий scope "drive.file"
# не дал бы доступа к уже существующей папке.
SCOPES = ["https://www.googleapis.com/auth/drive"]


def main() -> None:
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit(
            "Задайте GOOGLE_CLIENT_ID и GOOGLE_CLIENT_SECRET в .env перед запуском."
        )

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    if not credentials.refresh_token:
        raise SystemExit(
            "Google не вернул refresh_token. Отзовите доступ приложению в "
            "https://myaccount.google.com/permissions и запустите скрипт снова."
        )

    print("\nGOOGLE_REFRESH_TOKEN=" + credentials.refresh_token)
    print("\nСкопируйте строку выше в .env (локально) и в переменные окружения на Render.")


if __name__ == "__main__":
    main()
