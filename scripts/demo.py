import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.recommender import load_recommender

r = load_recommender()
t = r.games.set_index("game_id")["title"]
print("Cold-start:", t.loc[r.recommend_for({}, genres="Action|RPG", k=5)].tolist())
g = int(r.gids[0])
print("Game:", t.loc[g])
print("Similar:", t.loc[r.similar_games(g, k=5)].tolist())
