const calibrationKey = "nightSkyLabelReviewCalibration";
const sessionKey = "nightSkyLabelReviewSession";
const state = {
  pxPerMm: 3.78,
  calibrated: false,
  sessionId: "",
  cases: [],
  todo: [],
  current: null,
  clicks: {A: null, B: null},
  preference: null,
  startedAt: 0,
};

const byId = (id) => document.getElementById(id);

function sessionId() {
  try {
    let value = localStorage.getItem(sessionKey);
    if (!value) {
      value = crypto.randomUUID();
      localStorage.setItem(sessionKey, value);
    }
    return value;
  } catch {
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
}

function loadCalibration() {
  try {
    const stored = JSON.parse(localStorage.getItem(calibrationKey) || "null");
    if (stored && Number.isFinite(stored.pxPerMm) && stored.pxPerMm >= 1 && stored.pxPerMm <= 20) {
      state.pxPerMm = stored.pxPerMm;
    }
  } catch {
    state.pxPerMm = 3.78;
  }
  byId("pxPerMm").value = state.pxPerMm.toFixed(2);
  updateRuler();
}

function updateRuler() {
  const parsed = Number(byId("pxPerMm").value);
  if (!Number.isFinite(parsed) || parsed < 1 || parsed > 20) return;
  state.pxPerMm = parsed;
  byId("ruler").style.width = `${50 * parsed}px`;
  byId("scaleValue").textContent = `${parsed.toFixed(2).replace(".", ",")} px/mm`;
  try { localStorage.setItem(calibrationKey, JSON.stringify({pxPerMm: parsed})); } catch {}
}

async function start(calibrated) {
  updateRuler();
  state.calibrated = calibrated;
  state.sessionId = sessionId();
  let response;
  try {
    response = await fetch(`/api/session?session_id=${encodeURIComponent(state.sessionId)}`, {cache: "no-store"});
  } catch {
    showCalibrationError("Die lokale App antwortet nicht. Starte den Server erneut.");
    return;
  }
  const data = await response.json();
  if (!response.ok) {
    showCalibrationError(data.error || "Die Fallliste konnte nicht geladen werden.");
    return;
  }
  if (data.require_calibration && !calibrated) {
    showCalibrationError("Für diese Runde bitte die 50-mm-Linie messen und kalibriert starten.");
    return;
  }
  state.cases = data.cases;
  state.todo = data.cases.filter((item) => !item.completed);
  byId("calibration").classList.add("hidden");
  if (!state.todo.length) {
    byId("finished").classList.remove("hidden");
    return;
  }
  byId("review").classList.remove("hidden");
  byId("calibrationStatus").textContent = calibrated
    ? `Kalibriert · ${state.pxPerMm.toFixed(2)} px/mm`
    : "Unkalibriert · physische Anzeigegröße unsicher";
  showCase(0);
}

function showCalibrationError(message) {
  byId("calibrationError").textContent = message;
}

function showCase(index) {
  if (index >= state.todo.length) {
    byId("review").classList.add("hidden");
    byId("finished").classList.remove("hidden");
    return;
  }
  const item = state.todo[index];
  state.current = item;
  state.clicks = {A: null, B: null};
  state.preference = null;
  state.startedAt = performance.now();
  byId("progress").textContent = `Fall ${index + 1} von ${state.todo.length}`;
  byId("chartTitle").textContent = item.chart_code;
  byId("question").textContent = item.question;
  for (const [slot, imageId, statusId, url] of [
    ["A", "imageA", "statusA", item.image_a],
    ["B", "imageB", "statusB", item.image_b],
  ]) {
    const image = byId(imageId);
    image.src = url;
    image.style.width = `${item.print_width_mm * state.pxPerMm}px`;
    image.style.height = `${item.print_height_mm * state.pxPerMm}px`;
    image.dataset.slot = slot;
    image.onclick = onImageClick;
    byId(statusId).textContent = "Symbol anklicken";
  }
  byId("preference").disabled = true;
  byId("save").disabled = true;
  byId("note").value = "";
  byId("message").textContent = "";
  document.querySelectorAll(".choice").forEach((button) => button.classList.remove("selected"));
  byId("skip").disabled = false;
}

function onImageClick(event) {
  const slot = event.currentTarget.dataset.slot;
  const rect = event.currentTarget.getBoundingClientRect();
  const x = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
  const y = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
  state.clicks[slot] = {x, y};
  byId(slot === "A" ? "statusA" : "statusB").textContent = `Bild ${slot} ausgewählt`;
  if (state.clicks.A && state.clicks.B) byId("preference").disabled = false;
  updateSaveState();
}

function updateSaveState() {
  byId("save").disabled = !(state.clicks.A && state.clicks.B && state.preference);
}

document.querySelectorAll(".choice").forEach((button) => {
  button.addEventListener("click", () => {
    state.preference = button.dataset.value;
    document.querySelectorAll(".choice").forEach((item) => item.classList.toggle("selected", item === button));
    updateSaveState();
  });
});

async function submit(preference) {
  if (!state.current) return;
  const isSkip = preference === "skip";
  const payload = {
    session_id: state.sessionId,
    case_id: state.current.case_id,
    clicks: isSkip ? {} : state.clicks,
    preference,
    elapsed_ms: Math.max(0, Math.round(performance.now() - state.startedAt)),
    note: byId("note").value,
    px_per_mm: state.calibrated ? state.pxPerMm : null,
    calibrated: state.calibrated,
  };
  byId("save").disabled = true;
  byId("skip").disabled = true;
  byId("message").textContent = "Speichere lokal …";
  try {
    const response = await fetch("/api/answer", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Antwort konnte nicht gespeichert werden.");
    byId("message").textContent = "Gespeichert.";
    const nextIndex = state.todo.indexOf(state.current) + 1;
    window.setTimeout(() => showCase(nextIndex), 180);
  } catch (error) {
    byId("message").textContent = error.message;
    byId("skip").disabled = false;
    updateSaveState();
  }
}

byId("startCalibrated").addEventListener("click", () => start(true));
byId("startUncalibrated").addEventListener("click", () => start(false));
byId("pxPerMm").addEventListener("input", updateRuler);
byId("save").addEventListener("click", () => submit(state.preference));
byId("skip").addEventListener("click", () => submit("skip"));
byId("newSession").addEventListener("click", () => {
  try { localStorage.removeItem(sessionKey); } catch {}
  byId("finished").classList.add("hidden");
  byId("review").classList.add("hidden");
  byId("calibration").classList.remove("hidden");
  loadCalibration();
});

loadCalibration();
fetch("/api/config", {cache: "no-store"})
  .then((response) => response.json())
  .then((config) => {
    if (config.require_calibration) byId("startUncalibrated").classList.add("hidden");
  })
  .catch(() => {});
