import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_conn

name = f"ui_{random.randint(1000, 9999)}"

with TestClient(app) as c:
    assert "Login" in c.get("/login").text
    assert "Buat Akun" in c.get("/register").text

    r = c.post("/register", data={"username": name, "password": "rahasia123"})
    assert "Pilih genre favoritmu" in r.text
    print("1. login/register/onboarding render OK")

    genres = app.state.genres[:4]
    r = c.post("/onboarding", data={"genres": genres})
    assert "Recommended for You" in r.text and "Katalog Game" in r.text
    print("2. home render OK")

    gid = app.state.rec.recommend_for({}, "|".join(genres), k=1)[0]
    r = c.get(f"/game/{gid}")
    assert "Add to Library" in r.text and "Game Serupa" in r.text
    print("3. detail render OK")

    assert c.post(f"/library/add/{gid}").json()["ok"]
    assert c.post(f"/library/rate/{gid}", data={"rating": 4}).json()["ok"]
    r = c.get("/library")
    assert "My Library" in r.text and f'data-game="{gid}"' in r.text and "Rating: 4/5" in r.text
    print("4. library render OK")

    assert c.get("/static/css/style.css").status_code == 200
    assert c.get("/static/js/app.js").status_code == 200
    print("5. static OK")

with get_conn() as conn:
    conn.execute("DELETE FROM library WHERE user_id IN (SELECT user_id FROM users WHERE username=?)", (name,))
    conn.execute("DELETE FROM users WHERE username=?", (name,))
    conn.commit()
print("SMOKE TEST LULUS (data tester dibersihkan)")
