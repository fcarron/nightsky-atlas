const $ = (id) => document.getElementById(id);
let state = null;
let selected = new Set();
let zoom = 1;
let drag = null;
let spacePressed = false;
let suppressNextClick = false;
let contextLabelId = null;
let dragPaintedRects = [];

async function api(path, body) {
  const response = await fetch(path, body ? {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)} : {});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}
function setStatus(message) { $("status").textContent = message; }
function labelById(id) { return state.labels.find((item) => item.id === id); }
function labelInkBounds(label) {
  const glyphs = label.glyph_bounds || [];
  if (!glyphs.length) return label.bounds;
  const left = Math.min(...glyphs.map((item) => item.left_mm));
  const top = Math.min(...glyphs.map((item) => item.top_mm));
  const right = Math.max(...glyphs.map((item) => item.left_mm + item.width_mm));
  const bottom = Math.max(...glyphs.map((item) => item.top_mm + item.height_mm));
  const inset = 0.15;
  return {
    left_mm: left - inset,
    top_mm: top - inset,
    width_mm: right - left + 2 * inset,
    height_mm: bottom - top + 2 * inset,
  };
}
function pagePoint(event) {
  const point = new DOMPoint(event.clientX, event.clientY).matrixTransform($("overlay").getScreenCTM().inverse());
  return {x_mm:point.x, y_mm:point.y};
}
function renderDragPreview() {
  const canvas = $("drag-glyphs");
  const image = $("preview");
  const svg = $("overlay");
  svg.querySelector("#drag-preview")?.remove();
  let context = canvas.getContext("2d");
  for (const [x, y, width, height] of dragPaintedRects) context.clearRect(x, y, width, height);
  dragPaintedRects = [];
  if (!drag?.moved || drag.kind !== "label" || !image.naturalWidth) {
    if (canvas.width !== 1 || canvas.height !== 1) canvas.width = canvas.height = 1;
    return;
  }
  if (canvas.width !== image.naturalWidth || canvas.height !== image.naturalHeight) {
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    context = canvas.getContext("2d");
  }
  const pxPerMmX = image.naturalWidth / state.page.width_mm;
  const pxPerMmY = image.naturalHeight / state.page.height_mm;
  const scratch = document.createElement("canvas");
  const scratchContext = scratch.getContext("2d", {willReadFrequently:true});
  const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
  group.id = "drag-preview";
  group.classList.add("drag-preview");
  for (const id of drag.selected) {
    const label = labelById(id);
    if (!label) continue;
    const inkBounds = labelInkBounds(label);
    const left = inkBounds.left_mm + drag.dx;
    const top = inkBounds.top_mm + drag.dy;
    const glyphs = label.glyph_bounds?.length ? label.glyph_bounds : [label.bounds];
    for (const glyph of glyphs) {
      const sx = glyph.left_mm * pxPerMmX;
      const sy = glyph.top_mm * pxPerMmY;
      const sw = Math.max(1, Math.ceil(glyph.width_mm * pxPerMmX));
      const sh = Math.max(1, Math.ceil(glyph.height_mm * pxPerMmY));
      scratch.width = sw; scratch.height = sh;
      scratchContext.drawImage(image, sx, sy, sw, sh, 0, 0, sw, sh);
      const pixels = scratchContext.getImageData(0, 0, sw, sh);
      for (let index = 0; index < pixels.data.length; index += 4) {
        if (pixels.data[index] < 250 || pixels.data[index + 1] < 250 || pixels.data[index + 2] < 250) {
          pixels.data[index] = pixels.data[index + 1] = pixels.data[index + 2] = 255;
          pixels.data[index + 3] = 255;
        } else pixels.data[index + 3] = 0;
      }
      context.putImageData(pixels, sx, sy);
      const dx = (glyph.left_mm + drag.dx) * pxPerMmX;
      const dy = (glyph.top_mm + drag.dy) * pxPerMmY;
      context.drawImage(image, sx, sy, sw, sh, dx, dy, sw, sh);
      dragPaintedRects.push([sx, sy, sw, sh], [dx, dy, sw, sh]);
    }
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", left - 0.3);
    rect.setAttribute("y", top - 0.3);
    rect.setAttribute("width", inkBounds.width_mm + 0.3);
    rect.setAttribute("height", inkBounds.height_mm + 0.3);
    rect.setAttribute("rx", 0.25);
    group.append(rect);
  }
  svg.append(group);
}
function render() {
  if (!state) return;
  $("chart-title").textContent = `${state.edition} · ${state.chart_id} · ${state.chart.scale_mm_per_degree} mm/°`;
  renderSaveState();
  $("preview").src = `${state.preview_url}?v=${Date.now()}`;
  const svg = $("overlay");
  svg.setAttribute("viewBox", `0 0 ${state.page.width_mm} ${state.page.height_mm}`);
  svg.replaceChildren();
  const boxesOn = $("boxes").checked;
  const symbolsOn = $("symbols").checked;
  const selectedTargets = new Set([...selected].map((id) => labelById(id)?.target_id).filter(Boolean));
  const problemIds = new Set([...(state.issues || []), ...(state.ai_new_issues || [])].flatMap((item) => item.elements || []));
  for (const item of state.symbols) {
    if (!symbolsOn && !selectedTargets.has(item.id)) continue;
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", item.x_mm); circle.setAttribute("cy", item.y_mm); circle.setAttribute("r", selectedTargets.has(item.id) ? 1.8 : item.kind === "star" ? .45 : .7);
    circle.setAttribute("class", `symbol-anchor ${selectedTargets.has(item.id) ? "target-anchor" : ""}`);
    circle.addEventListener("click", (event) => {
      const matching = state.labels.filter((label) => label.target_id === item.id).map((label) => label.id);
      if (matching.length) { if (!event.shiftKey) selected.clear(); for (const id of matching) selected.add(id); render(); }
    });
    svg.append(circle);
  }
  for (const label of state.labels) {
    const inkBounds = labelInkBounds(label);
    if (boxesOn || selected.has(label.id) || problemIds.has(label.id)) {
      const box = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      box.setAttribute("x", inkBounds.left_mm);
      box.setAttribute("y", inkBounds.top_mm);
      box.setAttribute("width", inkBounds.width_mm);
      box.setAttribute("height", inkBounds.height_mm);
      box.setAttribute("class", `label-box ${boxesOn ? "visible" : ""} ${selected.has(label.id) ? "selected" : ""} ${label.locked ? "locked" : ""} ${problemIds.has(label.id) ? "label-issue" : ""}`);
      svg.append(box);
    }
    const r = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    r.dataset.labelId = label.id; r.setAttribute("x", label.bounds.left_mm); r.setAttribute("y", label.bounds.top_mm); r.setAttribute("width", label.bounds.width_mm); r.setAttribute("height", label.bounds.height_mm);
    r.setAttribute("class", "label-hit"); r.addEventListener("pointerdown", startLabelDrag); r.addEventListener("contextmenu", (event) => openContextMenu(event, label.id)); svg.append(r);
  }
  renderRegionSelection();
  $("zoom").textContent = `${Math.round(zoom*100)}%`; $("stage").style.transform = "none"; $("stage").style.width = `${state.page.width_mm*96/25.4*zoom}px`;
  $("undo").disabled = !state.undo_available; $("redo").disabled = !state.redo_available;
  $("save").disabled = !state.has_unsaved_changes;
  const manualDisabled = ["as_is", "ai_only"].includes($("mode").value);
  for (const id of ["candidate", "offset-x", "offset-y", "apply-offset", "leader", "locked", "restore"]) $(id).disabled = manualDisabled;
  renderSelection(); renderValidation();
  renderDragPreview();
  $("ask-ai").disabled = !["ai_only","ai_human"].includes($("mode").value);
  $("reset").disabled = manualDisabled;
  $("as-is").disabled = Boolean(state.external_overrides_path);
  $("override-source-warning").hidden = !state.external_overrides_path;
}
function renderSaveState() {
  const indicator = $("save-state");
  if (state.draft_status === "recovered") {
    indicator.textContent = "Recovered local draft";
    indicator.className = "save-state unsaved";
  } else if (state.has_unsaved_changes) {
    indicator.textContent = "Draft autosaved locally";
    indicator.className = "save-state unsaved";
  } else if (state.review_status === "accepted_as_is") {
    indicator.textContent = "Accepted as is";
    indicator.className = "save-state saved";
  } else if (state.review_status === "corrected") {
    indicator.textContent = "Corrections saved";
    indicator.className = "save-state saved";
  } else {
    indicator.textContent = "Not reviewed";
    indicator.className = "save-state";
  }
  const banner = $("draft-banner");
  const parts = [];
  if (state.draft_status === "recovered") parts.push("Recovered unsaved local draft. It is not yet saved as an atlas override.");
  else if (state.draft_status === "autosaved") parts.push("Unsaved edits are autosaved locally; use Save corrections to write the atlas override.");
  if (state.baseline_origin === "saved_workspace_overrides") parts.push(`Loaded saved workspace overrides: ${state.local_overrides_path}`);
  if (state.draft_warning) parts.push(state.draft_warning);
  banner.textContent = parts.join(" ");
  banner.hidden = !parts.length;
  banner.className = state.draft_warning ? "draft-banner warning" : "draft-banner";
}
function renderSelection() {
  const list = $("selection-list"); list.replaceChildren();
  for (const id of selected) {
    const label = labelById(id); if (!label) continue;
    const row = document.createElement("div"); row.className = "selection-item active"; row.textContent = `${label.text} · ${label.target_id}${label.locked ? " · locked" : ""}`; row.onclick = () => selectLabel(id, false); list.append(row);
  }
  const labels = [...selected].map(labelById).filter(Boolean);
  $("selection-hint").textContent = labels.length ? `${labels.length} label(s) selected` : "Select one or more labels on the chart.";
  const label = labels.length === 1 ? labels[0] : null;
  $("editor-controls").hidden = !label;
  if (!label) return;
  $("label-name").textContent = `${label.text} · ${label.target_id}`;
  $("label-id").textContent = label.id;
  $("candidate").replaceChildren();
  if (!label.candidates.some((item) => item.id === label.candidate_id)) {
    const option = document.createElement("option"); option.value = label.candidate_id; option.textContent = `Current · ${label.candidate} · manual offset`; option.selected = true; $("candidate").append(option);
  }
  for (const candidate of label.candidates) {
    const option = document.createElement("option"); option.value = candidate.id; option.textContent = `${candidate.position}${candidate.ring ? ` · ring ${candidate.ring}` : ""}`;
    option.selected = candidate.id === label.candidate_id; $("candidate").append(option);
  }
  $("offset-x").value = label.offset_mm.x; $("offset-y").value = label.offset_mm.y;
  $("leader").checked = label.leader_line; $("locked").checked = label.locked;
  $("label-state").textContent = `Candidate ${label.candidate} · ${label.locked ? "locked against automatic changes" : "unlocked"} · leader line ${label.leader_line ? "on" : "off"}`;
  for (const id of ["candidate", "offset-x", "offset-y", "apply-offset"]) $(id).disabled = ["as_is", "ai_only"].includes($("mode").value);
  $("restore").disabled = ["as_is", "ai_only"].includes($("mode").value);
}
function renderValidation() {
  const target = $("validation"); target.replaceChildren();
  const items = state.issues || [];
  const additions = state.ai_new_issues || [];
  $("issue-count").textContent = items.length || additions.length ? `(${items.length}${additions.length ? ` + ${additions.length} proposed` : ""})` : "(clear)";
  const hints = state.optimizer_hints || {};
  const hintHeader = document.createElement("div");
  hintHeader.className = "muted validation-scope";
  hintHeader.textContent = hints.scope || "Optimizer review hints";
  target.append(hintHeader);
  for (const [key, title] of [["warnings","Warnings"],["high_density","High local density"],["possible_ambiguity","Possible object ambiguity"]]) {
    const ids = hints[key] || [];
    const row = document.createElement("button");
    row.type = "button";
    row.className = "hint-row";
    const heading = document.createElement("strong"); heading.textContent = `${title}: ${ids.length}`; row.append(heading);
    if (ids.length) {
      const names = document.createElement("span");
      names.textContent = ids.map((id) => { const label=labelById(id); return label ? label.text : id; }).join(", ");
      row.append(names);
      row.title = "Select the labels associated with this baseline hint";
      row.addEventListener("click", () => { selected = new Set(ids); render(); });
    }
    target.append(row);
  }
  const hardHeading = document.createElement("div"); hardHeading.className = "validation-scope"; hardHeading.textContent = `Hard geometry errors in current layout: ${items.length}`; target.append(hardHeading);
  if (!items.length && !additions.length) { const clear=document.createElement("div");clear.className="muted";clear.textContent="No current hard layout violations.";target.append(clear);return; }
  const description = (item) => {
    const names = (item.elements || []).map((id) => {
      const label = labelById(id);
      return label ? `${label.text} (${label.target_id})` : id;
    });
    if (item.type === "label_dso" && names.length > 1) return `${names[0]} label overlaps object ${names[1]}`;
    if (item.type === "label_label" && names.length > 1) return `Labels ${names[0]} and ${names[1]} overlap`;
    return item.message;
  };
  for (const item of items) {
    const div = document.createElement("button");
    div.type = "button";
    div.className = "issue";
    div.textContent = description(item);
    div.title = "Select the labels involved in this layout issue";
    div.addEventListener("click", () => {
      const elements = new Set(item.elements || []);
      const related = state.labels.filter((label) => elements.has(label.id) || elements.has(label.target_id));
      if (related.length) { selected = new Set(related.map((label) => label.id)); render(); }
    });
    target.append(div);
  }
  for (const item of additions) { const div = document.createElement("div"); div.className = "issue"; div.textContent = `AI proposal adds: ${description(item)}`; target.append(div); }
}
function selectLabel(id, additive) { if (suppressNextClick) { suppressNextClick = false; return; } if (!additive) selected.clear(); if (selected.has(id) && additive) selected.delete(id); else selected.add(id); render(); }
function startLabelDrag(event) {
  if(event.button===1||spacePressed){drag={kind:"pan",clientX:event.clientX,clientY:event.clientY,left:$("viewport").scrollLeft,top:$("viewport").scrollTop};window.addEventListener("pointermove",moveRegionSelect);window.addEventListener("pointerup",endRegionSelect,{once:true});event.preventDefault();return;}
  const id = event.currentTarget.dataset.labelId;
  if (["as_is","ai_only"].includes($("mode").value)) {
    if (event.shiftKey) { if (selected.has(id)) selected.delete(id); else selected.add(id); }
    else selected = new Set([id]);
    render();
    event.preventDefault();
    return;
  }
  event.preventDefault(); event.stopPropagation();
  const selectionBefore = new Set(selected);
  const moving = selected.has(id) ? [...selected] : event.shiftKey ? [...selected, id] : [id];
  selected = new Set(moving);
  renderSelection();
  drag = {kind:"label", start:pagePoint(event), selected:moving, selectionBefore, clickedLabel:id, additive:event.shiftKey, moved:false};
  window.addEventListener("pointermove", moveLabelDrag); window.addEventListener("pointerup", endLabelDrag, {once:true});
}
function moveLabelDrag(event) {
  if (!drag) return; const now=pagePoint(event); drag.dx=now.x_mm-drag.start.x_mm; drag.dy=now.y_mm-drag.start.y_mm; drag.moved=Math.hypot(drag.dx,drag.dy)>.15;
  renderDragPreview();
  if (drag.moved) setStatus(`Moving ${drag.selected.length} label(s) · Δx ${drag.dx.toFixed(1)} mm · Δy ${drag.dy.toFixed(1)} mm`);
}
async function endLabelDrag(event) {
  if (!drag) return; const current=drag; drag=null; window.removeEventListener("pointermove", moveLabelDrag);
  if (!current.moved) {
    selected = current.selectionBefore;
    if (current.additive) {
      if (selected.has(current.clickedLabel)) selected.delete(current.clickedLabel);
      else selected.add(current.clickedLabel);
    } else selected = new Set([current.clickedLabel]);
    render(); return;
  }
  selected = new Set(current.selected); suppressNextClick = true; window.setTimeout(() => { suppressNextClick = false; }, 150);
  setStatus("Checking placement…");
  try { await refresh(await api("/api/apply", {operations:[{type:"group_move",label_ids:current.selected,dx_mm:current.dx,dy_mm:current.dy}],source:"human"})); setStatus("Placement updated and validated."); }
  catch (error) { render(); setStatus(error.message); }
}
function startRegionSelect(event) {
  if (event.target !== $("overlay")) return;
  if (event.button === 1 || spacePressed) { drag={kind:"pan",clientX:event.clientX,clientY:event.clientY,left:$("viewport").scrollLeft,top:$("viewport").scrollTop}; window.addEventListener("pointermove",moveRegionSelect);window.addEventListener("pointerup",endRegionSelect,{once:true});return; }
  drag={kind:"region",start:pagePoint(event),end:pagePoint(event),additive:event.shiftKey};
  window.addEventListener("pointermove",moveRegionSelect);window.addEventListener("pointerup",endRegionSelect,{once:true});
}
function moveRegionSelect(event) {
  if(!drag)return;
  if(drag.kind==="pan") { $("viewport").scrollLeft=drag.left-(event.clientX-drag.clientX);$("viewport").scrollTop=drag.top-(event.clientY-drag.clientY);return; }
  drag.end=pagePoint(event);
  renderRegionSelection();
}
function renderRegionSelection() {
  const svg = $("overlay");
  svg.querySelector("#region-selection")?.remove();
  if (!drag || drag.kind !== "region" || !drag.end) return;
  const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  rect.id = "region-selection";
  rect.setAttribute("x", Math.min(drag.start.x_mm, drag.end.x_mm));
  rect.setAttribute("y", Math.min(drag.start.y_mm, drag.end.y_mm));
  rect.setAttribute("width", Math.abs(drag.end.x_mm - drag.start.x_mm));
  rect.setAttribute("height", Math.abs(drag.end.y_mm - drag.start.y_mm));
  rect.setAttribute("class", "region-selection");
  svg.append(rect);
}
function endRegionSelect() {
  window.removeEventListener("pointermove",moveRegionSelect);
  if(!drag)return; const current=drag;drag=null;
  if(current.kind==="region") {
    const left=Math.min(current.start.x_mm,current.end.x_mm),right=Math.max(current.start.x_mm,current.end.x_mm),top=Math.min(current.start.y_mm,current.end.y_mm),bottom=Math.max(current.start.y_mm,current.end.y_mm);
    if(!current.additive)selected.clear();
    if(right-left>.8||bottom-top>.8) for(const label of state.labels) if(label.bounds.left_mm<right&&label.bounds.left_mm+label.bounds.width_mm>left&&label.bounds.top_mm<bottom&&label.bounds.top_mm+label.bounds.height_mm>top)selected.add(label.id);
    render();
  }
}
async function refresh(next) { state=next && next.labels ? next : await api("/api/state"); render(); }
async function applySingle(operation) { try { await refresh(await api("/api/apply",{operations:[operation],source:"human"})); setStatus("Placement updated."); } catch(e) { setStatus(e.message); } }
function closeContextMenu() { $("context-menu").hidden = true; contextLabelId = null; }
function openContextMenu(event, id) {
  event.preventDefault(); event.stopPropagation();
  if (!selected.has(id)) selectLabel(id, false);
  contextLabelId = id;
  const label = labelById(id);
  const menu = $("context-menu");
  menu.querySelector('[data-action="toggle-leader"]').textContent = label.leader_line ? "Hide leader line" : "Show leader line";
  menu.querySelector('[data-action="toggle-lock"]').textContent = label.locked ? "Unlock label" : "Lock label";
  menu.hidden = false;
  menu.style.left = `${Math.max(8, Math.min(event.clientX, window.innerWidth - menu.offsetWidth - 8))}px`;
  menu.style.top = `${Math.max(8, Math.min(event.clientY, window.innerHeight - menu.offsetHeight - 8))}px`;
  menu.querySelector("button")?.focus();
}
async function moveSelection(dx, dy) {
  const ids = [...selected];
  if (!ids.length) return;
  try {
    await refresh(await api("/api/apply", {operations:[{type:"group_move",label_ids:ids,dx_mm:dx,dy_mm:dy}],source:"human"}));
    setStatus(`Moved ${ids.length} label(s) by ${Math.hypot(dx,dy).toFixed(1)} mm.`);
  } catch (error) { setStatus(error.message); }
}
$("candidate").addEventListener("change", () => { const label=[...selected][0]; if(label) applySingle({type:"candidate",label_id:label,candidate:$("candidate").value}); });
$("select-all").onclick=()=>{selected=new Set(state.labels.map((label)=>label.id));render();};
$("clear-selection").onclick=()=>{selected.clear();render();};
$("apply-offset").onclick=()=>{const id=[...selected][0]; if(id) applySingle({type:"offset",label_id:id,x:Number($("offset-x").value),y:Number($("offset-y").value)});};
$("leader").onchange=()=>{const id=[...selected][0];if(id)applySingle({type:"leader_line",label_id:id,enabled:$("leader").checked});};
$("locked").onchange=()=>{const id=[...selected][0];if(id)applySingle({type:"lock",label_id:id,locked:$("locked").checked});};
$("restore").onclick=()=>{const id=[...selected][0];if(id)applySingle({type:"reset_position",label_id:id});};
$("undo").onclick=async()=>refresh(await api("/api/undo",{})); $("redo").onclick=async()=>refresh(await api("/api/redo",{})); $("reset").onclick=async()=>{if((state.has_unsaved_changes||state.review_status==="corrected")&&!window.confirm("Discard the current edits and restore the automatic layout? Saved overrides remain untouched until you explicitly save or accept as-is."))return;await refresh(await api("/api/reset",{}));};
$("save").onclick=async()=>{try{const result=await api("/api/save",{note:""});await refresh(await api("/api/state"));setStatus(`Saved corrections to ${result.override_path}.`);}catch(e){setStatus(e.message);}};
$("as-is").onclick=async()=>{if((state.has_unsaved_changes||state.review_status==="corrected")&&!window.confirm("Discard saved or unsaved corrections and accept the automatic layout as is?"))return;try{const result=await api("/api/accept-as-is",{note:""});selected.clear();await refresh(await api("/api/state"));setStatus(`Accepted deterministic baseline. Review record: ${result.review_path}`);}catch(e){setStatus(e.message);}};
$("export").onclick=async()=>{try{const result=await api("/api/export",{});setStatus(`Rendered with the atlas renderer: ${result.pdf_path}`);}catch(e){setStatus(e.message);}};
$("ask-ai").onclick=async()=>{try{const result=await api("/api/ai/suggest",{label_ids:[...selected],instruction:$("instruction").value});$("proposal").hidden=false;$("ai-preview").src=`${result.preview_url}?v=${Date.now()}`;$("accept-ai").disabled=!result.can_accept;$("ai-summary").textContent=`${result.applied_actions} suggested action(s), score ${result.page_score}${result.can_accept?"":" · adds hard issues; discard or request another proposal"}`;await refresh(await api("/api/state"));setStatus(result.usage?.cost_usd!=null?`AI proposal received; reported cost $${result.usage.cost_usd.toFixed(4)}.`:"AI proposal received.");}catch(e){setStatus(e.message);}};
$("accept-ai").onclick=async()=>{try{$("proposal").hidden=true;await refresh(await api("/api/ai/accept",{}));setStatus("AI proposal accepted as a reversible editor change.");}catch(e){setStatus(e.message);}};
$("reject-ai").onclick=async()=>{await refresh(await api("/api/ai/reject",{}));$("proposal").hidden=true;setStatus("AI proposal discarded.");};
$("zoom-in").onclick=()=>{zoom=Math.min(4,zoom*1.25);render();}; $("zoom-out").onclick=()=>{zoom=Math.max(.5,zoom/1.25);render();}; $("boxes").onchange=render; $("symbols").onchange=render; $("mode").onchange=render;
$("viewport").addEventListener("wheel",(event)=>{if(!event.ctrlKey)return;event.preventDefault();zoom=Math.max(.5,Math.min(4,zoom*(event.deltaY<0?1.1:.9)));render();},{passive:false});
$("overlay").addEventListener("pointerdown",startRegionSelect);
$("context-menu").addEventListener("click", async (event) => {
  const action = event.target.closest("button")?.dataset.action;
  const id = contextLabelId;
  closeContextMenu();
  if (!id || !action) return;
  const label = labelById(id);
  if (action === "toggle-leader") await applySingle({type:"leader_line",label_id:id,enabled:!label.leader_line});
  if (action === "toggle-lock") await applySingle({type:"lock",label_id:id,locked:!label.locked});
  if (action === "restore") await applySingle({type:"reset_position",label_id:id});
});
document.addEventListener("pointerdown", (event) => { if (!event.target.closest("#context-menu")) closeContextMenu(); });
window.addEventListener("keydown",async(event)=>{
  const editing = ["INPUT","TEXTAREA","SELECT"].includes(document.activeElement.tagName);
  const command = event.ctrlKey || event.metaKey;
  if (editing && command && ["z","y"].includes(event.key.toLowerCase())) return;
  if (event.key === "Escape") { if (drag?.kind === "label") { drag = null; window.removeEventListener("pointermove",moveLabelDrag); render(); } closeContextMenu(); return; }
  if (command && event.key.toLowerCase() === "z") { event.preventDefault(); closeContextMenu(); await refresh(await api(event.shiftKey?"/api/redo":"/api/undo",{})); return; }
  if (command && event.key.toLowerCase() === "y") { event.preventDefault(); closeContextMenu(); await refresh(await api("/api/redo",{})); return; }
  if (!editing && selected.size && ["ArrowUp","ArrowDown","ArrowLeft","ArrowRight"].includes(event.key)) { event.preventDefault(); const step=event.shiftKey?1:0.2; await moveSelection(event.key==="ArrowLeft"?-step:event.key==="ArrowRight"?step:0,event.key==="ArrowUp"?-step:event.key==="ArrowDown"?step:0); return; }
  if(event.code==="Space"&&!editing){spacePressed=true;event.preventDefault();}
});
window.addEventListener("keyup",(event)=>{if(event.code==="Space")spacePressed=false;});
$("preview").addEventListener("load", () => { if (drag?.moved) renderDragPreview(); });
api("/api/state").then((data)=>{state=data;render();}).catch((error)=>setStatus(error.message));
