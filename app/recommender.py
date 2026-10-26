import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize

MIN_RATINGS_HYBRID = 5   # di bawah ini: content-based saja (cold-start)
ALPHA = 0.5              # bobot CB pada hybrid

SHRINK = 10   # peredam similarity untuk overlap kecil
DAMP = 1.0    # peredam prediksi rating
BETA = 0.3    # bobot popularitas


def _tok(s):
    return [t for t in s.split("|") if t]


class Recommender:
    def __init__(self, games, ratings):
        self.games = games.reset_index(drop=True)
        self.gids = self.games["game_id"].to_numpy()
        self.idx = {g: i for i, g in enumerate(self.gids)}
        self.quality = self.games["positive_ratio"].fillna(
            0).to_numpy() / 100.0

        # Content-based: TF-IDF pada tags
        self.vec = TfidfVectorizer(
            tokenizer=_tok, lowercase=False, token_pattern=None)
        self.X = self.vec.fit_transform(self.games["tags"].fillna(""))
        self.cb_sim = cosine_similarity(self.X).astype(np.float32)

        # Collaborative: item-based, rating dipusatkan per user
        r = ratings[ratings["game_id"].isin(self.idx)].drop_duplicates([
            "user_id", "game_id"])
        _, u_idx = np.unique(r["user_id"], return_inverse=True)
        i_idx = r["game_id"].map(self.idx).to_numpy()
        vals = r["rating"].to_numpy(dtype=np.float32)
        umean = np.bincount(u_idx, weights=vals) / np.bincount(u_idx)
        M = csr_matrix((vals - umean[u_idx], (u_idx, i_idx)),
                       shape=(u_idx.max() + 1, len(self.gids)))

        B = csr_matrix((np.ones(len(vals), dtype=np.float32),
                       (u_idx, i_idx)), shape=M.shape)
        C = (B.T @ B).toarray()
        sim = cosine_similarity(M.T).astype(np.float32)
        sim *= C / (C + SHRINK)
        np.fill_diagonal(sim, 0)
        self.cf_sim = np.clip(sim, 0, None)
        self.global_mean = float(vals.mean())
        pop = np.bincount(i_idx[vals >= 4], minlength=len(
            self.gids)).astype(np.float32)
        self.pop = np.log1p(pop) / np.log1p(pop).max()

    def _cb_scores(self, ur, genres):
        prof = None
        if ur:
            ids = [self.idx[g] for g in ur if g in self.idx]
            w = np.array([max(ur[self.gids[i]] - 2, 0) for i in ids], dtype=np.float32)
            if w.sum() > 0:
                prof = normalize(csr_matrix(w) @ self.X[ids])
        if genres:
            gv = normalize(self.vec.transform([genres]))
            prof = gv if prof is None else normalize(prof + 0.5 * gv)
        if prof is None:
            return np.zeros(len(self.gids), dtype=np.float32)
        return cosine_similarity(prof, self.X).ravel()

    def _cf_scores(self, ur):
        ids = [self.idx[g] for g in ur if g in self.idx]
        if not ids:
            return np.full(len(self.gids), self.global_mean, dtype=np.float32)
        r = np.array([ur[self.gids[i]] for i in ids], dtype=np.float32)
        S = self.cf_sim[:, ids]
        return (S @ r + DAMP * self.global_mean) / (S.sum(1) + DAMP)

    def _cf_rank(self, ur):
        ids = [self.idx[g] for g in ur if g in self.idx]
        if not ids:
            return np.zeros(len(self.gids), dtype=np.float32)
        w = np.array([max(ur[self.gids[i]] - 2, 0)
                     for i in ids], dtype=np.float32)
        s = self.cf_sim[:, ids] @ w
        return s / s.max() if s.max() > 0 else s

    def recommend_for(self, ur, genres="", owned=None, k=12, mode="auto"):
        """ur: {game_id: rating}; genres: 'Action|RPG'; mode: auto|cb|cf|hybrid"""
        owned = set(owned or ()) | set(ur)
        if mode == "auto":
            mode = "hybrid" if len(ur) >= MIN_RATINGS_HYBRID else "cb"

        cb = self._cb_scores(ur, genres)
        if mode == "pop":
            score = self.pop
        elif mode == "cb":
            score = cb + BETA * self.pop
        else:
            cf = self._cf_rank(ur)
            score = cf if mode == "cf" else ALPHA * cb + (1 - ALPHA) * cf
            score = score + BETA * self.pop
        score = score + 0.05 * self.quality
        for g in owned:
            if g in self.idx:
                score[self.idx[g]] = -np.inf
        return [int(self.gids[i]) for i in np.argsort(-score)[:k]]

    def similar_games(self, game_id, k=6):
        i = self.idx[game_id]
        s = self.cb_sim[i] + 0.5 * self.cf_sim[i]
        s[i] = -1
        return [int(self.gids[j]) for j in np.argsort(-s)[:k]]


def load_recommender():
    from app.database import get_conn
    with get_conn() as conn:
        games = pd.read_sql(
            "SELECT game_id, title, tags, positive_ratio FROM games", conn)
        seed = pd.read_sql(
            "SELECT user_id, game_id, rating FROM seed_ratings", conn)
        lib = pd.read_sql(
            "SELECT user_id, game_id, rating FROM library WHERE rating IS NOT NULL", conn)
    lib["user_id"] = -lib["user_id"]   # hindari bentrok id dengan user dataset
    return Recommender(games, pd.concat([seed, lib], ignore_index=True))


def get_user_data(conn, user_id):
    rows = conn.execute(
        "SELECT game_id, rating FROM library WHERE user_id=?", (user_id,)).fetchall()
    ur = {r["game_id"]: r["rating"] for r in rows if r["rating"]}
    owned = {r["game_id"] for r in rows}
    row = conn.execute(
        "SELECT favorite_genres FROM users WHERE user_id=?", (user_id,)).fetchone()
    return ur, owned, (row["favorite_genres"] if row else "")
