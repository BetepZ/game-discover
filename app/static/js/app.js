async function post(url, data) {
  const opt = { method: "POST" };
  if (data) opt.body = new URLSearchParams(data);
  const res = await fetch(url, opt);
  if (res.status === 401) { window.location.href = "/login"; return null; }
  return res.json();
}

document.addEventListener("click", async (e) => {
  // Add to Library
  const add = e.target.closest("[data-add]");
  if (add) {
    add.disabled = true;
    const r = await post("/library/add/" + add.dataset.add);
    if (r && r.ok) {
      add.outerHTML = '<a href="/library" class="btn btn-success btn-lg">✓ In Library</a>';
    } else {
      add.disabled = false;
      alert((r && r.error) || "Gagal menambahkan game.");
    }
    return;
  }

  // Rating bintang
  const star = e.target.closest("[data-rate]");
  if (star) {
    const box = star.closest(".stars");
    const n = parseInt(star.dataset.rate, 10);
    const r = await post("/library/rate/" + box.dataset.game, { rating: n });
    if (r && r.ok) {
      box.querySelectorAll(".star").forEach((s) =>
        s.classList.toggle("active", parseInt(s.dataset.rate, 10) <= n));
      const txt = box.parentElement.querySelector(".rating-text");
      if (txt) txt.textContent = "Rating: " + n + "/5";
    } else {
      alert((r && r.error) || "Gagal menyimpan rating.");
    }
  }
});

// Onboarding: maksimal 5 genre
const genreBoxes = document.querySelectorAll('input[name="genres"]');
if (genreBoxes.length) {
  const counter = document.getElementById("genre-count");
  const countChecked = () => document.querySelectorAll('input[name="genres"]:checked').length;
  genreBoxes.forEach((cb) => cb.addEventListener("change", () => {
    if (countChecked() > 5) { cb.checked = false; alert("Maksimal 5 genre."); }
    if (counter) counter.textContent = countChecked();
  }));
  if (counter) counter.textContent = countChecked();
}
