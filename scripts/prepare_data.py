import pandas as pd

RAW, OUT = "data/raw/", "data/processed/"
N_GAMES, N_USERS, MIN_INTER = 2000, 5000, 5

# Pass 1: hitung jumlah review per game (chunked)
counts = pd.Series(dtype="int64")
for ch in pd.read_csv(RAW + "recommendations.csv", usecols=["app_id"], chunksize=2_000_000):
    counts = counts.add(ch["app_id"].value_counts(), fill_value=0)
top_games = set(counts.nlargest(N_GAMES).index.astype(int))

# Pass 2: filter game top + subset user (user_id % 200 == 0)
parts = []
cols = ["app_id", "user_id", "is_recommended", "hours"]
for ch in pd.read_csv(RAW + "recommendations.csv", usecols=cols, chunksize=2_000_000):
    ch = ch[ch["app_id"].isin(top_games) & (ch["user_id"] % 200 == 0)]
    parts.append(ch)
df = pd.concat(parts, ignore_index=True)
df = df.drop_duplicates(["user_id", "app_id"])

# Filter user aktif, lalu sampling
uc = df["user_id"].value_counts()
active = uc[uc >= MIN_INTER].index
active = pd.Series(active).sample(min(N_USERS, len(active)), random_state=42)
df = df[df["user_id"].isin(active)]

# Konversi ke rating 1-5


def to_rating(row):
    h, rec = row["hours"], row["is_recommended"]
    if rec:
        return 3 if h < 2 else (4 if h < 20 else 5)
    return 1 if h < 2 else 2


df["rating"] = df.apply(to_rating, axis=1)
ratings = df[["user_id", "app_id", "rating"]].rename(
    columns={"app_id": "game_id"})

# Metadata game
games = pd.read_csv(RAW + "games.csv")
games = games[games["app_id"].isin(ratings["game_id"].unique())]
meta = pd.read_json(RAW + "games_metadata.json", lines=True)
meta["tags"] = meta["tags"].apply(
    lambda t: "|".join(t) if isinstance(t, list) else "")
games = games.merge(
    meta[["app_id", "description", "tags"]], on="app_id", how="left")
games = games.rename(columns={
                     "app_id": "game_id", "price_final": "price", "date_release": "release_date"})
games["description"] = games["description"].fillna("")
games["tags"] = games["tags"].fillna("")
games["image_url"] = games["game_id"].apply(
    lambda i: f"https://cdn.akamai.steamstatic.com/steam/apps/{i}/header.jpg")
games = games[["game_id", "title", "tags", "description",
               "release_date", "price", "positive_ratio", "image_url"]]

games.to_csv(OUT + "games.csv", index=False)
ratings.to_csv(OUT + "ratings.csv", index=False)
print("games:", len(games), "| ratings:", len(ratings),
      "| users:", ratings["user_id"].nunique())
