/* EvalForge operator console — vanilla JS, service-layer API access */
(function () {
  const NAV = [
    { id: "overview", label: "Overview" },
    { id: "runs", label: "Evaluation Runs" },
    { id: "baselines", label: "Baselines" },
    { id: "regressions", label: "Regressions" },
    { id: "policy", label: "Policy Gates" },
    { id: "evidence", label: "Evidence" },
    { id: "approvals", label: "Approvals", maturity: "prototype" },
    { id: "audit", label: "Audit Log" },
    { id: "research", label: "Research / Benchmarks" },
    { id: "settings", label: "Settings" },
  ];

  const state = {
    view: "overview",
    selectedRunId: null,
    selectedEvidenceId: null,
    cache: {},
    error: null,
    loading: false,
  };

  const $ = (id) => document.getElementById(id);

  async function api(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (options.body && !(options.body instanceof FormData)) {
      headers["Content-Type"] = headers["Content-Type"] || "application/json";
    }
    const response = await fetch(path, { ...options, headers });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail || body);
      throw new Error(detail || `Request failed (${response.status})`);
    }
    return body;
  }

  const OperatorAPI = {
    overview: () => api("/api/operator/overview"),
    runs: (q = "") => api(`/api/operator/runs${q}`),
    run: (id) => api(`/api/operator/runs/${encodeURIComponent(id)}`),
    baselines: () => api("/api/operator/baselines"),
    regressions: (runId) => api(`/api/operator/regressions${runId ? `?run_id=${encodeURIComponent(runId)}` : ""}`),
    policy: (runId) => api(`/api/operator/policy${runId ? `?run_id=${encodeURIComponent(runId)}` : ""}`),
    evidence: (runId) => api(`/api/operator/evidence${runId ? `?run_id=${encodeURIComponent(runId)}` : ""}`),
    approvals: () => api("/api/operator/approvals"),
    decideApproval: (id, payload) => api(`/api/operator/approvals/${encodeURIComponent(id)}/decision`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
    audit: () => api("/api/operator/audit"),
    research: () => api("/api/operator/research"),
    settings: () => api("/api/operator/settings"),
    resetDemo: () => api("/api/operator/demo/reset", { method: "POST", body: "{}" }),
    health: () => api("/api/health"),
  };

  function escapeHtml(value = "") {
    return String(value).replace(/[&<>'"]/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    }[ch]));
  }

  function pill(value) {
    const v = value == null ? "—" : String(value);
    return `<span class="pill ${escapeHtml(v)}">${escapeHtml(v)}</span>`;
  }

  function toast(message) {
    const el = $("toast");
    el.textContent = message;
    el.classList.remove("hidden");
    setTimeout(() => el.classList.add("hidden"), 3800);
  }

  function setBanner(text, kind = "") {
    const el = $("banner");
    if (!text) {
      el.classList.add("hidden");
      return;
    }
    el.className = `banner ${kind}`.trim();
    el.textContent = text;
    el.classList.remove("hidden");
  }

  function renderNav() {
    $("navList").innerHTML = NAV.map((item) => `
      <button type="button" data-nav="${item.id}" class="${state.view === item.id || (state.view === "runDetail" && item.id === "runs") ? "active" : ""}">
        ${escapeHtml(item.label)}
        ${item.maturity ? `<span class="pill muted">${escapeHtml(item.maturity)}</span>` : ""}
      </button>
    `).join("");
    $("navList").querySelectorAll("[data-nav]").forEach((btn) => {
      btn.addEventListener("click", () => navigate(btn.dataset.nav));
    });
  }

  function titles(view) {
    const map = {
      overview: ["Overview", "Release readiness and control-plane health"],
      runs: ["Evaluation Runs", "Search and open governed evaluation runs"],
      runDetail: ["Evaluation Run Detail", "Decision chain, metrics, policy, and evidence"],
      baselines: ["Baselines", "Immutable baseline registry (read-oriented)"],
      regressions: ["Regressions", "Degradation analysis vs baseline"],
      policy: ["Policy Gates", "Inspectable release policy decisions"],
      evidence: ["Evidence", "Artifacts linked to decisions"],
      approvals: ["Approvals", "Human review queue (prototype)"],
      audit: ["Audit Log", "Append-style event trail (demo fixture)"],
      research: ["Research / Benchmarks", "Connected research artifacts"],
      settings: ["Settings", "Maturity labels and persistence notes"],
    };
    return map[view] || ["EvalForge", ""];
  }

  async function navigate(view, opts = {}) {
    state.view = view;
    if (opts.runId) state.selectedRunId = opts.runId;
    if (opts.evidenceId) state.selectedEvidenceId = opts.evidenceId;
    state.error = null;
    renderNav();
    const [title, sub] = titles(view);
    $("pageTitle").textContent = title;
    $("pageSubtitle").textContent = sub;
    await render();
  }

  function loadingHtml() {
    return `<div class="empty">Loading…</div>`;
  }

  function errorHtml(err) {
    return `<div class="error-box">API error: ${escapeHtml(err.message || err)}</div>`;
  }

  function emptyHtml(msg) {
    return `<div class="empty">${escapeHtml(msg)}</div>`;
  }

  function releaseCard(rr) {
    if (!rr) return emptyHtml("No release readiness data.");
    return `
      <div class="card">
        <div class="section-title"><h2>Release readiness</h2>${pill(rr.final_release_state)}</div>
        <div class="kv">
          <div>Candidate</div><div class="mono">${escapeHtml(rr.candidate)}</div>
          <div>Baseline</div><div class="mono">${escapeHtml(rr.baseline)}</div>
          <div>Evaluation status</div><div>${pill(rr.evaluation_status)}</div>
          <div>Regression status</div><div>${pill(rr.regression_status)}</div>
          <div>Policy decision</div><div>${pill(rr.policy_decision)}</div>
          <div>Human approval</div><div>${pill(rr.human_approval)}</div>
          <div>Final release state</div><div>${pill(rr.final_release_state)}</div>
        </div>
      </div>`;
  }

  async function renderOverview() {
    const data = await OperatorAPI.overview();
    state.cache.overview = data;
    $("maturityPill").textContent = data.source || "demo_fixture";
    const c = data.counts || {};
    return `
      <div class="grid stats">
        ${[
          [c.runs, "Runs (window)"],
          [c.allow, "ALLOW"],
          [c.warn, "WARN"],
          [c.review, "REVIEW"],
          [c.deny, "DENY"],
          [Math.round((data.regression_rate || 0) * 100) + "%", "Regression rate"],
          [Math.round((data.policy_failure_rate || 0) * 100) + "%", "Policy fail rate"],
          [(data.avg_latency_seconds ?? "—") + "s", "Avg latency"],
          [data.avg_cost_usd == null ? "n/a" : data.avg_cost_usd, "Avg cost"],
          [data.pending_reviews, "Pending reviews"],
          [data.critical_regressions, "Critical regressions"],
        ].map(([v, l]) => `<div class="card"><div class="stat-value">${escapeHtml(String(v))}</div><div class="stat-label">${escapeHtml(l)}</div></div>`).join("")}
      </div>
      <div class="grid two" style="margin-top:0.85rem">
        ${releaseCard(data.release_readiness)}
        <div class="card">
          <h2>System health</h2>
          <div class="kv">
            <div>API</div><div>${pill(data.system_health?.api)}</div>
            <div>CI</div><div>${pill(data.system_health?.ci)}</div>
            <div>Control plane</div><div>${pill(data.system_health?.control_plane)}</div>
            <div>Active baseline</div><div class="mono">${escapeHtml(data.active_baseline || "—")}</div>
            <div>Latest candidate</div><div class="mono">${escapeHtml(data.latest_candidate || "—")}</div>
            <div>Live CP runs</div><div>${escapeHtml(String(data.live_run_count ?? 0))}</div>
          </div>
          <p class="meta" style="margin-top:0.7rem">${escapeHtml(data.cost_note || "")}</p>
        </div>
      </div>
      <div class="grid two" style="margin-top:0.85rem">
        <div class="card">
          <h2>Recent policy decisions</h2>
          ${(data.recent_policy_decisions || []).map((d) => `
            <div class="meta" style="margin:0.35rem 0">
              <button class="linkish" data-open-run="${escapeHtml(d.run_id)}">${escapeHtml(d.run_id)}</button>
              ${pill(d.decision)} <span class="mono">${escapeHtml(d.at || "")}</span>
            </div>`).join("") || emptyHtml("None")}
        </div>
        <div class="card">
          <h2>Recent failed evaluations</h2>
          ${(data.recent_failed_evaluations || []).map((d) => `
            <div class="meta" style="margin:0.35rem 0">
              <button class="linkish" data-open-run="${escapeHtml(d.run_id)}">${escapeHtml(d.run_id)}</button>
              ${pill(d.status)} <span class="mono">${escapeHtml(d.at || "")}</span>
            </div>`).join("") || emptyHtml("None")}
        </div>
      </div>`;
  }

  async function renderRuns() {
    const model = $("filterModel")?.value || "";
    const params = new URLSearchParams();
    if (model) params.set("model", model);
    const policy = $("filterPolicy")?.value || "";
    if (policy) params.set("policy_decision", policy);
    const q = params.toString() ? `?${params}` : "";
    const runs = await OperatorAPI.runs(q);
    return `
      <div class="filters">
        <input id="filterModel" placeholder="Filter model" value="${escapeHtml(model)}" />
        <select id="filterPolicy">
          <option value="">Any policy decision</option>
          ${["ALLOW", "WARN", "REVIEW", "DENY"].map((p) => `<option value="${p}" ${policy === p ? "selected" : ""}>${p}</option>`).join("")}
        </select>
        <button type="button" class="btn ghost" id="applyRunFilters">Apply</button>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Run ID</th><th>Candidate / Model</th><th>Dataset</th><th>Suite</th>
              <th>Baseline</th><th>Started</th><th>Duration</th><th>Status</th><th>Result</th><th>Policy</th>
            </tr>
          </thead>
          <tbody>
            ${runs.map((r) => `
              <tr>
                <td><button class="linkish mono" data-open-run="${escapeHtml(r.run_id)}">${escapeHtml(r.run_id)}</button></td>
                <td>${escapeHtml(r.candidate || "—")}</td>
                <td>${escapeHtml(r.dataset || "—")}</td>
                <td>${escapeHtml(r.evaluation_suite || "—")}</td>
                <td>${escapeHtml(r.baseline_version || "—")}</td>
                <td class="mono">${escapeHtml(r.started_at || "—")}</td>
                <td>${r.duration_seconds == null ? "—" : escapeHtml(String(r.duration_seconds)) + "s"}</td>
                <td>${pill(r.status)}</td>
                <td>${pill(r.overall_result)}</td>
                <td>${pill(r.policy_decision)}</td>
              </tr>`).join("") || `<tr><td colspan="10">${emptyHtml("No runs match filters.")}</td></tr>`}
          </tbody>
        </table>
      </div>`;
  }

  function metricRows(run) {
    const regs = (run.regressions && run.regressions.results) || [];
    if (!regs.length) return emptyHtml("No metric comparison available for this run.");
    return `
      <div class="table-wrap">
        <table>
          <thead><tr><th>Metric</th><th>Baseline</th><th>Candidate</th><th>Delta</th><th>Threshold</th><th>Status</th></tr></thead>
          <tbody>
            ${regs.map((m) => `
              <tr>
                <td>${escapeHtml(m.metric)}</td>
                <td class="mono">${escapeHtml(String(m.baseline))}</td>
                <td class="mono">${escapeHtml(String(m.candidate))}</td>
                <td class="mono">${escapeHtml(String(m.absolute_delta))}</td>
                <td class="mono">${escapeHtml(String(m.threshold ?? "—"))}</td>
                <td>${pill(m.regression ? m.severity : "none")}</td>
              </tr>`).join("")}
          </tbody>
        </table>
      </div>`;
  }

  function chainHtml(chain) {
    return `<div class="chain">${(chain || []).map((s) => `
      <div class="chain-step ${escapeHtml(s.status || "")}">
        <div class="dot" aria-hidden="true"></div>
        <div>
          <strong>${escapeHtml(s.step)}</strong>
          <div class="meta">${pill(s.status)} ${escapeHtml(s.detail || "")}</div>
        </div>
      </div>`).join("")}</div>`;
  }

  async function renderRunDetail() {
    const id = state.selectedRunId;
    if (!id) return emptyHtml("Select a run from Evaluation Runs.");
    const run = await OperatorAPI.run(id);
    state.cache.run = run;
    const policy = run.policy || {};
    return `
      <div class="grid two">
        <div class="card">
          <div class="section-title"><h2>Summary</h2>${pill(run.policy_decision || run.overall_result)}</div>
          <div class="kv">
            <div>Run ID</div><div class="mono">${escapeHtml(run.run_id)}</div>
            <div>Candidate</div><div class="mono">${escapeHtml(run.candidate || run.model || "—")}</div>
            <div>Baseline</div><div class="mono">${escapeHtml(run.baseline_version || run.baseline_ref || "—")}</div>
            <div>Dataset</div><div>${escapeHtml(run.dataset_id || "—")}</div>
            <div>Evaluators</div><div class="mono">${escapeHtml((run.evaluators || []).join(", ") || "—")}</div>
            <div>Environment</div><div>${escapeHtml(run.environment || "—")}</div>
            <div>Started</div><div class="mono">${escapeHtml(run.started_at || "—")}</div>
            <div>Status</div><div>${pill(run.status)}</div>
            <div>Source</div><div>${pill(run.source || "unknown")}</div>
          </div>
        </div>
        <div class="card">
          <h2>Final release gate</h2>
          ${chainHtml(run.release_chain)}
        </div>
      </div>
      <div class="card" style="margin-top:0.85rem">
        <div class="section-title"><h2>Metric comparison</h2><span class="meta">Baseline | Candidate | Delta | Threshold | Status</span></div>
        ${metricRows(run)}
      </div>
      <div class="grid two" style="margin-top:0.85rem">
        <div class="card">
          <h2>Regression analysis</h2>
          ${((run.regressions && run.regressions.results) || []).filter((r) => r.regression).map((r) => `
            <div style="margin:0.55rem 0;padding:0.5rem;border:1px solid var(--line);border-radius:6px">
              <strong>${escapeHtml(r.metric)}</strong> ${pill(r.severity)}
              <div class="meta mono">Δ ${escapeHtml(String(r.absolute_delta))} · rel ${escapeHtml(String(r.relative_delta))} · threshold ${escapeHtml(String(r.threshold ?? "—"))}</div>
              <div class="meta">${escapeHtml(r.rationale || "")}</div>
            </div>`).join("") || emptyHtml("No regressions.")}
          <p class="meta">Metric degradation is separate from policy failure — inspect Policy Gates for rule actions.</p>
        </div>
        <div class="card">
          <h2>Policy decision</h2>
          <div class="kv">
            <div>Decision</div><div>${pill(policy.decision)}</div>
            <div>Policy</div><div class="mono">${escapeHtml(policy.policy_name || "—")}@${escapeHtml(policy.policy_version || "—")}</div>
            <div>Timestamp</div><div class="mono">${escapeHtml(policy.timestamp || "—")}</div>
          </div>
          <h3 style="margin:0.8rem 0 0.4rem;font-size:0.9rem">Matched rules</h3>
          ${(policy.matches || []).map((m) => `
            <div class="meta" style="margin:0.4rem 0">
              <span class="mono">${escapeHtml(m.rule_id)}</span> → ${pill(m.action)}<br/>
              ${escapeHtml(m.reason || "")}<br/>
              <span class="mono">${escapeHtml(JSON.stringify(m.matched_evidence || {}))}</span>
            </div>`).join("") || emptyHtml("No matched rules.")}
          <details style="margin-top:0.7rem">
            <summary>Advanced: raw policy configuration</summary>
            <pre class="raw">${escapeHtml(JSON.stringify(policy.raw_config || policy, null, 2))}</pre>
          </details>
        </div>
      </div>
      <div class="card" style="margin-top:0.85rem">
        <div class="section-title">
          <h2>Evidence</h2>
          <button type="button" class="btn ghost" data-nav-evidence>Open Evidence explorer</button>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>ID</th><th>Type</th><th>Source</th><th>Timestamp</th><th>Checksum</th><th>Redaction</th></tr></thead>
            <tbody id="runEvidenceBody"><tr><td colspan="6">Loading…</td></tr></tbody>
          </table>
        </div>
        <h3 style="margin:0.9rem 0 0.4rem;font-size:0.9rem">Audit manifest</h3>
        <pre class="raw">${escapeHtml(JSON.stringify(run.manifest || {}, null, 2))}</pre>
      </div>`;
  }

  async function hydrateRunEvidence(runId) {
    const items = await OperatorAPI.evidence(runId);
    const body = $("runEvidenceBody");
    if (!body) return;
    body.innerHTML = items.map((e) => `
      <tr>
        <td class="mono"><button class="linkish" data-open-evidence="${escapeHtml(e.evidence_id)}">${escapeHtml(e.evidence_id)}</button></td>
        <td>${escapeHtml(e.type || e.kind)}</td>
        <td>${escapeHtml(e.source || "—")}</td>
        <td class="mono">${escapeHtml(e.timestamp || e.created_at || "—")}</td>
        <td class="mono">${escapeHtml(e.checksum || e.sha256 || "—")}</td>
        <td>${pill(e.redaction_status || (e.redacted ? "redacted" : "clean"))}</td>
      </tr>`).join("") || `<tr><td colspan="6">${emptyHtml("No evidence artifacts.")}</td></tr>`;
  }

  async function renderBaselines() {
    const items = await OperatorAPI.baselines();
    return `
      <div class="banner warn">Baseline promotion is a governed operation. This UI is read-oriented; silent overwrite is not supported.</div>
      <div class="table-wrap" style="margin-top:0.75rem">
        <table>
          <thead><tr><th>ID</th><th>Model/App</th><th>Version</th><th>Suite</th><th>Dataset</th><th>Created</th><th>State</th><th>Owner</th></tr></thead>
          <tbody>
            ${items.map((b) => `
              <tr>
                <td class="mono">${escapeHtml(b.baseline_id || b.name)}</td>
                <td>${escapeHtml(b.model || b.application || b.name)}</td>
                <td>${escapeHtml(String(b.version ?? "—"))}</td>
                <td>${escapeHtml(b.evaluation_suite || "—")}</td>
                <td>${escapeHtml(b.dataset_id || "—")}</td>
                <td class="mono">${escapeHtml(b.created_at || "—")}</td>
                <td>${pill(b.active ? "active" : (b.archived ? "archived" : "inactive"))}</td>
                <td>${escapeHtml(b.owner || "—")}</td>
              </tr>`).join("")}
          </tbody>
        </table>
      </div>
      <div class="card" style="margin-top:0.85rem">
        <h2>Compare active vs archived (fixture)</h2>
        <pre class="raw">${escapeHtml(JSON.stringify(items.slice(0, 2).map((b) => ({ id: b.baseline_id, metrics: b.metrics })), null, 2))}</pre>
      </div>`;
  }

  async function renderRegressions() {
    const runId = state.selectedRunId;
    const data = await OperatorAPI.regressions(runId);
    const results = data.results || [];
    return `
      <div class="card">
        <div class="section-title">
          <h2>Regression explorer</h2>
          <span class="meta">Run <span class="mono">${escapeHtml(data.run_id || "—")}</span></span>
        </div>
        <div class="filters">
          <select id="sevFilter">
            <option value="">All severities</option>
            ${["none", "low", "medium", "high", "critical"].map((s) => `<option value="${s}">${s}</option>`).join("")}
          </select>
        </div>
        <div id="regList">
          ${results.map((r) => {
            const pct = Math.min(100, Math.abs(Number(r.relative_delta || 0)) * 100);
            const bad = r.regression;
            return `
              <div class="card" data-sev="${escapeHtml(r.severity)}" style="margin:0.45rem 0">
                <div class="section-title"><strong>${escapeHtml(r.metric)}</strong>${pill(r.severity)}</div>
                <div class="meta mono">baseline ${escapeHtml(String(r.baseline))} → candidate ${escapeHtml(String(r.candidate))} · Δ ${escapeHtml(String(r.absolute_delta))}</div>
                <div class="bar ${bad ? "bad" : ""}"><span style="width:${pct}%"></span></div>
                <div class="meta">${escapeHtml(r.rationale || "")}</div>
              </div>`;
          }).join("") || emptyHtml("No regression rows.")}
        </div>
      </div>`;
  }

  async function renderPolicy() {
    const data = await OperatorAPI.policy(state.selectedRunId);
    const decision = data.decision || {};
    return `
      <div class="grid two">
        <div class="card">
          <h2>Decision</h2>
          <div class="kv">
            <div>Run</div><div class="mono">${escapeHtml(data.run_id || "—")}</div>
            <div>Decision</div><div>${pill(decision.decision)}</div>
            <div>Policy</div><div class="mono">${escapeHtml(decision.policy_name || "—")}@${escapeHtml(decision.policy_version || "—")}</div>
          </div>
          <h3 style="margin:0.8rem 0 0.4rem;font-size:0.9rem">Decision timeline</h3>
          ${(data.timeline || []).map((t) => `
            <div style="margin:0.45rem 0;padding:0.5rem;border-left:3px solid var(--accent)">
              <div class="mono">${escapeHtml(t.at || "")}</div>
              <div><span class="mono">${escapeHtml(t.rule_id)}</span> → ${pill(t.action)}</div>
              <div class="meta">${escapeHtml(t.reason || "")}</div>
              <div class="meta mono">${escapeHtml(JSON.stringify(t.evidence || {}))}</div>
            </div>`).join("") || emptyHtml("No timeline events.")}
        </div>
        <div class="card">
          <h2>Policy catalog</h2>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Rule</th><th>Metric/Condition</th><th>Threshold</th><th>Action</th></tr></thead>
              <tbody>
                ${((data.catalog && data.catalog.rules) || []).map((r) => `
                  <tr>
                    <td class="mono">${escapeHtml(r.rule_id)}</td>
                    <td>${escapeHtml(r.metric || r.category || "—")} / ${escapeHtml(r.condition || "—")}</td>
                    <td class="mono">${escapeHtml(String(r.threshold))}</td>
                    <td>${pill(r.action)}</td>
                  </tr>`).join("")}
              </tbody>
            </table>
          </div>
          <details style="margin-top:0.7rem"><summary>Advanced raw config</summary>
            <pre class="raw">${escapeHtml(JSON.stringify(data.catalog || {}, null, 2))}</pre>
          </details>
        </div>
      </div>`;
  }

  async function renderEvidence() {
    const items = await OperatorAPI.evidence(state.selectedRunId);
    const selected = items.find((e) => e.evidence_id === state.selectedEvidenceId) || items[0];
    return `
      <div class="grid two">
        <div class="table-wrap">
          <table>
            <thead><tr><th>Artifact</th><th>Type</th><th>Run</th><th>Redaction</th></tr></thead>
            <tbody>
              ${items.map((e) => `
                <tr>
                  <td><button class="linkish mono" data-open-evidence="${escapeHtml(e.evidence_id)}">${escapeHtml(e.evidence_id)}</button></td>
                  <td>${escapeHtml(e.type || e.kind)}</td>
                  <td><button class="linkish mono" data-open-run="${escapeHtml(e.run_id || "")}">${escapeHtml(e.run_id || "—")}</button></td>
                  <td>${pill(e.redaction_status || "clean")}</td>
                </tr>`).join("") || `<tr><td colspan="4">${emptyHtml("No evidence.")}</td></tr>`}
            </tbody>
          </table>
        </div>
        <div class="card">
          <h2>Artifact detail</h2>
          ${selected ? `
            <div class="kv">
              <div>ID</div><div class="mono">${escapeHtml(selected.evidence_id)}</div>
              <div>Type</div><div>${escapeHtml(selected.type || selected.kind)}</div>
              <div>Source</div><div>${escapeHtml(selected.source || "—")}</div>
              <div>Timestamp</div><div class="mono">${escapeHtml(selected.timestamp || selected.created_at || "—")}</div>
              <div>Checksum</div><div class="mono">${escapeHtml(selected.checksum || selected.sha256 || "—")}</div>
              <div>Redaction</div><div>${pill(selected.redaction_status || "clean")}</div>
              <div>Run</div><div><button class="linkish mono" data-open-run="${escapeHtml(selected.run_id || "")}">${escapeHtml(selected.run_id || "—")}</button></div>
            </div>
            <pre class="raw" style="margin-top:0.7rem">${escapeHtml(JSON.stringify(selected.payload || {}, null, 2))}</pre>
          ` : emptyHtml("Select an artifact.")}
        </div>
      </div>`;
  }

  async function renderApprovals() {
    const items = await OperatorAPI.approvals();
    return `
      <div class="banner warn">Approvals are a prototype control boundary. AI/CI actors cannot self-approve.</div>
      <div class="table-wrap" style="margin-top:0.75rem">
        <table>
          <thead><tr><th>Run</th><th>Risk</th><th>Policy reason</th><th>Regression</th><th>Requester</th><th>Reviewer</th><th>State</th><th>Action</th></tr></thead>
          <tbody>
            ${items.map((a) => `
              <tr>
                <td><button class="linkish mono" data-open-run="${escapeHtml(a.run_id)}">${escapeHtml(a.run_id)}</button></td>
                <td>${pill(a.risk_level)}</td>
                <td>${escapeHtml(a.policy_reason || "—")}</td>
                <td>${escapeHtml(a.regression_summary || "—")}</td>
                <td class="mono">${escapeHtml(a.requester || "—")}</td>
                <td class="mono">${escapeHtml(a.reviewer || "—")}</td>
                <td>${pill(a.decision_state)}</td>
                <td>
                  ${a.decision_state === "PENDING" ? `
                    <button class="btn" data-approve="${escapeHtml(a.approval_id)}">Approve</button>
                    <button class="btn ghost" data-reject="${escapeHtml(a.approval_id)}">Reject</button>
                  ` : "—"}
                </td>
              </tr>`).join("")}
          </tbody>
        </table>
      </div>`;
  }

  async function renderAudit() {
    const items = await OperatorAPI.audit();
    return `
      <div class="banner">Demo fixture audit trail — not claiming durable append-only storage guarantees.</div>
      <div class="table-wrap" style="margin-top:0.75rem">
        <table>
          <thead><tr><th>Timestamp</th><th>Actor</th><th>Action</th><th>Entity</th><th>Entity ID</th><th>Decision</th><th>Policy</th><th>Correlation</th></tr></thead>
          <tbody>
            ${items.map((e) => `
              <tr>
                <td class="mono">${escapeHtml(e.timestamp || "—")}</td>
                <td class="mono">${escapeHtml(e.actor || "—")}</td>
                <td>${escapeHtml(e.action || "—")}</td>
                <td>${escapeHtml(e.entity || "—")}</td>
                <td class="mono">${escapeHtml(e.entity_id || "—")}</td>
                <td>${e.decision ? pill(e.decision) : "—"}</td>
                <td class="mono">${escapeHtml(e.policy || "—")}</td>
                <td class="mono">${escapeHtml(e.correlation_id || "—")}</td>
              </tr>`).join("")}
          </tbody>
        </table>
      </div>`;
  }

  async function renderResearch() {
    const data = await OperatorAPI.research();
    return `
      <div class="grid two">
        <div class="card">
          <h2>Benchmark</h2>
          <div class="kv">
            <div>Version</div><div class="mono">${escapeHtml(data.benchmark_version)}</div>
            <div>Dataset size</div><div>${escapeHtml(String(data.dataset_size))}</div>
            <div>Categories</div><div>${escapeHtml((data.evaluation_categories || []).join(", "))}</div>
            <div>Model</div><div class="mono">${escapeHtml(data.model)}</div>
            <div>Maturity</div><div>${pill(data.maturity)}</div>
          </div>
          <h3 style="margin:0.8rem 0 0.4rem;font-size:0.9rem">Metrics</h3>
          <pre class="raw">${escapeHtml(JSON.stringify(data.metrics || {}, null, 2))}</pre>
        </div>
        <div class="card">
          <h2>Ablation / reproducibility</h2>
          <pre class="raw">${escapeHtml(JSON.stringify(data.ablation_results || [], null, 2))}</pre>
          <p class="meta">${escapeHtml(data.failure_analysis || "")}</p>
          <p class="mono meta">${escapeHtml((data.reproducibility && data.reproducibility.command) || "")}</p>
        </div>
      </div>`;
  }

  async function renderSettings() {
    const data = await OperatorAPI.settings();
    return `
      <div class="card">
        <h2>Maturity labels</h2>
        <div class="kv">
          ${Object.entries(data.maturity_labels || {}).map(([k, v]) => `
            <div>${escapeHtml(k)}</div><div>${pill(v)}</div>`).join("")}
        </div>
        <p class="meta" style="margin-top:0.8rem">${escapeHtml(data.persistence || "")}</p>
        <p><a href="${escapeHtml(data.workbench_url || "/workbench")}">Open legacy evaluation workbench</a></p>
      </div>`;
  }

  async function render() {
    const root = $("viewRoot");
    state.loading = true;
    root.innerHTML = loadingHtml();
    try {
      let html = "";
      if (state.view === "overview") html = await renderOverview();
      else if (state.view === "runs") html = await renderRuns();
      else if (state.view === "runDetail") html = await renderRunDetail();
      else if (state.view === "baselines") html = await renderBaselines();
      else if (state.view === "regressions") html = await renderRegressions();
      else if (state.view === "policy") html = await renderPolicy();
      else if (state.view === "evidence") html = await renderEvidence();
      else if (state.view === "approvals") html = await renderApprovals();
      else if (state.view === "audit") html = await renderAudit();
      else if (state.view === "research") html = await renderResearch();
      else if (state.view === "settings") html = await renderSettings();
      else html = emptyHtml("Unknown view");
      root.innerHTML = html;
      bindViewEvents();
      if (state.view === "runDetail" && state.selectedRunId) {
        await hydrateRunEvidence(state.selectedRunId);
        bindViewEvents();
      }
      setBanner(
        state.view === "overview"
          ? "Demo fixture loaded: customer-support-agent-v12 vs v11 → policy REVIEW → approval PENDING. Not production telemetry."
          : "",
        "warn"
      );
    } catch (err) {
      state.error = err;
      root.innerHTML = errorHtml(err);
      setBanner(err.message, "error");
    } finally {
      state.loading = false;
    }
  }

  function bindViewEvents() {
    document.querySelectorAll("[data-open-run]").forEach((el) => {
      el.addEventListener("click", () => {
        const id = el.getAttribute("data-open-run");
        if (id) navigate("runDetail", { runId: id });
      });
    });
    document.querySelectorAll("[data-open-evidence]").forEach((el) => {
      el.addEventListener("click", () => {
        const id = el.getAttribute("data-open-evidence");
        navigate("evidence", { evidenceId: id });
      });
    });
    const apply = $("applyRunFilters");
    if (apply) apply.addEventListener("click", () => render());
    const sev = $("sevFilter");
    if (sev) {
      sev.addEventListener("change", () => {
        const v = sev.value;
        document.querySelectorAll("#regList [data-sev]").forEach((card) => {
          card.style.display = !v || card.getAttribute("data-sev") === v ? "" : "none";
        });
      });
    }
    const evBtn = document.querySelector("[data-nav-evidence]");
    if (evBtn) evBtn.addEventListener("click", () => navigate("evidence"));
    document.querySelectorAll("[data-approve]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const reviewer = window.prompt("Reviewer identity (human)", "governance.reviewer@example.com");
        if (!reviewer) return;
        try {
          await OperatorAPI.decideApproval(btn.getAttribute("data-approve"), {
            outcome: "APPROVED",
            reviewer,
            comment: "Approved after inspecting evidence",
          });
          toast("Approval recorded (prototype)");
          await render();
        } catch (err) {
          toast(err.message);
        }
      });
    });
    document.querySelectorAll("[data-reject]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const reviewer = window.prompt("Reviewer identity (human)", "governance.reviewer@example.com");
        if (!reviewer) return;
        try {
          await OperatorAPI.decideApproval(btn.getAttribute("data-reject"), {
            outcome: "REJECTED",
            reviewer,
            comment: "Rejected due to critical hallucination regression",
          });
          toast("Rejection recorded (prototype)");
          await render();
        } catch (err) {
          toast(err.message);
        }
      });
    });
  }

  async function boot() {
    renderNav();
    try {
      await OperatorAPI.health();
      $("healthDot").classList.add("ok");
    } catch {
      $("healthDot").classList.add("bad");
    }
    $("resetDemoBtn").addEventListener("click", async () => {
      try {
        await OperatorAPI.resetDemo();
        toast("Demo fixture reset");
        state.selectedRunId = "run_cs_agent_v12_001";
        await navigate("overview");
      } catch (err) {
        toast(err.message);
      }
    });
    state.selectedRunId = "run_cs_agent_v12_001";
    await navigate("overview");
  }

  boot().catch((err) => {
    $("viewRoot").innerHTML = errorHtml(err);
  });
})();
