const state = { uploads: [], artifacts: [], selectedArtifact: "" };

const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[char]));

async function jsonFetch(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

async function refreshHealth() {
  try { await jsonFetch("/api/health"); $("health").textContent = "Local service online"; document.querySelector(".status-dot").style.background = "var(--green)"; }
  catch (error) { $("health").textContent = "Service unavailable"; }
}

function renderUploads() {
  $("upload-list").innerHTML = state.uploads.length ? state.uploads.map((item) => `<div class="upload-item"><span>${escapeHtml(item.file_name)}</span><span class="muted">${Math.round(item.bytes / 1024)} KB</span></div>`).join("") : "";
}

function renderTrace(run) {
  $("run-status").textContent = run.status || "completed";
  const steps = run.steps || [];
  $("trace").className = "trace";
  $("trace").innerHTML = steps.map((step, index) => `<div class="trace-item"><div class="trace-index">${String(index + 1).padStart(2, "0")}</div><div><strong>${escapeHtml(step.agent)}</strong><span>${escapeHtml(step.summary)}</span></div></div>`).join("") || "No trace returned.";
  $("sources").innerHTML = (run.sources || []).length ? `<p class="section-kicker">SOURCES</p>${run.sources.map((source) => `<a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">${escapeHtml(source.title)}</a>`).join("")}` : "";
}

function renderArtifacts() {
  const select = $("artifact-select");
  select.innerHTML = `<option value="">Select an artifact</option>` + state.artifacts.map((item) => `<option value="${item.artifact_id}">${escapeHtml(item.file_name)} · v${item.version_count}</option>`).join("");
  $("artifacts").className = state.artifacts.length ? "artifact-list" : "artifacts empty-state";
  $("artifacts").innerHTML = state.artifacts.length ? state.artifacts.map((item) => `<div class="artifact-item"><strong>${escapeHtml(item.file_name)}</strong><div class="artifact-meta">${escapeHtml(item.file_type.toUpperCase())} · ${item.version_count} version(s) · ${escapeHtml(item.validation?.passed ? "validated" : "review required")}</div><div class="artifact-links"><a href="/api/artifacts/${item.artifact_id}/download" download>Download current</a><a href="/api/artifacts/${item.artifact_id}" target="_blank">Inspect trace</a></div></div>`).join("") : "Generated files will appear here.";
}

async function refreshArtifacts() { const data = await jsonFetch("/api/artifacts"); state.artifacts = data.artifacts || []; renderArtifacts(); }

async function uploadFiles(files) {
  for (const file of files) {
    const form = new FormData(); form.append("file", file);
    const result = await jsonFetch("/api/upload", { method: "POST", body: form });
    state.uploads.unshift(result.upload);
  }
  renderUploads();
}

async function runWorkflow(message, artifactId = null) {
  $("run-button").disabled = true; $("run-status").textContent = "Running"; $("trace").className = "trace empty-state"; $("trace").textContent = "Supervisor is delegating…";
  try {
    const result = await jsonFetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message, artifact_id: artifactId, upload_ids: state.uploads.map((item) => item.upload_id), slide_count: 12 }) });
    renderTrace(result); await refreshArtifacts();
  } catch (error) { $("run-status").textContent = "Error"; $("trace").textContent = error.message; }
  finally { $("run-button").disabled = false; }
}

$("file-input").addEventListener("change", (event) => uploadFiles(event.target.files).catch((error) => { $("upload-list").textContent = error.message; }));
$("run-button").addEventListener("click", () => runWorkflow($("message").value));
$("refresh-button").addEventListener("click", () => refreshArtifacts().catch((error) => { $("artifacts").textContent = error.message; }));
$("edit-button").addEventListener("click", () => { const id = $("artifact-select").value; const message = $("edit-input").value.trim(); if (!id || !message) return; runWorkflow(message, id); });
document.querySelectorAll(".chip").forEach((button) => button.addEventListener("click", () => { $("edit-input").value = button.dataset.prompt; }));
const dropzone = $("dropzone"); ["dragenter", "dragover"].forEach((eventName) => dropzone.addEventListener(eventName, (event) => { event.preventDefault(); dropzone.classList.add("dragging"); })); ["dragleave", "drop"].forEach((eventName) => dropzone.addEventListener(eventName, (event) => { event.preventDefault(); dropzone.classList.remove("dragging"); })); dropzone.addEventListener("drop", (event) => uploadFiles(event.dataTransfer.files).catch((error) => { $("upload-list").textContent = error.message; }));
refreshHealth(); refreshArtifacts().catch(() => {});
