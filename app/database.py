import sqlite3

DB_PATH = "gamediscover.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    game_id INTEGER PRIMARY KEY,
    title TEXT, tags TEXT, description TEXT,
    release_date TEXT, price REAL, positive_ratio INTEGER, image_url TEXT
);
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    favorite_genres TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS library (
    user_id INTEGER NOT NULL,
    game_id INTEGER NOT NULL,
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    added_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, game_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (game_id) REFERENCES games(game_id)
);
CREATE TABLE IF NOT EXISTS seed_ratings (
    user_id INTEGER NOT NULL,
    game_id INTEGER NOT NULL,
    rating INTEGER NOT NULL,
    PRIMARY KEY (user_id, game_id)
);
CREATE INDEX IF NOT EXISTS idx_seed_game ON seed_ratings(game_id);
CREATE INDEX IF NOT EXISTS idx_library_user ON library(user_id);
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
