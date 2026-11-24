"use strict";
const el = id => document.getElementById(id);
const fridgeKey = "fridge-to-meal.pantry.v1";
const key = sessionStorage.mealKey || crypto.randomUUID().replaceAll("-", "");
sessionStorage.mealKey = key;
let config, busy = true, ready = false, dirty = false;

async function api(path, body, onEvent) {
  const response = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: {"X-Meal-Session": key, "Content-Type": "application/json",
      Accept: onEvent ? "application/x-ndjson" : "application/json"},
    body: body && JSON.stringify(body)
  });
  if (response.ok && onEvent && response.headers.get("Content-Type")?.startsWith("application/x-ndjson")) {
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let pending = "";
    try {
      while (true) {
        const {value, done} = await reader.read();
        if (done) throw new Error("The response was interrupted. Please try again.");
        const lines = (pending + value).split("\n");
        pending = lines.pop();
        for (const line of lines) {
          if (!line) continue;
          const event = JSON.parse(line);
          if (event.type === "done") return event.data;
          if (event.type === "error") throw new Error(event.data);
          onEvent(event);
        }
      }
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
  }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed.");
  return data;
}
function controls() {
  el("fields").disabled = busy;
  el("message").disabled = el("send").disabled = busy || !ready || dirty;
  el("message").placeholder = busy ? "Please wait for the current request…"
    : !ready ? "Select Find recipes first to start a conversation…"
    : dirty ? "Select Find recipes to apply your changes first…"
    : "Make it for two people…";
}

function sameMealRequest(a, b) {
  if (!a || !b) return false;
  const values = request => [
    request.pantry?.map(item => [item.name, item.quantity, item.unit, item.expires_on ?? null]),
    request.servings, request.preferences?.dietary_restrictions,
    request.preferences?.likes, request.as_of_date
  ];
  return JSON.stringify(values(a)) === JSON.stringify(values(b));
}
function edited() {
  dirty = true;
  controls();
  el("status").textContent = "Select Find recipes to apply your changes.";
}
function today() {
  const now = new Date();
  return new Date(now - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}
function markExpiry(row) {
  const expiry = row.querySelector(".expiry").value;
  row.querySelector(".expired").hidden = !expiry || !el("date").value || expiry >= el("date").value;
}
function fridgeEdited() {
  el("fridge-status").textContent = "Save fridge to keep these ingredients for next time.";
  edited();
}
function addRow(item = {}) {
  const row = el("row").content.firstElementChild.cloneNode(true);
  const unit = row.querySelector(".unit");
  config.units.forEach(value => unit.add(new Option(value, value)));
  unit.value = item.unit || "g";
  row.querySelector(".name").value = item.name || "";
  row.querySelector(".qty").value = item.quantity ?? "";
  row.querySelector(".expiry").value = item.expires_on || "";
  row.querySelector(".remove").onclick = () => { row.remove(); fridgeEdited(); };
  el("rows").append(row);
  markExpiry(row);
}
function populate(state) {
  el("rows").replaceChildren();
  el("servings").value = state.servings ?? 2;
  el("date").value = state.as_of_date || today();
  (state.pantry ?? [{}]).forEach(addRow);
  el("likes").value = state.preferences.likes.join(", ");
  for (const box of el("restrictions").querySelectorAll("input"))
    box.checked = state.preferences.dietary_restrictions.includes(box.value);
}
function pantryFromForm() {
  return Array.from(el("rows").children, row => ({
      name: row.querySelector(".name").value.trim(), quantity: row.querySelector(".qty").valueAsNumber,
      unit: row.querySelector(".unit").value, expires_on: row.querySelector(".expiry").value || null
    }));
}
function requestFromForm() {
  return {
    pantry: pantryFromForm(),
    preferences: {
      dietary_restrictions: Array.from(el("restrictions").querySelectorAll(":checked"), box => box.value),
      likes: el("likes").value.split(",").map(s => s.trim()).filter(Boolean)
    },
    servings: el("servings").valueAsNumber, as_of_date: el("date").value
  };
}
const titles = {recommended:"Recipe recommendation", no_feasible_recipe:"No matching recipe",
  needs_clarification:"A question for you", tool_error:"Search unavailable"};
function appendList(parent, title, items, ordered = false) {
  const heading = document.createElement("h3");
  heading.textContent = title;
  parent.append(heading);
  const list = document.createElement(ordered ? "ol" : "ul");
  for (const item of items) {
    const li = document.createElement("li");
    li.append(item);
    list.append(li);
  }
  parent.append(list);
}
function sourceLink(label, value) {
  if (typeof value !== "string" || !value || /[\s\\]/.test(value)) return null;
  try {
    const url = new URL(value.startsWith("www.") ? "https://" + value : value);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) return null;
    const link = document.createElement("a");
    link.href = url.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = label || url.hostname;
    return link;
  } catch {
    return null;
  }
}
function runDetails(run) {
  const details = document.createElement("details");
  details.className = "run-details";
  const summary = document.createElement("summary");
  summary.textContent = "Run details";
  details.append(summary);

  const tasks = [], steps = [], sources = new Map();
  const trace = run.tool_trace || [];
  const request = run.request;
  if (run.follow_up_processed) steps.push("Interpreted your follow-up in this session.");
  if (request?.servings && request.pantry) {
    const restrictions = request.preferences.dietary_restrictions.join(", ") || "none";
    steps.push(`Current meal request: ${request.servings} serving(s), ${request.pantry.length} pantry lot(s), dietary restrictions: ${restrictions}.`);
  }
  const selected = new Set(run.result.recipe_ids);
  function cite(label, url) {
    const link = sourceLink(label, url);
    if (link && !sources.has(link.href)) sources.set(link.href, link);
  }
  for (const call of trace) {
    const result = call.result || {};
    tasks.push(call.tool);
    if (call.tool === "search_recipes") {
      const count = result.candidates?.length || 0;
      if (result.status === "found") steps.push(`Searched the catalogue and matched ${count} feasible recipe(s).`);
      else if (result.status === "no_match") steps.push("Searched the catalogue; no feasible recipe was confirmed.");
      else steps.push(`Search returned ${result.error_code || "an error"}.`);
      for (const recipe of result.candidates || []) {
        if (!selected.has(recipe.recipe_id)) continue;
        cite(recipe.title, recipe.source_url);
        for (const note of recipe.storage_guidance || [])
          cite("FoodKeeper storage guidance", note.source?.archive || note.source?.official_catalogue);
      }
    } else if (call.tool === "read_recipe") {
      steps.push(call.error_type ? "Could not read the selected recipe." : "Read the selected recipe’s source record.");
      cite(result.title, result.source_url);
    } else if (call.tool === "validate_adaptation") {
      steps.push(result.valid ? "Checked the adjusted recipe against quantities, servings and dietary restrictions."
        : "Rejected an adjustment that did not pass validation.");
    }
  }
  for (const recipe of run.adapted_recipes || []) {
    cite(recipe.source_title, recipe.source_url);
  }
  if (run.adapted_recipes?.length && !tasks.includes("validate_adaptation")) {
    steps.push("Rechecked the saved recipe adjustment against the current meal request.");
  }
  const outcomes = {recommended:"Returned the recipe recommendation.", no_feasible_recipe:"Reported no confirmed match.",
    needs_clarification:"Returned a clarification or additional details.", tool_error:"Reported a tool error."};
  steps.push(outcomes[run.result.status] || "Returned the response.");
  appendList(details, "Tools called", tasks.length ? tasks.map(name => {
    const code = document.createElement("code");
    code.textContent = name;
    return code;
  }) : ["No tools were called this turn."]);
  appendList(details, "Steps taken", steps, true);
  appendList(details, "Sources", sources.size ? [...sources.values()] : ["No source link cited for this response."]);
  if (run.result.status === "needs_clarification") {
    const related = new Map();
    for (const call of trace) {
      for (const recipe of call.result?.alternatives || []) {
        const link = sourceLink(recipe.title, recipe.source_url);
        if (link && !related.has(link.href)) related.set(link.href, link);
      }
    }
    if (related.size) appendList(details, "Related recipe records", [...related.values()]);
  }
  const metrics = document.createElement("p");
  metrics.className = "run-metrics";
  metrics.textContent = [...selected, run.metrics.model_calls + " model calls", run.metrics.elapsed_seconds + " s"].join(" · ");
  details.append(metrics);
  return details;
}
function entry(title, text) {
  el("empty")?.remove();
  const article = document.createElement("article");
  article.className = "entry";
  const heading = document.createElement("small");
  heading.textContent = title;
  const p = document.createElement("p");
  p.textContent = text;
  article.append(heading, p);
  el("history").append(article);
  el("history").scrollTop = el("history").scrollHeight;
  return {article, heading, p};
}
async function submit(body) {
  if (busy) return;
  busy = true;
  controls();
  el("status").textContent = "Checking your pantry and finding recipes…";
  if (body.message) entry("You", body.message);
  const reply = entry("Meal assistant", "Checking your pantry and finding recipes…");
  let hasText = false;
  reply.article.setAttribute("aria-busy", "true");
  try {
    const run = await api("/api/turn", body, event => {
      if (event.type === "progress" && !hasText) reply.p.textContent = event.data;
      if (event.type === "text") {
        if (!hasText) reply.p.textContent = "";
        hasText = true;
        reply.p.append(event.data);
        el("history").scrollTop = el("history").scrollHeight;
      }
    });
    const result = run.result;
    reply.heading.textContent = run.display_title || titles[result.status] || "Meal assistant";
    reply.p.textContent = result.message;
    reply.article.append(runDetails(run));
    reply.article.removeAttribute("aria-busy");
    // A source clarification can still accept the submitted pantry. Only retain
    // dirty input when the server did not accept that request snapshot.
    if (!body.update || result.status !== "needs_clarification" || sameMealRequest(body.update, run.request)) {
      populate(run.request);
      dirty = false;
    }
    ready = run.request.pantry !== null;
    el("message").value = "";
    el("status").textContent = "";
  } catch (error) {
    reply.article.remove();
    el("status").textContent = error.message;
  } finally {
    busy = false;
    controls();
  }
}
el("add").onclick = () => { addRow(); fridgeEdited(); };
el("rows").oninput = event => {
  if (event.target.matches(".name")) event.target.setCustomValidity("");
  markExpiry(event.target.closest(".ingredient"));
  fridgeEdited();
};
el("date").oninput = () => Array.from(el("rows").children).forEach(markExpiry);
el("save-fridge").onclick = () => {
  for (const row of el("rows").children) {
    const name = row.querySelector(".name");
    name.setCustomValidity(name.value.trim() ? "" : "Enter an ingredient name.");
    for (const field of row.querySelectorAll("input,select")) {
      if (!field.reportValidity()) return;
    }
  }
  try {
    localStorage.setItem(fridgeKey, JSON.stringify(pantryFromForm()));
    el("fridge-status").textContent = "Fridge saved in this browser.";
  } catch {
    el("fridge-status").textContent = "Could not save. Check browser storage settings.";
  }
};
el("example").onclick = () => { populate(config.example); fridgeEdited(); };
el("kitchen").oninput = edited;
el("kitchen").onsubmit = event => { event.preventDefault(); submit({update:requestFromForm()}); };
el("chat").onsubmit = event => { event.preventDefault(); const message = el("message").value.trim(); if (message) submit({message}); };
async function start() {
  try {
    config = await api("/api/kitchen");
    el("catalogue-status").textContent = config.catalogue?.description || "";
    for (const value of config.restrictions) {
      const label = document.createElement("label"), box = document.createElement("input");
      box.type = "checkbox"; box.value = value; label.append(box, document.createTextNode(value));
      el("restrictions").append(label);
    }
    const view = {...config.state};
    try {
      const stored = localStorage.getItem(fridgeKey);
      if (stored !== null) {
        const pantry = JSON.parse(stored);
        if (!Array.isArray(pantry) || !pantry.every(item =>
          item && typeof item.name === "string" && item.name.trim() &&
          Number.isFinite(item.quantity) && item.quantity >= 0 && config.units.includes(item.unit) &&
          (item.expires_on == null || /^\d{4}-\d{2}-\d{2}$/.test(item.expires_on))
        )) throw new Error("Invalid saved fridge");
        view.pantry = pantry;
        view.as_of_date = today();
        dirty = JSON.stringify(pantry) !== JSON.stringify(config.state.pantry) ||
          view.as_of_date !== config.state.as_of_date;
        el("fridge-status").textContent = "Saved fridge loaded for today.";
      }
    } catch {
      el("fridge-status").textContent = "Saved fridge unavailable. Check the ingredients before saving again.";
    }
    populate(view);
    ready = config.state.pantry !== null;
    busy = false;
    controls();
  } catch (error) { el("status").textContent = error.message; }
}
start();
