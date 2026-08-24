const state = {
  projects: [],
  activeProject: null,
  latestRun: null,
  reviewItems: [],
  activeReview: null,
  view: "project",
};

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }
  const response = await fetch(path, { ...options, headers });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string"
      ? body.detail
      : JSON.stringify(body.detail || body);
    throw new Error(detail || `Request failed: ${response.status}`);
  }
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
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  }[char]));
}

function badge(value) {
  return `<span class="badge ${escapeHtml(value)}">${escapeHtml(String(value).replaceAll("_", " "))}</span>`;
}

function showView(view) {
  state.view = view;
  $("emptyState").classList.toggle("hidden", view !== "empty");
  $("projectView").classList.toggle("hidden", view !== "project");
  $("reviewView").classList.toggle("hidden", view !== "review");
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
  state.latestRun = state.activeProject.runs?.[0]
    ? await api(`/api/runs/${state.activeProject.runs[0].id}`)
    : null;
  showView("project");
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
    <div class="record">
      <strong>${escapeHtml(doc.title)}</strong>
      <div class="meta">${escapeHtml(doc.content.slice(0, 150))}${doc.content.length > 150 ? "…" : ""}</div>
    </div>
  `).join("") || `<div class="meta">No reference documents.</div>`;

  $("caseList").innerHTML = project.cases.map((item) => `
    <div class="record">
      <div class="result-header">
        <strong>${escapeHtml(item.name)}</strong>
        ${item.expected_label ? badge(item.expected_label) : ""}
      </div>
      <div class="meta">${escapeHtml(item.prompt.slice(0, 120))}${item.prompt.length > 120 ? "…" : ""}</div>
      ${item.external_case_id ? `<div class="meta">case_id: ${escapeHtml(item.external_case_id)}</div>` : ""}
    </div>
  `).join("") || `<div class="meta">No evaluation cases.</div>`;

  renderRun();
  renderApiTarget();
}

function renderApiTarget() {
  const target = state.activeProject?.api_target;
  const summary = $("apiTargetSummary");
  if (!target) {
    summary.textContent = "No API target configured.";
    $("apiTargetUrl").value = "";
    $("apiTargetBody").value = '{"input": "{{prompt}}"}';
    $("apiTargetPath").value = "data.answer";
    $("apiTargetTimeout").value = "30";
    $("apiTargetAuthHeader").value = "Authorization";
    $("apiTargetAuthEnv").value = "";
    return;
  }
  $("apiTargetUrl").value = target.url || "";
  $("apiTargetBody").value = target.body_template || '{"input": "{{prompt}}"}';
  $("apiTargetPath").value = target.response_field_path || "data.answer";
  $("apiTargetTimeout").value = String(target.timeout_seconds ?? 30);
  $("apiTargetAuthHeader").value = target.auth_header || "Authorization";
  $("apiTargetAuthEnv").value = target.auth_env_var || "";
  summary.textContent = `Configured: ${target.url} · path=${target.response_field_path} · timeout=${target.timeout_seconds}s${target.auth_env_var ? ` · auth env=${target.auth_env_var}` : ""}`;
}

function renderRun() {
  const run = state.latestRun;
  const metrics = $("runMetrics");
  const results = $("runResults");
  const config = $("runConfig");
  const exportLinks = $("exportLinks");

  if (!run) {
    metrics.innerHTML = "";
    results.innerHTML = `<div class="empty-inline">No runs yet.</div>`;
    config.textContent = "";
    exportLinks.innerHTML = "";
    return;
  }

  const m = run.metrics || {};
  metrics.innerHTML = [
    [m.accuracy ?? "—", "Accuracy"],
    [m.case_count ?? run.results?.length ?? 0, "Cases"],
    [m.human_review_count ?? 0, "Review queue"],
    [run.status, "Status"],
  ].map(([value, label]) => `<div class="metric"><strong>${escapeHtml(String(value))}</strong><span>${label}</span></div>`).join("");

  const cfg = run.config || {};
  config.innerHTML = cfg.provider
    ? `Config snapshot: ${escapeHtml(cfg.provider)} / ${escapeHtml(cfg.model)} · top_k=${escapeHtml(String(cfg.retrieval_top_k ?? ""))} · prompt_version=${escapeHtml(cfg.prompt_version || "")} · app=${escapeHtml(cfg.app_version || "")}${cfg.git_commit_sha ? ` · git=${escapeHtml(cfg.git_commit_sha.slice(0, 8))}` : ""}`
    : "";

  exportLinks.innerHTML = `
    <a class="meta" href="/api/runs/${run.id}/export?format=json">JSON</a> ·
    <a class="meta" href="/api/runs/${run.id}/export?format=jsonl">JSONL</a> ·
    <a class="meta" href="/api/runs/${run.id}/export?format=csv">CSV</a>
  `;

  results.innerHTML = (run.results || []).map((item) => `
    <div class="result-card">
      <div class="result-header">
        <strong>${escapeHtml(item.case_name || `Case ${item.case_id}`)}</strong>
        <div>${badge(item.severity)} ${item.needs_human_review ? badge("review") : ""}</div>
      </div>
      <p>${escapeHtml(item.reason || "")}</p>
      <div class="meta">confidence ${escapeHtml(String(item.confidence))} · expected ${escapeHtml(item.expected_label || "—")} · ${escapeHtml(item.review_status || "PENDING")}</div>
      ${item.raw?.api_call ? `<div class="meta">API: status ${escapeHtml(String(item.raw.api_call.http_status ?? "—"))} · ${escapeHtml(String(item.raw.api_call.latency_ms ?? "—"))} ms${item.raw.api_call.error ? ` · error: ${escapeHtml(item.raw.api_call.error)}` : ""}</div>` : ""}
      <details class="details">
        <summary>Evidence, rules, claims</summary>
        <div class="evidence">${escapeHtml(JSON.stringify(item.evidence || [], null, 2))}</div>
        <div class="evidence">${escapeHtml(JSON.stringify(item.rule_findings || [], null, 2))}</div>
        <div class="evidence">${escapeHtml(JSON.stringify(item.claims || [], null, 2))}</div>
      </details>
    </div>
  `).join("") || `<div class="empty-inline">No results.</div>`;
}

async function loadReviews() {
  const params = new URLSearchParams();
  if (state.activeProject) params.set("project_id", state.activeProject.id);
  const status = $("reviewStatusFilter").value;
  if (status) params.set("review_status", status);
  const [sortBy, sortDir] = ($("reviewSort").value || "confidence:asc").split(":");
  params.set("sort_by", sortBy);
  params.set("sort_dir", sortDir);
  params.set("needs_human_review", "true");
  state.reviewItems = await api(`/api/reviews?${params.toString()}`);
  $("reviewList").innerHTML = state.reviewItems.map((item) => `
    <div class="record" data-result="${item.id}" style="cursor:pointer">
      <div class="result-header">
        <strong>${escapeHtml(item.case_name || `Result ${item.id}`)}</strong>
        ${badge(item.severity)}
      </div>
      <div class="meta">confidence ${escapeHtml(String(item.confidence))} · ${escapeHtml(item.review_status)}</div>
    </div>
  `).join("") || `<div class="meta">No items in the review queue.</div>`;
  $("reviewList").querySelectorAll("[data-result]").forEach((node) => {
    node.addEventListener("click", () => openReview(Number(node.dataset.result)));
  });
}

async function openReview(resultId) {
  state.activeReview = await api(`/api/reviews/${resultId}`);
  renderReviewDetail();
}

function renderReviewDetail() {
  const item = state.activeReview;
  if (!item) {
    $("reviewDetail").innerHTML = `<div class="empty-inline">Select a result to review.</div>`;
    return;
  }
  const decisions = item.decisions || [];
  const showAdjudicate = item.review_status === "DISAGREEMENT";
  $("reviewDetail").innerHTML = `
    <div class="stack">
      <div class="result-header">
        <h3>${escapeHtml(item.case_name || `Result ${item.id}`)}</h3>
        ${badge(item.severity)}
      </div>
      <div class="meta">Expected: ${escapeHtml(item.expected_label || "—")} · Confidence: ${escapeHtml(String(item.confidence))} · Status: ${escapeHtml(item.review_status)}</div>
      <div><strong>Prompt</strong><div class="evidence">${escapeHtml(item.prompt || "")}</div></div>
      <div><strong>Candidate response</strong><div class="evidence">${escapeHtml(item.response || "")}</div></div>
      <div><strong>Retrieved evidence</strong><div class="evidence">${escapeHtml(JSON.stringify(item.evidence || [], null, 2))}</div></div>
      <div><strong>Rule findings</strong><div class="evidence">${escapeHtml(JSON.stringify(item.rule_findings || [], null, 2))}</div></div>
      <div><strong>Claim verdicts</strong><div class="evidence">${escapeHtml(JSON.stringify(item.claims || [], null, 2))}</div></div>
      <div><strong>Previous decisions</strong>
        ${decisions.map((d) => `<div class="record"><strong>${escapeHtml(d.reviewer)}</strong> → ${badge(d.final_label)} <span class="meta">${escapeHtml(d.status)}</span><div class="meta">${escapeHtml(d.comment || "")}</div></div>`).join("") || `<div class="meta">No decisions yet.</div>`}
      </div>
      <form id="decisionForm" class="stack">
        <input id="reviewerName" placeholder="Reviewer name" required />
        <select id="reviewerLabel" required>
          <option value="no_issue">no_issue</option>
          <option value="minor">minor</option>
          <option value="major">major</option>
        </select>
        <textarea id="reviewerComment" placeholder="Comment (optional)" rows="3"></textarea>
        <button type="submit">Save decision</button>
      </form>
      ${showAdjudicate ? `
        <form id="adjudicateForm" class="stack">
          <div class="notice"><strong>Disagreement</strong><p>Provide an adjudicated final label.</p></div>
          <input id="adjudicatorName" placeholder="Adjudicator name" required />
          <select id="adjudicatorLabel" required>
            <option value="no_issue">no_issue</option>
            <option value="minor">minor</option>
            <option value="major">major</option>
          </select>
          <textarea id="adjudicatorComment" placeholder="Adjudication comment" rows="2"></textarea>
          <button type="submit">Adjudicate</button>
        </form>
      ` : ""}
    </div>
  `;

  $("decisionForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      state.activeReview = await api(`/api/reviews/${item.id}/decisions`, {
        method: "POST",
        body: JSON.stringify({
          reviewer: $("reviewerName").value,
          final_label: $("reviewerLabel").value,
          comment: $("reviewerComment").value || null,
        }),
      });
      showToast("Review decision saved");
      renderReviewDetail();
      await loadReviews();
    } catch (error) {
      showToast(error.message);
    }
  });

  const adj = $("adjudicateForm");
  if (adj) {
    adj.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        state.activeReview = await api(`/api/reviews/${item.id}/adjudicate`, {
          method: "POST",
          body: JSON.stringify({
            adjudicator: $("adjudicatorName").value,
            final_label: $("adjudicatorLabel").value,
            comment: $("adjudicatorComment").value || null,
          }),
        });
        showToast("Adjudication saved");
        renderReviewDetail();
        await loadReviews();
      } catch (error) {
        showToast(error.message);
      }
    });
  }
}

function bindEvents() {
  $("refreshProjects").addEventListener("click", () => loadProjects().catch((e) => showToast(e.message)));
  $("createProjectForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const project = await api("/api/projects", {
        method: "POST",
        body: JSON.stringify({
          name: $("projectName").value,
          description: $("projectDescription").value,
        }),
      });
      $("createProjectForm").reset();
      await loadProjects();
      await openProject(project.id);
      showToast("Project created");
    } catch (error) {
      showToast(error.message);
    }
  });

  $("seedSample").addEventListener("click", async () => {
    if (!state.activeProject) return;
    try {
      await api(`/api/projects/${state.activeProject.id}/seed`, { method: "POST", body: "{}" });
      await openProject(state.activeProject.id);
      showToast("Sample accounting benchmark loaded");
    } catch (error) {
      showToast(error.message);
    }
  });

  $("documentForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api(`/api/projects/${state.activeProject.id}/documents`, {
        method: "POST",
        body: JSON.stringify({
          title: $("docTitle").value,
          content: $("docContent").value,
        }),
      });
      $("documentForm").reset();
      await openProject(state.activeProject.id);
      showToast("Document added");
    } catch (error) {
      showToast(error.message);
    }
  });

  $("caseForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api(`/api/projects/${state.activeProject.id}/cases`, {
        method: "POST",
        body: JSON.stringify({
          name: $("caseName").value,
          case_id: $("caseExternalId").value || null,
          prompt: $("casePrompt").value,
          response: $("caseResponse").value,
          expected_label: $("caseExpected").value || null,
        }),
      });
      $("caseForm").reset();
      await openProject(state.activeProject.id);
      showToast("Case added");
    } catch (error) {
      showToast(error.message);
    }
  });

  $("importForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const file = $("importFile").files[0];
      if (!file) throw new Error("Choose a file");
      const form = new FormData();
      form.append("file", file);
      form.append("dry_run", $("importDryRun").checked ? "true" : "false");
      form.append("atomic", $("importAtomic").checked ? "true" : "false");
      const result = await api(`/api/projects/${state.activeProject.id}/cases/import`, {
        method: "POST",
        body: form,
      });
      showToast(`Import: ${result.imported_rows} imported, ${result.rejected_rows} rejected`);
      if (!result.dry_run && result.imported_rows) {
        await openProject(state.activeProject.id);
      }
    } catch (error) {
      showToast(error.message);
    }
  });

  $("apiTargetForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const saved = await api(`/api/projects/${state.activeProject.id}/api-target`, {
        method: "PUT",
        body: JSON.stringify({
          url: $("apiTargetUrl").value,
          body_template: $("apiTargetBody").value,
          response_field_path: $("apiTargetPath").value,
          timeout_seconds: Number($("apiTargetTimeout").value),
          auth_header: $("apiTargetAuthHeader").value || "Authorization",
          auth_env_var: $("apiTargetAuthEnv").value || null,
        }),
      });
      state.activeProject.api_target = saved;
      renderApiTarget();
      showToast("API target saved (secret values are never stored)");
    } catch (error) {
      showToast(error.message);
    }
  });

  $("runForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.submitter;
    button.disabled = true;
    try {
      state.latestRun = await api(`/api/projects/${state.activeProject.id}/runs`, {
        method: "POST",
        body: JSON.stringify({
          provider: $("runProvider").value,
          model: $("runModel").value,
          top_k: Number($("runTopK").value),
        }),
      });
      await openProject(state.activeProject.id);
      showToast("Evaluation completed");
    } catch (error) {
      showToast(error.message);
    } finally {
      button.disabled = false;
    }
  });

  $("runProvider").addEventListener("change", () => {
    if ($("runProvider").value === "openai" && $("runModel").value === "offline") {
      $("runModel").value = "gpt-5.6";
    }
    if ($("runProvider").value === "heuristic") {
      $("runModel").value = "offline";
    }
    if ($("runProvider").value === "client_api" && $("runModel").value === "offline") {
      $("runModel").value = "client-api";
    }
  });

  const openReviews = async () => {
    showView("review");
    await loadReviews();
  };
  $("openReviewQueue").addEventListener("click", () => openReviews().catch((e) => showToast(e.message)));
  $("openReviewsForProject").addEventListener("click", () => openReviews().catch((e) => showToast(e.message)));
  $("backToProject").addEventListener("click", () => {
    if (state.activeProject) showView("project");
    else showView("empty");
  });
  $("refreshReviews").addEventListener("click", () => loadReviews().catch((e) => showToast(e.message)));
  $("reviewStatusFilter").addEventListener("change", () => loadReviews().catch((e) => showToast(e.message)));
  $("reviewSort").addEventListener("change", () => loadReviews().catch((e) => showToast(e.message)));
}

async function boot() {
  bindEvents();
  await checkHealth();
  await loadProjects();
  if (!state.projects.length) showView("empty");
}

boot().catch((error) => showToast(error.message));
