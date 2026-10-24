"""MCP-инструменты: описание в формате JSON Schema, обработчики и безопасный калькулятор."""
import ast
import operator

import db


class ToolError(Exception):
    """Ошибка вызова инструмента (неверные аргументы, ничего не найдено и т.п.)."""


# ---------- Безопасный калькулятор (без eval) ----------

_BIN_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_MAX_POWER = 1000


def safe_eval(expression: str) -> float:
    """Вычисляет арифметическое выражение через разбор AST. Допустимы только числа и + - * / // % **."""
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ToolError(f"Некорректное выражение: {expression!r}") from exc

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > _MAX_POWER:
                raise ToolError("Слишком большая степень")
            try:
                return _BIN_OPS[type(node.op)](left, right)
            except ZeroDivisionError as exc:
                raise ToolError("Деление на ноль") from exc
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
            return _UNARY_OPS[type(node.op)](walk(node.operand))
        raise ToolError("Разрешены только числа и операции + - * / // % **")

    return walk(tree)


# ---------- Описание инструментов (MCP JSON Schema) ----------

def _schema(properties: dict | None = None, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties or {}, "required": required or []}


MCP_TOOLS = [
    {
        "name": "list_books",
        "description": "Возвращает список книг с постраничной выдачей и общее количество книг в магазине",
        "inputSchema": _schema({
            "limit": {"type": "integer", "description": "Сколько книг вернуть (по умолчанию 20, максимум 100)"},
            "offset": {"type": "integer", "description": "Сколько книг пропустить (по умолчанию 0)"},
        }),
    },
    {
        "name": "find_book",
        "description": "Ищет книги по части названия (без учёта регистра)",
        "inputSchema": _schema({"title": {"type": "string", "description": "Часть названия книги"}}, ["title"]),
    },
    {
        "name": "find_book_by_id",
        "description": "Находит книгу по её номеру (ID)",
        "inputSchema": _schema({"book_id": {"type": "integer", "description": "ID книги"}}, ["book_id"]),
    },
    {
        "name": "find_books_by_genre",
        "description": "Ищет книги по жанру. Жанры: Фантастика, Детектив, Роман, Научпоп, Программирование, Детям",
        "inputSchema": _schema({"genre": {"type": "string", "description": "Название жанра"}}, ["genre"]),
    },
    {
        "name": "find_books_by_author",
        "description": "Ищет книги по автору (часть имени)",
        "inputSchema": _schema({"author": {"type": "string", "description": "Имя автора или его часть"}}, ["author"]),
    },
    {
        "name": "add_book",
        "description": "Добавляет новую книгу в каталог",
        "inputSchema": _schema({
            "title": {"type": "string", "description": "Название книги"},
            "author": {"type": "string", "description": "Автор"},
            "genre": {"type": "string", "description": "Жанр"},
            "price": {"type": "number", "description": "Цена в рублях"},
        }, ["title", "author", "genre", "price"]),
    },
    {
        "name": "update_price",
        "description": "Меняет цену книги по её ID",
        "inputSchema": _schema({
            "book_id": {"type": "integer", "description": "ID книги"},
            "price": {"type": "number", "description": "Новая цена в рублях"},
        }, ["book_id", "price"]),
    },
    {
        "name": "delete_book",
        "description": "Удаляет книгу из каталога по ID",
        "inputSchema": _schema({"book_id": {"type": "integer", "description": "ID книги"}}, ["book_id"]),
    },
    {
        "name": "get_stats",
        "description": "Статистика каталога: число книг, средняя/минимальная/максимальная цена и разбивка по жанрам",
        "inputSchema": _schema(),
    },
    {
        "name": "calculate",
        "description": "Безопасный калькулятор для арифметических выражений (+ - * / // % **)",
        "inputSchema": _schema({"expression": {"type": "string", "description": "Выражение, например 2+2*3"}},
                               ["expression"]),
    },
]


# ---------- Обработчики ----------

def _require(args: dict, name: str, kind):
    """Достаёт обязательный аргумент и приводит его к нужному типу."""
    if name not in args or args[name] in (None, ""):
        raise ToolError(f"Не указан параметр '{name}'")
    try:
        value = kind(args[name])
    except (TypeError, ValueError) as exc:
        raise ToolError(f"Параметр '{name}' имеет неверный тип") from exc
    if kind is str:
        value = value.strip()
        if not value:
            raise ToolError(f"Параметр '{name}' не должен быть пустым")
    return value


def _positive_price(args: dict) -> float:
    price = _require(args, "price", float)
    if price < 0:
        raise ToolError("Цена не может быть отрицательной")
    return price


def _found(items: list[dict]) -> dict:
    return {"count": len(items), "books": items}


def _list_books(args: dict) -> dict:
    limit = max(1, min(int(args.get("limit") or 20), 100))
    offset = max(0, int(args.get("offset") or 0))
    return db.list_books(limit, offset)


def _find_book_by_id(args: dict) -> dict:
    book = db.find_by_id(_require(args, "book_id", int))
    if book is None:
        raise ToolError(f"Книга с ID {args['book_id']} не найдена")
    return book


def _update_price(args: dict) -> dict:
    book = db.update_price(_require(args, "book_id", int), _positive_price(args))
    if book is None:
        raise ToolError(f"Книга с ID {args['book_id']} не найдена")
    return book


def _delete_book(args: dict) -> dict:
    book = db.delete_book(_require(args, "book_id", int))
    if book is None:
        raise ToolError(f"Книга с ID {args['book_id']} не найдена")
    return {"deleted": book}


HANDLERS = {
    "list_books": _list_books,
    "find_book": lambda a: _found(db.find_by_title(_require(a, "title", str))),
    "find_book_by_id": _find_book_by_id,
    "find_books_by_genre": lambda a: _found(db.find_by_genre(_require(a, "genre", str))),
    "find_books_by_author": lambda a: _found(db.find_by_author(_require(a, "author", str))),
    "add_book": lambda a: db.add_book(
        _require(a, "title", str), _require(a, "author", str), _require(a, "genre", str), _positive_price(a)),
    "update_price": _update_price,
    "delete_book": _delete_book,
    "get_stats": lambda a: db.get_stats(),
    "calculate": lambda a: {"expression": a.get("expression"), "result": safe_eval(_require(a, "expression", str))},
}


def call_tool(name: str, arguments: dict | None) -> dict:
    handler = HANDLERS.get(name)
    if handler is None:
        raise ToolError(f"Неизвестный инструмент: {name}")
    return handler(arguments or {})
