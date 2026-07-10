const state = { projects: [], activeProject: null, latestRun: null };

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Request failed: ${response.status}`);
  return body;
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  setTimeout(() => toast.classList.add("hidden"), 4200);
}

function escapeHtml(value = "") {
  return String(value).replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  }[char]));
}

function badge(value) {
  return `<span class="badge ${escapeHtml(value)}">${escapeHtml(value.replaceAll("_", " "))}</span>`;
}

async function checkHealth() {
  try {
    await api("/api/health");
    $("healthStatus").textContent = "Service online";
  } catch {
    $("healthStatus").textContent = "Service unavailable";
  }
}

async function loadProjects() {
  state.projects = await api("/api/projects");
  const list = $("projectList");
  list.innerHTML = state.projects.map((project) => `
    <div class="project-card ${state.activeProject?.id === project.id ? "active" : ""}" data-project="${project.id}">
      <strong>${escapeHtml(project.name)}</strong>
      <div class="meta">${project.case_count} cases · ${project.document_count} docs · ${project.run_count} runs</div>
    </div>
  `).join("") || `<div class="meta">No projects yet.</div>`;
  list.querySelectorAll("[data-project]").forEach((node) => {
    node.addEventListener("click", () => openProject(Number(node.dataset.project)));
  });
}

async function openProject(id) {
  state.activeProject = await api(`/api/projects/${id}`);
  state.latestRun = state.activeProject.runs?.[0] ? await api(`/api/runs/${state.activeProject.runs[0].id}`) : null;
  $("emptyState").classList.add("hidden");
  $("projectView").classList.remove("hidden");
  $("activeProjectName").textContent = state.activeProject.name;
  $("activeProjectDescription").textContent = state.activeProject.description || "No description";
  renderProject();
  await loadProjects();
}

function renderProject() {
  const project = state.activeProject;
  const latestMetrics = state.latestRun?.metrics || {};
  $("projectStats").innerHTML = [
    [project.documents.length, "Reference documents"],
    [project.cases.length, "Evaluation cases"],
    [project.runs.length, "Runs"],
    [latestMetrics.human_review_count ?? "—", "Needs human review"],
  ].map(([value, label]) => `<div class="stat"><strong>${value}</strong><span>${label}</span></div>`).join("");

  $("documentList").innerHTML = project.documents.map((doc) => `
    <div class="record"><strong>${escapeHtml(doc.title)}</strong><div class="meta">${escapeHtml(doc.content.slice(0, 150))}${doc.content.length > 150 ? "…" : ""}</div></div>
  `).join("") || `<div class="meta">No reference documents.</div>`;

  $("caseList").innerHTML = project.cases.map((item) => `
    <div class="record">
      <div