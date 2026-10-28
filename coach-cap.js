// Coach cap overlay for ClawjCal — Training Tilt activities from Matt Buck.
//
// Data file: coach-plan.json (refreshed daily by the sync job, never edited
// by hand). Shape:
//   {
//     "updated": "2026-10-28T07:00:00Z",
//     "source": "Training Tilt — Matt Buck, Running Adventures",
//     "days": {
//       "2026-10-29": [
//         { "title": "Easy run 45 min", "detail": "Coach notes…",
//           "url": "https://runningadventures.trainingtiltapp.com/…" }
//       ]
//     }
//   }
//
// Any day with one or more activities gets a 🧢 in its calendar tile.
// Tapping the cap opens a modal with what Matt scheduled, the coach's extra
// info, and a link to Training Tilt where the session can be marked done.
// This deliberately does NOT duplicate the plan into the events array:
// Training Tilt stays the system of record; the calendar only marks the day.
(function () {
  var DATA_URL = "coach-plan.json";
  var plan = null;

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function prettyDate(iso) {
    try {
      var parts = iso.split("-");
      var d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]), 12);
      return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
    } catch (e) {
      return iso;
    }
  }

  function ensureStyles() {
    if (document.getElementById("coach-cap-styles")) return;
    var st = document.createElement("style");
    st.id = "coach-cap-styles";
    st.textContent =
      ".coach-cap{background:none;border:0;padding:2px 4px;margin:0;font-size:0.95rem;line-height:1;cursor:pointer;-webkit-tap-highlight-color:transparent;}" +
      ".coach-cap:active{transform:scale(0.9);}" +
      ".coach-modal-backdrop{position:fixed;inset:0;background:rgba(23,32,42,0.55);z-index:9998;display:flex;align-items:flex-end;justify-content:center;padding:16px;}" +
      "@media(min-width:500px){.coach-modal-backdrop{align-items:center;}}" +
      ".coach-modal{background:var(--paper,#fffdf8);color:var(--ink,#17202a);border:1px solid var(--line,#ded6c8);border-radius:16px;width:min(100%,430px);max-height:80vh;overflow:auto;padding:20px;box-shadow:0 12px 40px rgba(0,0,0,0.25);}" +
      ".coach-modal-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:4px;}" +
      ".coach-modal-head h2{margin:0;font-size:1.05rem;}" +
      ".coach-modal-close{background:none;border:0;font-size:1.4rem;line-height:1;cursor:pointer;color:var(--muted,#7b7468);padding:0 2px;}" +
      ".coach-modal-sub{color:var(--muted,#7b7468);font-size:0.85rem;margin:0 0 14px;}" +
      ".coach-modal-act{border-top:1px solid var(--line,#ded6c8);padding:12px 0;}" +
      ".coach-modal-act:first-of-type{border-top:0;padding-top:4px;}" +
      ".coach-modal-act h3{margin:0 0 6px;font-size:0.98rem;}" +
      ".coach-modal-act p{margin:0 0 10px;white-space:pre-wrap;font-size:0.92rem;line-height:1.45;}" +
      ".coach-modal-done{display:inline-block;padding:9px 14px;border-radius:999px;background:rgba(255,226,77,0.38);color:var(--ink,#17202a);font-weight:800;font-size:0.9rem;text-decoration:none;}" +
      ".coach-modal-done:active{transform:translateY(1px);}";
    document.head.appendChild(st);
  }

  function closeModal() {
    var el = document.getElementById("coach-modal-backdrop");
    if (el) el.remove();
    document.removeEventListener("keydown", onKey);
  }

  function onKey(e) {
    if (e.key === "Escape") closeModal();
  }

  function openModal(iso, acts) {
    ensureStyles();
    closeModal();
    var blocks = acts.map(function (a) {
      var detail = a.detail ? "<p>" + esc(a.detail) + "</p>" : "";
      var link = a.url
        ? '<a class="coach-modal-done" href="' + esc(a.url) + '" target="_blank" rel="noopener">Mark as done on Training Tilt ↗</a>'
        : "";
      return '<div class="coach-modal-act"><h3>' + esc(a.title || "Coach session") + "</h3>" + detail + link + "</div>";
    }).join("");
    var wrap = document.createElement("div");
    wrap.id = "coach-modal-backdrop";
    wrap.className = "coach-modal-backdrop";
    wrap.innerHTML =
      '<div class="coach-modal" role="dialog" aria-modal="true" aria-label="Coach session">' +
      '<div class="coach-modal-head"><h2>🧢 Coach session</h2>' +
      '<button class="coach-modal-close" type="button" aria-label="Close">×</button></div>' +
      '<p class="coach-modal-sub">' + esc(prettyDate(iso)) + " · planned by Matt</p>" +
      blocks +
      "</div>";
    wrap.addEventListener("click", function (e) {
      if (e.target === wrap) closeModal();
    });
    wrap.querySelector(".coach-modal-close").addEventListener("click", closeModal);
    document.body.appendChild(wrap);
    document.addEventListener("keydown", onKey);
  }

  function decorate() {
    if (!plan || !plan.days) return;
    var cells = document.querySelectorAll('#calendar .day[data-iso]');
    cells.forEach(function (cell) {
      var iso = cell.getAttribute("data-iso");
      var acts = plan.days[iso];
      var row = cell.querySelector(".date-row");
      if (!row) return;
      var existing = row.querySelector(".coach-cap");
      if (acts && acts.length) {
        if (!existing) {
          var cap = document.createElement("button");
          cap.className = "coach-cap";
          cap.type = "button";
          cap.textContent = "🧢";
          cap.setAttribute("aria-label", "Coach session");
          cap.title = "Coach session: " + acts.map(function (a) { return a.title; }).join(", ");
          cap.addEventListener("click", function (ev) {
            ev.stopPropagation();
            openModal(iso, plan.days[iso] || acts);
          });
          row.appendChild(cap);
        } else {
          existing.title = "Coach session: " + acts.map(function (a) { return a.title; }).join(", ");
        }
      } else if (existing) {
        existing.remove();
      }
    });
  }

  function load() {
    fetch(DATA_URL, { cache: "no-cache" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (json) {
        if (json && json.days) {
          plan = json;
          decorate();
        }
      })
      .catch(function () { /* no coach data yet — tiles simply show no caps */ });
  }

  function init() {
    ensureStyles();
    var grid = document.getElementById("calendar");
    if (grid && "MutationObserver" in window) {
      // renderCalendar rebuilds the grid (view switches, history expand);
      // re-decorate whenever its direct children change.
      new MutationObserver(function () { decorate(); }).observe(grid, { childList: true });
    }
    load();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
