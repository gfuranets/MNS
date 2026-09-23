/* script.js - the app. Requires auth.js to be loaded first.

   Every screen is a function that fetches what it needs and returns
   { title, back, actions, tab, body }. render() picks the function from the
   URL hash and puts the result on the page. User data only ever reaches the
   DOM through h(), which sets textContent - never innerHTML. */

const $view = document.getElementById("view");
const $top = document.getElementById("topbar");
const $tabs = document.getElementById("tabbar");

const MESSAGE_LIMIT = 1000;   // must match NotificationCreate in schema.py

const STATUS_LABEL = { overdue: "Overdue", due_soon: "Due soon", up_to_date: "Up to date" };
const STYLE_LABEL = { off: "Off", gentle: "Gentle nudges", frequent: "Frequent" };
const LANGUAGE_LABEL = { en: "English", lv: "Latviešu", ru: "Русский" };
const RISK_LABEL = {
  family_cancer: "Cancer in family",
  family_diabetes: "Diabetes in family",
  family_heart: "Heart disease in family",
};
const COUNTRIES = [
  "Latvia", "Lithuania", "Estonia", "Finland", "Sweden", "Norway", "Denmark",
  "Poland", "Germany", "Netherlands", "Ireland", "United Kingdom", "Ukraine",
  "Georgia", "United States",
];

let me = null;          // the logged-in user, from /api/me
let catalog = null;     // /api/checkup-types, loaded once
let renderId = 0;       // drops a slow screen if the user has already moved on

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
  trail.push(location.hash);
  window.addEventListener("hashchange", () => {
    if (replacing) trail[trail.length - 1] = location.hash;
    else if (trail.length > 1 && trail[trail.length - 2] === location.hash) trail.pop();
    else trail.push(location.hash);
    replacing = false;
    render();
  });
  render();
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
  el.append(...children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false));
  return el;
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

const localIso = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const todayIso = () => localIso(new Date());

function fmtDate(iso) {
  if (!iso) return "";
  return new Date(`${iso}T00:00`).toLocaleDateString("en-GB", {
    day: "numeric", month: "short", year: "numeric",
  });
}

function fmtWhen(iso) {
  return new Date(iso).toLocaleString("en-GB", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

const capitalise = (s) => s.charAt(0).toUpperCase() + s.slice(1);

async function saveBlob(res, fallbackName) {
  const blob = await res.blob();
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(res.headers.get("Content-Disposition") || "");
  const a = h("a", {
    href: URL.createObjectURL(blob),
    download: match ? decodeURIComponent(match[1]) : fallbackName,
  });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

async function getCatalog() {
  if (!catalog) catalog = await api("/api/checkup-types");
  return catalog;
}

/* --------------------------------------------------------------------------
   router
   -------------------------------------------------------------------------- */

const ROUTES = [
  [/^\/home$/, viewHome],
  [/^\/schedule$/, viewSchedule],
  [/^\/checkup\/(\d+)$/, viewCheckup],
  [/^\/log$/, viewLog],
  [/^\/log\/new$/, viewLogNew],
  [/^\/prep$/, viewPrep],
  [/^\/settings$/, viewSettings],
  [/^\/settings\/notifications$/, viewReminderStyle],
  [/^\/settings\/channels$/, viewChannels],
  [/^\/settings\/language$/, viewLanguage],
  [/^\/settings\/profile$/, () => viewProfile(false)],
  [/^\/vaccinations$/, viewVaccinations],
  [/^\/privacy$/, viewPrivacy],
  [/^\/inbox$/, viewInbox],
  [/^\/broadcast$/, viewBroadcast],
  [/^\/onboarding$/, () => viewProfile(true)],
  [/^\/onboarding\/reminders$/, viewOnboardingReminders],
];

async function render() {
  const [path, queryString] = (location.hash.slice(1) || "/home").split("?");
  const query = new URLSearchParams(queryString);

  // Nothing can be planned without a profile, so finish onboarding first.
  if (!me.profile_complete && !path.startsWith("/onboarding")) {
    replace("#/onboarding");
    return;
  }

  const route = ROUTES.find(([pattern]) => pattern.test(path));
  if (!route) return replace("#/home");
  const params = path.match(route[0]).slice(1);

  const id = ++renderId;
  $view.replaceChildren(h("p", { class: "loading" }, "Loading…"));

  let screen;
  try {
    screen = await route[1](...params, query);
  } catch (error) {
    screen = {
      title: "Something went wrong",
      back: "#/home",
      body: [
        h("p", { class: "message error" }, error.message),
        h("div", { class: "form-foot" },
          h("button", { class: "btn outline", onclick: render }, "Try again")),
      ],
    };
  }
  if (id !== renderId) return;   // the user navigated away while we were loading

  paint(screen);
}

function paint({ title, back: backTo, close, actions = [], tab = null, body }) {
  const left = backTo || close
    ? h("button", {
        class: "icon-btn",
        "aria-label": close ? "Close" : "Back",
        onclick: () => back(backTo || close),
      }, close ? "✕" : "←")
    : null;

  // The close button sits on the right, as in the log-entry mockup.
  $top.replaceChildren(...[close ? null : left, h("h1", {}, title), ...actions, close ? left : null].filter(Boolean));
  $view.replaceChildren(...[body].flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false));

  $tabs.hidden = tab === null;
  for (const a of $tabs.querySelectorAll("a")) a.classList.toggle("active", a.dataset.tab === tab);
  document.title = `${title} - Health Companion`;
  window.scrollTo(0, 0);
}

/* --------------------------------------------------------------------------
   shared pieces
   -------------------------------------------------------------------------- */

function statusBadge(item) {
  if (item.status === "up_to_date") return h("span", { class: "check", "aria-label": "Up to date" }, "✓");
  return h("span", { class: `pill ${item.status}` }, STATUS_LABEL[item.status]);
}

function scheduleRow(item) {
  return h("a", { class: "row", href: `#/checkup/${item.id}` },
    h("div", { class: "grow" },
      h("div", { class: "title" }, item.name),
      h("div", { class: "sub" }, item.status_text),
      item.snoozed_until && h("div", { class: "sub" }, `Reminders paused until ${fmtDate(item.snoozed_until)}`),
    ),
    statusBadge(item),
    h("span", { class: "chev", "aria-hidden": "true" }, "›"),
  );
}

function label(text, kind) {
  return h("h2", { class: `label ${kind || ""}` }, text);
}

function empty(text, action) {
  return h("div", { class: "empty" }, h("p", {}, text), action && h("div", { class: "form-foot" }, action));
}

function box(caption, input) {
  return h("label", { class: "box" }, h("span", { class: "cap" }, caption), input);
}

function choice({ type = "radio", name, value, checked, title, text, onchange }) {
  return h("label", { class: "choice" },
    h("input", { type, name, value, checked, onchange }),
    h("div", {}, h("div", { class: "title" }, title), text && h("div", { class: "muted small" }, text)),
  );
}

function channelsText(user) {
  const on = [user.remind_push && "Push", user.remind_sms && "SMS"].filter(Boolean);
  return on.length ? on.join(" + ") : "None";
}

async function saveSettings(changes, message = "Saved") {
  me = await api("/api/me/settings", { method: "PATCH", body: changes });
  toast(message);
}

/* --------------------------------------------------------------------------
   home
   -------------------------------------------------------------------------- */

async function viewHome() {
  const data = await api("/api/home");
  const { counts } = data;
  const total = counts.overdue + counts.due_soon + counts.up_to_date;

  const bell = h("a", { class: "icon-btn", href: "#/inbox", "aria-label": `Notifications, ${data.unread_notifications} unread` },
    "🔔",
    data.unread_notifications > 0 && h("span", { class: "badge" }, String(data.unread_notifications)),
  );
  const gear = h("a", { class: "icon-btn", href: "#/settings", "aria-label": "Settings" }, "⚙");

  return {
    title: `Hi, ${data.name}`,
    actions: [bell, gear],
    tab: "home",
    body: [
      data.urgent && h("a", { class: "urgent", href: `#/checkup/${data.urgent.id}` },
        h("div", { class: "kicker" }, "⚠ Overdue"),
        h("div", { class: "flex" },
          h("span", { class: "title" }, data.urgent.name),
          h("span", { "aria-hidden": "true" }, "›")),
        h("div", { class: "muted small" }, capitalise(data.urgent.status_text)),
      ),

      h("div", { class: "counts" },
        h("a", { href: "#/schedule" }, h("strong", {}, String(counts.up_to_date)), "up to date"),
        h("a", { href: "#/schedule" }, h("strong", {}, String(counts.due_soon)), "due soon"),
        h("a", { href: "#/schedule", class: counts.overdue ? "has-overdue" : null },
          h("strong", {}, String(counts.overdue)), "overdue"),
      ),

      h("a", { class: "btn primary", href: "#/log/new" }, "+ Log something you did"),

      label("Coming up"),
      data.coming_up.length
        ? data.coming_up.map(scheduleRow)
        : empty(total
            ? "Nothing due in the next 30 days."
            : "No checks apply to your profile yet. Check your birth year, sex and country in Settings."),
    ],
  };
}

/* --------------------------------------------------------------------------
   schedule
   -------------------------------------------------------------------------- */

async function viewSchedule(query) {
  const coverage = query.get("coverage") || "all";
  const items = await api(`/api/schedule?coverage=${coverage}`);

  const chip = (value, text) => h("button", {
    "aria-pressed": String(coverage === value),
    onclick: () => replace(value === "all" ? "#/schedule" : `#/schedule?coverage=${value}`),
  }, text);

  const group = (status, heading, kind) => {
    const rows = items.filter((i) => i.status === status);
    return rows.length ? [label(heading, kind), rows.map(scheduleRow)] : null;
  };

  return {
    title: "Your schedule",
    tab: "schedule",
    body: [
      h("div", { class: "chips" },
        chip("all", "All"), chip("state", "State-covered"), chip("private", "Private")),
      items.length
        ? [group("overdue", "Overdue", "overdue"), group("due_soon", "Due soon", "soon"), group("up_to_date", "Up to date")]
        : h("div", { class: "form-foot" }, empty(coverage === "all"
            ? "No checks apply to your profile yet."
            : `No ${coverage === "state" ? "state-covered" : "private"} checks on your schedule.`)),
    ],
  };
}

/* --------------------------------------------------------------------------
   item detail
   -------------------------------------------------------------------------- */

async function viewCheckup(id) {
  const d = await api(`/api/checkups/${id}`);

  const tagText = d.status === "up_to_date"
    ? `Up to date, next due ${fmtDate(d.due_on)}`
    : capitalise(d.status_text);

  const markDone = h("button", {
    class: "btn primary",
    onclick: async (e) => {
      e.target.disabled = true;
      try {
        await api(`/api/checkups/${id}/done`, { method: "POST", body: {} });
        toast(`${d.name} marked as done`);
        render();
      } catch (error) {
        toast(error.message);
        e.target.disabled = false;
      }
    },
  }, "Mark as done");

  const snoozeTo = (days) => async () => {
    try {
      const item = await api(`/api/checkups/${id}/snooze`, { method: "POST", body: { days } });
      toast(`Reminders paused until ${fmtDate(item.snoozed_until)}`);
      render();
    } catch (error) {
      toast(error.message);
    }
  };
  const snoozeOptions = h("div", { class: "snooze-options", hidden: true },
    h("button", { class: "btn outline", onclick: snoozeTo(7) }, "1 week"),
    h("button", { class: "btn outline", onclick: snoozeTo(30) }, "1 month"),
    h("button", { class: "btn outline", onclick: snoozeTo(90) }, "3 months"),
  );
  const remindLater = h("button", {
    class: "btn outline",
    "aria-expanded": "false",
    onclick: (e) => {
      snoozeOptions.hidden = !snoozeOptions.hidden;
      e.target.setAttribute("aria-expanded", String(!snoozeOptions.hidden));
    },
  }, "Remind me later");

  return {
    title: d.name,
    back: "#/schedule",
    body: [
      h("span", { class: `status-tag ${d.status}` }, tagText),
      d.snoozed_until && h("p", { class: "muted small" }, `Reminders paused until ${fmtDate(d.snoozed_until)}.`),

      h("p", { class: "prose" }, d.summary),
      h("p", { class: "muted small prose" },
        d.last_done
          ? `Last done ${fmtDate(d.last_done)}. Repeats every ${d.interval_months} months.`
          : `No record yet. Repeats every ${d.interval_months} months.`),

      d.source_url && h("p", { class: "prose" },
        h("a", { href: d.source_url, target: "_blank", rel: "noopener" }, "ⓘ View guideline source")),

      d.more_info && h("details", { class: "more" },
        h("summary", {}, "Show more info"), h("div", {}, d.more_info)),
      d.preparation && h("details", { class: "more", id: "prep" },
        h("summary", {}, "See preparation guide"), h("div", {}, d.preparation)),

      d.history.length > 0 && [label("Your history"), d.history.map(entryRow)],

      h("div", { class: "actions" },
        markDone,
        h("a", { class: "btn outline", href: `#/log/new?checkup=${d.id}` }, "Done on another day"),
        remindLater,
        snoozeOptions,
      ),
    ],
  };
}

/* --------------------------------------------------------------------------
   log
   -------------------------------------------------------------------------- */

function entryRow(entry) {
  const download = entry.attachment_name && h("button", {
    class: "link-btn",
    onclick: async () => {
      try {
        await saveBlob(await api(`/api/log/${entry.id}/attachment`, { raw: true }), entry.attachment_name);
      } catch (error) {
        toast(error.message);
      }
    },
  }, `📎 ${entry.attachment_name}`);

  const remove = h("button", {
    class: "link-btn",
    onclick: async () => {
      if (!confirm(`Delete "${entry.title}" from ${fmtDate(entry.done_on)}?`)) return;
      try {
        await api(`/api/log/${entry.id}`, { method: "DELETE" });
        toast("Entry deleted");
        render();
      } catch (error) {
        toast(error.message);
      }
    },
  }, "Delete");

  return h("div", { class: "row entry" },
    h("div", { class: "grow" },
      h("div", { class: "title" }, entry.title),
      h("div", { class: "sub" }, fmtDate(entry.done_on)),
      entry.notes && h("div", { class: "sub" }, entry.notes),
      h("div", { class: "actions-inline" }, download, remove),
    ),
    entry.checkup_type_id && h("a", {
      class: "chev", href: `#/checkup/${entry.checkup_type_id}`, "aria-label": `Open ${entry.title}`,
    }, "›"),
  );
}

async function viewLog() {
  const entries = await api("/api/log");
  return {
    title: "Your log",
    tab: "log",
    body: [
      h("a", { class: "btn primary", href: "#/log/new" }, "+ Log an entry"),
      label("Everything you've logged"),
      entries.length
        ? entries.map(entryRow)
        : empty("Nothing logged yet. Add something you've already done, even from years ago, and your schedule updates."),
    ],
  };
}

async function viewLogNew(query) {
  const types = await getCatalog();
  const preset = types.find((t) => String(t.id) === query.get("checkup"));

  const title = h("input", {
    type: "text", required: true, maxlength: 80, list: "checkup-names",
    placeholder: "e.g. Blood test", value: preset ? preset.name : "",
  });
  const matchNote = h("p", { class: "field-note" });
  const match = () => types.find((t) => t.name.toLowerCase() === title.value.trim().toLowerCase());
  const updateMatch = () => {
    const m = match();
    matchNote.textContent = !title.value.trim()
      ? "Pick from the list, or type anything you did."
      : m
        ? `Updates your ${m.name.toLowerCase()} schedule.`
        : "Not a tracked check. It will be saved to your log only.";
  };
  title.addEventListener("input", updateMatch);
  updateMatch();

  const when = h("input", { type: "date", required: true, max: todayIso(), value: todayIso() });
  const notes = h("textarea", { maxlength: 2000, placeholder: "Optional" });

  const fileName = h("span", {}, "+ Add photo or PDF (optional)");
  const file = h("input", {
    type: "file", accept: ".pdf,image/jpeg,image/png,image/webp,image/heic",
    onchange: () => {
      const f = file.files[0];
      fileName.textContent = f ? `📎 ${f.name}` : "+ Add photo or PDF (optional)";
    },
  });

  const message = h("p", { class: "message" });
  const save = h("button", { type: "submit", class: "btn primary" }, "Save entry");

  const form = h("form", {
    onsubmit: async (e) => {
      e.preventDefault();
      const f = file.files[0];
      if (f && f.size > 10 * 1024 * 1024) return showMessage(message, "That file is over 10 MB. Choose a smaller one.");
      save.disabled = true;
      showMessage(message, "");
      const m = match();
      try {
        const entry = await api("/api/log", {
          method: "POST",
          body: {
            title: title.value.trim(), done_on: when.value,
            checkup_type_id: m ? m.id : null, notes: notes.value.trim() || null,
          },
        });
        if (f) {
          const data = new FormData();
          data.append("file", f);
          await api(`/api/log/${entry.id}/attachment`, { method: "POST", form: data });
        }
        toast("Entry saved");
        replace(entry.checkup_type_id ? `#/checkup/${entry.checkup_type_id}` : "#/log");
      } catch (error) {
        showMessage(message, error.message);
        save.disabled = false;
      }
    },
  },
    box("What did you do?", title),
    h("datalist", { id: "checkup-names" }, types.map((t) => h("option", { value: t.name }))),
    matchNote,
    box("When?", when),
    h("p", { class: "field-note" }, "You can backdate this. Log something you already did."),
    h("label", { class: "dropzone" }, file, fileName),
    h("div", { class: "form-foot" }, box("Notes", notes)),
    h("div", { class: "form-foot" }, save),
    message,
  );

  return { title: "Log an entry", close: "#/log", body: form };
}

/* --------------------------------------------------------------------------
   prep
   -------------------------------------------------------------------------- */

async function viewPrep() {
  const guides = await api("/api/prep");
  return {
    title: "Get ready",
    tab: "prep",
    body: [
      h("p", { class: "muted" }, "How to prepare for what's overdue or coming up."),
      label("Your next checks"),
      guides.length
        ? guides.map((g) => h("details", { class: "row more" },
            h("summary", {},
              h("span", { class: "title" }, g.name), " ",
              h("span", { class: `pill ${g.status}` }, STATUS_LABEL[g.status])),
            h("div", {},
              h("p", { class: "prose" }, g.preparation),
              h("p", { class: "form-foot" }, h("a", { href: `#/checkup/${g.id}` }, "Open details"))),
          ))
        : empty("Nothing coming up that needs preparing."),
    ],
  };
}

/* --------------------------------------------------------------------------
   settings
   -------------------------------------------------------------------------- */

async function viewSettings() {
  const inbox = await api("/api/notifications");
  const item = (href, text, value) =>
    h("a", { href }, h("span", {}, text), h("span", { class: "value" }, value ? `${value} ›` : "›"));

  return {
    title: "Settings",
    tab: "settings",
    body: h("nav", { class: "settings-list" },
      item("#/settings/notifications", "Notifications", STYLE_LABEL[me.reminder_style]),
      item("#/settings/channels", "Reminder channels", channelsText(me)),
      item("#/inbox", "Inbox", inbox.unread ? `${inbox.unread} unread` : ""),
      item("#/settings/profile", "Health profile", me.country ? `${me.birth_year}, ${me.country}` : ""),
      item("#/vaccinations", "Vaccination passport", ""),
      item("#/settings/language", "Language", LANGUAGE_LABEL[me.language]),
      h("div", { class: "disabled" }, h("span", {}, "Family members"), h("span", { class: "value" }, "Coming soon")),
      item("#/privacy", "Privacy & data", ""),
      item("#/broadcast", "Message all patients", ""),
      h("button", { onclick: logOut }, "Sign out"),
    ),
  };
}

async function viewReminderStyle() {
  const result = h("p", { class: "message" });
  const options = [
    ["off", "Off", "No reminders. You can still check the app yourself."],
    ["gentle", "Gentle nudges", "Overdue checks, and anything due within a week. At most once a month per check."],
    ["frequent", "Frequent", "Everything due in the next 30 days. At most once a week per check."],
  ];

  const checkNow = h("button", {
    class: "btn outline",
    onclick: async () => {
      checkNow.disabled = true;
      try {
        const r = await api("/api/notifications/check", { method: "POST" });
        const parts = [];
        if (r.push) parts.push(`${r.push} reminder${r.push === 1 ? "" : "s"} sent to your inbox`);
        if (r.sms) parts.push(`1 text message ${r.dry_run ? "logged (SMS is in test mode)" : "sent"}`);
        showMessage(result, parts.length
          ? `${capitalise(parts.join(" and "))}.`
          : "Nothing new to remind you about. Either nothing is due, it's paused, or you were reminded recently.",
          "ok");
      } catch (error) {
        showMessage(result, error.message);
      } finally {
        checkNow.disabled = false;
      }
    },
  }, "Check for reminders now");

  return {
    title: "Notifications",
    back: "#/settings",
    body: [
      h("p", { class: "muted" }, "How often should we remind you about checks that are due?"),
      h("div", { class: "form-foot" },
        options.map(([value, title, text]) => choice({
          name: "style", value, title, text, checked: me.reminder_style === value,
          onchange: () => saveSettings({ reminder_style: value }, `Notifications: ${title}`).catch((e) => toast(e.message)),
        }))),
      label("Try it"),
      h("p", { class: "muted small" }, "Reminders are checked automatically every hour. This runs the check for you right now."),
      h("div", { class: "form-foot" }, checkNow),
      result,
    ],
  };
}

function channelFields(user) {
  const push = h("input", { type: "checkbox", checked: user.remind_push });
  const sms = h("input", { type: "checkbox", checked: user.remind_sms });
  const phone = h("input", { type: "tel", maxlength: 20, value: user.phone || "", placeholder: "20 123 456" });
  const row = (input, title, text) => h("label", { class: "choice" }, input,
    h("div", {}, h("div", { class: "title" }, title), h("div", { class: "muted small" }, text)));

  return {
    push, sms, phone,
    nodes: [
      row(push, "In-app notifications", "Shown in your inbox, under the bell on Home."),
      row(sms, "Text messages", "Sent to the number below."),
      h("div", { class: "form-foot" }, box("Phone number", phone)),
      h("p", { class: "field-note" }, "A local number works. The country from your profile adds the code."),
    ],
    values: () => ({ remind_push: push.checked, remind_sms: sms.checked, phone: phone.value.trim() || null }),
  };
}

async function viewChannels() {
  const fields = channelFields(me);
  const message = h("p", { class: "message" });
  const save = h("button", { type: "submit", class: "btn primary" }, "Save channels");

  return {
    title: "Reminder channels",
    back: "#/settings",
    body: h("form", {
      onsubmit: async (e) => {
        e.preventDefault();
        save.disabled = true;
        try {
          await saveSettings(fields.values(), "Channels saved");
          back("#/settings");
        } catch (error) {
          showMessage(message, error.message);
          save.disabled = false;
        }
      },
    }, fields.nodes, h("div", { class: "form-foot" }, save), message),
  };
}

async function viewLanguage() {
  return {
    title: "Language",
    back: "#/settings",
    body: [
      Object.entries(LANGUAGE_LABEL).map(([value, title]) => choice({
        name: "language", value, title, checked: me.language === value,
        onchange: () => saveSettings({ language: value }, `Language: ${title}`).catch((e) => toast(e.message)),
      })),
      h("p", { class: "field-note form-foot" },
        "The app is in English for now. Your choice is saved and will be used when translations arrive."),
    ],
  };
}

/* --------------------------------------------------------------------------
   profile - onboarding step 2, and Settings > Health profile
   -------------------------------------------------------------------------- */

async function viewProfile(onboarding) {
  const thisYear = new Date().getFullYear();
  const year = h("input", {
    type: "number", required: true, min: 1900, max: thisYear, inputmode: "numeric",
    placeholder: "1994", value: me.birth_year || "",
  });

  const sexes = [["female", "Female"], ["male", "Male"], ["other", "Other"]];
  const sex = h("div", { class: "segmented", role: "radiogroup", "aria-label": "Sex" },
    sexes.map(([value, text]) => h("label", {},
      h("input", { type: "radio", name: "sex", value, required: true, checked: me.sex === value }),
      h("span", {}, text))));

  const countries = me.country && !COUNTRIES.includes(me.country) ? [me.country, ...COUNTRIES] : COUNTRIES;
  const country = h("select", { required: true },
    h("option", { value: "", disabled: true, selected: !me.country }, "Choose your country"),
    countries.map((c) => h("option", { value: c, selected: me.country === c }, c)));

  const saved = new Map(me.risk_factors.map((r) => [r.code, r.note]));
  const risks = Object.entries(RISK_LABEL).map(([code, text]) =>
    h("label", {}, h("input", { type: "checkbox", value: code, checked: saved.has(code) }), text));
  const otherBox = h("input", { type: "checkbox", value: "other", checked: saved.has("other") });
  const otherText = h("input", {
    class: "other-text", type: "text", maxlength: 200, placeholder: "type here…",
    value: saved.get("other") || "", oninput: () => { if (otherText.value.trim()) otherBox.checked = true; },
  });

  const message = h("p", { class: "message" });
  const save = h("button", { type: "submit", class: "btn primary" }, onboarding ? "Continue" : "Save profile");

  const form = h("form", {
    onsubmit: async (e) => {
      e.preventDefault();
      save.disabled = true;
      showMessage(message, "");
      const codes = [...form.querySelectorAll(".checklist input[type=checkbox]:checked")].map((c) => c.value);
      try {
        me = await api("/api/me/profile", {
          method: "PUT",
          body: {
            birth_year: Number(year.value),
            sex: form.querySelector("input[name=sex]:checked").value,
            country: country.value,
            risk_factors: codes.filter((c) => c !== "other"),
            risk_other: codes.includes("other") ? otherText.value.trim() || null : null,
          },
        });
        if (onboarding) {
          go("#/onboarding/reminders");
        } else {
          toast("Profile saved");
          back("#/settings");
        }
      } catch (error) {
        showMessage(message, error.message);
        save.disabled = false;
      }
    },
  },
    onboarding && h("div", { class: "steps" }, h("i", { class: "on" }), h("i", { class: "on" }), h("i"), h("span", {}, "Step 2 of 3")),
    box("Birth year", year),
    label("Sex"),
    sex,
    h("div", { class: "form-foot" }, box("Country", country)),
    label("Risk factors, optional"),
    h("div", { class: "checklist" }, risks,
      h("label", {}, otherBox, "Other:", otherText)),
    h("p", { class: "field-note" }, "Only used to suggest checks earlier or more often. Nothing here is required."),
    h("div", { class: "form-foot" }, save),
    message,
  );

  return {
    title: onboarding ? "Set up your profile" : "Health profile",
    back: onboarding ? null : "#/settings",
    body: form,
  };
}

async function viewOnboardingReminders() {
  let style = me.reminder_style;
  const styles = [
    ["gentle", "Gentle nudges", "Overdue checks and anything due within a week. At most once a month each."],
    ["frequent", "Frequent", "Everything due in the next 30 days. At most once a week each."],
    ["off", "Off", "I'll check the app myself."],
  ];
  const fields = channelFields(me);
  const message = h("p", { class: "message" });
  const finish = h("button", { type: "submit", class: "btn primary" }, "Finish");

  return {
    title: "Reminders",
    back: "#/onboarding",
    body: h("form", {
      onsubmit: async (e) => {
        e.preventDefault();
        finish.disabled = true;
        try {
          await saveSettings({ reminder_style: style, ...fields.values() }, "You're all set");
          replace("#/home");
        } catch (error) {
          showMessage(message, error.message);
          finish.disabled = false;
        }
      },
    },
      h("div", { class: "steps" }, h("i", { class: "on" }), h("i", { class: "on" }), h("i", { class: "on" }), h("span", {}, "Step 3 of 3")),
      h("p", { class: "muted" }, "How pushy should we be when a check is due?"),
      h("div", { class: "form-foot" }, styles.map(([value, title, text]) => choice({
        name: "style", value, title, text, checked: style === value, onchange: () => { style = value; },
      }))),
      label("Where to reach you"),
      fields.nodes,
      h("div", { class: "form-foot" }, finish),
      message,
    ),
  };
}

/* --------------------------------------------------------------------------
   vaccination passport
   -------------------------------------------------------------------------- */

async function viewVaccinations() {
  const vaccines = await api("/api/vaccinations");
  return {
    title: "Vaccination passport",
    back: "#/settings",
    body: [
      h("a", { class: "btn primary", href: "#/log/new" }, "+ Log a vaccination"),
      label("Recommended for you"),
      vaccines.length
        ? vaccines.map((v) => h("a", { class: "row", href: `#/checkup/${v.id}` },
            h("div", { class: "grow" },
              h("div", { class: "title" }, v.name),
              h("div", { class: "sub" }, v.doses.length
                ? `${v.doses.length} dose${v.doses.length === 1 ? "" : "s"}: ${v.doses.map(fmtDate).join(", ")}`
                : "No doses logged"),
              h("div", { class: "sub" }, v.last_done ? `Next due ${fmtDate(v.due_on)}` : "Log your last dose to see when the next is due"),
            ),
            statusBadge(v),
          ))
        : empty("No vaccinations apply to your profile."),
    ],
  };
}

/* --------------------------------------------------------------------------
   privacy
   -------------------------------------------------------------------------- */

async function viewPrivacy() {
  const exportBtn = h("button", {
    class: "btn outline",
    onclick: async () => {
      try {
        await saveBlob(await api("/api/me/export", { raw: true }), "my-health-data.json");
      } catch (error) {
        toast(error.message);
      }
    },
  }, "Download my data");

  const deleteBtn = h("button", {
    class: "btn danger",
    onclick: async () => {
      const typed = prompt("This permanently deletes your account, your log and any uploaded files.\n\nType DELETE to confirm.");
      if (typed !== "DELETE") return;
      try {
        await api("/api/me", { method: "DELETE" });
        token.clear();
        location.replace("login.html");
      } catch (error) {
        toast(error.message);
      }
    },
  }, "Delete my account");

  return {
    title: "Privacy & data",
    back: "#/settings",
    body: [
      h("p", { class: "prose" }, "We keep your name, email, birth year, sex, country, optional phone number and risk factors, plus what you log and the reminders we send."),
      h("p", { class: "prose muted" }, "Your data is never sold. Only your birth year is stored, not your full date of birth."),
      label("Your data"),
      exportBtn,
      h("p", { class: "field-note" }, "Everything we hold about you, as a JSON file."),
      label("Delete account"),
      deleteBtn,
    ],
  };
}

/* --------------------------------------------------------------------------
   inbox
   -------------------------------------------------------------------------- */

async function viewInbox() {
  const inbox = await api("/api/notifications");

  const open = (n) => async () => {
    try {
      if (!n.read_at) await api(`/api/notifications/${n.id}/read`, { method: "POST" });
    } catch { /* reading still works even if marking fails */ }
    if (n.checkup_type_id) go(`#/checkup/${n.checkup_type_id}`);
    else render();
  };

  const readAll = inbox.unread > 0 && h("button", {
    class: "link-btn small",
    onclick: async () => {
      await api("/api/notifications/read-all", { method: "POST" });
      render();
    },
  }, "Mark all read");

  return {
    title: "Notifications",
    back: "#/home",
    actions: [readAll].filter(Boolean),
    body: inbox.items.length
      ? inbox.items.map((n) => h("button", {
          class: `note kind-${n.kind}${n.read_at ? "" : " unread"}`, onclick: open(n),
        }, n.message, h("span", { class: "when" }, fmtWhen(n.created_at))))
      : empty("No notifications yet. Reminders show up here when a check is due.",
          h("a", { class: "btn outline", href: "#/settings/notifications" }, "Reminder settings")),
  };
}

/* --------------------------------------------------------------------------
   broadcast - text every user who has a phone number
   -------------------------------------------------------------------------- */

async function viewBroadcast() {
  const { recipients } = await api("/api/notifications/recipients");

  const text = h("textarea", {
    maxlength: MESSAGE_LIMIT, required: true,
    placeholder: "Your blood test results are ready. Please contact the clinic.",
  });
  const chars = h("p", { class: "field-note" });
  const updateChars = () => { chars.textContent = `${MESSAGE_LIMIT - text.value.length} characters left`; };
  text.addEventListener("input", updateChars);
  updateChars();

  const status = h("p", { class: "message" });
  const report = h("div", { class: "result-list" });
  const sendLabel = recipients === 1 ? "Send to 1 person" : `Send to ${recipients} people`;
  const send = h("button", { type: "submit", class: "btn primary", disabled: recipients === 0 }, sendLabel);

  const form = h("form", {
    onsubmit: async (e) => {
      e.preventDefault();
      send.disabled = true;
      send.textContent = "Sending…";
      showMessage(status, "");
      try {
        const r = await api("/api/notifications/send", { method: "POST", body: { message: text.value } });
        renderReport(report, r);
        const parts = [r.dry_run ? `${r.sent} logged (test mode)` : `${r.sent} sent`];
        if (r.skipped) parts.push(`${r.skipped} skipped`);
        if (r.failed) parts.push(`${r.failed} failed`);
        showMessage(status, parts.join(", "), r.failed ? "error" : "ok");
        text.value = "";
        updateChars();
      } catch (error) {
        showMessage(status, error.message);
      } finally {
        send.disabled = false;
        send.textContent = sendLabel;
      }
    },
  },
    box("Message", text), chars,
    h("div", { class: "form-foot" }, send),
    status,
  );

  return {
    title: "Message all patients",
    back: "#/settings",
    body: [
      h("p", { class: "muted" }, recipients === 0
        ? "Nobody has saved a phone number yet, so there is nobody to text."
        : `Sends a text message to the ${recipients} ${recipients === 1 ? "person" : "people"} who saved a phone number.`),
      h("div", { class: "form-foot" }, form),
      report,
    ],
  };
}

function renderReport(container, report) {
  container.replaceChildren(h("div", {},
    label("Delivery report"),
    report.dry_run && h("p", { class: "banner" },
      "Test mode: Twilio is not configured, so nothing left the server. Set TWILIO_SID, TWILIO_TOKEN and TWILIO_FROM in app/.env to send for real."),
    report.results.map((r) => h("div", { class: "result" },
      h("span", { class: `pill ${r.status}` }, r.status === "dry_run" ? "test" : r.status),
      h("span", {}, r.name),
      h("span", { class: "num" }, r.phone || "no number"),
      r.detail && r.status !== "sent" && r.status !== "dry_run" && h("span", { class: "why" }, r.detail),
    )),
  ));
}
