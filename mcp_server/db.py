"""SQLite-слой книжного магазина: подключение, инициализация, тестовые данные и запросы."""
import os
import random
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "books.db")

GENRES = {
    "Фантастика": ["Звёздный дрейф", "Последний рейс", "Город на орбите", "Эхо галактики", "Кибер-сад"],
    "Детектив": ["Тёмная аллея", "Дело о хрустальной вазе", "Ночной свидетель", "Тихий омут", "Улика"],
    "Роман": ["Осенний вальс", "Письма из Венеции", "Дом у реки", "Время сирени", "Зимняя соната"],
    "Научпоп": ["Как устроен мозг", "Квантовый мир", "История вещей", "Математика вокруг", "Биология жизни"],
    "Программирование": ["Python с нуля", "Чистая архитектура API", "Алгоритмы простыми словами", "SQL на практике", "Основы MCP"],
    "Детям": ["Приключения ежа", "Сказки про луну", "Весёлая азбука", "Тайна старого сада", "Лесные друзья"],
}
AUTHORS = [
    "А. Волков", "М. Орлова", "И. Седов", "Е. Громова", "Д. Ларин",
    "О. Киселёва", "П. Румянцев", "Н. Белова", "С. Фролов", "Т. Миронова",
]


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # SQLite сравнивает регистр только для ASCII, поэтому для кириллицы своя lower()
    conn.create_function("py_lower", 1, lambda s: s.lower() if isinstance(s, str) else s)
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                genre TEXT NOT NULL,
                price REAL NOT NULL
            )
            """
        )


def populate_test_data(count: int = 100) -> bool:
    """Заполняет пустую таблицу тестовыми книгами. Возвращает True, если данные добавлены."""
    with get_connection() as conn:
        if conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] > 0:
            return False
        rng = random.Random(42)  # детерминированно: одинаковые данные при каждой инициализации
        rows = []
        for i in range(1, count + 1):
            genre = rng.choice(list(GENRES))
            title = f"{rng.choice(GENRES[genre])} {i}"
            rows.append((title, rng.choice(AUTHORS), genre, round(rng.uniform(150, 1500), 2)))
        conn.executemany("INSERT INTO books (title, author, genre, price) VALUES (?, ?, ?, ?)", rows)
        return True


def _rows(cursor: sqlite3.Cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]


def list_books(limit: int = 20, offset: int = 0) -> dict:
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        books = _rows(conn.execute("SELECT * FROM books ORDER BY id LIMIT ? OFFSET ?", (limit, offset)))
    return {"total": total, "offset": offset, "books": books}


def find_by_title(title: str) -> list[dict]:
    with get_connection() as conn:
        return _rows(conn.execute(
            "SELECT * FROM books WHERE py_lower(title) LIKE ? ORDER BY id", (f"%{title.lower()}%",)))


def find_by_id(book_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        return dict(row) if row else None


def find_by_genre(genre: str) -> list[dict]:
    with get_connection() as conn:
        return _rows(conn.execute(
            "SELECT * FROM books WHERE py_lower(genre) LIKE ? ORDER BY id", (f"%{genre.lower()}%",)))


def find_by_author(author: str) -> list[dict]:
    with get_connection() as conn:
        return _rows(conn.execute(
            "SELECT * FROM books WHERE py_lower(author) LIKE ? ORDER BY id", (f"%{author.lower()}%",)))


def add_book(title: str, author: str, genre: str, price: float) -> dict:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO books (title, author, genre, price) VALUES (?, ?, ?, ?)",
            (title, author, genre, price))
        return {"id": cur.lastrowid, "title": title, "author": author, "genre": genre, "price": price}


def update_price(book_id: int, price: float) -> dict | None:
    with get_connection() as conn:
        cur = conn.execute("UPDATE books SET price = ? WHERE id = ?", (price, book_id))
        if cur.rowcount == 0:
            return None
    return find_by_id(book_id)


def delete_book(book_id: int) -> dict | None:
    book = find_by_id(book_id)
    if book is None:
        return None
    with get_connection() as conn:
        conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
    return book


def get_stats() -> dict:
    with get_connection() as conn:
        total, avg_price, min_price, max_price = conn.execute(
            "SELECT COUNT(*), AVG(price), MIN(price), MAX(price) FROM books").fetchone()
        genres = _rows(conn.execute(
            "SELECT genre, COUNT(*) AS count, ROUND(AVG(price), 2) AS avg_price "
            "FROM books GROUP BY genre ORDER BY count DESC"))
    return {
        "total_books": total,
        "avg_price": round(avg_price, 2) if avg_price is not None else None,
        "min_price": min_price,
        "max_price": max_price,
        "genres": genres,
    }
