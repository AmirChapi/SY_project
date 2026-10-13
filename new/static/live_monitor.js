// מסך שיחה חיה - מרענן מצב מהשרת כל שנייה ומעדכן שלב, ציון, אינדיקציות, מדיניות ו-Step-Up
(function () {
  const card = document.querySelector(".live-call-card");
  if (!card) return;

  const statusUrl = card.dataset.statusUrl;
  const stepUpUrlTemplate = card.dataset.stepUpUrl;

  const el = (id) => document.getElementById(id);
  const scoreEl = el("gauge-score"), levelEl = el("gauge-level"), progressEl = el("risk-progress-fill");
  const actionEl = el("risk-action"), rawNoteEl = el("raw-score-note"), timerEl = el("call-timer");
  const listEl = el("indicators-list"), emptyEl = el("indicators-empty");
  const policyList = el("policy-list"), reqLabel = el("requested-action-label"), reqState = el("requested-action-state");
  const stepUpBox = el("step-up-box"), stepUpChannel = el("step-up-channel"), stepUpStatus = el("step-up-status");
  const stepUpActions = el("step-up-actions"), stepUpResult = el("step-up-result");
  const eventList = el("event-list"), overlay = el("incoming-call-overlay"), phaseLabel = el("phase-label");
  const agentAction = el("agent-action");

  const shownIndicators = new Set();
  let shownEvents = 0;

  const PHASE_LABELS = { ivr: "בהמתנה / IVR", agent: "נציג על הקו", step_up: "ממתין לאישור Push", resolved: "Step-Up הוכרע" };
  const PHASE_ORDER = ["ivr", "agent", "step_up", "resolved"];

  function levelColor(levelKey) {
    return levelKey === "high" ? "#dc2626" : levelKey === "medium" ? "#ca8a04" : "#16a34a";
  }
  function fmt(sec) {
    const m = String(Math.floor(sec / 60)).padStart(2, "0"), s = String(Math.floor(sec % 60)).padStart(2, "0");
    return m + ":" + s;
  }

  function renderPhase(phase) {
    const idx = PHASE_ORDER.indexOf(phase);
    document.querySelectorAll(".phase-step").forEach((step) => {
      const i = PHASE_ORDER.indexOf(step.dataset.phase);
      step.classList.toggle("done", i < idx);
      step.classList.toggle("active", i === idx);
    });
    phaseLabel.textContent = PHASE_LABELS[phase] || phase;
    if (phase !== "ivr" && overlay && !overlay.classList.contains("hidden")) overlay.classList.add("hidden");
  }

  function renderIndicators(indicators) {
    indicators.forEach((ind) => {
      if (!ind.is_present || shownIndicators.has(ind.key)) return;
      shownIndicators.add(ind.key);
      const li = document.createElement("li");
      li.className = "new-indicator";
      const phaseTag = ind.detected_phase === "ivr" ? "זוהה בשלב IVR" : "זוהה בשיחה";
      li.innerHTML = "";
      const strong = document.createElement("strong"); strong.textContent = ind.label;
      const meta = document.createElement("small");
      meta.textContent = " · משקל " + ind.weight + " · " + ind.category + " · מקור: " + ind.source + " · " + phaseTag;
      li.appendChild(strong); li.appendChild(meta);
      listEl.appendChild(li);
      emptyEl.classList.add("hidden");
      setTimeout(() => li.classList.remove("new-indicator"), 1500);
    });
  }

  function renderPolicy(actions, requested) {
    policyList.innerHTML = "";
    actions.forEach((a) => {
      const li = document.createElement("li");
      li.className = a.allowed ? "allowed" : "blocked";
      li.textContent = (a.allowed ? "✔ " : "✖ ") + a.label;
      policyList.appendChild(li);
    });
    if (requested) {
      reqLabel.textContent = requested.label;
      reqState.textContent = requested.allowed ? "מותר ברמה זו" : "חסום ברמה זו";
      reqState.className = requested.allowed ? "state-ok" : "state-blocked";
    }
  }

  function renderStepUp(su) {
    if (!su.required) return;
    stepUpBox.classList.remove("hidden");
    stepUpChannel.textContent = "ערוץ: " + su.channel_label;
    if (su.result && su.result !== "pending") {
      stepUpActions.classList.add("hidden");
      stepUpResult.classList.remove("hidden");
      stepUpStatus.textContent = su.result === "approved" ? "התקבלה תשובת אישור מהאפליקציה" : "לא התקבלה תשובת אישור מהאפליקציה";
      stepUpResult.textContent = su.result === "approved"
        ? "✔ הלקוח אישר באפליקציה - הזהות אומתה, הסיכון תוקן כלפי מטה"
        : "✖ הלקוח לא אישר - החשד מתחזק, הסיכון תוקן כלפי מעלה";
      stepUpResult.className = "step-up-result " + su.result;
    }
  }

  function renderEvents(events) {
    for (let i = shownEvents; i < events.length; i++) {
      const li = document.createElement("li");
      li.textContent = "[" + fmt(events[i].at) + "] " + events[i].text;
      eventList.appendChild(li);
    }
    shownEvents = events.length;
  }

  function render(d) {
    renderPhase(d.phase);
    timerEl.textContent = fmt(d.elapsed);
    scoreEl.textContent = d.score;
    levelEl.textContent = "רמת סיכון: " + d.level;
    const color = levelColor(d.level_key);
    scoreEl.style.color = color;
    progressEl.style.width = Math.min(d.score, 100) + "%";
    progressEl.style.backgroundColor = color;
    actionEl.textContent = d.recommendation;
    actionEl.className = "risk-action level-" + d.level_key;
    if (d.raw_score !== d.score) {
      rawNoteEl.classList.remove("hidden");
      rawNoteEl.textContent = "ציון גולמי " + d.raw_score + " → תוקן ל-" + d.score + " לאחר Step-Up";
    }
    renderIndicators(d.indicators);
    renderPolicy(d.actions, d.requested_action);
    renderStepUp(d.step_up);
    renderEvents(d.events);
    agentAction.value = d.level_key === "high" ? "escalate" : (d.phase === "step_up" ? "step_up_wait" : "continue");
  }

  async function poll() {
    try {
      const r = await fetch(statusUrl);
      if (!r.ok) return;
      const d = await r.json();
      render(d);
      if (!d.finished || d.phase === "step_up") setTimeout(poll, 1000);
    } catch (e) {
      console.error("שגיאה בטעינת סטטוס השיחה:", e);
      setTimeout(poll, 2000);
    }
  }

  stepUpActions.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const url = stepUpUrlTemplate.replace("RESULT", btn.dataset.result);
      const r = await fetch(url, { method: "POST" });
      if (r.ok) render(await r.json());
    });
  });

  document.querySelectorAll("#finish-form button[type=submit]").forEach((btn) => {
    btn.addEventListener("click", () => { agentAction.value = btn.dataset.action; });
  });

  poll();
})();
