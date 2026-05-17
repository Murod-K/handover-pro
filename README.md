# Handover Pro Bot 🏗

Telegram бот для передачи смены на строительной площадке.

## Деплой на Render

### 1. Firebase Service Account
1. Firebase Console → Project Settings → Service Accounts
2. Generate new private key → скачать JSON
3. Из JSON скопировать значения в переменные Render (см. ниже)

### 2. Переменные окружения в Render Dashboard

| Переменная | Откуда брать |
|---|---|
| `BOT_TOKEN` | @BotFather в Telegram |
| `OPENAI_API_KEY` | platform.openai.com |
| `FIREBASE_PRIVATE_KEY_ID` | Firebase SA JSON → `private_key_id` |
| `FIREBASE_PRIVATE_KEY` | Firebase SA JSON → `private_key` (с переносами как `\n`) |
| `FIREBASE_CLIENT_EMAIL` | Firebase SA JSON → `client_email` |
| `FIREBASE_CLIENT_ID` | Firebase SA JSON → `client_id` |
| `FIREBASE_CERT_URL` | Firebase SA JSON → `client_x509_cert_url` |

### 3. Mini App в BotFather
1. @BotFather → /newapp или /mybots → выбрать бота → Bot Menu Button
2. URL: `https://handover-pro-bot.onrender.com/app`

### 4. Firebase Rules
В Firebase Realtime Database → Rules:
```json
{
  "rules": {
    ".read": true,
    ".write": true
  }
}
```
(для продакшена настроить аутентификацию)

## Локальный запуск

```bash
cp .env.example .env
# заполнить .env

pip install -r requirements.txt
python main.py
```

## Структура данных Firebase

### /users/{id}
```json
{
  "telegram_id": 123456789,
  "name": "Расулов А.Б.",
  "role": "engineer",
  "shift_type": "day"
}
```

### /shifts/{id}
```json
{
  "engineer_id": "...",
  "engineer_name": "...",
  "object_name": "ЖК Tashkent City",
  "block": "Б-1",
  "floor": "5",
  "shift_type": "day",
  "status": "open",
  "created_at": "2025-01-15T08:00:00",
  "constructions": [...],
  "photos": [...],
  "warnings": [...]
}
```

## Команды бота
- `/start` — главное меню
- `/smena` — создать смену (текст или голос)
- `/history` — последние 5 смен
- `/status` — открытые смены
- `/report [ID]` — HTML отчёт

## AI флоу
Пользователь пишет: `Колонны К-1 К-2 К-3, арматура сдана, бетон 45 кубов насосом`
→ GPT-4o парсит в JSON конструкций
→ Бот показывает превью с inline кнопками
→ Подтверждение → запись в Firebase
