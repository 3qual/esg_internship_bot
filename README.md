# ESG Stazher Bot 🤖

Telegram-бот «ESG-стажировка» — интерактивная обучающая игра по ESG-терминологии.

## Быстрый старт

### 1. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 2. Токен бота
Открой `config.py` и замени строку:
```python
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
```
на токен, который выдал @BotFather.

### 3. Запуск
```bash
python bot.py
```

## Структура проекта
```
esg_bot/
├── bot.py              # Точка входа
├── config.py           # Токен и настройки
├── database.py         # SQLite, все запросы
├── handlers/
│   ├── start.py        # /start, анкета
│   ├── days.py         # Дни 1–5, FSM
│   └── quiz.py         # Финальный тест
├── content/
│   ├── day1.py         # Контент дня 1 ✅
│   ├── day2.py         # TODO
│   ├── day3.py         # TODO
│   ├── day4.py         # TODO
│   ├── day5.py         # TODO
│   └── final_quiz.py   # 27 вопросов ✅
└── utils/
    ├── keyboards.py    # Inline-клавиатуры
    ├── gender.py       # Склонение по полу
    └── rating_calc.py  # Логика рейтинга
```

## Добавление медиафайлов
В коде все места под медиа помечены комментарием `# TODO: media`.
Когда файлы будут готовы:
1. Положи файл в папку `media/`
2. Замени в нужном шаге `send_message` на `send_voice` / `send_video`
3. Передай `FSInputFile("media/имя_файла.ogg")`

## Деплой на VPS
Рекомендуемые параметры сервера: 1 vCPU, 512 MB RAM, Ubuntu 22.04.
Подойдёт любой VPS от ~$3/мес (Timeweb, Selectel, Beget и др.)

```bash
# На сервере
git clone <repo>
cd esg_bot
pip install -r requirements.txt
# Вписать токен в config.py
nohup python bot.py &   # или через systemd/supervisor
```
