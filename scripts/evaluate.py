import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from app.database import get_conn
from app.recommender import Recommender

K, TEST_USERS, HOLDOUT = 10, 300, 0.2
rng = np.random.default_rng(42)

with get_conn() as conn:
    games = pd.read_sql("SELECT game_id, title, tags, positive_ratio FROM games", conn)
    ratings = pd.read_sql("SELECT user_id, game_id, rating FROM seed_ratings", conn)

cnt = ratings["user_id"].value_counts()
eligible = cnt[cnt >= 10].index.to_numpy()
test_users = rng.choice(eligible, size=min(TEST_USERS, len(eligible)), replace=False)

test_mask = pd.Series(False, index=ratings.index)
for u, grp in ratings[ratings["user_id"].isin(test_users)].groupby("user_id"):
    n = max(2, int(len(grp) * HOLDOUT))
    test_mask.loc[rng.choice(grp.index.to_numpy(), size=n, replace=False)] = True
train, test = ratings[~test_mask], ratings[test_mask]


def to_dict(df):
    d = {}
    for u, g, r in df[["user_id", "game_id", "rating"]].itertuples(index=False):
        d.setdefault(u, {})[g] = r
    return d


tr, te = to_dict(train), to_dict(test)
rec = Recommender(games, train)

err, base = [], []
res = {m: [] for m in ("pop", "cb", "cf", "hybrid")}
for u in test_users:
    ur, held = tr[u], te[u]
    pred = rec._cf_scores(ur)
    for g, r in held.items():
        err.append(pred[rec.idx[g]] - r)
        base.append(rec.global_mean - r)
    rel = {g for g, r in held.items() if r >= 4}
    if not rel:
        continue
    for m in res:
        hit = len(rel & set(rec.recommend_for(ur, k=K, mode=m)))
        res[m].append((hit / K, hit / len(rel)))

err, base = np.array(err), np.array(base)
print(f"Train: {len(train)} | Test: {len(test)} | Test users: {len(test_users)}")
print(f"CF       RMSE {np.sqrt((err**2).mean()):.4f} | MAE {np.abs(err).mean():.4f}")
print(f"Baseline RMSE {np.sqrt((base**2).mean()):.4f} | MAE {np.abs(base).mean():.4f}  (rata-rata global)")
for m, v in res.items():
    a = np.array(v)
    print(f"{m:7s} Precision@{K} {a[:,0].mean():.4f} | Recall@{K} {a[:,1].mean():.4f}")
