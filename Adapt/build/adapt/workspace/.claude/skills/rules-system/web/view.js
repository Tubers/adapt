(function () {
  "use strict";

  var BOOT = window.VIEW || { mode: "live", poll: 2000 };
  var KIND_ORDER = ["run", "finding", "decision", "change", "dead-end", "note", "candidate"];
  var ICON = { done: "✅", now: "🔄", blocked: "⛔", next: "🔜" };
  var TASK_HELP = {
    done: "Done: finished and logged in the history. The two newest stay in the window.",
    now: "In progress: the one task being worked on now.",
    blocked: "Blocked: waiting on something. The reason is at the start of its paragraph.",
    next: "Not started: the next tasks in line, three to five of them."
  };
  // hover text for the history kinds and statuses, shown on the filter chips and on every entry's badge
  var KIND_HELP = {
    run: "Run: a test run in the game, where its results are and what it showed.",
    finding: "Finding: something learned, a measured or observed fact about how things work.",
    decision: "Decision: a choice that was made, and why. Answered questions and dropped tasks land here.",
    question: "Question: one you answered, recorded as a decision once the instance read it. Questions still open " +
      "sit on their task in the Tasks tab. Research unknowns are notes tagged open-question.",
    action: "Action: something only you could do, recorded as a note once you marked it done and the instance read it. " +
      "Actions still open sit on their task in the Tasks tab, marked ❗.",
    change: "Change: a lasting change to files, such as code, rules, docs or data. Finished tasks land here.",
    "dead-end": "Dead end: an approach that was tried and abandoned, so no one tries it again.",
    note: "Note: context worth keeping that is none of the other kinds.",
    candidate: "Candidate: a fact proposed as a rule, waiting for the user to approve or reject it."
  };
  var STATUS_HELP = {
    open: "Open: still being worked on or still true to check.",
    closed: "Closed: settled; nothing more to do.",
    withdrawn: "Withdrawn: turned out wrong; kept so the mistake is not repeated.",
    pending: "Pending: waiting for the user to approve or reject it as a rule.",
    approved: "Approved: the user accepted it and it became part of a rule.",
    rejected: "Rejected: the user declined it as a rule."
  };
  var S = {
    tab: ["tasks", "history", "candidates"].indexOf(location.hash.slice(1)) >= 0 ? location.hash.slice(1) : "tasks",
    data: null,
    sig: "",
    open: new Set(),
    drafts: {},
    prevF: null,
    fresh: new Set(),
    f: { kinds: new Set(), status: "", from: "", to: "", text: "", ref: "", tag: "", folder: "", session: "" },
    cand: new Set(["pending"]),
    filtersBuilt: false
  };

  function $(sel) { return document.querySelector(sel); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function uniq(list) { return Array.from(new Set(list.filter(Boolean))).sort(); }

  // ---------------------------------------------------------------- tabs
  function showTab(name) {
    S.tab = name;
    history.replaceState(null, "", "#" + name);
    document.querySelectorAll("nav.tabs button").forEach(function (b) {
      b.setAttribute("aria-selected", b.dataset.tab === name ? "true" : "false");
    });
    ["tasks", "history", "candidates"].forEach(function (t) { $("#tab-" + t).hidden = t !== name; });
  }
  document.querySelectorAll("nav.tabs button").forEach(function (b) {
    b.addEventListener("click", function () { showTab(b.dataset.tab); });
  });

  // ---------------------------------------------------------------- expand on click, remembered across redraws
  document.addEventListener("click", function (ev) {
    var head = ev.target.closest(".line, .row");
    if (!head) return;
    var item = head.parentElement;
    if (!item.dataset.key || !item.querySelector(".details")) return;
    item.classList.toggle("open");
    if (item.classList.contains("open")) S.open.add(item.dataset.key); else S.open.delete(item.dataset.key);
  });

  // ---------------------------------------------------------------- tasks
  function renderTasks() {
    var t = S.data.tasks, box = $("#tab-tasks");
    if (!t) {
      box.innerHTML = '<p class="empty">This project has no TASKS.md yet.</p>';
      $("#n-tasks").textContent = "";
      return;
    }
    var rows = t.tasks.map(function (k) {
      var para = k.id ? t.details[k.id] : "";
      var mine = (S.data.questions || []).filter(function (q) { return q.task === k.id; });
      var kids = (S.data.children || {})[k.id] || [];
      var sent = mine.filter(replied).length;
      // a done task also shows what came of it: the history entry its `done` logged, keyed by the task id
      var logged = k.id ? S.data.history.filter(function (e) { return e.task === k.id; }).pop() : null;
      var det = (para ? "<p>" + esc(para) + "</p>" : '<p class="missing">No paragraph yet: rules.py tasks detail ' +
        esc(k.id) + ' "&lt;paragraph&gt;"</p>') +
        mine.map(function (q) { return isAction(q) ? actBlock(q) : qaBlock(q); }).join("") +
        kids.map(function (rel) {
          return '<p class="result sub"><span>Sub-project</span><a href="#" data-open="' + esc(rel) + '">' + esc(rel) +
            "/</a> - open its tasks and history in a separate window</p>";
        }).join("") +
        (logged ? '<p class="result"><span>' + (k.status === "done" ? "Result" : "Logged") + "</span>" +
          esc(logged.result || logged.what || logged.title) + "</p>" : "");
      var key = "task:" + (k.id || k.text);
      var date = k.date ? '<span class="date">' + (k.since ? "since " : "") + esc(k.date) + "</span>" : "";
      return '<li class="task ' + k.status + " has-details" + (S.open.has(key) ? " open" : "") +
        (S.fresh.has(key) ? " fresh" : "") +
        '" data-key="' + esc(key) + '"><div class="line"><span class="icon" title="' + esc(TASK_HELP[k.status]) + '">' +
        ICON[k.status] + "</span>" +
        // the id instances name in chat and in questions ("t5"), so the user can match them to a line
        (k.id ? '<span class="tid" title="Task id ' + esc(k.id) + ': the name instances use for this task">' +
          esc(k.id) + "</span>" : "") +
        (k.question ? '<span class="q" title="A question for you: click to open the task and answer it">❓</span>' : "") +
        (k.action ? '<span class="q act" title="An action for you: click to open the task, do it, then mark it done">❗</span>' : "") +
        (sent && !k.question && !k.action ? '<span class="q" title="Your reply is sent; the instance is told">📨</span>' : "") +
        // one sub-project: the icon itself opens it; several: the icon opens the task, which lists a link to each
        (kids.length === 1 ? '<a href="#" class="q sub" data-open="' + esc(kids[0]) + '" title="Sub-project ' +
          esc(kids[0]) + '/: click to open its tasks and history in a separate window">🗂</a>' : "") +
        (kids.length > 1 ? '<span class="q" title="This task has ' + kids.length +
          ' sub-projects: click to open the task, then open each one from its link">🗂</span>' : "") +
        '<span class="text">' + esc(k.text) + "</span>" + date + '<span class="chev">›</span>' +
        '</div><div class="details">' + det + "</div></li>";
    }).join("");
    // keep a half-typed answer and its cursor across a redraw: the list is rebuilt whenever the records change
    var act = document.activeElement, keep = act && act.matches && act.matches("textarea[data-q]")
      ? { q: act.dataset.q, a: act.selectionStart, b: act.selectionEnd } : null;
    var up = S.data.parent_task;
    box.innerHTML = (up ? '<p class="parent"><span>Part of</span><a href="#" data-open="' + esc(up.project) + '">' +
      esc(up.project) + "/</a> · " + esc(up.task) + " " + esc(up.text) + "</p>" : "") +
      (t.goal ? '<p class="goal' + (S.fresh.has("goal") ? " fresh" : "") + '"><span>Goal</span>' +
      esc(t.goal) + "</p>" : "") +
      '<ul class="tasklist">' + rows + "</ul>" +
      (t.problems && t.problems.length ? '<p class="warn">' + t.problems.map(esc).join("<br>") + "</p>" : "");
    if (keep) {
      var el = box.querySelector('textarea[data-q="' + keep.q + '"]');
      if (el) { el.focus(); el.setSelectionRange(keep.a, keep.b); }
    }
    var waiting = (S.data.questions || []).filter(function (q) { return !replied(q); });
    var open = waiting.filter(function (q) { return !isAction(q); }).length, todo = waiting.length - open;
    $("#n-tasks").textContent = (t.tasks.filter(function (k) { return k.status !== "done"; }).length || "") +
      (open ? " · ❓" + open : "") + (todo ? " · ❗" + todo : "");
  }

  // QUESTIONS.jsonl holds two kinds: a question the user answers, and an action the user does and marks done
  function isAction(q) { return q.kind === "action"; }
  function replied(q) { return isAction(q) ? !!q.done : !!q.answer; }

  // ---------------------------------------------------------------- an action for the user, inside its task
  function actBlock(a) {
    var id = esc(a.id);
    var body = a.done
      ? '<p class="qdone"><span>Done</span>' + esc(a.note || "") +
        "<em>marked " + esc(String(a.done).replace("T", " ")) + " · the instance is told</em></p>"
      : BOOT.token
        ? '<textarea rows="2" data-q="' + id + '" placeholder="A note for the instance (optional)">' +
          esc(S.drafts[a.id] || "") + '</textarea><div class="qact"><button type="button" class="did" data-a="' + id +
          '">Mark done</button><span class="qmsg" data-q="' + id + '"></span></div>'
        : '<p class="qdone">Open the live viewer (rules.py view) to mark it done.</p>';
    return '<div class="qa action' + (a.done ? " answered" : "") + '"><div class="qhead"><span class="qid aid">❗ ' + id +
      "</span>an action for you</div>" + '<p class="qtext">' + esc(a.action) + "</p>" + body + "</div>";
  }

  // ---------------------------------------------------------------- a question for the user, inside its task
  function qaBlock(q) {
    var id = esc(q.id);
    var body = q.answer
      ? '<p class="qdone"><span>Your answer</span>' + esc(q.answer) +
        "<em>sent " + esc(String(q.answered || "").replace("T", " ")) + " · the instance is told</em></p>"
      : BOOT.token
        ? '<textarea rows="10" data-q="' + id + '" placeholder="Your answer">' + esc(S.drafts[q.id] || "") +
          '</textarea><div class="qact"><button type="button" class="send" data-q="' + id + '">Send answer</button>' +
          '<span class="qmsg" data-q="' + id + '"></span></div>'
        : '<p class="qdone">Open the live viewer (rules.py view) to answer.</p>';
    return '<div class="qa' + (q.answer ? " answered" : "") + '"><div class="qhead"><span class="qid">❓ ' + id +
      "</span>a question for you</div>" + '<p class="qtext">' + esc(q.question) + "</p>" + body + "</div>";
  }

  // What changed since the last poll, as one fingerprint per item. The items that differ glow until the next
  // change replaces them; the first load marks nothing.
  function fingerprints(d) {
    var f = {}, qs = d.questions || [];
    if (d.tasks) {
      if (d.tasks.goal) f.goal = d.tasks.goal;
      d.tasks.tasks.forEach(function (k) {
        f["task:" + (k.id || k.text)] = JSON.stringify([k.status, k.text, k.date, k.question, k.action,
          d.tasks.details[k.id] || "",
          qs.filter(function (q) { return q.task === k.id; }).map(function (q) { return [q.id, q.answer || "", q.done || ""]; })]);
      });
    }
    (d.history || []).forEach(function (e) { f["h:" + e.id] = JSON.stringify([e.status || "", e.title]); });
    (d.candidates || []).forEach(function (c) { f["c:" + c.id] = c.status || "pending"; });
    return f;
  }

  function noteChanges(d) {
    var now = fingerprints(d), was = S.prevF;
    S.prevF = now;
    if (!was) return;
    var changed = Object.keys(now).filter(function (k) { return now[k] !== was[k]; });
    if (changed.length) S.fresh = new Set(changed);
  }

  // drill down to a sub-project, or back up to the parent: the server starts that project's viewer, and it opens in a
  // separate window, so this one stays open (the user, 2026-09-15). The window is opened inside the click itself, since
  // a browser blocks one opened later from a fetch; it is pointed at the viewer once the server answers. It is named
  // after the project, so a second click brings the same window forward instead of opening another.
  document.addEventListener("click", function (ev) {
    var a = ev.target.closest && ev.target.closest("a[data-open]");
    if (!a) return;
    ev.preventDefault();
    ev.stopPropagation();
    if (!BOOT.token) { alert("Run: rules.py view " + a.dataset.open); return; }
    var up = a.closest(".parent");
    if (up && window.opener && !window.opener.closed) { window.opener.focus(); return; }   // back to the page that opened this one
    var win = window.open("", "rules-view:" + a.dataset.open, "popup,width=1100,height=900");
    fetch("/open?project=" + encodeURIComponent(a.dataset.open), { method: "POST", cache: "no-store",
                                                                  headers: { "X-View-Token": BOOT.token } })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (!j.url) { if (win) win.close(); a.textContent += " (" + (j.error || "failed") + ")"; return; }
        if (win && !win.closed) { win.location.href = j.url; win.focus(); } else location.href = j.url;
      })
      .catch(function () { if (win) win.close(); a.textContent += " (the viewer is not running)"; });
  }, true);

  document.addEventListener("input", function (ev) {
    if (ev.target.matches && ev.target.matches("textarea[data-q]")) S.drafts[ev.target.dataset.q] = ev.target.value;
  });

  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest && ev.target.closest("button.send");
    if (!btn) return;
    var id = btn.dataset.q, text = (S.drafts[id] || "").trim();
    var msg = document.querySelector('.qmsg[data-q="' + id + '"]');
    if (text.length < 8) { msg.textContent = "A full sentence, please."; return; }
    btn.disabled = true;
    msg.textContent = "sending…";
    fetch("/answer", { method: "POST", cache: "no-store",
                       headers: { "Content-Type": "application/json", "X-View-Token": BOOT.token },
                       body: JSON.stringify({ id: id, answer: text }) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (res.ok) { delete S.drafts[id]; msg.textContent = "sent · the instance is told"; schedule(0); }
        else { btn.disabled = false; msg.textContent = res.j.error || "not saved"; }
      })
      .catch(function () { btn.disabled = false; msg.textContent = "the viewer is not running: rules.py view"; });
  });

  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest && ev.target.closest("button.did");
    if (!btn) return;
    var id = btn.dataset.a, note = (S.drafts[id] || "").trim();
    var msg = document.querySelector('.qmsg[data-q="' + id + '"]');
    btn.disabled = true;
    msg.textContent = "sending…";
    fetch("/done", { method: "POST", cache: "no-store",
                     headers: { "Content-Type": "application/json", "X-View-Token": BOOT.token },
                     body: JSON.stringify({ id: id, note: note }) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (res.ok) { delete S.drafts[id]; msg.textContent = "marked done · the instance is told"; schedule(0); }
        else { btn.disabled = false; msg.textContent = res.j.error || "not saved"; }
      })
      .catch(function () { btn.disabled = false; msg.textContent = "the viewer is not running: rules.py view"; });
  });

  // ---------------------------------------------------------------- history filters
  function buildFilters() {
    $("#filters").innerHTML =
      '<div class="chips" id="f-kinds"></div>' +
      '<div class="grid">' +
      '<label>Search<input id="f-text" type="search" placeholder="words in any field"></label>' +
      '<label>Status<select id="f-status"></select></label>' +
      '<label>From<input id="f-from" type="date"></label>' +
      '<label>To<input id="f-to" type="date"></label>' +
      '<label>Rule referenced<input id="f-ref" list="f-refs" placeholder="area/slug"><datalist id="f-refs"></datalist></label>' +
      '<label>Tag<select id="f-tag"></select></label>' +
      '<label>Subfolder<select id="f-folder"></select></label>' +
      '<label>Session<select id="f-session"></select></label>' +
      "</div>" +
      '<button class="clear" id="f-clear">Clear filters</button>';
    ["text", "status", "from", "to", "ref", "tag", "folder", "session"].forEach(function (name) {
      var input = $("#f-" + name);
      input.addEventListener("input", function () { S.f[name] = input.value; renderEntries(); });
    });
    $("#f-kinds").addEventListener("click", function (ev) {
      var chip = ev.target.closest(".chip");
      if (!chip) return;
      var k = chip.dataset.kind;
      if (S.f.kinds.has(k)) S.f.kinds.delete(k); else S.f.kinds.add(k);
      refreshFilters();
      renderEntries();
    });
    $("#f-clear").addEventListener("click", function () {
      S.f = { kinds: new Set(), status: "", from: "", to: "", text: "", ref: "", tag: "", folder: "", session: "" };
      ["text", "status", "from", "to", "ref", "tag", "folder", "session"].forEach(function (n) { $("#f-" + n).value = ""; });
      refreshFilters();
      renderEntries();
    });
    S.filtersBuilt = true;
  }

  function setOptions(select, values, current, label) {
    select.innerHTML = '<option value="">' + esc(label) + "</option>" + values.map(function (v) {
      return '<option value="' + esc(v) + '"' + (v === current ? " selected" : "") + ">" + esc(v) + "</option>";
    }).join("");
  }

  function refsOf(e) {
    var refs = (e.refs || []).slice();
    if (e.decided && e.decided.rule) refs.push(e.decided.rule);
    return refs;
  }

  function relFolder(e) {
    var p = S.data.project, f = e._folder || p;
    return f === p ? "" : f.indexOf(p + "/") === 0 ? f.slice(p.length + 1) : f;
  }

  function refreshFilters() {
    var H = S.data.history;
    var counts = {};
    H.forEach(function (e) { counts[e.kind] = (counts[e.kind] || 0) + 1; });
    // not a kind of its own: an answered question is a decision entry carrying a `question` key
    var asked = H.filter(function (e) { return e.question; }).length;
    if (asked) counts.question = asked;
    // nor is a done action: a note entry carrying an `action` key
    var did = H.filter(function (e) { return e.action; }).length;
    if (did) counts.action = did;
    var kinds = KIND_ORDER.filter(function (k) { return counts[k]; })
      .concat(Object.keys(counts).filter(function (k) { return KIND_ORDER.indexOf(k) < 0; }));
    $("#f-kinds").innerHTML = kinds.map(function (k) {
      return '<button class="chip" data-kind="' + esc(k) + '" title="' + esc(KIND_HELP[k] || k) +
        '" aria-pressed="' + S.f.kinds.has(k) + '">' +
        esc(k) + '<span class="c">' + counts[k] + "</span></button>";
    }).join("");
    setOptions($("#f-status"), uniq(H.map(function (e) { return e.status; })), S.f.status, "any status");
    setOptions($("#f-tag"), uniq([].concat.apply([], H.map(function (e) { return e.tags || []; }))), S.f.tag, "any tag");
    setOptions($("#f-folder"), uniq(H.map(relFolder)), S.f.folder, "the whole project");
    setOptions($("#f-session"), uniq(H.map(function (e) { return (e.session || (e.found && e.found.session) || "").slice(0, 8); })), S.f.session, "any session");
    $("#f-refs").innerHTML = uniq([].concat.apply([], H.map(refsOf))).map(function (r) {
      return '<option value="' + esc(r) + '">';
    }).join("");
  }

  function matches(e) {
    var f = S.f;
    if (f.kinds.size && !f.kinds.has(e.kind) && !(e.question && f.kinds.has("question")) &&
        !(e.action && f.kinds.has("action"))) return false;
    if (f.status && e.status !== f.status) return false;
    if (f.from && String(e.ts) < f.from) return false;
    if (f.to && String(e.ts) > f.to) return false;
    if (f.tag && (e.tags || []).indexOf(f.tag) < 0) return false;
    if (f.folder) {
      var rf = relFolder(e);
      if (rf !== f.folder && rf.indexOf(f.folder + "/") !== 0) return false;
    }
    if (f.session && (e.session || (e.found && e.found.session) || "").indexOf(f.session) !== 0) return false;
    if (f.ref) {
      var want = f.ref.toLowerCase();
      if (!refsOf(e).some(function (r) { return String(r).toLowerCase().indexOf(want) >= 0; })) return false;
    }
    if (f.text && JSON.stringify(e).toLowerCase().indexOf(f.text.toLowerCase()) < 0) return false;
    return true;
  }

  // ---------------------------------------------------------------- history entries
  function kv(label, value) {
    return value === undefined || value === null || value === "" ? "" : "<dt>" + esc(label) + "</dt><dd>" + value + "</dd>";
  }

  function detailOf(e) {
    var nums = e.numbers ? Object.keys(e.numbers).map(function (k) {
      return esc(k.replace(/_/g, " ")) + ": <strong>" + esc(e.numbers[k]) + "</strong>";
    }).join("<br>") : "";
    var ev = (e.evidence || []).map(function (p) { return "<code>" + esc(p) + "</code>"; }).join("<br>");
    var refs = refsOf(e).map(function (r) { return "<code>" + esc(r) + "</code>"; }).join(" ");
    var tags = (e.tags || []).map(function (t) { return '<span class="tagpill">' + esc(t) + "</span>"; }).join("");
    var body = "<dl class=\"kv\">" +
      kv("what", esc(e.what)) + kv("result", esc(e.result)) + kv("reason", esc(e.reason)) +
      kv("numbers", nums) + kv("evidence", ev) + kv("rules", refs) + kv("no rule because", esc(e.no_rule)) +
      kv("tags", tags) + kv("subfolder", esc(relFolder(e))) + kv("id", "<code>" + esc(e.id) + "</code>") +
      kv("logged", esc(e.time || e.ts)) + kv("session", esc(e.session || (e.found && e.found.session))) +
      "</dl>";
    return body + "<details><summary>raw entry</summary><pre>" + esc(JSON.stringify(stripPrivate(e), null, 2)) + "</pre></details>";
  }

  function stripPrivate(e) {
    var out = {};
    Object.keys(e).forEach(function (k) { if (k.charAt(0) !== "_") out[k] = e[k]; });
    return out;
  }

  function renderEntries() {
    var H = S.data.history, shown = H.filter(matches).slice().reverse();
    $("#h-count").textContent = shown.length === H.length ? H.length + " entries" : shown.length + " of " + H.length + " entries";
    $("#entries").innerHTML = shown.map(function (e) {
      var key = "h:" + e.id, sub = relFolder(e);
      return '<li class="entry kind-' + esc(e.kind) + (S.open.has(key) ? " open" : "") +
        (S.fresh.has(key) ? " fresh" : "") + '" data-key="' + esc(key) + '">' +
        '<div class="row"><span class="date">' + esc(e.ts) + '</span><span class="badge" title="' + esc(KIND_HELP[e.kind] || e.kind) + '">' + esc(e.kind) + "</span>" +
        (e.question ? '<span class="badge kind-q" title="' + esc(KIND_HELP.question) + '">question ' +
          esc(e.question) + "</span>" : "") +
        (e.action ? '<span class="badge kind-a" title="' + esc(KIND_HELP.action) + '">action ' +
          esc(e.action) + "</span>" : "") +
        '<span class="title">' + esc(e.title) + "</span>" +
        (sub ? '<span class="sub" title="the subfolder this entry was logged from">' + esc(sub) + "</span>" : "") +
        (e.status ? '<span class="status ' + esc(e.status) + '" title="' + esc(STATUS_HELP[e.status] || e.status) + '">' +
          esc(e.status) + "</span>" : "") +
        '<span class="chev">›</span></div><div class="details">' + detailOf(e) + "</div></li>";
    }).join("") || '<li class="empty">No entry matches these filters.</li>';
    $("#n-history").textContent = H.length || "";
  }

  // ---------------------------------------------------------------- candidates
  function renderCandidates() {
    var C = S.data.candidates, counts = { pending: 0, approved: 0, rejected: 0 };
    C.forEach(function (c) { counts[c.status || "pending"] = (counts[c.status || "pending"] || 0) + 1; });
    $("#c-status").innerHTML = ["pending", "approved", "rejected"].map(function (s) {
      return '<button class="chip" data-status="' + s + '" title="' + esc(STATUS_HELP[s]) + '" aria-pressed="' +
        S.cand.has(s) + '">' + s +
        '<span class="c">' + counts[s] + "</span></button>";
    }).join("");
    var shown = C.filter(function (c) { return S.cand.has(c.status || "pending"); }).slice().reverse();
    $("#cands").innerHTML = shown.map(function (c) {
      var key = "c:" + c.id, pass = c.pass || {}, dec = c.decided || {};
      var near = (pass.nearest || []).map(function (n) { return "<code>" + esc(n.rule) + "</code> " + esc(n.score); }).join("<br>");
      var body = '<dl class="kv">' + kv("fact", esc(c.what)) +
        kv("source", c.run ? "<code>" + esc(c.run) + "</code>" : esc("no run: " + (c.no_rule || c.no_run || ""))) +
        kv("found", esc(((c.found || {}).time || c.ts) + "  session " + ((c.found || {}).session || "").slice(0, 8))) +
        kv("nearest rules when parked", near || esc(pass.unavailable)) +
        kv("decision", c.status && c.status !== "pending" ? esc(c.status + ": " + (c.reason || "")) : "") +
        kv("rule", dec.rule ? "<code>" + esc(dec.rule) + "</code>" : "") + "</dl>";
      return '<li class="entry kind-candidate' + (S.open.has(key) ? " open" : "") +
        (S.fresh.has(key) ? " fresh" : "") + '" data-key="' + esc(key) + '">' +
        '<div class="row"><span class="date">' + esc(c.ts) + '</span><span class="status ' + esc(c.status || "pending") + '" title="' +
        esc(STATUS_HELP[c.status || "pending"]) + '">' +
        esc(c.status || "pending") + '</span><span class="title">' + esc(c.title) + '</span><span class="chev">›</span></div>' +
        '<div class="details">' + body + "</div></li>";
    }).join("") || '<li class="empty">No candidates with this status in this project.</li>';
    $("#n-candidates").textContent = counts.pending || "";
  }
  $("#c-status").addEventListener("click", function (ev) {
    var chip = ev.target.closest(".chip");
    if (!chip) return;
    var s = chip.dataset.status;
    if (S.cand.has(s)) S.cand.delete(s); else S.cand.add(s);
    renderCandidates();
  });

  // ---------------------------------------------------------------- the whole page
  function renderAll() {
    var d = S.data;
    document.title = d.project + " · records";
    $("#repo").textContent = d.repo;
    $("#project").textContent = d.project;
    renderTasks();
    if (!S.filtersBuilt) buildFilters();
    refreshFilters();
    renderEntries();
    renderCandidates();
    // a soft dot on each tab holding something that just changed, so a change on a hidden tab is not missed
    [["tasks", /^(task:|goal$)/], ["history", /^h:/], ["candidates", /^c:/]].forEach(function (p) {
      var tab = document.querySelector('[data-tab="' + p[0] + '"]');
      if (tab) tab.classList.toggle("has-fresh", Array.from(S.fresh).some(function (k) { return p[1].test(k); }));
    });
  }

  function setLive(state, text) {
    var el = $("#live");
    el.className = "live " + state;
    $("#live-text").textContent = text;
  }

  function stamp() { return new Date().toLocaleTimeString(); }

  // ONE polling loop. Coming back to the tab asks at once by rescheduling that loop, never by starting a
  // second one: an earlier version added a loop on every visibility change.
  var timer = null, inflight = false;
  function schedule(ms) { clearTimeout(timer); timer = setTimeout(poll, ms); }
  function poll() {
    if (inflight) return;
    inflight = true;
    fetch("/data?sig=" + encodeURIComponent(S.sig), { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.unchanged) { noteChanges(d); S.data = d; S.sig = d.signature; renderAll(); }
        setLive("ok", "live · checked " + stamp());
      })
      .catch(function () { setLive("down", "stopped · run rules.py view again"); })
      .then(function () { inflight = false; schedule(BOOT.poll || 2000); });
  }

  showTab(S.tab);
  if (BOOT.mode === "static") {
    S.data = BOOT.data;
    renderAll();
    setLive("", "snapshot · " + BOOT.data.generated);
  } else {
    poll();
    document.addEventListener("visibilitychange", function () { if (!document.hidden) schedule(0); });
  }
})();
