/* script.js - the app. Needs i18n.js, icons.js and auth.js loaded first.

   Every screen is a function that fetches what it needs and returns
   { title, back, actions, tab, body }. render() picks the function from the
   URL hash and paints the result. User data only ever reaches the DOM
   through h(), which sets textContent - never innerHTML. */

const $view = document.getElementById("view");
const $top = document.getElementById("topbar");
const $tabs = document.getElementById("tabbar");
const $modal = document.getElementById("modal-root");

const MESSAGE_LIMIT = 1000;   // must match NotificationCreate in schema.py
const CATEGORY_CHOICES = ["appointment", "vaccination", "screening", "checkup", "test", "medication", "other"];
const RISKS = ["cancer", "diabetes", "heart"];
const LEAD_DAYS = [0, 1, 3, 7, 14, 30];
const TABS = [
  ["home", "#/home", "home"], ["schedule", "#/schedule", "calendar"], ["add", "#/add", "plus"],
  ["log", "#/log", "log"], ["info", "#/info", "info"], ["ai", "#/ai", "chat"],
];

let me = null;            // the logged-in user, from /api/me
let renderId = 0;         // drops a slow screen if the user has already moved on
let waitingCount = 0;     // reminders waiting for Accept - the bell badge
const chat = [];          // the AI screen's conversation, kept while the page is open
const dismissed = new Map();   // reminder id -> when "Not now" was pressed
const cal = (() => {
  const d = new Date();
  return { year: d.getFullYear(), month: d.getMonth(), selected: localIso(d) };
})();

/* Our own copy of the in-app history, so "back" never leaves the app and
   redirects (replace) do not count as a step. */
const trail = [];
let replacing = false;

if (requireLogin()) start();

async function start() {
  try {
    me = await api("/api/me");
  } catch {
    return logOut();
  }
  setLang(me.language);
  buildTabbar();
  trail.push(location.hash);
  window.addEventListener("hashchange", () => {
    if (replacing) trail[trail.length - 1] = location.hash;
    else if (trail.length > 1 && trail[trail.length - 2] === location.hash) trail.pop();
    else trail.push(location.hash);
    replacing = false;
    render();
  });
  await render();
  showPendingReminders();
  // "If you ignore it, it keeps reminding": look again every few minutes.
  setInterval(showPendingReminders, 5 * 60 * 1000);
}

/* --------------------------------------------------------------------------
   tiny helpers
   -------------------------------------------------------------------------- */

/* h("a", { class: "row", href: "#/x", onclick: fn }, "text", childNode, [more]) */
function h(tag, props, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (key === "class") el.className = value;
    else if (key in el && typeof value !== "string") el[key] = value;
    else el.setAttribute(key, value === true ? "" : value);
  }
  el.append(...flat(children));
  return el;
}

function flat(children) {
  return [children].flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false);
}

/* replaceChildren that accepts nested arrays and skips null/false, like h(). */
function fill(el, ...children) {
  el.replaceChildren(...flat(children));
}

function go(hash) { location.hash = hash; }

function replace(hash) {
  if (location.hash === hash) return render();
  replacing = true;
  location.replace(hash);
}

function back(fallback) {
  if (trail.length > 1) history.back();
  else replace(fallback);
}

let toastTimer;
function toast(text) {
  const el = document.getElementById("toast");
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
}

function localIso(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
const todayIso = () => localIso(new Date());

/* "2026-09-24T09:00" for <input type="datetime-local"> */
function localDateTime(d) {
  return `${localIso(d)}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

async function saveBlob(res, fallbackName) {
  const blob = await res.blob();
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(res.headers.get("Content-Disposition") || "");
  const a = h("a", { href: URL.createObjectURL(blob), download: match ? decodeURIComponent(match[1]) : fallbackName });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function guard(fn) {
  return async (...args) => {
    try {
      await fn(...args);
    } catch (error) {
      toast(error.message);
    }
  };
}

/* --------------------------------------------------------------------------
   router
   -------------------------------------------------------------------------- */

const ROUTES = [
  [/^\/onboarding\/consent$/, viewConsent],
  [/^\/onboarding\/profile$/, () => viewProfileForm(true)],
  [/^\/home$/, viewHome],
  [/^\/done$/, viewDone],
  [/^\/schedule$/, viewSchedule],
  [/^\/checkup\/(\d+)$/, viewCheckup],
  [/^\/task\/(\d+)$/, viewTask],
  [/^\/add$/, viewAdd],
  [/^\/log$/, viewLog],
  [/^\/info$/, viewInfo],
  [/^\/procedure\/(\d+)$/, viewProcedure],
  [/^\/ai$/, viewAi],
  [/^\/profile$/, viewProfile],
  [/^\/profile\/edit$/, () => viewProfileForm(false)],
  [/^\/profile\/reminders$/, viewReminderSettings],
  [/^\/vaccinations$/, viewPassport],
  [/^\/inbox$/, viewInbox],
  [/^\/privacy$/, viewPrivacy],
  [/^\/broadcast$/, viewBroadcast],
];

async function render() {
  const [path, queryString] = (location.hash.slice(1) || "/home").split("?");
  const query = new URLSearchParams(queryString);

  // Onboarding comes first: consent, then the health profile.
  if (!me.consent_at && path !== "/onboarding/consent") return replace("#/onboarding/consent");
  if (me.consent_at && !me.profile_complete && path !== "/onboarding/profile") {
    return replace("#/onboarding/profile");
  }

  const route = ROUTES.find(([pattern]) => pattern.test(path));
  if (!route) return replace("#/home");
  const params = path.match(route[0]).slice(1);

  const id = ++renderId;
  fill($view, h("p", { class: "loading" }, t("common.loading")));

  let screen;
  try {
    screen = await route[1](...params, query);
  } catch (error) {
    screen = {
      title: t("common.error_title"),
      back: "#/home",
      body: [
        h("p", { class: "message error" }, error.message),
        h("div", { class: "form-foot" }, h("button", { class: "btn outline", onclick: render }, t("common.try_again"))),
      ],
    };
  }
  if (id !== renderId) return;   // the user navigated away while we were loading
  paint(screen);
}

function paint({ title, back: backTo, actions, tab = null, tabs = true, wide = false, body }) {
  const backBtn = backTo && h("button", {
    class: "icon-btn plain", "aria-label": t("common.back"), onclick: () => back(backTo),
  }, icon("back"));

  fill($top, backBtn, h("h1", {}, title), actions === undefined ? topActions() : actions);
  fill($view, body);

  // Home, schedule, log and info use the full width; forms and details stay readable.
  $view.classList.toggle("wide", wide);
  $top.classList.toggle("wide", wide);
  $tabs.hidden = !tabs;
  for (const a of $tabs.querySelectorAll("a")) a.classList.toggle("active", a.dataset.tab === tab);
  document.title = `${title} - ${t("app.name")}`;
  window.scrollTo(0, 0);
}

function buildTabbar() {
  // The brand only shows on wide screens, where the tab bar becomes the top navigation.
  fill($tabs,
    h("a", { class: "brand-link", href: "#/home" }, h("span", { class: "brand-mark" }, icon("heart")), t("app.name")),
    TABS.map(([name, href, iconName]) => h("a",
      { href, "data-tab": name, class: name === "add" ? "add-tab" : null },
      name === "add" ? h("span", { class: "add-disc" }, icon(iconName)) : icon(iconName),
      h("span", {}, t(`nav.${name}`)),
    )));
}

/* The bell (reminders waiting) and the profile icon, top right. */
function topActions() {
  return [
    h("a", { class: "icon-btn", href: "#/inbox", "aria-label": t("nav.inbox"), id: "bell" },
      icon("bell"), waitingCount > 0 && h("span", { class: "badge" }, String(waitingCount))),
    h("a", { class: "icon-btn", href: "#/profile", "aria-label": t("nav.profile") }, icon("user")),
  ];
}

function updateBell() {
  const bell = document.getElementById("bell");
  if (!bell) return;
  bell.querySelector(".badge")?.remove();
  if (waitingCount > 0) bell.append(h("span", { class: "badge" }, String(waitingCount)));
}

/* --------------------------------------------------------------------------
   modal
   -------------------------------------------------------------------------- */

let onModalClose = null;

function openModal(children, { celebrate = false, onClose = null } = {}) {
  onModalClose = onClose;
  const dialog = h("div", { class: `dialog${celebrate ? " celebrate" : ""}`, role: "dialog", "aria-modal": "true" }, children);
  const overlay = h("div", { class: "overlay", onclick: (e) => { if (e.target === overlay) closeModal(); } }, dialog);
  fill($modal, overlay);
  (dialog.querySelector("input, button.primary, button") || dialog).focus();
}

function closeModal() {
  if (!$modal.childElementCount) return;
  fill($modal);
  const after = onModalClose;
  onModalClose = null;
  if (after) after();
}

document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

/* "Great job taking care of yourself!" - shown after anything is marked done. */
function celebrate({ next = null, then = render } = {}) {
  openModal([
    h("div", { class: "seal" }, icon("check")),
    h("h2", {}, t("great.title")),
    h("p", { class: "muted body" }, t("great.logged")),
    next && h("p", { class: "body" }, t("great.next", { date: fmtDate(next) })),
    h("div", { class: "actions" }, h("button", { class: "btn primary", onclick: closeModal }, t("great.ok"))),
  ], { celebrate: true, onClose: then });
}

/* Ask for the date something was done (default today, past allowed). */
function askDate(title) {
  return new Promise((resolve) => {
    let answer = null;
    const input = h("input", { type: "date", required: true, max: todayIso(), value: todayIso() });
    openModal([
      h("h2", {}, title),
      h("div", { class: "body" },
        h("label", { class: "field" }, h("span", {}, t("done.confirm_title")), input),
        h("p", { class: "hint" }, t("done.backdate_hint"))),
      h("div", { class: "actions" },
        h("button", { class: "btn primary", onclick: () => { if (input.value) { answer = input.value; closeModal(); } } },
          t("home.mark_done")),
        h("button", { class: "btn outline", onclick: closeModal }, t("common.cancel"))),
    ], { onClose: () => resolve(answer) });
  });
}

/* --------------------------------------------------------------------------
   marking things done - one path for every screen and the pop-ups
   -------------------------------------------------------------------------- */

async function completeGuideline(checkupId, doneOn = null) {
  await api(`/api/checkups/${checkupId}/done`, { method: "POST", body: { done_on: doneOn } });
}

async function completeEvent(eventId, doneOn = null) {
  const res = await api(`/api/task-events/${eventId}/done`, { method: "POST", body: { done_on: doneOn } });
  return res.next_due;
}

/* Mark a schedule item done; ask for the date first when `ask` is set. */
async function completeItem(item, { ask = false, then = render } = {}) {
  const doneOn = ask ? await askDate(item.name) : null;
  if (ask && !doneOn) return;
  try {
    const next = item.kind === "guideline"
      ? await completeGuideline(item.id, doneOn)
      : await completeEvent(item.id, doneOn);
    celebrate({ next, then });
  } catch (error) {
    toast(error.message);
  }
}

async function completePopup(p, then = render) {
  try {
    let next = null;
    if (p.checkup_type_id) await completeGuideline(p.checkup_type_id);
    else if (p.task_event_id) next = await completeEvent(p.task_event_id);
    else if (p.prep_item_id) {
      await api(`/api/prep-items/${p.prep_item_id}`, { method: "PATCH", body: { checked: true } });
      await api(`/api/notifications/${p.notification_id}/accept`, { method: "POST" });
    }
    celebrate({ next, then });
  } catch (error) {
    toast(error.message);
  }
}

const canComplete = (p) => Boolean(p.checkup_type_id || p.task_event_id || p.prep_item_id);

/* --------------------------------------------------------------------------
   reminder pop-ups: they keep coming back until accepted
   -------------------------------------------------------------------------- */

async function showPendingReminders() {
  if ($modal.childElementCount || !me.profile_complete) return;
  let pending;
  try {
    pending = await api("/api/reminders/pending");
  } catch {
    return;
  }
  waitingCount = pending.length;
  updateBell();
  const now = Date.now();
  const queue = pending.filter((p) => !(dismissed.get(p.notification_id) > now - 30 * 60 * 1000));
  if (queue.length) showReminder(queue, 0);
}

function showReminder(queue, index) {
  const p = queue[index];
  if (!p) return render();
  const next = () => showReminder(queue, index + 1);
  const left = queue.length - index - 1;

  openModal([
    h("h2", {}, t("reminder.title")),
    h("p", { class: "body" }, p.message),
    h("p", { class: "hint" }, t("reminder.later_hint")),
    left > 0 && h("p", { class: "hint" }, t("reminder.more", { n: left })),
    h("div", { class: "actions" },
      h("button", {
        class: "btn primary",
        onclick: guard(async () => {
          await api(`/api/notifications/${p.notification_id}/accept`, { method: "POST" });
          onModalClose = null;
          closeModal();
          next();
        }),
      }, t("home.accept")),
      canComplete(p) && h("button", {
        class: "btn soft",
        onclick: () => { onModalClose = null; closeModal(); completePopup(p, next); },
      }, t("home.mark_done")),
      h("button", { class: "btn outline", onclick: () => closeModal() }, t("reminder.later")),
    ),
  ], {
    onClose: () => { dismissed.set(p.notification_id, Date.now()); next(); },
  });
}

/* --------------------------------------------------------------------------
   shared pieces
   -------------------------------------------------------------------------- */

const statusPill = (status) => h("span", { class: `pill ${status}` }, t(`status.${status}`));
const section = (text) => h("h2", { class: "section" }, text);
const empty = (text, action) => h("div", { class: "empty" }, h("p", {}, text), action && h("div", { class: "form-foot" }, action));
const field = (label, input, hint) => [h("label", { class: "field" }, h("span", {}, label), input), hint && h("p", { class: "hint" }, hint)];
const chev = () => h("span", { class: "chev" }, icon("chevron"));

function itemHref(item) {
  return item.kind === "guideline" ? `#/checkup/${item.id}` : `#/task/${item.task_id}`;
}

function itemRow(item, { showLast = false } = {}) {
  return h("a", { class: "row", href: itemHref(item) },
    h("span", { class: `mark ${item.status}` }),
    h("div", { class: "grow" },
      h("div", { class: "title" }, item.name),
      h("div", { class: "sub" }, whenText(item)),
      showLast && h("div", { class: "sub" },
        item.last_done ? t("when.last", { date: fmtDate(item.last_done) }) : t("when.never")),
    ),
    statusPill(item.status),
    chev(),
  );
}

function list(rows) {
  return h("div", { class: "list" }, rows);
}

function categorySelect(value = "") {
  const known = CATEGORY_CHOICES.includes(value) || value === "";
  const select = h("select", { required: true },
    CATEGORY_CHOICES.map((c) => h("option", { value: c, selected: c === value }, categoryLabel(c))),
    h("option", { value: "__custom", selected: !known }, `${t("done.custom_category")}…`));
  const custom = h("input", { type: "text", maxlength: 40, placeholder: t("done.custom_ph"), value: known ? "" : value, hidden: known });
  select.addEventListener("change", () => { custom.hidden = select.value !== "__custom"; if (!custom.hidden) custom.focus(); });
  return {
    nodes: [h("label", { class: "field" }, h("span", {}, t("done.category")), select), custom],
    select,
    value: () => (select.value === "__custom" ? custom.value.trim() : select.value),
  };
}

function consentList() {
  const pairs = ["what", "why", "who", "control", "advice"];
  return h("dl", { class: "consent" }, pairs.map((k) => [h("dt", {}, t(`consent.${k}_h`)), h("dd", {}, t(`consent.${k}`))]));
}

/* --------------------------------------------------------------------------
   onboarding: consent (step 2) and profile (step 3)
   -------------------------------------------------------------------------- */

async function viewConsent() {
  const agree = h("input", { type: "checkbox", class: "check" });
  const button = h("button", { class: "btn primary", disabled: true }, t("consent.submit"));
  agree.addEventListener("change", () => { button.disabled = !agree.checked; });
  button.addEventListener("click", guard(async () => {
    button.disabled = true;
    me = await api("/api/me/consent", { method: "POST" });
    replace("#/onboarding/profile");
  }));

  return {
    title: t("consent.title"),
    actions: [],
    tabs: false,
    body: [
      h("div", { class: "steps" }, h("i", { class: "on" }), h("i", { class: "on" }), h("i"), h("span", {}, t("signup.step", { n: 2 }))),
      h("p", { class: "muted" }, t("consent.intro")),
      h("div", { class: "card form-foot" }, consentList()),
      h("label", { class: "check-row card form-foot" }, agree, h("span", { class: "grow" }, t("consent.agree"))),
      h("div", { class: "form-foot" }, button),
    ],
  };
}

async function viewProfileForm(onboarding) {
  const name = h("input", { type: "text", required: true, maxlength: 40, value: me.name || "" });
  const surname = h("input", { type: "text", required: true, maxlength: 40, value: me.surname || "" });
  const phone = h("input", { type: "tel", maxlength: 20, value: me.phone || "" });
  const birth = h("input", { type: "date", required: true, max: todayIso(), min: "1900-01-01", value: me.birth_date || "" });

  const sex = h("div", { class: "segmented", role: "radiogroup", "aria-label": t("profile_form.gender") },
    ["female", "male", "other"].map((v) => h("label", {},
      h("input", { type: "radio", name: "sex", value: v, required: true, checked: me.sex === v }),
      h("span", {}, t(`profile_form.${v}`)))));

  const countries = me.country && !COUNTRIES.some(([en]) => en === me.country)
    ? [[me.country, me.country], ...COUNTRIES] : COUNTRIES;
  const country = h("select", { required: true },
    h("option", { value: "", disabled: true, selected: !me.country }, t("profile_form.choose_country")),
    countries.map(([en]) => h("option", { value: en, selected: me.country === en }, countryLabel(en))));

  const has = (code, scope) => me.risk_factors.some((r) => r.code === code && r.scope === scope);
  const note = (scope) => (me.risk_factors.find((r) => r.code === "other" && r.scope === scope) || {}).note || "";
  const box = (code, scope) => h("label", {}, h("input", {
    type: "checkbox", "data-code": code, "data-scope": scope, checked: has(code, scope),
    "aria-label": `${t(`risk.${code}`)}: ${t(`profile_form.${scope === "personal" ? "me" : "family"}`)}`,
  }));
  const otherText = h("input", { class: "input", type: "text", maxlength: 200, placeholder: t("profile_form.other_ph"),
    value: note("personal") || note("family") });

  const riskGrid = h("div", { class: "risk-grid" },
    h("span", { class: "head" }), h("span", { class: "head" }, t("profile_form.me")), h("span", { class: "head" }, t("profile_form.family")),
    RISKS.map((code) => [h("span", {}, t(`risk.${code}`)), box(code, "personal"), box(code, "family")]),
    h("span", {}, t("risk.other")), box("other", "personal"), box("other", "family"),
    h("div", { class: "other-text" }, otherText),
  );
  otherText.addEventListener("input", () => {
    const boxes = riskGrid.querySelectorAll('input[data-code="other"]');
    if (otherText.value.trim() && ![...boxes].some((b) => b.checked)) boxes[1].checked = true;
  });

  const message = h("p", { class: "message" });
  const save = h("button", { type: "submit", class: "btn primary" }, onboarding ? t("profile_form.finish") : t("profile_form.save"));

  const form = h("form", {
    onsubmit: async (e) => {
      e.preventDefault();
      save.disabled = true;
      showMessage(message, "");
      const risks = [...riskGrid.querySelectorAll("input[data-code]:checked")].map((b) => ({
        code: b.dataset.code, scope: b.dataset.scope,
        note: b.dataset.code === "other" ? otherText.value.trim() : null,
      }));
      try {
        me = await api("/api/me/profile", {
          method: "PUT",
          body: {
            name: name.value.trim(), surname: surname.value.trim(), phone: phone.value.trim() || null,
            birth_date: birth.value, sex: form.querySelector("input[name=sex]:checked").value,
            country: country.value, risk_factors: risks,
          },
        });
        toast(t("profile_form.saved"));
        if (onboarding) replace("#/home");
        else back("#/profile");
      } catch (error) {
        showMessage(message, error.message);
        save.disabled = false;
      }
    },
  },
    onboarding && h("div", { class: "steps" }, h("i", { class: "on" }), h("i", { class: "on" }), h("i", { class: "on" }),
      h("span", {}, t("signup.step", { n: 3 }))),
    onboarding && h("p", { class: "muted" }, t("profile_form.intro")),
    !onboarding && [
      h("div", { class: "two" }, field(t("signup.name"), name), field(t("signup.surname"), surname)),
      h("div", { class: "form-foot" }, field(t("signup.phone"), phone)),
    ],
    h("div", { class: onboarding ? "form-foot" : "" }, field(t("profile_form.birth_date"), birth)),
    section(t("profile_form.gender")),
    sex,
    h("div", { class: "form-foot" }, field(t("profile_form.country"), country)),
    section(t("profile_form.risks")),
    h("p", { class: "hint" }, t("profile_form.risks_hint")),
    h("div", { class: "card form-foot" }, riskGrid),
    h("div", { class: "form-foot" }, save),
    message,
  );

  return {
    title: onboarding ? t("profile_form.title") : t("profile.edit"),
    back: onboarding ? null : "#/profile",
    actions: onboarding ? [] : undefined,
    tabs: !onboarding,
    body: form,
  };
}

/* --------------------------------------------------------------------------
   home
   -------------------------------------------------------------------------- */

async function viewHome() {
  const d = await api("/api/home");
  waitingCount = d.pending_reminders;
  const { counts } = d;
  const total = counts.up_to_date + counts.due_soon + counts.overdue;

  let top = null;
  if (d.popup) {
    const p = d.popup;
    top = h("div", { class: "popup", role: "status" },
      h("span", { class: "icon" }, icon("bell")),
      h("div", { class: "grow" },
        h("p", {}, p.message),
        h("div", { class: "actions" },
          h("button", {
            class: "btn small accept",
            onclick: guard(async () => { await api(`/api/notifications/${p.notification_id}/accept`, { method: "POST" }); render(); }),
          }, t("home.accept")),
          canComplete(p) && h("button", { class: "btn small done", onclick: () => completePopup(p) }, t("home.mark_done"))),
        d.pending_reminders > 1 && h("p", { class: "more" }, t("home.waiting", { n: d.pending_reminders - 1 })),
      ));
  } else if (d.next_item) {
    top = h("a", { class: "popup next", href: itemHref(d.next_item) },
      h("div", { class: "grow" },
        h("div", { class: "kicker" }, t("home.next_up")),
        h("p", {}, d.next_item.name),
        h("div", { class: "muted small" }, whenText(d.next_item))),
      chev());
  } else {
    top = h("div", { class: "popup next" },
      h("span", { class: "icon" }, icon("check")),
      h("div", { class: "grow" }, h("p", {}, t("home.all_clear")), h("div", { class: "muted small" }, t("app.tagline"))));
  }

  const shortcut = (href, iconName, text) =>
    h("a", { class: "row", href }, h("span", { class: "shortcut-icon" }, icon(iconName)), h("span", { class: "grow title" }, text), chev());

  const segment = (status) => counts[status] > 0 && h("span", { class: status, style: `flex:${counts[status]}` });
  const legend = (status) => h("a", { href: "#/schedule", class: status },
    h("strong", {}, String(counts[status])), t(`strip.${status}`));

  return {
    title: t("home.greeting", { name: d.name }),
    tab: "home",
    wide: true,
    body: [
      h("div", { class: "home-hero" },
        h("div", { class: "hero-main" }, top),
        h("div", { class: "hero-side" },
          h("div", { class: "strip" },
            h("div", { class: "bar", "aria-hidden": "true" }, segment("up_to_date"), segment("due_soon"), segment("overdue")),
            h("div", { class: "legend" }, legend("up_to_date"), legend("due_soon"), legend("overdue"))),
          h("a", { class: "btn primary big", href: "#/done" }, icon("plus"), t("home.log_button")))),

      h("div", { class: "home-grid" },
        h("section", {},
          section(t("home.coming_up")),
          d.coming_up.length ? list(d.coming_up.map((i) => itemRow(i)))
            : empty(total ? t("home.nothing_due") : t("home.no_items"))),
        h("section", {},
          d.plans.length > 0 && [section(t("home.plans")), list(d.plans.map(planRow))],
          section(t("home.shortcuts")),
          list([
            shortcut("#/add", "plus", t("add.title")),
            shortcut("#/schedule", "calendar", t("schedule.title")),
            shortcut("#/info", "info", t("info.title")),
            shortcut("#/vaccinations", "check", t("profile.passport")),
          ]))),
    ],
  };
}

function planRow(plan) {
  const done = plan.items.filter((i) => i.checked).length;
  return h("a", { class: "row", href: `#/procedure/${plan.procedure_id}` },
    h("span", { class: "mark planned" }),
    h("div", { class: "grow" },
      h("div", { class: "title" }, plan.procedure_name),
      h("div", { class: "sub" }, t("proc.appointment", { when: fmtDateTime(plan.appointment_at) })),
      h("div", { class: "sub" }, t("home.progress", { done, total: plan.items.length })),
      h("div", { class: "progress" }, h("span", { style: `width:${(100 * done) / Math.max(plan.items.length, 1)}%` }))),
    chev());
}

/* --------------------------------------------------------------------------
   log something you did: from a reminder, or your own entry
   -------------------------------------------------------------------------- */

async function viewDone(query) {
  const items = (await api("/api/schedule")).filter((i) => i.status !== "up_to_date");

  const reminderRows = items.map((item) => h("div", { class: "row" },
    h("span", { class: `mark ${item.status}` }),
    h("a", { class: "grow", href: itemHref(item) },
      h("div", { class: "title" }, item.name),
      h("div", { class: "sub" }, whenText(item))),
    h("button", { class: "btn small soft", onclick: () => completeItem(item, { ask: true }) }, icon("check"), t("done.button"))));

  // "Add your own"
  const title = h("input", { type: "text", required: true, maxlength: 80, placeholder: t("done.what_ph") });
  const category = categorySelect(query.get("category") || "other");
  const date = h("input", { type: "date", required: true, max: todayIso(), value: todayIso() });
  const renew = h("input", { type: "date" });
  const renewField = h("div", { class: "form-foot" }, field(t("done.renew_on"), renew));
  const showRenew = () => { renewField.hidden = category.value() !== "vaccination"; };
  category.select.addEventListener("change", showRenew);
  showRenew();
  const notes = h("textarea", { maxlength: 2000 });
  const fileName = h("span", {}, t("done.attach"));
  const file = h("input", {
    type: "file", accept: ".pdf,image/jpeg,image/png,image/webp,image/heic",
    onchange: () => { fileName.textContent = file.files[0] ? file.files[0].name : t("done.attach"); },
  });
  const message = h("p", { class: "message" });
  const save = h("button", { type: "submit", class: "btn primary" }, t("done.save"));

  const form = h("form", {
    onsubmit: async (e) => {
      e.preventDefault();
      const f = file.files[0];
      if (f && f.size > 10 * 1024 * 1024) return showMessage(message, t("done.file_too_big"));
      if (!category.value()) return showMessage(message, t("done.custom_category"));
      save.disabled = true;
      showMessage(message, "");
      try {
        const entry = await api("/api/log", {
          method: "POST",
          body: {
            title: title.value.trim(), category: category.value(), done_on: date.value,
            renew_on: !renewField.hidden && renew.value ? renew.value : null, notes: notes.value.trim() || null,
          },
        });
        if (f) {
          const data = new FormData();
          data.append("file", f);
          await api(`/api/log/${entry.id}/attachment`, { method: "POST", form: data });
        }
        celebrate({ then: () => replace("#/log") });
      } catch (error) {
        showMessage(message, error.message);
        save.disabled = false;
      }
    },
  },
    field(t("done.what"), title),
    h("div", { class: "form-foot" }, category.nodes),
    h("div", { class: "form-foot" }, field(t("done.date"), date, t("done.backdate_hint"))),
    renewField,
    h("div", { class: "form-foot" }, field(t("done.notes"), notes)),
    h("label", { class: "dropzone" }, file, icon("clip"), fileName),
    h("div", { class: "form-foot" }, save),
    message,
  );

  return {
    title: t("done.title"),
    back: "#/home",
    wide: true,
    body: h("div", { class: "split" },
      h("section", {},
        section(t("done.from")),
        items.length ? [h("p", { class: "hint", style: "margin:-4px 0 10px" }, t("done.from_hint")), list(reminderRows)]
          : empty(t("done.none"))),
      h("section", {},
        section(t("done.own")),
        h("p", { class: "hint", style: "margin:-4px 0 12px" }, t("done.own_hint")),
        h("div", { class: "card" }, form))),
  };
}

/* --------------------------------------------------------------------------
   schedule: calendar of everything, plus the full list
   -------------------------------------------------------------------------- */

async function viewSchedule(query) {
  const source = query.get("source") || "all";
  const month = `${cal.year}-${String(cal.month + 1).padStart(2, "0")}`;
  const [entries, items] = await Promise.all([
    api(`/api/calendar?month=${month}`),
    api(`/api/schedule?source=${source}`),
  ]);

  const calendarCard = h("div", { class: "card cal" });
  const dayList = h("div");

  const entryHref = (e) => ({
    guideline: `#/checkup/${e.id}`, task: `#/task/${e.id}`, log: "#/log", prep: `#/procedure/${e.id}`,
  })[e.kind];

  function drawDay() {
    const today = entries.filter((e) => e.date === cal.selected);
    fill(dayList,
      h("h2", { class: "section day-title" }, fmtDate(cal.selected)),
      today.length
        ? list(today.map((e) => h("a", { class: "row", href: entryHref(e) },
            h("span", { class: `mark ${e.status}` }),
            h("div", { class: "grow" }, h("div", { class: "title" }, e.title), h("div", { class: "sub" }, categoryLabel(e.category))),
            statusPill(e.status), chev())))
        : empty(t("schedule.day_empty")));
  }

  function drawCalendar() {
    const first = new Date(cal.year, cal.month, 1);
    const offset = (first.getDay() + 6) % 7;          // Monday first
    const days = new Date(cal.year, cal.month + 1, 0).getDate();
    const byDay = {};
    for (const e of entries) (byDay[e.date] ||= new Set()).add(e.status);

    const shift = (delta) => () => {
      const d = new Date(cal.year, cal.month + delta, 1);
      cal.year = d.getFullYear();
      cal.month = d.getMonth();
      cal.selected = localIso(d);
      render();
    };

    fill(calendarCard,
      h("div", { class: "cal-head" },
        h("button", { class: "icon-btn plain", "aria-label": t("schedule.prev"), onclick: shift(-1) }, icon("back")),
        h("h2", {}, monthTitle(cal.year, cal.month)),
        h("button", { class: "icon-btn plain", "aria-label": t("schedule.next"), onclick: shift(1) }, icon("chevron"))),
      h("div", { class: "cal-grid" },
        weekdayInitials().map((d) => h("span", { class: "dow" }, d)),
        [...Array(offset)].map(() => h("span")),
        [...Array(days)].map((_, i) => {
          const iso = localIso(new Date(cal.year, cal.month, i + 1));
          const statuses = [...(byDay[iso] || [])].slice(0, 3);
          return h("button", {
            class: `cal-day${iso === todayIso() ? " today" : ""}${iso === cal.selected ? " selected" : ""}`,
            "aria-pressed": String(iso === cal.selected),
            "aria-label": `${fmtDate(iso)}${statuses.length ? `, ${statuses.map((s) => t(`status.${s}`)).join(", ")}` : ""}`,
            onclick: () => { cal.selected = iso; drawCalendar(); drawDay(); },
          }, String(i + 1), h("span", { class: "dots" }, statuses.map((s) => h("span", { class: `dot ${s}` }))));
        })),
    );
  }

  drawCalendar();
  drawDay();

  const chip = (value) => h("button", {
    "aria-pressed": String(source === value),
    onclick: () => replace(value === "all" ? "#/schedule" : `#/schedule?source=${value}`),
  }, t(`schedule.${value}`));

  return {
    title: t("schedule.title"),
    tab: "schedule",
    wide: true,
    body: [
      h("div", { class: "split" }, calendarCard, dayList),
      h("div", { class: "section-row" }, section(t("schedule.list"))),
      h("div", { class: "chips", style: "margin-bottom:12px" }, chip("all"), chip("recommended"), chip("mine")),
      items.length ? h("div", { class: "list cards" }, items.map((i) => itemRow(i, { showLast: true }))) : empty(t("schedule.empty")),
    ],
  };
}

/* --------------------------------------------------------------------------
   recommended check: guideline, source, mark as done
   -------------------------------------------------------------------------- */

async function viewCheckup(id) {
  const d = await api(`/api/checkups/${id}`);
  const item = d.item;
  // A function, not one node: the note appears in two places.
  const englishNote = () => lang === "lv" && h("p", { class: "hint", style: "margin:0 0 6px" }, t("checkup.english_only"));

  return {
    title: item.name,
    back: "#/schedule",
    body: [
      h("span", { class: `status-tag ${item.status}` }, whenText(item)),

      h("div", { class: "card form-foot stack" },
        h("h2", {}, t("checkup.guideline")),
        h("p", {}, d.summary),
        h("dl", { class: "facts" },
          h("dt", {}, t("when.last", { date: "" }).trim()),
          h("dd", {}, item.last_done ? fmtDate(item.last_done) : t("when.never")),
          h("dt", {}, t("when.next", { date: "" }).trim()),
          h("dd", {}, fmtDate(item.due_on))),
        h("p", { class: "muted small" }, t("checkup.repeats", { n: item.interval_months })),
        h("p", { class: "muted small" }, t("checkup.research")),
        d.source_url && h("p", {}, h("a", { href: d.source_url, target: "_blank", rel: "noopener" }, t("checkup.source"))),
      ),

      (d.more_info || d.preparation) && h("div", { class: "form-foot" },
        d.more_info && h("details", { class: "fold" }, h("summary", {}, t("checkup.more")), h("div", {}, englishNote(), d.more_info)),
        d.preparation && h("details", { class: "fold" }, h("summary", {}, t("checkup.prep")),
          h("div", {}, englishNote(), d.preparation,
            d.procedure_id && h("p", { class: "form-foot" }, h("a", { href: `#/procedure/${d.procedure_id}` }, t("checkup.open_guide")))))),

      d.history.length > 0 && [
        section(t("checkup.history")),
        list(d.history.map((e) => h("div", { class: "row" },
          h("span", { class: "mark done" }),
          h("div", { class: "grow" }, h("div", { class: "title" }, fmtDate(e.done_on)), e.notes && h("div", { class: "sub" }, e.notes)),
          statusPill("done")))),
      ],

      h("div", { class: "actions" },
        h("button", { class: "btn primary", onclick: () => completeItem(item) }, icon("check"), t("home.mark_done")),
        h("button", { class: "btn outline", onclick: () => completeItem(item, { ask: true }) }, t("checkup.other_day"))),
    ],
  };
}

/* --------------------------------------------------------------------------
   your own task: details, dates, done / missed
   -------------------------------------------------------------------------- */

async function viewTask(id) {
  const task = await api(`/api/tasks/${id}`);
  const today = todayIso();

  const eventRow = (e) => {
    const late = e.status === "pending" && e.due_on < today;
    const shown = e.status === "pending" ? (late ? "overdue" : "due_soon") : e.status;
    return h("div", { class: "row" },
      h("span", { class: `mark ${shown}` }),
      h("div", { class: "grow" },
        h("div", { class: "title" }, fmtDate(e.due_on)),
        e.done_on && e.done_on !== e.due_on && h("div", { class: "sub" }, t("when.last", { date: fmtDate(e.done_on) }))),
      e.status === "pending"
        ? [
          h("button", {
            class: "btn small soft",
            onclick: () => completeItem({ kind: "task", id: e.id, name: task.title }, { ask: true }),
          }, t("done.button")),
          h("button", {
            class: "btn small outline",
            onclick: guard(async () => {
              await api(`/api/task-events/${e.id}/missed`, { method: "POST" });
              toast(t("task.marked_missed"));
              render();
            }),
          }, t("task.missed")),
        ]
        : statusPill(e.status));
  };

  const newDate = h("input", { class: "input", type: "date", required: true });
  const addDate = !task.repeat_every && h("form", {
    class: "two form-foot",
    onsubmit: guard(async (ev) => {
      ev.preventDefault();
      await api(`/api/tasks/${id}/dates`, { method: "POST", body: { due_on: newDate.value } });
      render();
    }),
  }, newDate, h("button", { class: "btn outline", type: "submit" }, t("task.add_date")));

  const facts = [
    [t("done.category"), categoryLabel(task.category)],
    [t("add.how_often"), task.repeat_every ? repeatText(task.repeat_every, task.repeat_unit) : t("task.manual")],
    task.doctor_name && [t("task.doctor"), task.doctor_name],
    task.doctor_specialty && [t("task.specialty"), task.doctor_specialty],
  ].filter(Boolean);

  return {
    title: task.title,
    back: "#/schedule",
    body: [
      h("div", { class: "card stack" },
        h("dl", { class: "facts" }, facts.map(([k, v]) => [h("dt", {}, k), h("dd", {}, v)])),
        task.description && h("p", { class: "muted" }, task.description)),
      section(t("task.dates")),
      // What is still to do first (soonest on top), then history (newest on top).
      list([
        ...task.events.filter((e) => e.status === "pending"),
        ...task.events.filter((e) => e.status !== "pending").reverse(),
      ].map(eventRow)),
      addDate,
      h("div", { class: "actions" },
        h("button", {
          class: "btn danger",
          onclick: guard(async () => {
            if (!confirm(t("task.delete_confirm", { title: task.title }))) return;
            await api(`/api/tasks/${id}`, { method: "DELETE" });
            toast(t("task.deleted"));
            replace("#/schedule");
          }),
        }, t("task.delete"))),
    ],
  };
}

/* --------------------------------------------------------------------------
   add: your own appointment, vaccine shot, test...
   -------------------------------------------------------------------------- */

async function viewAdd() {
  let category = "appointment";
  const customCategory = h("input", { class: "input form-foot", type: "text", maxlength: 40, placeholder: t("done.custom_ph"), hidden: true });
  const chips = h("div", { class: "chips" });
  const drawChips = () => fill(chips,
    [...CATEGORY_CHOICES, "__custom"].map((c) => h("button", {
      type: "button", "aria-pressed": String(category === c),
      onclick: () => { category = c; customCategory.hidden = c !== "__custom"; drawChips(); if (c === "__custom") customCategory.focus(); },
    }, c === "__custom" ? `${t("done.custom_category")}…` : categoryLabel(c))));
  drawChips();

  const title = h("input", { type: "text", required: true, maxlength: 80, placeholder: t("add.name_ph") });
  const first = h("input", { type: "date", required: true, value: todayIso() });

  let mode = "repeat";
  const every = h("input", { type: "number", min: 1, max: 365, value: 1, required: true, inputmode: "numeric" });
  const unit = h("select", {}, ["day", "week", "month", "year"].map((u) => h("option", { value: u, selected: u === "month" }, t(`unit.${u}`))));
  const repeatBox = h("div", { class: "two form-foot" }, field(t("add.every"), every), field(" ", unit));
  const extra = h("div");
  const addExtra = () => extra.append(h("input", { class: "input form-foot", type: "date", "data-extra": "1" }));
  const manualBox = h("div", { hidden: true },
    h("p", { class: "hint form-foot" }, t("add.more_dates")), extra,
    h("button", { type: "button", class: "link-btn form-foot", onclick: addExtra }, `+ ${t("add.add_date")}`));
  addExtra();

  const modeSwitch = h("div", { class: "segmented form-foot" },
    [["repeat", t("add.repeats")], ["manual", t("add.manual")]].map(([v, text]) => h("label", {},
      h("input", {
        type: "radio", name: "mode", value: v, checked: v === mode,
        onchange: () => { mode = v; repeatBox.hidden = v !== "repeat"; manualBox.hidden = v !== "manual"; },
      }),
      h("span", {}, text))));

  const description = h("textarea", { maxlength: 2000 });
  const doctor = h("input", { type: "text", maxlength: 80 });
  const specialty = h("input", { type: "text", maxlength: 80, placeholder: t("add.specialty_ph") });
  const message = h("p", { class: "message" });
  const save = h("button", { type: "submit", class: "btn primary" }, t("add.save"));

  const form = h("form", {
    onsubmit: async (e) => {
      e.preventDefault();
      const cat = category === "__custom" ? customCategory.value.trim() : category;
      if (!cat) return showMessage(message, t("done.custom_category"));
      save.disabled = true;
      showMessage(message, "");
      const body = {
        title: title.value.trim(), category: cat, first_date: first.value,
        description: description.value.trim() || null,
        doctor_name: doctor.value.trim() || null, doctor_specialty: specialty.value.trim() || null,
      };
      if (mode === "repeat") Object.assign(body, { repeat_every: Number(every.value), repeat_unit: unit.value });
      else body.extra_dates = [...extra.querySelectorAll("input")].map((i) => i.value).filter(Boolean);
      try {
        const task = await api("/api/tasks", { method: "POST", body });
        toast(t("add.saved"));
        replace(`#/task/${task.id}`);
      } catch (error) {
        showMessage(message, error.message);
        save.disabled = false;
      }
    },
  },
    section(t("add.type")), chips, customCategory,
    h("div", { class: "form-foot pair" }, h("div", {}, field(t("add.name"), title)), h("div", {}, field(t("add.first_date"), first))),
    section(t("add.how_often")), modeSwitch, repeatBox, manualBox,
    h("div", { class: "form-foot pair" }, h("div", {}, field(t("add.doctor_name"), doctor)), h("div", {}, field(t("add.doctor_specialty"), specialty))),
    h("div", { class: "form-foot" }, field(t("add.description"), description)),
    h("div", { class: "form-foot" }, save),
    message,
  );

  return { title: t("add.title"), tab: "add", body: form };
}

/* --------------------------------------------------------------------------
   log: pick a category, see what was done or missed
   -------------------------------------------------------------------------- */

async function viewLog(query) {
  const selected = query.get("category") || "";
  const [categories, lines] = await Promise.all([
    api("/api/categories"),
    api(`/api/log${selected ? `?category=${encodeURIComponent(selected)}` : ""}`),
  ]);

  const picker = h("select", {
    onchange: () => replace(picker.value ? `#/log?category=${encodeURIComponent(picker.value)}` : "#/log"),
  },
    h("option", { value: "" }, t("log.all")),
    categories.map((c) => h("option", { value: c, selected: c === selected }, categoryLabel(c))));

  const row = (l) => {
    const href = l.checkup_type_id ? `#/checkup/${l.checkup_type_id}` : l.task_id ? `#/task/${l.task_id}` : null;
    return h("div", { class: "row" },
      h("span", { class: `mark ${l.kind}` }),
      h("div", { class: "grow" },
        href ? h("a", { class: "title", href }, l.title) : h("div", { class: "title" }, l.title),
        h("div", { class: "sub" }, `${fmtDate(l.date)} · ${categoryLabel(l.category)}`),
        l.notes && h("div", { class: "sub" }, l.notes),
        l.kind === "done" && h("div", { class: "sub", style: "display:flex;gap:14px;margin-top:4px" },
          l.attachment_name && h("button", {
            class: "link-btn",
            onclick: guard(async () => saveBlob(await api(`/api/log/${l.id}/attachment`, { raw: true }), l.attachment_name)),
          }, l.attachment_name),
          h("button", {
            class: "link-btn danger",
            onclick: guard(async () => {
              if (!confirm(t("log.delete_confirm", { title: l.title, date: fmtDate(l.date) }))) return;
              await api(`/api/log/${l.id}`, { method: "DELETE" });
              toast(t("log.deleted"));
              render();
            }),
          }, t("common.delete")))),
      statusPill(l.kind));
  };

  return {
    title: t("log.title"),
    tab: "log",
    wide: true,
    body: [
      h("div", { class: "toolbar" },
        h("div", { class: "grow" }, field(t("log.category"), picker)),
        h("a", { class: "btn outline", href: "#/done" }, icon("plus"), t("log.add"))),
      h("div", { class: "form-foot" }, lines.length ? h("div", { class: "list cards" }, lines.map(row)) : empty(t("log.empty"))),
    ],
  };
}

/* --------------------------------------------------------------------------
   info: the searchable preparation library
   -------------------------------------------------------------------------- */

async function viewInfo() {
  const [plans, all] = await Promise.all([api("/api/prep-plans"), api("/api/procedures")]);
  const results = h("div");
  const draw = (procs, q) => fill(results, procs.length
    ? h("div", { class: "list cards" }, procs.map((p) => h("a", { class: "row", href: `#/procedure/${p.id}` },
        h("div", { class: "grow" }, h("div", { class: "title" }, p.name),
          h("div", { class: "sub", style: "display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden" }, p.summary)),
        chev())))
    : empty(t("info.no_results", { q })));
  draw(all, "");

  let timer;
  const search = h("input", {
    class: "input", type: "search", placeholder: t("info.search"), "aria-label": t("info.search"),
    oninput: () => {
      clearTimeout(timer);
      timer = setTimeout(guard(async () => {
        const q = search.value.trim();
        draw(q ? await api(`/api/procedures?q=${encodeURIComponent(q)}`) : all, q);
      }), 200);
    },
  });

  return {
    title: t("info.title"),
    tab: "info",
    wide: true,
    body: [
      h("div", { class: "search" }, icon("search"), search),
      plans.length > 0 && [section(t("info.plans")), h("div", { class: "list cards" }, plans.map(planRow))],
      section(t("info.library")),
      results,
    ],
  };
}

async function viewProcedure(id) {
  const p = await api(`/api/procedures/${id}`);

  const planCard = (plan) => h("div", { class: "card form-foot" },
    h("div", { class: "section-row" },
      h("h2", {}, t("proc.appointment", { when: fmtDateTime(plan.appointment_at) })),
      h("button", {
        class: "link-btn danger",
        onclick: guard(async () => {
          await api(`/api/prep-plans/${plan.id}`, { method: "DELETE" });
          toast(t("proc.removed"));
          render();
        }),
      }, t("proc.remove"))),
    h("div", { class: "form-foot", style: "margin-inline:-16px" },
      plan.items.map((item) => {
        const box = h("input", { type: "checkbox", checked: item.checked });
        const rowEl = h("label", { class: `check-row${item.checked ? " done" : ""}` }, box,
          h("div", { class: "grow" },
            h("div", { class: "text" }, item.text),
            item.remind_at && h("div", { class: "hint", style: "margin:2px 0 0" },
              item.sent_at ? t("proc.reminded") : t("proc.remind_at", { when: fmtDateTime(item.remind_at) }))));
        box.addEventListener("change", guard(async () => {
          await api(`/api/prep-items/${item.id}`, { method: "PATCH", body: { checked: box.checked } });
          rowEl.classList.toggle("done", box.checked);
        }));
        return rowEl;
      })));

  // "Set reminder": appointment time + which lines to be reminded about
  const soon = new Date(Date.now() + 24 * 3600 * 1000);
  soon.setHours(9, 0, 0, 0);
  const when = h("input", { type: "datetime-local", required: true, min: localDateTime(new Date()), value: localDateTime(soon) });
  const picks = p.steps.map((s) => {
    const box = h("input", { type: "checkbox", checked: s.hours_before !== null, "data-step": s.id });
    const time = h("div", { class: "hint", style: "margin:2px 0 0" });
    return { s, box, time, row: h("label", { class: "check-row" }, box, h("div", { class: "grow" }, h("div", {}, s.text), time)) };
  });
  const updateTimes = () => {
    const at = new Date(when.value);
    for (const { s, box, time } of picks) {
      const remindAt = new Date(at.getTime() - (s.hours_before ?? 1) * 3600 * 1000);
      time.textContent = !box.checked || Number.isNaN(at.getTime()) ? ""
        : remindAt <= new Date() ? t("proc.remind_now")   // already past: it goes out straight away
        : t("proc.remind_at", { when: fmtDateTime(remindAt) });
    }
  };
  when.addEventListener("input", updateTimes);
  picks.forEach(({ box }) => box.addEventListener("change", updateTimes));
  updateTimes();

  const message = h("p", { class: "message" });
  const form = h("form", {
    class: "card form-foot",
    hidden: true,
    onsubmit: async (e) => {
      e.preventDefault();
      if (new Date(when.value) < new Date()) return showMessage(message, t("proc.past"));
      try {
        await api(`/api/procedures/${id}/plans`, {
          method: "POST",
          body: {
            appointment_at: `${when.value}:00`,
            reminders: picks.filter(({ box }) => box.checked).map(({ s }) => ({ step_id: s.id })),
          },
        });
        toast(t("proc.saved"));
        render();
      } catch (error) {
        showMessage(message, error.message);
      }
    },
  },
    field(t("proc.when"), when),
    h("p", { class: "section" }, t("proc.remind_about")),
    h("div", { style: "margin-inline:-16px" }, picks.map(({ row }) => row)),
    h("div", { class: "form-foot" }, h("button", { type: "submit", class: "btn primary" }, t("proc.save"))),
    message,
  );

  return {
    title: p.name,
    back: "#/info",
    body: [
      h("p", { class: "card" }, p.summary),
      p.plans.map(planCard),
      section(t("proc.checklist")),
      list(p.steps.map((s) => h("div", { class: "row" },
        h("span", { class: "pill neutral" }, String(s.position)),
        h("div", { class: "grow" }, h("div", {}, s.text),
          s.hours_before !== null && h("div", { class: "sub" }, t("proc.before", { n: s.hours_before })))))),
      h("div", { class: "form-foot" },
        h("button", {
          class: "btn primary",
          onclick: (e) => { form.hidden = false; e.currentTarget.hidden = true; when.focus(); },
        }, icon("bell"), t("proc.set_reminder"))),
      form,
    ],
  };
}

/* --------------------------------------------------------------------------
   AI: the chat interface, not connected to a model yet
   -------------------------------------------------------------------------- */

async function viewAi() {
  const thread = h("div", { class: "chat" });
  const draw = () => {
    fill(thread,
      h("div", { class: "bubble bot" }, t("ai.intro")),
      chat.map((m) => h("div", { class: `bubble ${m.from}` }, m.text)));
    window.scrollTo(0, document.body.scrollHeight);
  };
  draw();

  const input = h("input", { type: "text", maxlength: 1000, placeholder: t("ai.placeholder"), "aria-label": t("ai.placeholder") });
  const form = h("form", {
    class: "composer",
    onsubmit: (e) => {
      e.preventDefault();
      const text = input.value.trim();
      if (!text) return;
      chat.push({ from: "me", text });
      input.value = "";
      draw();
      // TODO: send to the assistant API once it exists.
      setTimeout(() => { chat.push({ from: "bot", text: t("ai.stub") }); draw(); }, 400);
    },
  }, input, h("button", { class: "icon-btn", type: "submit", "aria-label": t("ai.send") }, icon("send")));

  return {
    title: t("ai.title"),
    tab: "ai",
    body: [thread, form, h("p", { class: "hint", style: "text-align:center" }, t("ai.note"))],
  };
}

/* --------------------------------------------------------------------------
   profile and everything behind it
   -------------------------------------------------------------------------- */

async function viewProfile() {
  const age = me.birth_date && (() => {
    const b = new Date(`${me.birth_date}T00:00`);
    const now = new Date();
    return now.getFullYear() - b.getFullYear() - ((now.getMonth() < b.getMonth()
      || (now.getMonth() === b.getMonth() && now.getDate() < b.getDate())) ? 1 : 0);
  })();

  const link = (href, text, value) => h("a", { class: "row", href },
    h("span", { class: "grow title" }, text), value && h("span", { class: "value" }, value), chev());

  const languages = h("div", { class: "segmented", style: "min-width:150px" },
    Object.entries(LANGS).map(([code, label]) => h("label", {},
      h("input", {
        type: "radio", name: "lang", value: code, checked: lang === code,
        onchange: guard(async () => {
          me = await api("/api/me/settings", { method: "PATCH", body: { language: code } });
          setLang(code);
          buildTabbar();
          render();
        }),
      }),
      h("span", {}, code.toUpperCase()))));

  return {
    title: t("profile.title"),
    back: "#/home",
    actions: [],
    body: [
      h("div", { class: "card who" },
        h("div", { class: "avatar" }, `${me.name[0] || ""}${(me.surname || "")[0] || ""}`.toUpperCase()),
        h("div", { class: "grow" },
          h("div", { class: "name" }, `${me.name} ${me.surname || ""}`.trim()),
          h("div", { class: "muted small" }, me.email),
          h("div", { class: "muted small" },
            [age !== null && age !== undefined && t("profile.years", { n: age }), me.country && countryLabel(me.country)]
              .filter(Boolean).join(", ")))),

      h("div", { class: "form-foot" }, list([
        link("#/profile/edit", t("profile.edit")),
        link("#/vaccinations", t("profile.passport")),
        link("#/profile/reminders", t("profile.reminders"),
          me.reminders_on ? t(`settings.lead_${LEAD_DAYS.includes(me.reminder_lead_days) ? me.reminder_lead_days : 7}`) : "—"),
        link("#/inbox", t("profile.inbox"), waitingCount ? String(waitingCount) : ""),
        h("div", { class: "row" }, h("span", { class: "grow title" }, t("profile.language")), languages),
        link("#/privacy", t("profile.privacy")),
        link("#/broadcast", t("profile.broadcast")),
      ])),

      section(t("profile.family")),
      h("div", { class: "card" },
        h("button", { class: "btn outline", disabled: true }, icon("plus"), t("profile.family_add")),
        h("p", { class: "hint", style: "text-align:center" }, t("profile.soon"))),

      h("div", { class: "form-foot" }, h("button", { class: "btn danger", onclick: logOut }, t("profile.sign_out"))),
    ],
  };
}

async function viewReminderSettings() {
  const on = h("input", { type: "checkbox", checked: me.reminders_on });
  const lead = h("select", {}, LEAD_DAYS.map((d) => h("option", { value: d, selected: d === me.reminder_lead_days }, t(`settings.lead_${d}`))));
  const push = h("input", { type: "checkbox", checked: me.remind_push });
  const sms = h("input", { type: "checkbox", checked: me.remind_sms });
  const phone = h("input", { type: "tel", maxlength: 20, value: me.phone || "", placeholder: "20 123 456" });
  const toggleRow = (input, title, hint) => h("label", { class: "check-row" },
    h("div", { class: "grow" }, h("div", { class: "title", style: "font-weight:700" }, title), h("div", { class: "hint", style: "margin:2px 0 0" }, hint)),
    h("span", { class: "toggle" }, input, h("span")));

  const message = h("p", { class: "message" });
  const result = h("p", { class: "message" });
  const save = h("button", { type: "submit", class: "btn primary" }, t("common.save"));

  const checkNow = h("button", {
    type: "button",
    class: "btn outline",
    onclick: async () => {
      checkNow.disabled = true;
      try {
        const r = await api("/api/notifications/check", { method: "POST" });
        const n = r.push + r.sms + r.prep;
        showMessage(result, [n ? t("settings.check_sent", { n }) : t("settings.check_none"),
          r.sms && r.dry_run ? t("settings.sms_test") : ""].filter(Boolean).join(" "), "ok");
        showPendingReminders();
      } catch (error) {
        showMessage(result, error.message);
      } finally {
        checkNow.disabled = false;
      }
    },
  }, t("settings.check_now"));

  return {
    title: t("settings.title"),
    back: "#/profile",
    body: [
      h("form", {
        onsubmit: async (e) => {
          e.preventDefault();
          save.disabled = true;
          showMessage(message, "");
          try {
            me = await api("/api/me/settings", {
              method: "PATCH",
              body: {
                reminders_on: on.checked, reminder_lead_days: Number(lead.value),
                remind_push: push.checked, remind_sms: sms.checked, phone: phone.value.trim() || null,
              },
            });
            toast(t("common.saved"));
          } catch (error) {
            showMessage(message, error.message);
          } finally {
            save.disabled = false;
          }
        },
      },
        h("div", { class: "list" }, toggleRow(on, t("settings.on"), t("settings.on_hint"))),
        h("div", { class: "form-foot" }, field(t("settings.lead"), lead)),
        section(t("settings.channels")),
        h("div", { class: "list" },
          toggleRow(push, t("settings.push"), t("settings.push_hint")),
          toggleRow(sms, t("settings.sms"), t("settings.sms_hint"))),
        h("div", { class: "form-foot" }, field(t("settings.phone"), phone, t("settings.phone_hint"))),
        h("div", { class: "form-foot" }, save),
        message,
      ),
      h("div", { class: "form-foot" }, checkNow),
      result,
    ],
  };
}

async function viewPassport() {
  const rows = await api("/api/vaccinations");
  const recorded = rows.filter((v) => v.doses.length);
  const missing = rows.filter((v) => !v.doses.length);

  const row = (v) => h(v.checkup_type_id ? "a" : "div", { class: "row", href: v.checkup_type_id ? `#/checkup/${v.checkup_type_id}` : null },
    h("span", { class: `mark ${v.status || ""}` }),
    h("div", { class: "grow" },
      h("div", { class: "title" }, v.name),
      v.doses.length
        ? [h("div", { class: "sub" }, `${t("passport.given")}: ${v.doses.map(fmtDate).join(", ")}`),
           h("div", { class: "sub" }, v.renew_on ? `${t("passport.renew")}: ${fmtDate(v.renew_on)}` : t("passport.unknown"))]
        : h("div", { class: "sub" }, t("passport.not_recorded"))),
    v.status && statusPill(v.status),
    v.doses.length > 0 && h("span", { class: "pill neutral" }, dosesText(v.doses.length)));

  return {
    title: t("passport.title"),
    back: "#/profile",
    body: [
      h("a", { class: "btn primary", href: "#/done?category=vaccination" }, icon("plus"), t("passport.add")),
      recorded.length > 0 && h("div", { class: "form-foot" }, list(recorded.map(row))),
      missing.length > 0 && [section(t("passport.recommended")), list(missing.map(row))],
      !rows.length && h("div", { class: "form-foot" }, empty(t("log.empty"))),
    ],
  };
}

async function viewInbox() {
  const inbox = await api("/api/notifications");
  waitingCount = inbox.waiting;

  return {
    title: t("inbox.title"),
    back: "#/home",
    actions: inbox.waiting > 0 ? [h("button", {
      class: "link-btn",
      onclick: guard(async () => { await api("/api/notifications/accept-all", { method: "POST" }); render(); }),
    }, t("inbox.accept_all"))] : [],
    body: inbox.items.length
      ? list(inbox.items.map((n) => h("div", { class: "row" },
          h("span", { class: `mark ${n.accepted_at ? "" : n.kind === "overdue" ? "overdue" : "due_soon"}` }),
          h("div", { class: "grow" },
            h("div", {}, n.message),
            h("div", { class: "sub" }, fmtDateTime(n.created_at))),
          n.accepted_at
            ? h("span", { class: "pill neutral" }, t("inbox.accepted"))
            : h("button", {
                class: "btn small soft",
                onclick: guard(async () => { await api(`/api/notifications/${n.id}/accept`, { method: "POST" }); render(); }),
              }, t("home.accept")))))
      : empty(t("inbox.empty")),
  };
}

async function viewPrivacy() {
  return {
    title: t("privacy.title"),
    back: "#/profile",
    body: [
      h("div", { class: "card" }, consentList(),
        me.consent_at && h("p", { class: "hint form-foot" }, t("consent.given", { date: fmtDate(me.consent_at) }))),
      h("div", { class: "form-foot" },
        h("button", {
          class: "btn outline",
          onclick: guard(async () => saveBlob(await api("/api/me/export", { raw: true }), "my-health-data.json")),
        }, t("privacy.export")),
        h("p", { class: "hint" }, t("privacy.export_hint"))),
      h("div", { class: "form-foot" },
        h("button", {
          class: "btn danger",
          onclick: guard(async () => {
            if (prompt(t("privacy.delete_confirm")) !== "DELETE") return;
            await api("/api/me", { method: "DELETE" });
            token.clear();
            location.replace("login.html");
          }),
        }, t("privacy.delete"))),
    ],
  };
}

/* --------------------------------------------------------------------------
   broadcast - text every user who has a phone number
   -------------------------------------------------------------------------- */

async function viewBroadcast() {
  const { recipients } = await api("/api/notifications/recipients");

  const text = h("textarea", { maxlength: MESSAGE_LIMIT, required: true });
  const chars = h("p", { class: "hint" });
  const updateChars = () => { chars.textContent = t("broadcast.chars", { n: MESSAGE_LIMIT - text.value.length }); };
  text.addEventListener("input", updateChars);
  updateChars();

  const status = h("p", { class: "message" });
  const report = h("div");
  const sendLabel = t("broadcast.send", { n: recipients });
  const send = h("button", { type: "submit", class: "btn primary", disabled: recipients === 0 }, sendLabel);

  const form = h("form", {
    onsubmit: async (e) => {
      e.preventDefault();
      send.disabled = true;
      send.textContent = t("broadcast.sending");
      showMessage(status, "");
      try {
        const r = await api("/api/notifications/send", { method: "POST", body: { message: text.value } });
        fill(report,
          section(t("broadcast.report")),
          r.dry_run && h("p", { class: "banner" }, t("broadcast.test_mode")),
          h("div", { class: "list form-foot" }, r.results.map((x) => h("div", { class: "result" },
            h("span", { class: `pill ${x.status}` }, x.status === "dry_run" ? "test" : x.status),
            h("span", {}, x.name),
            h("span", { class: "muted small" }, x.phone || ""),
            x.detail && !["sent", "dry_run"].includes(x.status) && h("span", { class: "why" }, x.detail)))));
        showMessage(status, t("broadcast.summary", r), r.failed ? "error" : "ok");
        text.value = "";
        updateChars();
      } catch (error) {
        showMessage(status, error.message);
      } finally {
        send.disabled = false;
        send.textContent = sendLabel;
      }
    },
  }, field(t("broadcast.message"), text), chars, h("div", { class: "form-foot" }, send), status);

  return {
    title: t("broadcast.title"),
    back: "#/profile",
    body: [
      h("p", { class: "muted" }, recipients ? t("broadcast.intro", { n: recipients }) : t("broadcast.nobody")),
      h("div", { class: "card form-foot" }, form),
      report,
    ],
  };
}
