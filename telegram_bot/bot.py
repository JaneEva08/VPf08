"""Telegram-бот: сообщение -> LLM -> (вызов MCP-инструмента) -> LLM -> ответ."""
import asyncio
import json
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from openai import AsyncOpenAI

import mcp_client
from config import (HISTORY_LIMIT, MAX_TOOL_ROUNDS, OPENAI_API_KEY, OPENAI_MODEL,
                    SYSTEM_PROMPT, TELEGRAM_API_TOKEN)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

llm = AsyncOpenAI(api_key=OPENAI_API_KEY)
dp = Dispatcher()

# История диалога по chat_id (в памяти процесса)
histories: dict[int, list[dict]] = {}
openai_tools: list[dict] = []

WELCOME = (
    "👋 Привет! Я помощник книжного магазина.\n\n"
    "Я умею:\n"
    "• показывать каталог и искать книги по названию, автору, жанру или ID\n"
    "• добавлять, удалять книги и менять цены\n"
    "• показывать статистику каталога\n"
    "• считать (например, сумму заказа)\n\n"
    "Примеры:\n"
    "— «покажи фантастику»\n"
    "— «найди книги автора Волков»\n"
    "— «добавь книгу Мастер и Маргарита, Булгаков, роман, 450»\n"
    "— «сколько стоят 3 книги по 450 со скидкой 10%?»\n\n"
    "/reset — забыть историю диалога."
)


def trim(history: list[dict]) -> list[dict]:
    """Оставляет последние сообщения, не обрывая пары tool_calls/tool в начале."""
    history = history[-HISTORY_LIMIT:]
    while history and history[0]["role"] != "user":
        history = history[1:]
    return history


async def answer(chat_id: int, text: str) -> str:
    history = histories.setdefault(chat_id, [])
    history.append({"role": "user", "content": text})

    for _ in range(MAX_TOOL_ROUNDS + 1):
        response = await llm.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, *history],
            tools=openai_tools,
        )
        message = response.choices[0].message
        if not message.tool_calls:
            reply = message.content or "Не удалось получить ответ, попробуйте переформулировать."
            history.append({"role": "assistant", "content": reply})
            histories[chat_id] = trim(history)
            return reply

        history.append(message.model_dump(exclude_none=True))
        for call in message.tool_calls:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            log.info("Вызов MCP-инструмента: %s %s", call.function.name, arguments)
            result = await mcp_client.call_tool(call.function.name, arguments)
            history.append({"role": "tool", "tool_call_id": call.id, "content": result[:8000]})

    histories[chat_id] = trim(history)
    return "Не получилось выполнить запрос за разумное число шагов. Попробуйте уточнить его."


async def send_long(message: Message, text: str) -> None:
    """Telegram ограничивает сообщение 4096 символами — режем по строкам."""
    chunk = ""
    for line in text.split("\n"):
        if len(chunk) + len(line) + 1 > 4000:
            await message.answer(chunk)
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        await message.answer(chunk)


@dp.message(Command("start"))
async def on_start(message: Message) -> None:
    histories.pop(message.chat.id, None)
    await message.answer(WELCOME)


@dp.message(Command("reset"))
async def on_reset(message: Message) -> None:
    histories.pop(message.chat.id, None)
    await message.answer("История диалога очищена.")


@dp.message()
async def on_message(message: Message) -> None:
    if not message.text:
        await message.answer("Я понимаю только текстовые сообщения.")
        return
    status = await message.answer("Обрабатываю запрос...")
    try:
        reply = await answer(message.chat.id, message.text)
    except Exception:  # noqa: BLE001 - пользователю нужен понятный ответ при любой ошибке
        log.exception("Ошибка обработки сообщения")
        histories.pop(message.chat.id, None)
        reply = "Произошла ошибка при обработке запроса. Проверьте, что MCP-сервер запущен, и попробуйте ещё раз."
    await status.delete()
    await send_long(message, reply)


async def main() -> None:
    global openai_tools
    openai_tools = mcp_client.to_openai_tools(await mcp_client.list_tools())
    log.info("Загружено MCP-инструментов: %d", len(openai_tools))
    print("Telegram бот запущен...")
    await dp.start_polling(Bot(token=TELEGRAM_API_TOKEN))


if __name__ == "__main__":
    asyncio.run(main())
