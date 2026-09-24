/* i18n.js - every word the app shows, in English and Latvian.
   Loaded by every page before anything else.

     t("home.greeting", { name: "Baiba" })   -> "Hi, Baiba"
     applyI18n(document)                     -> fills [data-i18n] / [data-i18n-placeholder]

   The language lives in localStorage so the sign-in page can use it before
   anyone is logged in; after login the saved profile language wins.

   Latvian numbers change the noun's case with the preposition:
     pēc / pirms / ik pēc + 1  -> genitive singular  (pēc 1 dienas)
     par                  + 1  -> accusative singular (par 1 dienu)
     any                 + 12  -> dative plural       (pēc 12 dienām)
   A number ending in 1 (but not 11) takes the singular. See span(). */

const LANG_KEY = "mns_lang";
const LANGS = { en: "English", lv: "Latviešu" };

let lang = (() => {
  try {
    const saved = localStorage.getItem(LANG_KEY);
    if (saved in LANGS) return saved;
  } catch { /* storage blocked - fall back below */ }
  return (navigator.language || "en").toLowerCase().startsWith("lv") ? "lv" : "en";
})();

function setLang(code) {
  if (!(code in LANGS)) return;
  lang = code;
  try { localStorage.setItem(LANG_KEY, code); } catch { /* ignore */ }
  document.documentElement.lang = code;
}

const STRINGS = {
  en: {
    "app.name": "Health Companion",
    "app.tagline": "Know what's due. Show up ready.",

    "nav.home": "Home", "nav.schedule": "Schedule", "nav.add": "Add",
    "nav.log": "Log", "nav.info": "Info",
    "nav.profile": "Profile", "nav.inbox": "Reminders",

    "common.back": "Back", "common.close": "Close", "common.save": "Save",
    "common.cancel": "Cancel", "common.delete": "Delete", "common.loading": "Loading…",
    "common.try_again": "Try again", "common.error_title": "Something went wrong",
    "common.continue": "Continue", "common.optional": "optional", "common.saved": "Saved",
    "common.open": "Open", "common.today": "Today",

    "status.overdue": "Late", "status.due_soon": "Upcoming", "status.up_to_date": "Up to date",
    "status.done": "Done", "status.missed": "Missed", "status.planned": "Planned",
    "strip.up_to_date": "up to date", "strip.due_soon": "upcoming", "strip.overdue": "late",

    "when.no_record": "No record yet",
    "when.today": "Due today",
    "when.in": "Due in {span}",
    "when.late": "Late by {span}",
    "when.next": "Next due {date}",
    "when.last": "Last done {date}",
    "when.never": "Never logged",

    "cat.appointment": "Appointment", "cat.vaccination": "Vaccination",
    "cat.screening": "Screening", "cat.checkup": "Check-up", "cat.test": "Test",
    "cat.medication": "Medication", "cat.procedure": "Procedure", "cat.other": "Other",

    "unit.day": "days", "unit.week": "weeks", "unit.month": "months", "unit.year": "years",

    "login.title": "Sign in",
    "login.email": "Email",
    "login.password": "Password",
    "login.submit": "Sign in",
    "login.new": "New here?",
    "login.create": "Create an account",
    "login.language": "Language",
    "login.privacy": "Your health data is never sold.",

    "signup.title": "Create your account",
    "signup.step": "Step {n} of 3",
    "signup.name": "First name",
    "signup.surname": "Surname",
    "signup.password_hint": "At least 8 characters.",
    "signup.phone": "Phone",
    "signup.phone_hint": "Only used for text reminders, and only if you turn them on.",
    "signup.have_account": "Already have an account?",

    "consent.title": "How we use your data",
    "consent.intro": "Before you add anything, here is exactly what this app keeps and why.",
    "consent.what_h": "What we store",
    "consent.what": "Your name, email, phone, birth date, gender and country; health conditions you or your family have; what you log, plan and upload; and the reminders we send you.",
    "consent.why_h": "Why",
    "consent.why": "To work out which check-ups apply to you, when they are due, and to remind you. Nothing else.",
    "consent.who_h": "Who sees it",
    "consent.who": "Only you. We never sell your data or share it with advertisers or insurers.",
    "consent.control_h": "You stay in control",
    "consent.control": "Download everything or delete your account at any time, from your profile.",
    "consent.advice_h": "Not medical advice",
    "consent.advice": "Reminders follow public screening guidelines. Your doctor's advice comes first.",
    "consent.agree": "I agree to my data being used as described above",
    "consent.submit": "Agree and continue",
    "consent.given": "You agreed on {date}.",

    "profile_form.title": "Your health profile",
    "profile_form.intro": "Birth date, gender and country decide which check-ups we suggest.",
    "profile_form.birth_date": "Birth date",
    "profile_form.gender": "Gender",
    "profile_form.female": "Female", "profile_form.male": "Male", "profile_form.other": "Other",
    "profile_form.country": "Country",
    "profile_form.choose_country": "Choose your country",
    "profile_form.risks": "Health conditions",
    "profile_form.risks_hint": "Tick what applies to you or runs in your family. It only makes some checks start earlier or come more often.",
    "profile_form.me": "Me", "profile_form.family": "Family",
    "risk.cancer": "Cancer", "risk.diabetes": "Diabetes", "risk.heart": "Heart disease", "risk.other": "Other",
    "profile_form.other_ph": "Describe…",
    "profile_form.finish": "Finish",
    "profile_form.save": "Save profile",
    "profile_form.saved": "Profile saved",

    "home.greeting": "Hi, {name}",
    "home.accept": "Accept",
    "home.mark_done": "Mark as done",
    "home.next_up": "Next up",
    "home.log_button": "Log something you did",
    "home.coming_up": "Coming up",
    "home.nothing_due": "Nothing due in the next 30 days.",
    "home.no_items": "Nothing on your schedule yet. Check your profile, or add your own plan.",
    "home.plans": "Getting ready",
    "home.progress": "{done} of {total} ticked",
    "home.waiting": "{n} more reminders waiting",
    "home.all_clear": "You're all caught up.",
    "home.shortcuts": "Personal data",

    "great.title": "Great job taking care of yourself!",
    "great.logged": "Saved to your log.",
    "great.next": "Next one: {date}",
    "great.ok": "Thanks",

    "done.title": "Log something you did",
    "done.from": "From your reminders",
    "done.from_hint": "Tap Done on the one you completed.",
    "done.none": "Nothing is waiting right now.",
    "done.button": "Done",
    "done.confirm_title": "When did you do it?",
    "done.date": "Date",
    "done.backdate_hint": "You can pick a past date.",
    "done.own": "Add your own",
    "done.own_hint": "An extra visit, a test, or anything outside the guidelines.",
    "done.what": "What did you do?",
    "done.what_ph": "e.g. Allergy test",
    "done.category": "Category",
    "done.custom_category": "Your own category",
    "done.custom_ph": "e.g. Dermatology",
    "done.renew_on": "Renew by (if you know)",
    "done.notes": "Notes",
    "done.attach": "Add photo or PDF",
    "done.save": "Save entry",
    "done.file_too_big": "That file is over 10 MB. Choose a smaller one.",

    "schedule.title": "Schedule",
    "schedule.all": "All", "schedule.recommended": "Recommended", "schedule.mine": "My own",
    "schedule.list": "Everything on your schedule",
    "schedule.day_empty": "Nothing on this day.",
    "schedule.prev": "Previous month", "schedule.next": "Next month",
    "schedule.empty": "Nothing here yet.",

    "checkup.guideline": "Guideline",
    "checkup.source": "View guideline source",
    "checkup.research": "Based on public, research-based screening guidelines.",
    "checkup.repeats": "Repeats every {n} months",
    "checkup.more": "Show more info",
    "checkup.prep": "How to prepare",
    "checkup.open_guide": "Open the preparation guide",
    "checkup.history": "Your history",
    "checkup.other_day": "Done on another day",
    "checkup.english_only": "Details are in English for now.",

    "task.doctor": "Doctor",
    "task.specialty": "Specialty",
    "task.manual": "On the dates you picked",
    "task.dates": "Dates",
    "task.missed": "Missed",
    "task.add_date": "Add a date",
    "task.delete": "Delete this plan",
    "task.delete_confirm": "Delete “{title}” and its future dates? Your log stays.",
    "task.deleted": "Plan deleted",
    "task.marked_missed": "Marked as missed",

    "add.title": "Add to your plan",
    "add.type": "What is it?",
    "add.name": "Name",
    "add.name_ph": "e.g. Physiotherapy",
    "add.first_date": "First date",
    "add.how_often": "How often",
    "add.remind": "Email reminders",
    "add.remind_hint": "Emails start when it is within your reminder window (Profile > Reminders) and stop when it is done or deleted.",
    "add.remind_once": "Once per date",
    "add.remind_daily": "Every day until done",
    "add.remind_weekly": "Every week until done",
    "add.remind_minute": "Every minute (demo)",
    "add.repeats": "Repeats",
    "add.manual": "Pick dates",
    "add.every": "Every",
    "add.more_dates": "More dates",
    "add.add_date": "Add another date",
    "add.description": "Description",
    "add.doctor_name": "Doctor's name",
    "add.doctor_specialty": "Specialty",
    "add.specialty_ph": "e.g. Cardiologist",
    "add.save": "Add to plan",
    "add.saved": "Added to your plan",

    "log.title": "Log",
    "log.category": "Category",
    "log.all": "All categories",
    "log.empty": "Nothing here yet.",
    "log.add": "Log something",
    "log.delete_confirm": "Delete “{title}” from {date}?",
    "log.deleted": "Entry deleted",

    "info.title": "Preparation guides",
    "info.search": "Search, e.g. gastroscopy",
    "info.plans": "Your upcoming preparations",
    "info.library": "All guides",
    "info.no_results": "No guide matches “{q}”.",

    "labs.title": "Blood test results",
    "labs.summary": "{n} blood tests · latest {date}",
    "labs.out_of_range": "{n} out of range in the latest test",
    "labs.all_in_range": "Everything in range in the latest test",
    "labs.all": "All",
    "labs.flag.low": "Low", "labs.flag.normal": "In range", "labs.flag.high": "High",
    "labs.range": "Normal range",
    "labs.range_between": "Normal range {low}–{high}",
    "labs.range_under": "Normal range under {high}",
    "labs.range_over": "Normal range over {low}",
    "labs.show_values": "Show all values",
    "labs.date": "Date", "labs.value": "Value",
    "labs.empty": "No lab results yet.",
    "labs.highlight": "Highlighted: the blood test of {date}",
    "labs.see": "See results",
    "labcat.vitamin": "Vitamins", "labcat.mineral": "Minerals", "labcat.heavy_metal": "Heavy metals",
    "labcat.blood_count": "Blood count", "labcat.metabolic": "Blood sugar", "labcat.lipid": "Cholesterol",
    "labcat.hormone": "Hormones", "labcat.inflammation": "Inflammation",

    "checks.title": "State-paid checks",
    "checks.intro": "Preventive checks the Latvian state pays for, as listed by the National Health Service (NVD) and SPKC.",
    "checks.for_you": "On your schedule",
    "checks.not_for_you": "Not for your age or sex right now",
    "checks.women": "Women", "checks.men": "Men", "checks.everyone": "Everyone",
    "checks.ages": "{min}–{max}", "checks.from": "from {min}",
    "schedule.all_checks": "All state-paid checks",

    "proc.checklist": "Checklist",
    "proc.before": "{n} h before",
    "proc.set_reminder": "Set reminder",
    "proc.when": "When is your appointment?",
    "proc.remind_about": "Remind me about",
    "proc.save": "Save reminders",
    "proc.saved": "Reminders set",
    "proc.appointment": "Appointment {when}",
    "proc.remove": "Remove",
    "proc.removed": "Preparation removed",
    "proc.reminded": "Reminded",
    "proc.remind_at": "Reminder {when}",
    "proc.remind_now": "Reminder right away - that time has already passed",
    "proc.past": "Pick a time in the future.",


    "profile.title": "Profile",
    "profile.edit": "Personal data",
    "profile.passport": "Vaccination passport",
    "profile.family": "Family members",
    "profile.family_add": "Add family member",
    "profile.soon": "Coming soon",
    "profile.reminders": "Reminders",
    "profile.inbox": "Reminder inbox",
    "profile.language": "Language",
    "profile.privacy": "Privacy & data",
    "profile.broadcast": "Message all patients",
    "profile.sign_out": "Sign out",
    "profile.years": "{n} years",

    "settings.title": "Reminders",
    "settings.on": "Daily reminders",
    "settings.on_hint": "Once a day, every day, until each item is marked done.",
    "settings.lead": "Start reminding",
    "settings.lead_0": "On the day",
    "settings.lead_1": "1 day before",
    "settings.lead_3": "3 days before",
    "settings.lead_7": "1 week before",
    "settings.lead_14": "2 weeks before",
    "settings.lead_30": "1 month before",
    "settings.channels": "Where to reach you",
    "settings.push": "In the app",
    "settings.push_hint": "Your reminder inbox, behind the bell.",
    "settings.email": "Email",
    "settings.email_hint": "To {email}, once for each due date - no daily repeats.",
    "settings.email_sent": "Check {email}.",
    "settings.email_test": "Email is in test mode (no Gmail keys), so it was only logged.",
    "settings.sms": "Text message",
    "settings.sms_hint": "One text a day listing everything due.",
    "settings.phone": "Phone number",
    "settings.phone_hint": "A local number works: your country adds the code.",
    "settings.check_now": "Check for reminders now",
    "settings.check_sent": "Sent {n} new reminders.",
    "settings.check_none": "Nothing new. Either nothing is due, or you were already reminded today.",
    "settings.sms_test": "Texts are in test mode (no Twilio keys), so they were only logged.",

    "inbox.title": "Reminder inbox",
    "inbox.accept_all": "Accept all",
    "inbox.empty": "No reminders yet.",
    "inbox.accepted": "Accepted",
    "inbox.waiting": "Waiting",

    "passport.title": "Vaccination passport",
    "passport.given": "Given",
    "passport.renew": "Renew by",
    "passport.not_recorded": "Not recorded yet",
    "passport.unknown": "Renewal date unknown",
    "passport.add": "Add a vaccine",
    "passport.recommended": "Recommended for you",

    "privacy.title": "Privacy & data",
    "privacy.export": "Download my data",
    "privacy.export_hint": "Everything we hold about you, as a JSON file.",
    "privacy.delete": "Delete my account",
    "privacy.delete_confirm": "This permanently deletes your account, your log and any uploaded files.\n\nType DELETE to confirm.",

    "broadcast.title": "Message all patients",
    "broadcast.intro": "Sends a text message to everyone who saved a phone number ({n}).",
    "broadcast.nobody": "Nobody has saved a phone number yet.",
    "broadcast.message": "Message",
    "broadcast.chars": "{n} characters left",
    "broadcast.send": "Send to {n}",
    "broadcast.sending": "Sending…",
    "broadcast.report": "Delivery report",
    "broadcast.test_mode": "Test mode: Twilio is not configured, so nothing left the server.",
    "broadcast.summary": "{sent} sent, {skipped} skipped, {failed} failed",
  },

  lv: {
    "app.name": "Veselības palīgs",
    "app.tagline": "Ziniet, kas jādara. Ierodieties sagatavoti.",

    "nav.home": "Sākums", "nav.schedule": "Kalendārs", "nav.add": "Pievienot",
    "nav.log": "Žurnāls", "nav.info": "Info",
    "nav.profile": "Profils", "nav.inbox": "Atgādinājumi",

    "common.back": "Atpakaļ", "common.close": "Aizvērt", "common.save": "Saglabāt",
    "common.cancel": "Atcelt", "common.delete": "Dzēst", "common.loading": "Ielādē…",
    "common.try_again": "Mēģināt vēlreiz", "common.error_title": "Kaut kas nogāja greizi",
    "common.continue": "Turpināt", "common.optional": "nav obligāti", "common.saved": "Saglabāts",
    "common.open": "Atvērt", "common.today": "Šodien",

    "status.overdue": "Nokavēts", "status.due_soon": "Drīzumā", "status.up_to_date": "Kārtībā",
    "status.done": "Paveikts", "status.missed": "Izlaists", "status.planned": "Plānots",
    "strip.up_to_date": "kārtībā", "strip.due_soon": "drīzumā", "strip.overdue": "nokavēti",

    "when.no_record": "Vēl nav ieraksta",
    "when.today": "Termiņš šodien",
    "when.in": "Termiņš pēc {span}",
    "when.late": "Nokavēts par {span}",
    "when.next": "Nākamais termiņš {date}",
    "when.last": "Pēdējo reizi {date}",
    "when.never": "Nav ierakstīts",

    "cat.appointment": "Vizīte", "cat.vaccination": "Vakcinācija",
    "cat.screening": "Skrīnings", "cat.checkup": "Pārbaude", "cat.test": "Analīzes",
    "cat.medication": "Medikamenti", "cat.procedure": "Procedūra", "cat.other": "Cits",

    "unit.day": "dienas", "unit.week": "nedēļas", "unit.month": "mēneši", "unit.year": "gadi",

    "login.title": "Pieteikties",
    "login.email": "E-pasts",
    "login.password": "Parole",
    "login.submit": "Pieteikties",
    "login.new": "Jauns lietotājs?",
    "login.create": "Izveidot kontu",
    "login.language": "Valoda",
    "login.privacy": "Jūsu veselības dati netiek pārdoti.",

    "signup.title": "Izveidojiet kontu",
    "signup.step": "{n}. solis no 3",
    "signup.name": "Vārds",
    "signup.surname": "Uzvārds",
    "signup.password_hint": "Vismaz 8 rakstzīmes.",
    "signup.phone": "Tālrunis",
    "signup.phone_hint": "Tiek izmantots tikai īsziņu atgādinājumiem un tikai tad, ja tos ieslēgsiet.",
    "signup.have_account": "Jau ir konts?",

    "consent.title": "Kā mēs izmantojam jūsu datus",
    "consent.intro": "Pirms kaut ko pievienojat, lūk, ko tieši šī lietotne glabā un kāpēc.",
    "consent.what_h": "Ko mēs glabājam",
    "consent.what": "Jūsu vārdu, e-pastu, tālruni, dzimšanas datumu, dzimumu un valsti; slimības, kas ir jums vai jūsu ģimenē; to, ko ierakstāt, plānojat un augšupielādējat; un atgādinājumus, ko jums sūtām.",
    "consent.why_h": "Kāpēc",
    "consent.why": "Lai noteiktu, kuras pārbaudes jums ir ieteicamas, kad tās jāveic, un lai jums atgādinātu. Neko citu.",
    "consent.who_h": "Kas to redz",
    "consent.who": "Tikai jūs. Mēs nekad nepārdodam jūsu datus un nedodam tos reklāmdevējiem vai apdrošinātājiem.",
    "consent.control_h": "Kontrole paliek jums",
    "consent.control": "Jebkurā laikā profilā varat lejupielādēt visus datus vai dzēst kontu.",
    "consent.advice_h": "Tas nav medicīnisks padoms",
    "consent.advice": "Atgādinājumi balstās uz publiskām skrīninga vadlīnijām. Ārsta ieteikumi ir svarīgāki.",
    "consent.agree": "Piekrītu, ka mani dati tiek izmantoti, kā aprakstīts iepriekš",
    "consent.submit": "Piekrist un turpināt",
    "consent.given": "Jūs piekritāt {date}.",

    "profile_form.title": "Jūsu veselības profils",
    "profile_form.intro": "Dzimšanas datums, dzimums un valsts nosaka, kuras pārbaudes iesakām.",
    "profile_form.birth_date": "Dzimšanas datums",
    "profile_form.gender": "Dzimums",
    "profile_form.female": "Sieviete", "profile_form.male": "Vīrietis", "profile_form.other": "Cits",
    "profile_form.country": "Valsts",
    "profile_form.choose_country": "Izvēlieties valsti",
    "profile_form.risks": "Veselības stāvoklis",
    "profile_form.risks_hint": "Atzīmējiet, kas attiecas uz jums vai ir jūsu ģimenē. Tas tikai liek dažām pārbaudēm sākties agrāk vai notikt biežāk.",
    "profile_form.me": "Man", "profile_form.family": "Ģimenē",
    "risk.cancer": "Vēzis", "risk.diabetes": "Diabēts", "risk.heart": "Sirds slimības", "risk.other": "Cits",
    "profile_form.other_ph": "Aprakstiet…",
    "profile_form.finish": "Pabeigt",
    "profile_form.save": "Saglabāt profilu",
    "profile_form.saved": "Profils saglabāts",

    "home.greeting": "Sveiki, {name}!",
    "home.accept": "Pieņemt",
    "home.mark_done": "Atzīmēt kā paveiktu",
    "home.next_up": "Nākamais",
    "home.log_button": "Ierakstīt paveikto",
    "home.coming_up": "Tuvākie",
    "home.nothing_due": "Nākamajās 30 dienās nekas nav jādara.",
    "home.no_items": "Jūsu plānā vēl nekā nav. Pārbaudiet profilu vai pievienojiet savu plānu.",
    "home.plans": "Gatavošanās",
    "home.progress": "Atzīmēti {done} no {total}",
    "home.waiting": "Gaida vēl atgādinājumi: {n}",
    "home.all_clear": "Viss ir izdarīts.",
    "home.shortcuts": "Personīgie dati",

    "great.title": "Lieliski, ka rūpējaties par sevi!",
    "great.logged": "Saglabāts žurnālā.",
    "great.next": "Nākamā reize: {date}",
    "great.ok": "Paldies",


    "done.title": "Ierakstīt paveikto",
    "done.from": "No jūsu atgādinājumiem",
    "done.from_hint": "Nospiediet Paveikts pie tā, ko izdarījāt.",
    "done.none": "Pašlaik nekas negaida.",
    "done.button": "Paveikts",
    "done.confirm_title": "Kad tas notika?",
    "done.date": "Datums",
    "done.backdate_hint": "Varat izvēlēties pagātnes datumu.",
    "done.own": "Pievienot savu",
    "done.own_hint": "Papildu vizīte, analīzes vai kas cits ārpus vadlīnijām.",
    "done.what": "Ko jūs darījāt?",
    "done.what_ph": "piem., alerģijas tests",
    "done.category": "Kategorija",
    "done.custom_category": "Sava kategorija",
    "done.custom_ph": "piem., dermatoloģija",
    "done.renew_on": "Atjaunot līdz (ja zināms)",
    "done.notes": "Piezīmes",
    "done.attach": "Pievienot foto vai PDF",
    "done.save": "Saglabāt ierakstu",
    "done.file_too_big": "Fails ir lielāks par 10 MB. Izvēlieties mazāku.",

    "schedule.title": "Kalendārs",
    "schedule.all": "Visi", "schedule.recommended": "Ieteiktie", "schedule.mine": "Mani",
    "schedule.list": "Viss jūsu plānā",
    "schedule.day_empty": "Šajā dienā nekā nav.",
    "schedule.prev": "Iepriekšējais mēnesis", "schedule.next": "Nākamais mēnesis",
    "schedule.empty": "Šeit vēl nekā nav.",

    "checkup.guideline": "Vadlīnija",
    "checkup.source": "Skatīt vadlīnijas avotu",
    "checkup.research": "Balstīts uz publiskām, pētījumos pamatotām skrīninga vadlīnijām.",
    "checkup.repeats": "Atkārtojas ik pēc {n} mēnešiem",
    "checkup.more": "Vairāk informācijas",
    "checkup.prep": "Kā sagatavoties",
    "checkup.open_guide": "Atvērt sagatavošanās ceļvedi",
    "checkup.history": "Jūsu vēsture",
    "checkup.other_day": "Paveikts citā dienā",
    "checkup.english_only": "Sīkāka informācija pagaidām ir tikai angļu valodā.",

    "task.doctor": "Ārsts",
    "task.specialty": "Specialitāte",
    "task.manual": "Jūsu izvēlētajos datumos",
    "task.dates": "Datumi",
    "task.missed": "Izlaists",
    "task.add_date": "Pievienot datumu",
    "task.delete": "Dzēst šo plānu",
    "task.delete_confirm": "Dzēst “{title}” un tā nākamos datumus? Žurnāls saglabāsies.",
    "task.deleted": "Plāns dzēsts",
    "task.marked_missed": "Atzīmēts kā izlaists",

    "add.title": "Pievienot plānam",
    "add.type": "Kas tas ir?",
    "add.name": "Nosaukums",
    "add.name_ph": "piem., fizioterapija",
    "add.first_date": "Pirmais datums",
    "add.how_often": "Cik bieži",
    "add.remind": "E-pasta atgādinājumi",
    "add.remind_hint": "E-pasti sākas, kad termiņš ir jūsu atgādinājumu logā (Profils > Atgādinājumi), un beidzas, kad tas ir paveikts vai dzēsts.",
    "add.remind_once": "Vienreiz par katru datumu",
    "add.remind_daily": "Katru dienu, līdz paveikts",
    "add.remind_weekly": "Katru nedēļu, līdz paveikts",
    "add.remind_minute": "Katru minūti (demo)",
    "add.repeats": "Atkārtojas",
    "add.manual": "Izvēlēties datumus",
    "add.every": "Ik pēc",
    "add.more_dates": "Citi datumi",
    "add.add_date": "Pievienot vēl datumu",
    "add.description": "Apraksts",
    "add.doctor_name": "Ārsta vārds",
    "add.doctor_specialty": "Specialitāte",
    "add.specialty_ph": "piem., kardiologs",
    "add.save": "Pievienot plānam",
    "add.saved": "Pievienots plānam",

    "log.title": "Žurnāls",
    "log.category": "Kategorija",
    "log.all": "Visas kategorijas",
    "log.empty": "Šeit vēl nekā nav.",
    "log.add": "Ierakstīt",
    "log.delete_confirm": "Dzēst “{title}” ({date})?",
    "log.deleted": "Ieraksts dzēsts",

    "info.title": "Sagatavošanās ceļveži",
    "info.search": "Meklēt, piem., gastroskopija",
    "info.plans": "Jūsu gaidāmās sagatavošanās",
    "info.library": "Visi ceļveži",
    "info.no_results": "Nav ceļveža, kas atbilst “{q}”.",

    "labs.title": "Asins analīžu rezultāti",
    "labs.summary": "Analīzes: {n} · pēdējās {date}",
    "labs.out_of_range": "Ārpus normas pēdējās analīzēs: {n}",
    "labs.all_in_range": "Pēdējās analīzēs viss normas robežās",
    "labs.all": "Visi",
    "labs.flag.low": "Zems", "labs.flag.normal": "Normā", "labs.flag.high": "Augsts",
    "labs.range": "Normas robežas",
    "labs.range_between": "Norma {low}–{high}",
    "labs.range_under": "Norma zem {high}",
    "labs.range_over": "Norma virs {low}",
    "labs.show_values": "Rādīt visas vērtības",
    "labs.date": "Datums", "labs.value": "Vērtība",
    "labs.empty": "Vēl nav analīžu rezultātu.",
    "labs.highlight": "Izceltas {date} analīzes",
    "labs.see": "Skatīt rezultātus",
    "labcat.vitamin": "Vitamīni", "labcat.mineral": "Minerālvielas", "labcat.heavy_metal": "Smagie metāli",
    "labcat.blood_count": "Asins aina", "labcat.metabolic": "Cukura līmenis", "labcat.lipid": "Holesterīns",
    "labcat.hormone": "Hormoni", "labcat.inflammation": "Iekaisums",

    "checks.title": "Valsts apmaksātās pārbaudes",
    "checks.intro": "Profilaktiskās pārbaudes, ko apmaksā valsts, saskaņā ar Nacionālā veselības dienesta (NVD) un SPKC informāciju.",
    "checks.for_you": "Jūsu kalendārā",
    "checks.not_for_you": "Pašlaik neatbilst jūsu vecumam vai dzimumam",
    "checks.women": "Sievietes", "checks.men": "Vīrieši", "checks.everyone": "Visi",
    "checks.ages": "{min}–{max} g.", "checks.from": "no {min} g.",
    "schedule.all_checks": "Visas valsts apmaksātās pārbaudes",

    "proc.checklist": "Kontrolsaraksts",
    "proc.before": "{n} st. pirms",
    "proc.set_reminder": "Iestatīt atgādinājumu",
    "proc.when": "Kad ir jūsu vizīte?",
    "proc.remind_about": "Atgādināt par",
    "proc.save": "Saglabāt atgādinājumus",
    "proc.saved": "Atgādinājumi iestatīti",
    "proc.appointment": "Vizīte {when}",
    "proc.remove": "Noņemt",
    "proc.removed": "Sagatavošanās noņemta",
    "proc.reminded": "Atgādināts",
    "proc.remind_at": "Atgādinājums {when}",
    "proc.remind_now": "Atgādinājums uzreiz - šis laiks jau ir pagājis",
    "proc.past": "Izvēlieties laiku nākotnē.",


    "profile.title": "Profils",
    "profile.edit": "Personas dati",
    "profile.passport": "Vakcinācijas pase",
    "profile.family": "Ģimenes locekļi",
    "profile.family_add": "Pievienot ģimenes locekli",
    "profile.soon": "Drīzumā",
    "profile.reminders": "Atgādinājumi",
    "profile.inbox": "Atgādinājumu iesūtne",
    "profile.language": "Valoda",
    "profile.privacy": "Privātums un dati",
    "profile.broadcast": "Ziņa visiem pacientiem",
    "profile.sign_out": "Iziet",
    "profile.years": (v) => `${v.n} ${lvSingular(v.n) ? "gads" : "gadi"}`,

    "settings.title": "Atgādinājumi",
    "settings.on": "Ikdienas atgādinājumi",
    "settings.on_hint": "Reizi dienā, katru dienu, līdz katrs vienums ir atzīmēts kā paveikts.",
    "settings.lead": "Sākt atgādināt",
    "settings.lead_0": "Tajā pašā dienā",
    "settings.lead_1": "1 dienu iepriekš",
    "settings.lead_3": "3 dienas iepriekš",
    "settings.lead_7": "1 nedēļu iepriekš",
    "settings.lead_14": "2 nedēļas iepriekš",
    "settings.lead_30": "1 mēnesi iepriekš",
    "settings.channels": "Kur jūs sasniegt",
    "settings.push": "Lietotnē",
    "settings.push_hint": "Atgādinājumu iesūtne zem zvaniņa.",
    "settings.email": "E-pasts",
    "settings.email_hint": "Uz {email}, vienreiz par katru termiņu - bez ikdienas atkārtojumiem.",
    "settings.email_sent": "Pārbaudiet {email}.",
    "settings.email_test": "E-pasts ir testa režīmā (nav Gmail atslēgu), tāpēc tas tikai reģistrēts.",
    "settings.sms": "Īsziņa",
    "settings.sms_hint": "Viena īsziņa dienā ar visu, kas jādara.",
    "settings.phone": "Tālruņa numurs",
    "settings.phone_hint": "Der vietējais numurs: valsts kodu pievienosim paši.",
    "settings.check_now": "Pārbaudīt atgādinājumus tagad",
    "settings.check_sent": "Nosūtīti jauni atgādinājumi: {n}.",
    "settings.check_none": "Nekā jauna. Vai nu nekas nav jādara, vai šodien jau atgādinājām.",
    "settings.sms_test": "Īsziņas ir testa režīmā (nav Twilio atslēgu), tāpēc tās tikai reģistrētas.",

    "inbox.title": "Atgādinājumu iesūtne",
    "inbox.accept_all": "Pieņemt visus",
    "inbox.empty": "Atgādinājumu vēl nav.",
    "inbox.accepted": "Pieņemts",
    "inbox.waiting": "Gaida",

    "passport.title": "Vakcinācijas pase",
    "passport.given": "Veikta",
    "passport.renew": "Atjaunot līdz",
    "passport.not_recorded": "Vēl nav ierakstīta",
    "passport.unknown": "Atjaunošanas datums nav zināms",
    "passport.add": "Pievienot vakcīnu",
    "passport.recommended": "Jums ieteicamās",

    "privacy.title": "Privātums un dati",
    "privacy.export": "Lejupielādēt manus datus",
    "privacy.export_hint": "Viss, ko par jums glabājam, vienā JSON failā.",
    "privacy.delete": "Dzēst manu kontu",
    "privacy.delete_confirm": "Tas neatgriezeniski dzēsīs jūsu kontu, žurnālu un augšupielādētos failus.\n\nIerakstiet DELETE, lai apstiprinātu.",

    "broadcast.title": "Ziņa visiem pacientiem",
    "broadcast.intro": "Nosūta īsziņu visiem, kuri norādījuši tālruni ({n}).",
    "broadcast.nobody": "Neviens vēl nav norādījis tālruni.",
    "broadcast.message": "Ziņa",
    "broadcast.chars": "Atlikušas rakstzīmes: {n}",
    "broadcast.send": "Sūtīt ({n})",
    "broadcast.sending": "Sūta…",
    "broadcast.report": "Piegādes atskaite",
    "broadcast.test_mode": "Testa režīms: Twilio nav konfigurēts, tāpēc nekas netika nosūtīts.",
    "broadcast.summary": "Nosūtītas: {sent}, izlaistas: {skipped}, neizdevās: {failed}",
  },
};

// Country names are stored in English (the guidelines match on them) and shown translated.
const COUNTRIES = [
  ["Latvia", "Latvija"], ["Lithuania", "Lietuva"], ["Estonia", "Igaunija"],
  ["Finland", "Somija"], ["Sweden", "Zviedrija"], ["Norway", "Norvēģija"],
  ["Denmark", "Dānija"], ["Poland", "Polija"], ["Germany", "Vācija"],
  ["Netherlands", "Nīderlande"], ["Ireland", "Īrija"], ["United Kingdom", "Apvienotā Karaliste"],
  ["Ukraine", "Ukraina"], ["Georgia", "Gruzija"], ["United States", "ASV"],
];

function t(key, vars = {}) {
  const value = STRINGS[lang][key] ?? STRINGS.en[key] ?? key;
  if (typeof value === "function") return value(vars);
  return value.replace(/\{(\w+)\}/g, (_, name) => (name in vars ? vars[name] : `{${name}}`));
}

/* Fill static markup: <span data-i18n="login.title">, <input data-i18n-placeholder="..."> */
function applyI18n(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  document.documentElement.lang = lang;
}

/* ---- numbers, spans, dates -------------------------------------------- */

const lvSingular = (n) => n % 10 === 1 && n % 100 !== 11;

const LV_UNITS = {
  //        genitive sg, accusative sg, dative pl
  day:   ["dienas", "dienu", "dienām"],
  week:  ["nedēļas", "nedēļu", "nedēļām"],
  month: ["mēneša", "mēnesi", "mēnešiem"],
  year:  ["gada", "gadu", "gadiem"],
};

function amount(days) {
  days = Math.abs(days);
  if (days < 14) return [days, "day"];
  if (days < 60) return [Math.floor(days / 7), "week"];
  if (days < 730) return [Math.floor(days / 30), "month"];
  return [Math.floor(days / 365), "year"];
}

/* A length of time after a preposition. caseLv: "gen" after pēc, "acc" after par. */
function span(days, caseLv = "gen") {
  const [n, unit] = amount(days);
  if (lang === "lv") {
    const [gen, acc, datPl] = LV_UNITS[unit];
    return `${n} ${lvSingular(n) ? (caseLv === "gen" ? gen : acc) : datPl}`;
  }
  return `${n} ${unit}${n === 1 ? "" : "s"}`;
}

/* "Every 2 weeks" / "Ik pēc 2 nedēļām" / "Katru nedēļu" */
function repeatText(every, unit) {
  if (lang === "lv") {
    if (every === 1) return `Katru ${LV_UNITS[unit][1]}`;
    return `Ik pēc ${every} ${lvSingular(every) ? LV_UNITS[unit][0] : LV_UNITS[unit][2]}`;
  }
  return every === 1 ? `Every ${unit}` : `Every ${every} ${unit}s`;
}

function dosesText(n) {
  if (lang === "lv") return `${n} ${lvSingular(n) ? "deva" : "devas"}`;
  return `${n} dose${n === 1 ? "" : "s"}`;
}

const locale = () => (lang === "lv" ? "lv-LV" : "en-GB");

function fmtDate(iso) {
  if (!iso) return "";
  return new Date(`${String(iso).slice(0, 10)}T00:00`).toLocaleDateString(locale(), {
    day: "numeric", month: "short", year: "numeric",
  });
}

function fmtDateTime(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString(locale(), {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

function monthTitle(year, month) {
  const s = new Date(year, month, 1).toLocaleDateString(locale(), { month: "long", year: "numeric" });
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function weekdayInitials() {
  // Monday first. 2024-01-01 was a Monday.
  return [...Array(7)].map((_, i) =>
    new Date(2024, 0, 1 + i).toLocaleDateString(locale(), { weekday: "short" }).replace(".", ""));
}

/* The status line under an item: "Late by 3 months", "Due in 12 days"... */
function whenText(item) {
  if (item.kind === "guideline" && !item.last_done) return t("when.no_record");
  if (item.days < 0) return t("when.late", { span: span(item.days, "acc") });
  if (item.days === 0) return t("when.today");
  if (item.status === "up_to_date") return t("when.next", { date: fmtDate(item.due_on) });
  return t("when.in", { span: span(item.days) });
}

function categoryLabel(category) {
  const key = `cat.${category}`;
  const known = STRINGS.en[key] !== undefined;
  return known ? t(key) : category.charAt(0).toUpperCase() + category.slice(1);
}

function countryLabel(value) {
  const row = COUNTRIES.find(([en]) => en === value);
  return row ? (lang === "lv" ? row[1] : row[0]) : value;
}
