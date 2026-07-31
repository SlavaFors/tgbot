# Fondtale Memory Bot

Личный Telegram-бот: пишете ему текст/фото/голосовое/аудио/видео-кружочек с
хэштегом (`#фраза`, `#спор`, `#смешное`, любой другой) — он сохраняет
запись в ваш Google Drive (markdown-файл + медиа + индекс `index.json`).
Отвечает только владельцу бота, работает через webhook на Render.

## 1. Создать Telegram-бота

1. Откройте [@BotFather](https://t.me/BotFather) в Telegram, отправьте `/newbot`
   и следуйте инструкциям.
2. Скопируйте выданный токен — это `BOT_TOKEN`.

## 2. Узнать свой Telegram user_id

1. Откройте [@userinfobot](https://t.me/userinfobot), отправьте ему любое
   сообщение.
2. Он пришлёт ваш числовой `Id` — это `ALLOWED_USER_ID`. Только сообщения
   от этого ID бот будет обрабатывать, все остальные молча игнорируются.

## 3. Настроить Google Cloud и Drive API

1. Откройте [Google Cloud Console](https://console.cloud.google.com/) →
   создайте новый проект (или выберите существующий).
2. В разделе **APIs & Services → Library** найдите **Google Drive API** и
   нажмите **Enable**.
3. В разделе **APIs & Services → OAuth consent screen**:
   - выберите тип **External**, заполните обязательные поля (имя приложения,
     email);
   - на шаге Scopes ничего добавлять не обязательно;
   - на шаге Test users добавьте свой собственный Google-аккаунт (email, на
     который зарегистрирован Drive, куда будут писаться записи).
4. В разделе **APIs & Services → Credentials** → **Create Credentials →
   OAuth client ID**:
   - тип приложения: **Desktop app**;
   - после создания скопируйте **Client ID** и **Client Secret** — это
     `GOOGLE_CLIENT_ID` и `GOOGLE_CLIENT_SECRET`.

## 4. Получить refresh-токен (один раз, локально)

1. Склонируйте репозиторий, перейдите в `tgBot/`.
2. Скопируйте `.env.example` в `.env`, впишите `GOOGLE_CLIENT_ID` и
   `GOOGLE_CLIENT_SECRET` из шага 3 (остальные поля пока не важны).
3. Установите зависимости:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. Запустите:
   ```bash
   python scripts/get_gdrive_refresh_token.py
   ```
5. Откроется браузер — войдите в тот же Google-аккаунт, что добавили как
   test user на шаге 3, разрешите доступ. Скрипт выведет в консоль строку
   `GOOGLE_REFRESH_TOKEN=...` — впишите её в `.env`.

## 5. Создать папку в Google Drive и получить её ID

1. В [Google Drive](https://drive.google.com) создайте папку, например
   `Fondtale Memories`.
2. Откройте её, скопируйте ID из адресной строки браузера:
   `https://drive.google.com/drive/folders/ЭТОТ_КУСОК_И_ЕСТЬ_ID`
3. Впишите его в `.env` как `GDRIVE_ROOT_FOLDER_ID`.

## 6. Заполнить оставшиеся переменные

В `.env` также впишите:
- `WEBHOOK_SECRET` — любая случайная строка (используется для проверки, что
  запросы на вебхук действительно от Telegram).

## 7. Задеплоить на Render

1. Запушьте репозиторий на GitHub.
2. На [Render](https://render.com) → **New → Web Service**, подключите
   репозиторий.
3. Настройки сервиса:
   - **Root Directory**: `tgBot`
   - **Runtime**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
   - **Plan**: Free
4. В разделе **Environment** добавьте все переменные из `.env` (кроме
   `RENDER_EXTERNAL_URL` и `PORT` — их Render задаёт сам автоматически).
5. Разверните сервис. После первого успешного старта бот сам зарегистрирует
   webhook в Telegram (используя `RENDER_EXTERNAL_URL`, который Render
   передаёт в переменных окружения).

## 8. Проверить, что всё работает

1. Откройте чат со своим ботом в Telegram, отправьте `/start`.
2. Отправьте текст с хэштегом, например `#смешное сказал сегодня "трава невкусная"`.
3. Бот должен ответить `✅ Сохранено под #смешное`.
4. Проверьте папку в Google Drive — там должны появиться `entries/`,
   `media/` (если отправляли фото/голосовое/аудио/видео-кружочек) и
   `index.json` с новой записью.
5. Если сервис на Render "спал" (не было сообщений >15 минут), первый ответ
   может занять до ~60 секунд — это ожидаемое поведение, не ошибка.

## Локальная разработка (без деплоя)

Для быстрой проверки изменений без деплоя на Render можно временно
использовать [ngrok](https://ngrok.com/):

```bash
ngrok http 8080
```

Скопируйте выданный `https://...ngrok...` адрес в `.env` как
`RENDER_EXTERNAL_URL` (без слэша на конце), затем запустите:

```bash
python bot.py
```

и пишите боту как обычно.

## Структура проекта

```
tgBot/
  bot.py       — точка входа: хендлеры сообщений, webhook-сервер
  storage.py   — работа с Google Drive: файлы, папки, index.json
  config.py    — чтение и валидация переменных окружения
  scripts/
    get_gdrive_refresh_token.py — разовое получение refresh-токена
```
