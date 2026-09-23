/* script.js - the dashboard page. Requires auth.js to be loaded first. */

const MESSAGE_LIMIT = 1000;   // must match NotificationCreate in schema.py

if (requireLogin()) {
  loadProfile();
  wireNavigation();
  wireMockForms();
  wireNotifications();
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

    // The count goes stale as people sign up, so re-read it on every visit.
    if (pageId === "notify") loadRecipients();
  };

  /* [data-page] matters: #logout-btn is also a .nav-btn, and without the
     filter it would try to switch to a page that does not exist. */
  document.querySelectorAll(".nav-btn[data-page]").forEach((button) =>
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

/* --------------------------------------------------------------------------
   send notification

   There is nothing to choose: phone numbers come from signup, so the message
   goes to every user who filled that field in. The page only asks for a body.
   -------------------------------------------------------------------------- */

function wireNotifications() {
  document.getElementById("notify-text")
    .addEventListener("input", updateCharCount);
  document.getElementById("notify-form")
    .addEventListener("submit", sendNotification);

  updateCharCount();
}

async function loadRecipients() {
  const status = document.getElementById("notify-status");

  try {
    const { recipients } = await api("/api/notifications/recipients");
    showRecipientCount(recipients);
    showMessage(status, "");
  } catch (error) {
    showRecipientCount(0, "Could not check who can be reached.");
    showMessage(status, error.message);
  }
}

/* Keeps the hint line and the button label honest about who gets this. */
function showRecipientCount(count, problem) {
  const hint = document.getElementById("notify-count");
  const button = document.getElementById("notify-send");

  if (count === 0) {
    hint.textContent =
      problem || "Nobody has a phone number saved yet, so there is nobody to text.";
    button.textContent = "Send SMS";
    button.disabled = true;
    return;
  }

  hint.textContent =
    count === 1
      ? "1 patient gave a phone number at signup and will receive this."
      : `${count} patients gave a phone number at signup and will receive this.`;
  button.textContent = count === 1 ? "Send to 1 person" : `Send to ${count} people`;
  button.disabled = false;
}

function updateCharCount() {
  const used = document.getElementById("notify-text").value.length;
  document.getElementById("notify-chars").textContent =
    `${MESSAGE_LIMIT - used} characters left`;
}

async function sendNotification(event) {
  event.preventDefault();

  const button = document.getElementById("notify-send");
  const status = document.getElementById("notify-status");
  const text = document.getElementById("notify-text");

  button.disabled = true;
  button.textContent = "Sending...";
  showMessage(status, "");

  try {
    const report = await api("/api/notifications/send", {
      method: "POST",
      body: { message: text.value },
    });

    renderReport(report);
    showMessage(status, summarise(report), report.failed ? "error" : "ok");
    text.value = "";
    updateCharCount();
  } catch (error) {
    showMessage(status, error.message);
  } finally {
    loadRecipients();   // restores the button's label, and re-counts
  }
}

function summarise(report) {
  const parts = [
    report.dry_run ? `${report.sent} logged (dry run)` : `${report.sent} sent`,
  ];
  if (report.skipped) parts.push(`${report.skipped} skipped`);
  if (report.failed) parts.push(`${report.failed} failed`);
  return parts.join(", ");
}

function renderReport(report) {
  const list = document.getElementById("notify-results");
  list.replaceChildren();

  if (report.dry_run) {
    const banner = document.createElement("p");
    banner.className = "dry-banner";
    banner.textContent =
      "Dry run - Twilio is not configured, so nothing actually left the server. " +
      "Set TWILIO_SID, TWILIO_TOKEN and TWILIO_FROM in app/.env to send for real.";
    list.append(banner);
  }

  report.results.forEach((result) => {
    const row = document.createElement("div");
    row.className = "result";

    const pill = document.createElement("span");
    pill.className = `pill ${result.status}`;
    pill.textContent = result.status === "dry_run" ? "dry run" : result.status;

    const who = document.createElement("span");
    who.className = "who";
    who.textContent = result.name;

    const number = document.createElement("span");
    number.className = "num";
    number.textContent = result.phone || "no number";

    row.append(pill, who, number);

    // The Twilio message id is noise; a reason for *not* sending is not.
    if (result.detail && result.status !== "sent") {
      const why = document.createElement("span");
      why.className = "why";
      why.textContent = result.detail;
      row.append(why);
    }

    list.append(row);
  });

  document.getElementById("notify-report").hidden = false;
}
