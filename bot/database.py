import json
from pathlib import Path
import aiosqlite
from bot.config import settings

CREATE_SQL = '''
CREATE TABLE IF NOT EXISTS loads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER,
    trip_number TEXT,
    reference_number TEXT,
    data_json TEXT NOT NULL,
    original_text TEXT NOT NULL
);
'''

async def init_db():
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(settings.database_path) as db:
        await db.execute(CREATE_SQL)
        await db.commit()

async def save_load(user_id: int, load: dict) -> int:
    async with aiosqlite.connect(settings.database_path) as db:
        cursor = await db.execute(
            "INSERT INTO loads (user_id, trip_number, reference_number, data_json, original_text) VALUES (?, ?, ?, ?, ?)",
            (user_id, load.get("trip_number"), load.get("reference_number"),
             json.dumps(load, ensure_ascii=False), load.get("original_text", ""))
        )
        await db.commit()
        return cursor.lastrowid

async def latest_loads(limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT id, created_at, data_json FROM loads ORDER BY id DESC LIMIT ?", (limit,))
        rows = await cur.fetchall()
    result = []
    for row in rows:
        data = json.loads(row["data_json"])
        data["_id"] = row["id"]
        data["_created_at"] = row["created_at"]
        result.append(data)
    return result

async def search_loads(query: str, limit: int = 10) -> list[dict]:
    like = f"%{query}%"
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, created_at, data_json FROM loads WHERE trip_number LIKE ? OR reference_number LIKE ? ORDER BY id DESC LIMIT ?",
            (like, like, limit)
        )
        rows = await cur.fetchall()
    result = []
    for row in rows:
        data = json.loads(row["data_json"])
        data["_id"] = row["id"]
        data["_created_at"] = row["created_at"]
        result.append(data)
    return result
