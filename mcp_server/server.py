"""MCP-сервер книжного магазина (product-mcp): FastAPI + SQLite.

Эндпоинты:
  GET  /health  - проверка работоспособности
  GET  /tools   - список инструментов в формате MCP JSON Schema
  POST /call    - вызов инструмента: {"name": "...", "arguments": {...}}
  POST /mcp     - JSON-RPC 2.0 (initialize, tools/list, tools/call)
"""
import json
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import db
from tools import MCP_TOOLS, ToolError, call_tool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("product-mcp")

@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    if db.populate_test_data():
        log.info("База пуста: добавлено 100 тестовых книг")
    else:
        log.info("В базе уже есть данные, заполнение пропущено")
    yield


app = FastAPI(title="product-mcp", version="1.0.0", lifespan=lifespan)


class CallRequest(BaseModel):
    name: str
    arguments: dict = Field(default_factory=dict)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/tools")
def list_tools() -> dict:
    return {"tools": MCP_TOOLS}


@app.post("/call")
def call(request: CallRequest) -> dict:
    log.info("call %s %s", request.name, request.arguments)
    try:
        return {"result": call_tool(request.name, request.arguments)}
    except ToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/mcp")
def mcp_rpc(request: dict) -> dict:
    """Минимальная реализация MCP поверх JSON-RPC 2.0."""
    req_id, method, params = request.get("id"), request.get("method"), request.get("params") or {}
    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "product-mcp", "version": "1.0.0"},
            }
        elif method == "tools/list":
            result = {"tools": MCP_TOOLS}
        elif method == "tools/call":
            try:
                data = call_tool(params.get("name", ""), params.get("arguments"))
                result = {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]}
            except ToolError as exc:
                result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        else:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}
    except Exception as exc:  # noqa: BLE001 - JSON-RPC должен всегда вернуть ответ
        log.exception("Ошибка обработки %s", method)
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": str(exc)}}
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


if __name__ == "__main__":
    print("MCP Server запущен на http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
