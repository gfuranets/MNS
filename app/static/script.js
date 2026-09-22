/* script.js - the dashboard page. Requires auth.js to be loaded first. */

if (requireLogin()) {
  loadProfile();
  wireNavigation();
  wireMockForms();
}

/* Ask the API who we are. A 401 here means the token expired - auth.js's
   logOut() sends the user back to the login page. */
async function loadProfile() {
  try {
    const user = await api("/api/me");

    document.getElementById("avatar").textContent =
      (user.name[0] + user.surname[0]).toUpperCase();
    document.getElementById("welcome-title").textContent =
      `Welcome back, ${user.name}`;
  } catch {
    logOut();
  }
}

function wireNavigation() {
  const show = (pageId) => {
    document.querySelectorAll(".page").forEach((page) =>
      page.classList.toggle("active", page.id === pageId)
    );
    document.querySelectorAll(".nav-btn").forEach((button) =>
      button.classList.toggle("active", button.dataset.page === pageId)
    );
    document.getElementById("page-title").textContent =
      document.querySelector(`.nav-btn[data-page="${pageId}"]`).textContent.trim();
  };

  document.querySelectorAll(".nav-btn").forEach((button) =>
    button.addEventListener("click", () => show(button.dataset.page))
  );
  document.querySelectorAll(".card[data-open]").forEach((card) =>
    card.addEventListener("click", () => show(card.dataset.open))
  );

  document.getElementById("logout-btn").addEventListener("click", logOut);
}

/* The profile, records and vaccination forms are still mockups - there are no
   tables behind them yet. Say so plainly instead of failing silently. */
function wireMockForms() {
  const notReady = (event) => {
    event.preventDefault();
    window.alert("Not connected yet - this feature comes after the user system.");
  };

  document.getElementById("profile-form").addEventListener("submit", notReady);
  document.getElementById("vaccine-form").addEventListener("submit", notReady);
  document.getElementById("upload-btn").addEventListener("click", notReady);
}
