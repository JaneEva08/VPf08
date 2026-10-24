"""HTTP-клиент для MCP-сервера: получение списка инструментов и их вызов."""
import json

import httpx

from config import MCP_SERVER_URL

_TIMEOUT = 15.0


async def list_tools() -> list[dict]:
    """Запрашивает у сервера актуальный список инструментов (MCP JSON Schema)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.get(f"{MCP_SERVER_URL}/tools")
        response.raise_for_status()
        return response.json()["tools"]


async def call_tool(name: str, arguments: dict) -> str:
    """Вызывает инструмент и возвращает ответ строкой JSON (ошибки тоже строкой, чтобы их увидела LLM)."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(f"{MCP_SERVER_URL}/call", json={"name": name, "arguments": arguments})
    except httpx.HTTPError as exc:
        return json.dumps({"error": f"MCP-сервер недоступен: {exc}"}, ensure_ascii=False)
    if response.status_code != 200:
        detail = response.json().get("detail", response.text) if response.content else response.text
        return json.dumps({"error": detail}, ensure_ascii=False)
    return json.dumps(response.json()["result"], ensure_ascii=False)


def to_openai_tools(mcp_tools: list[dict]) -> list[dict]:
    """Преобразует MCP-описание инструментов в формат function calling OpenAI."""
    return [
        {
            "type": "function",
            "function": {"name": t["name"], "description": t["description"], "parameters": t["inputSchema"]},
        }
        for t in mcp_tools
    ]
