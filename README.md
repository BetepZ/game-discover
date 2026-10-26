# Game Discover

Prototipe website rekomendasi game digital (mirip Steam) untuk tugas mata kuliah Sistem Rekomendasi.

## Fitur
- Register / Login (username + password, session cookie) dan onboarding pilih 3-5 genre favorit
- Home: katalog game (pencarian, filter genre, pagination) dan bagian "Recommended for You"
- Detail Game: info game, tombol "Add to Library", daftar "Game Serupa"
- My Library: game yang dimiliki dan rating bintang 1-5

## Tech Stack
Python 3.11, FastAPI, Jinja2, SQLite, Pandas, Scikit-learn, Bootstrap 5 (CDN), JavaScript vanilla.

## Sistem Rekomendasi
- Content-based: TF-IDF pada tags game + cosine similarity. Dipakai untuk cold-start (rating user < 5) dari genre favorit.
- Collaborative filtering: item-based, rating dipusatkan per user, similarity diredam (shrinkage) untuk overlap kecil.
- Hybrid: skor = 0.5 x content-based + 0.5 x collaborative, ditambah bobot popularitas kecil. Aktif bila user punya minimal 5 rating.
- Similar Games: kombinasi similarity content-based dan collaborative.

## Dataset
Kaggle "Game Recommendations on Steam" (antonkozyriev), di-sampling menjadi 1.994 game, 5.000 user, 52.293 rating.
Rating 1-5 diturunkan dari kolom is_recommended dan jam bermain. Dataset tidak punya kolom genre, sehingga tags dipakai sebagai genre.

## Struktur Proyek
    app/            main.py, auth.py, database.py, recommender.py, templates/, static/
    scripts/        prepare_data.py, seed_db.py, evaluate.py, demo.py, smoke_ui.py
    data/raw/       file dataset Kaggle (tidak di-commit)
    data/processed/ hasil prepare_data.py

## Cara Menjalankan
    conda create -n game-discover python=3.11 -y
    conda activate game-discover
    pip install -r requirements.txt

    # data/processed/ sudah disertakan, langsung seed database
    python scripts/seed_db.py
    uvicorn app.main:app --reload

    # (opsional) bangun ulang data dari Kaggle:
    # mkdir -p data/raw, taruh games.csv, games_metadata.json, recommendations.csv di sana,
    # lalu jalankan: python scripts/prepare_data.py

Buka http://127.0.0.1:8000

## Pengujian
    python scripts/evaluate.py    # evaluasi model (RMSE/MAE, Precision@10, Recall@10)
    python scripts/smoke_ui.py    # uji end-to-end seluruh halaman dan rute

## Hasil Evaluasi (300 user uji, 20% rating disembunyikan)
| Metode | Precision@10 | Recall@10 |
|---|---|---|
| Popularitas (baseline) | 0.0159 | 0.0562 |
| Content-based | 0.0138 | 0.0537 |
| Collaborative | 0.0179 | 0.0628 |
| Hybrid | 0.0162 | 0.0646 |

Prediksi rating: CF RMSE 1.1815 / MAE 0.8940 (baseline rata-rata global 1.1856 / 0.8983).

## Keterbatasan
- Data jarang (sekitar 10 rating per user) sehingga keunggulan atas baseline popularitas kecil.
- Rating dataset diturunkan dari jam main dan rekomendasi, bukan rating eksplisit.
- Matriks similarity collaborative dilatih saat server start. Rating baru dari user web langsung memengaruhi rekomendasi user itu sendiri, tetapi baru masuk ke model collaborative setelah server di-restart.
- Dengan sedikit rating, rekomendasi cenderung didominasi game yang mirip dengan game yang baru dirating (kurang beragam).
- Prototipe: SECRET_KEY default hanya untuk pengembangan. Set variabel lingkungan SECRET_KEY untuk penggunaan nyata.
