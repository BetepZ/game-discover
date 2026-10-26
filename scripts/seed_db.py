import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from app.database import get_conn, init_db

init_db()
games = pd.read_csv("data/processed/games.csv")
ratings = pd.read_csv("data/processed/ratings.csv")

with get_conn() as conn:
    conn.execute("DELETE FROM games")
    conn.execute("DELETE FROM seed_ratings")
    games.to_sql("games", conn, if_exists="append", index=False)
    ratings.to_sql("seed_ratings", conn, if_exists="append", index=False)
    print("games:", conn.execute("SELECT COUNT(*) FROM games").fetchone()[0])
    print("seed_ratings:", conn.execute("SELECT COUNT(*) FROM seed_ratings").fetchone()[0])
