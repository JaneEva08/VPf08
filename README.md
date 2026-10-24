# Книжный магазин: MCP-сервер + Telegram-бот

Домашнее задание VPf08 «MCP (Model Context Protocol)». Базовый проект `product-mcp` из урока адаптирован под
предметную область **книжный магазин** и расширен.

**Как это работает.** `mcp_server` — HTTP-сервер (FastAPI + SQLite), который хранит каталог из 100 тестовых книг и
публикует инструменты в формате MCP JSON Schema (`name`, `description`, `inputSchema`). `telegram_bot` при старте
сам запрашивает список инструментов у сервера, передаёт их модели OpenAI (function calling) и, когда модель решает
вызвать инструмент, делает HTTP-запрос к MCP-серверу и подставляет результат в ответ. Бот хранит историю диалога
(последние 20 сообщений), поэтому понимает «эта книга» и «а похожие?», а при непонятном запросе задаёт уточняющий вопрос.

## Что изменено относительно урока
- Домен: `products` → таблица `books` (`id, title, author, genre, price`), 100 книг, 6 жанров.
- Новые инструменты: поиск по ID, жанру и автору, `update_price`, `delete_book`, `get_stats`, постраничный `list_books`.
- Бот берёт список инструментов у сервера динамически: новый инструмент достаточно описать в `tools.py`.
- Контекст диалога, команда `/reset`, нарезка длинных ответов под лимит Telegram.
- Дополнительно сервер понимает JSON-RPC 2.0 на `POST /mcp` (`initialize`, `tools/list`, `tools/call`).

## Инструменты
| Инструмент | Что делает |
|---|---|
| `list_books(limit, offset)` | список книг и общее количество |
| `find_book(title)` | поиск по части названия |
| `find_book_by_id(book_id)` | поиск по ID |
| `find_books_by_genre(genre)` | поиск по жанру |
| `find_books_by_author(author)` | поиск по автору |
| `add_book(title, author, genre, price)` | добавить книгу |
| `update_price(book_id, price)` | изменить цену |
| `delete_book(book_id)` | удалить книгу |
| `get_stats()` | статистика и разбивка по жанрам |
| `calculate(expression)` | калькулятор на `ast`, без `eval` |

## Структура
```
mcp_server/   server.py (FastAPI), db.py (SQLite), tools.py (инструменты, safe_eval), requirements.txt
telegram_bot/ bot.py, config.py (.env), mcp_client.py, requirements.txt
.env.example
```

## Запуск
1. Установить зависимости (лучше в отдельных venv):
   ```
   cd mcp_server && pip install -r requirements.txt
   cd ../telegram_bot && pip install -r requirements.txt
   ```
2. Создать `telegram_bot/.env` по образцу `.env.example` (`TELEGRAM_API_TOKEN` от @BotFather, `OPENAI_API_KEY`).
3. Запустить MCP-сервер (создаст `books.db` и заполнит его при первом запуске): `cd mcp_server && python server.py`
4. В другом терминале запустить бота: `cd telegram_bot && python bot.py`
5. В Telegram: `/start`, затем например «покажи фантастику», «найди книги автора Волков», «покажи книгу 5»,
   «добавь книгу Мастер и Маргарита, Булгаков, роман, 450», «сколько будет 3 книги по 450 со скидкой 10%?».

Проверка сервера без бота: `curl localhost:8000/tools` и
`curl -X POST localhost:8000/call -H 'content-type: application/json' -d '{"name":"get_stats","arguments":{}}'`.
