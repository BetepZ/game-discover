import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth import hash_password, verify_password
from app.database import get_conn, init_db
from app.recommender import get_user_data, load_recommender

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
PER_PAGE = 24
N_GENRES = 30
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")


@asynccontextmanager
async def lifespan(app):
    init_db()
    rec = load_recommender()
    app.state.rec = rec
    app.state.pop_order = np.argsort(-rec.pop).tolist()
    counts = {}
    for s in rec.games["tags"].fillna(""):
        for t in s.split("|"):
            if t:
                counts[t] = counts.get(t, 0) + 1
    app.state.genres = [t for t, _ in sorted(counts.items(), key=lambda x: -x[1])[:N_GENRES]]
    yield


app = FastAPI(title="Game Discover", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
    max_age=7 * 24 * 3600,
)
(BASE / "static").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


# ---------- util ----------
class NotAuthenticated(Exception):
    pass


@app.exception_handler(NotAuthenticated)
async def _not_auth(request: Request, exc: NotAuthenticated):
    if request.method == "POST" and request.url.path.startswith("/library"):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    return RedirectResponse("/login", status_code=303)


def db():
    conn = get_conn()
    try:
        yield conn
    finally:
        conn.close()


def current_user(request: Request, conn=Depends(db)):
    uid = request.session.get("user_id")
    row = None
    if uid:
        row = conn.execute(
            "SELECT user_id, username, favorite_genres FROM users WHERE user_id=?", (uid,)
        ).fetchone()
    if not row:
        request.session.clear()
        raise NotAuthenticated()
    return dict(row)


def render(request: Request, name: str, ctx: dict, status: int = 200):
    """Render template; bila template belum ada (sebelum Fase 5) kembalikan JSON."""
    if (BASE / "templates" / name).exists():
        return templates.TemplateResponse(request, name, ctx, status_code=status)
    return JSONResponse({"template": name, **ctx}, status_code=status)


def fetch_games(conn, ids, full=False):
    if not ids:
        return []
    q = ",".join("?" * len(ids))
    rows = conn.execute(
        "SELECT game_id, title, tags, description, release_date, price, positive_ratio, image_url "
        f"FROM games WHERE game_id IN ({q})", list(ids)
    ).fetchall()
    by_id = {}
    for r in rows:
        g = {k: (None if isinstance(v, float) and v != v else v) for k, v in dict(r).items()}
        g["tag_list"] = [t for t in (g["tags"] or "").split("|") if t][:6]
        if not full:
            g["description"] = (g["description"] or "")[:140]
        by_id[g["game_id"]] = g
    return [by_id[i] for i in ids if i in by_id]


# ---------- auth ----------
@app.get("/register")
def register_page(request: Request):
    return render(request, "register.html", {"error": None})


@app.post("/register")
def register(request: Request, username: str = Form(...), password: str = Form(...),
             conn=Depends(db)):
    username = username.strip()
    err = None
    if not USERNAME_RE.match(username):
        err = "Username 3-30 karakter: huruf, angka, underscore."
    elif len(password) < 6:
        err = "Password minimal 6 karakter."
    elif conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
        err = "Username sudah dipakai."
    if err:
        return render(request, "register.html", {"error": err}, 400)
    cur = conn.execute("INSERT INTO users(username, password_hash) VALUES (?, ?)",
                       (username, hash_password(password)))
    conn.commit()
    request.session["user_id"] = cur.lastrowid
    return RedirectResponse("/onboarding", status_code=303)


@app.get("/login")
def login_page(request: Request):
    return render(request, "login.html", {"error": None})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...),
          conn=Depends(db)):
    row = conn.execute("SELECT user_id, password_hash FROM users WHERE username=?",
                       (username.strip(),)).fetchone()
    if not row or not verify_password(password, row["password_hash"]):
        return render(request, "login.html", {"error": "Username atau password salah."}, 401)
    request.session["user_id"] = row["user_id"]
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/onboarding")
def onboarding_page(request: Request, user=Depends(current_user)):
    return render(request, "onboarding.html", {
        "user": user, "genres": request.app.state.genres,
        "selected": [g for g in (user["favorite_genres"] or "").split("|") if g],
        "error": None})


@app.post("/onboarding")
def onboarding(request: Request, genres: list[str] = Form([]),
               user=Depends(current_user), conn=Depends(db)):
    valid = [g for g in genres if g in request.app.state.genres]
    if not 3 <= len(valid) <= 5:
        return render(request, "onboarding.html", {
            "user": user, "genres": request.app.state.genres, "selected": valid,
            "error": "Pilih 3-5 genre."}, 400)
    conn.execute("UPDATE users SET favorite_genres=? WHERE user_id=?",
                 ("|".join(valid), user["user_id"]))
    conn.commit()
    return RedirectResponse("/", status_code=303)


# ---------- halaman utama ----------
@app.get("/")
def home(request: Request, q: str = "", tag: str = "", page: int = 1,
         user=Depends(current_user), conn=Depends(db)):
    ur, owned, genres = get_user_data(conn, user["user_id"])
    if not genres and not owned:
        return RedirectResponse("/onboarding", status_code=303)

    rec = request.app.state.rec
    mask = np.ones(len(rec.games), dtype=bool)
    if q:
        mask &= rec.games["title"].str.contains(q, case=False, regex=False).to_numpy()
    if tag:
        mask &= rec.games["tags"].fillna("").apply(lambda s: tag in s.split("|")).to_numpy()
    pos = [i for i in request.app.state.pop_order if mask[i]]
    pages = max(1, -(-len(pos) // PER_PAGE))
    page = min(max(page, 1), pages)
    ids = [int(rec.gids[i]) for i in pos[(page - 1) * PER_PAGE: page * PER_PAGE]]

    rec_ids = rec.recommend_for(ur, genres, owned, k=12)
    return render(request, "home.html", {
        "user": user,
        "games": fetch_games(conn, ids),
        "recommended": fetch_games(conn, rec_ids),
        "owned_ids": sorted(owned),
        "q": q, "tag": tag, "page": page, "pages": pages, "total": len(pos),
        "genres": request.app.state.genres})


@app.get("/game/{game_id}")
def detail(game_id: int, request: Request, user=Depends(current_user), conn=Depends(db)):
    g = fetch_games(conn, [game_id], full=True)
    if not g:
        raise HTTPException(404, "Game tidak ditemukan")
    rec = request.app.state.rec
    similar = fetch_games(conn, rec.similar_games(game_id, 6)) if game_id in rec.idx else []
    row = conn.execute("SELECT rating FROM library WHERE user_id=? AND game_id=?",
                       (user["user_id"], game_id)).fetchone()
    return render(request, "detail.html", {
        "user": user, "game": g[0], "similar": similar,
        "in_library": row is not None, "my_rating": row["rating"] if row else None})


@app.get("/library")
def library(request: Request, user=Depends(current_user), conn=Depends(db)):
    rows = conn.execute(
        "SELECT g.game_id, g.title, g.image_url, g.tags, g.price, l.rating, l.added_at "
        "FROM library l JOIN games g ON g.game_id = l.game_id "
        "WHERE l.user_id=? ORDER BY l.added_at DESC, g.title", (user["user_id"],)).fetchall()
    items = []
    for r in rows:
        d = {k: (None if isinstance(v, float) and v != v else v) for k, v in dict(r).items()}
        d["tag_list"] = [t for t in (d["tags"] or "").split("|") if t][:4]
        items.append(d)
    return render(request, "library.html", {"user": user, "items": items})


# ---------- aksi (JSON, dipanggil JS fetch) ----------
@app.post("/library/add/{game_id}")
def add_to_library(game_id: int, user=Depends(current_user), conn=Depends(db)):
    if not conn.execute("SELECT 1 FROM games WHERE game_id=?", (game_id,)).fetchone():
        return JSONResponse({"ok": False, "error": "Game tidak ditemukan"}, status_code=404)
    conn.execute("INSERT OR IGNORE INTO library(user_id, game_id) VALUES (?, ?)",
                 (user["user_id"], game_id))
    conn.commit()
    return {"ok": True, "in_library": True}


@app.post("/library/rate/{game_id}")
def rate_game(game_id: int, rating: int = Form(...),
              user=Depends(current_user), conn=Depends(db)):
    if not 1 <= rating <= 5:
        return JSONResponse({"ok": False, "error": "Rating harus 1-5"}, status_code=400)
    cur = conn.execute("UPDATE library SET rating=? WHERE user_id=? AND game_id=?",
                       (rating, user["user_id"], game_id))
    conn.commit()
    if cur.rowcount == 0:
        return JSONResponse({"ok": False, "error": "Tambahkan ke library dulu"}, status_code=404)
    return {"ok": True, "rating": rating}
