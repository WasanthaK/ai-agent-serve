"""Minimal operator-facing Training / Skill Improvement console.

The HTML shell contains no business data and no credentials. Operators provide
an existing API key at runtime; the browser keeps it in page memory only and
uses the existing authenticated JSON APIs for every read or write.
"""

from fastapi.responses import HTMLResponse


TRAINING_UI_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Training &amp; Skill Improvement</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f6f7f9;
      color: #172033;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: #f6f7f9; }
    button, input, select, textarea { font: inherit; }
    button { cursor: pointer; }
    .shell { min-height: 100vh; }
    header {
      background: #101828;
      color: white;
      padding: 24px clamp(20px, 4vw, 48px);
    }
    header h1 { margin: 0 0 6px; font-size: clamp(24px, 3vw, 34px); }
    header p { margin: 0; max-width: 900px; color: #d0d5dd; }
    main { padding: 24px clamp(16px, 3vw, 40px) 48px; }
    .panel {
      background: white;
      border: 1px solid #e4e7ec;
      border-radius: 14px;
      box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
    }
    .connect {
      padding: 18px;
      display: grid;
      grid-template-columns: minmax(220px, 1fr) auto auto;
      gap: 10px;
      align-items: end;
      margin-bottom: 18px;
    }
    label { display: grid; gap: 6px; font-size: 13px; color: #475467; }
    input, select, textarea {
      width: 100%;
      border: 1px solid #d0d5dd;
      border-radius: 9px;
      padding: 9px 11px;
      background: white;
      color: #101828;
    }
    textarea { min-height: 92px; resize: vertical; }
    input:focus, select:focus, textarea:focus {
      outline: 2px solid #84adff;
      outline-offset: 1px;
      border-color: #528bff;
    }
    .button {
      border: 1px solid #344054;
      border-radius: 9px;
      padding: 9px 14px;
      background: #344054;
      color: white;
      font-weight: 600;
    }
    .button.secondary { background: white; color: #344054; border-color: #d0d5dd; }
    .button.danger { background: #b42318; border-color: #b42318; }
    .button:disabled { cursor: not-allowed; opacity: 0.5; }
    .note { font-size: 12px; color: #667085; margin-top: 6px; }
    .status-line { min-height: 20px; font-size: 13px; color: #475467; }
    .workspace {
      display: grid;
      grid-template-columns: minmax(300px, 0.9fr) minmax(420px, 1.6fr);
      gap: 18px;
      align-items: start;
    }
    .queue { overflow: hidden; }
    .toolbar {
      display: grid;
      grid-template-columns: 1fr 1fr auto;
      gap: 10px;
      padding: 14px;
      border-bottom: 1px solid #eaecf0;
    }
    .case-list { max-height: 70vh; overflow: auto; }
    .case-button {
      width: 100%;
      text-align: left;
      background: white;
      border: 0;
      border-bottom: 1px solid #f2f4f7;
      padding: 14px;
      color: #101828;
    }
    .case-button:hover, .case-button.active { background: #f9fafb; }
    .case-title { display: flex; justify-content: space-between; gap: 10px; align-items: start; }
    .case-title strong { font-size: 14px; }
    .case-summary { margin-top: 7px; color: #667085; font-size: 13px; line-height: 1.4; }
    .badge {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 11px;
      font-weight: 700;
      background: #eef2ff;
      color: #3538cd;
      white-space: nowrap;
    }
    .detail { min-height: 480px; }
    .detail-header { padding: 18px 20px; border-bottom: 1px solid #eaecf0; }
    .detail-header h2 { margin: 0 0 6px; font-size: 20px; }
    .detail-body { padding: 18px 20px; display: grid; gap: 18px; }
    .section { border-top: 1px solid #eaecf0; padding-top: 16px; }
    .section:first-child { border-top: 0; padding-top: 0; }
    .section h3 { margin: 0 0 10px; font-size: 15px; }
    .kv { display: grid; grid-template-columns: 160px 1fr; gap: 8px 12px; font-size: 13px; }
    .kv dt { color: #667085; }
    .kv dd { margin: 0; color: #101828; overflow-wrap: anywhere; }
    pre {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      background: #f9fafb;
      border: 1px solid #eaecf0;
      border-radius: 9px;
      padding: 12px;
      font-size: 12px;
      margin: 0;
      max-height: 300px;
      overflow: auto;
    }
    .action-box {
      border: 1px solid #d6e4ff;
      background: #f5f8ff;
      border-radius: 12px;
      padding: 16px;
    }
    .action-box h3 { margin: 0 0 6px; }
    .action-box p { margin: 0 0 12px; color: #475467; font-size: 13px; }
    .form-grid { display: grid; gap: 12px; }
    .row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .case-row {
      display: grid;
      grid-template-columns: 1.1fr 0.8fr 0.8fr 1.4fr auto;
      gap: 8px;
      align-items: end;
      padding: 10px 0;
      border-top: 1px solid #d6e4ff;
    }
    .case-row:first-child { border-top: 0; }
    .empty { padding: 28px 18px; color: #667085; text-align: center; }
    .error { color: #b42318; }
    .success { color: #027a48; }
    .muted { color: #667085; }
    @media (max-width: 950px) {
      .workspace { grid-template-columns: 1fr; }
      .case-list { max-height: 420px; }
    }
    @media (max-width: 720px) {
      .connect, .toolbar, .row-2 { grid-template-columns: 1fr; }
      .case-row { grid-template-columns: 1fr; }
      .kv { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
<div class="shell">
  <header>
    <h1>Training &amp; Skill Improvement</h1>
    <p>Review real cases, propose corrections, run regression evidence, and revise failed candidates. Promotion remains intentionally unavailable until the controlled promotion capability is implemented.</p>
  </header>
  <main>
    <section class="panel connect">
      <label>
        Operator API key
        <input id="api-key" type="password" autocomplete="off" spellcheck="false" placeholder="Enter an existing operator key">
        <span class="note">The key stays in this page's memory only and is cleared when the page is refreshed or disconnected.</span>
      </label>
      <button id="connect" class="button">Connect</button>
      <button id="disconnect" class="button secondary" disabled>Disconnect</button>
      <div id="connection-status" class="status-line" style="grid-column: 1 / -1"></div>
    </section>

    <div class="workspace">
      <section class="panel queue">
        <div class="toolbar">
          <label>
            Stage
            <select id="stage-filter">
              <option value="">All stages</option>
              <option value="accepted">Accepted</option>
              <option value="needs_improvement_proposal">Needs improvement proposal</option>
              <option value="needs_regression_test">Needs regression test</option>
              <option value="regression_failed">Regression failed</option>
              <option value="ready_for_promotion_review">Ready for promotion review</option>
            </select>
          </label>
          <label>
            Skill
            <input id="skill-filter" type="text" placeholder="e.g. request_clarification">
          </label>
          <button id="refresh" class="button secondary" disabled>Refresh</button>
        </div>
        <div id="case-list" class="case-list">
          <div class="empty">Connect with an operator API key to load training cases.</div>
        </div>
      </section>

      <section class="panel detail">
        <div id="detail">
          <div class="empty">Select a training case to review the evidence and available actions.</div>
        </div>
      </section>
    </div>
  </main>
</div>

<script>
(() => {
  "use strict";

  let apiKey = "";
  let cases = [];
  let selectedEvaluationId = null;

  const byId = (id) => document.getElementById(id);
  const status = byId("connection-status");
  const list = byId("case-list");
  const detail = byId("detail");
  const connectButton = byId("connect");
  const disconnectButton = byId("disconnect");
  const refreshButton = byId("refresh");

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
  }

  function setStatus(message, kind) {
    status.className = "status-line" + (kind ? " " + kind : "");
    status.textContent = message || "";
  }

  function valueOrDash(value) {
    return value === null || value === undefined || value === "" ? "—" : String(value);
  }

  async function requestJson(path, options = {}) {
    if (!apiKey) throw new Error("Connect with an operator API key first.");
    const headers = new Headers(options.headers || {});
    headers.set("X-API-Key", apiKey);
    if (options.body !== undefined) headers.set("Content-Type", "application/json");
    const response = await fetch(path, {
      ...options,
      headers,
      cache: "no-store",
      credentials: "same-origin"
    });
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : null;
    if (!response.ok) {
      const message = payload && payload.detail ? payload.detail : "Request failed with status " + response.status;
      throw new Error(message);
    }
    return payload;
  }

  function kvSection(title, entries) {
    const section = node("section", "section");
    section.append(node("h3", "", title));
    const dl = node("dl", "kv");
    for (const [label, value] of entries) {
      dl.append(node("dt", "", label), node("dd", "", valueOrDash(value)));
    }
    section.append(dl);
    return section;
  }

  function jsonSection(title, value) {
    const section = node("section", "section");
    section.append(node("h3", "", title));
    const pre = node("pre");
    pre.textContent = JSON.stringify(value || {}, null, 2);
    section.append(pre);
    return section;
  }

  function stageLabel(stage) {
    const labels = {
      accepted: "Accepted",
      needs_improvement_proposal: "Needs proposal",
      needs_regression_test: "Needs regression",
      regression_failed: "Regression failed",
      ready_for_promotion_review: "Promotion-ready"
    };
    return labels[stage] || stage;
  }

  function renderList() {
    list.replaceChildren();
    if (!cases.length) {
      list.append(node("div", "empty", "No training cases match the current filters."));
      return;
    }
    for (const item of cases) {
      const button = node("button", "case-button" + (item.evaluation_id === selectedEvaluationId ? " active" : ""));
      button.type = "button";
      const title = node("div", "case-title");
      title.append(
        node("strong", "", item.skill_name + " · " + item.skill_version),
        node("span", "badge", stageLabel(item.training_stage))
      );
      const summary = item.request && item.request.summary ? item.request.summary : "No request summary";
      button.append(title, node("div", "case-summary", summary));
      button.addEventListener("click", () => selectCase(item.evaluation_id));
      list.append(button);
    }
  }

  async function loadCases(preferredEvaluationId = null) {
    setStatus("Loading training cases…");
    const params = new URLSearchParams();
    const stage = byId("stage-filter").value;
    const skill = byId("skill-filter").value.trim();
    if (stage) params.set("stage", stage);
    if (skill) params.set("skill_name", skill);
    params.set("limit", "100");
    const payload = await requestJson("/training/cases?" + params.toString());
    cases = payload.cases || [];
    selectedEvaluationId = preferredEvaluationId && cases.some(c => c.evaluation_id === preferredEvaluationId)
      ? preferredEvaluationId
      : (cases[0] ? cases[0].evaluation_id : null);
    renderList();
    if (selectedEvaluationId) {
      await selectCase(selectedEvaluationId);
    } else {
      detail.replaceChildren(node("div", "empty", "No training case selected."));
    }
    setStatus("Loaded " + cases.length + " training case" + (cases.length === 1 ? "" : "s") + ".", "success");
  }

  async function selectCase(evaluationId) {
    selectedEvaluationId = evaluationId;
    renderList();
    detail.replaceChildren(node("div", "empty", "Loading case…"));
    try {
      const item = await requestJson("/training/cases/" + encodeURIComponent(evaluationId));
      renderDetail(item);
    } catch (error) {
      detail.replaceChildren(node("div", "empty error", error.message));
    }
  }

  function renderDetail(item) {
    detail.replaceChildren();
    const header = node("div", "detail-header");
    header.append(
      node("h2", "", item.skill_name + " · " + item.skill_version),
      node("span", "badge", stageLabel(item.training_stage))
    );
    const body = node("div", "detail-body");

    body.append(kvSection("Real case", [
      ["Request", item.request_id],
      ["Source", item.request && item.request.source],
      ["Status", item.request && item.request.status],
      ["Category", item.request && item.request.category],
      ["Summary", item.request && item.request.summary],
      ["Urgency", item.request && item.request.urgency]
    ]));

    body.append(kvSection("Human evaluation", [
      ["Verdict", item.evaluation_verdict],
      ["Notes", item.evaluation_notes],
      ["Evaluated by", item.evaluated_by],
      ["Evaluation ID", item.evaluation_id]
    ]));

    body.append(jsonSection("Outcome evidence", item.outcome_snapshot));

    if (item.proposal) {
      body.append(kvSection("Improvement proposal", [
        ["Proposal ID", item.proposal.proposal_id],
        ["Scope", item.proposal.change_scope],
        ["Proposed change", item.proposal.proposed_change],
        ["Rationale", item.proposal.rationale],
        ["Status", item.proposal.status]
      ]));
    }

    if (item.revision) {
      body.append(kvSection("Latest revision", [
        ["Revision", item.revision.revision_number],
        ["Revision ID", item.revision.revision_id],
        ["Revised change", item.revision.proposed_change],
        ["Rationale", item.revision.rationale]
      ]));
    }

    if (item.regression) {
      body.append(kvSection("Latest regression evidence", [
        ["Regression ID", item.regression.regression_test_id],
        ["Suite", item.regression.suite_name + " · " + item.regression.suite_version],
        ["Verdict", item.regression.verdict],
        ["Target cases fixed", item.regression.fixed_target_cases + " / " + item.regression.target_cases],
        ["Regression failures", item.regression.regression_failures],
        ["Candidate failures", item.regression.candidate_failures]
      ]));
    }

    body.append(buildActionBox(item));
    detail.append(header, body);
  }

  function actionIntro(title, description) {
    const box = node("section", "action-box");
    box.append(node("h3", "", title), node("p", "", description));
    return box;
  }

  function labeledField(labelText, control) {
    const label = node("label");
    label.append(node("span", "", labelText), control);
    return label;
  }

  function textInput(placeholder = "") {
    const input = node("input");
    input.type = "text";
    input.placeholder = placeholder;
    return input;
  }

  function textarea(placeholder = "") {
    const area = node("textarea");
    area.placeholder = placeholder;
    return area;
  }

  function selectControl(options) {
    const select = node("select");
    for (const [value, label] of options) {
      const option = node("option", "", label);
      option.value = value;
      select.append(option);
    }
    return select;
  }

  async function submitAction(button, task, item) {
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Saving…";
    try {
      await task();
      setStatus("Training case updated.", "success");
      await loadCases(item.evaluation_id);
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  function proposalForm(item) {
    const box = actionIntro(
      "Propose an improvement",
      "Describe what should change and why. The proposal remains evidence only until regression testing and future promotion."
    );
    const form = node("div", "form-grid");
    const scope = selectControl([["instructions", "Instructions"], ["policy", "Policy"]]);
    const change = textarea("What should the skill do differently?");
    const rationale = textarea("Why is this change needed for the reviewed case?");
    const submit = node("button", "button", "Create proposal");
    submit.type = "button";
    submit.addEventListener("click", () => submitAction(submit, async () => {
      await requestJson("/requests/" + item.request_id + "/skill-improvement-proposals", {
        method: "POST",
        body: JSON.stringify({
          evaluation_id: item.evaluation_id,
          change_scope: scope.value,
          proposed_change: change.value.trim(),
          rationale: rationale.value.trim()
        })
      });
    }, item));
    form.append(labeledField("Change scope", scope), labeledField("Proposed change", change), labeledField("Rationale", rationale), submit);
    box.append(form);
    return box;
  }

  function revisionForm(item) {
    const box = actionIntro(
      "Revise the failed candidate",
      "Create a new immutable revision. The failed proposal and regression evidence remain preserved in history."
    );
    const form = node("div", "form-grid");
    const change = textarea("Revised instruction or policy change");
    const rationale = textarea("Explain how this revision addresses the failed regression");
    const submit = node("button", "button", "Create revision");
    submit.type = "button";
    submit.addEventListener("click", () => submitAction(submit, async () => {
      await requestJson("/requests/" + item.request_id + "/skill-improvement-revisions", {
        method: "POST",
        body: JSON.stringify({
          proposal_id: item.proposal.proposal_id,
          proposed_change: change.value.trim(),
          rationale: rationale.value.trim()
        })
      });
    }, item));
    form.append(labeledField("Revised change", change), labeledField("Rationale", rationale), submit);
    box.append(form);
    return box;
  }

  function regressionForm(item) {
    const box = actionIntro(
      "Record regression evidence",
      "Include at least one known failing target case and one known-good regression case. A candidate passes only when every candidate result passes."
    );
    const form = node("div", "form-grid");
    const suiteRow = node("div", "row-2");
    const suiteName = textInput("e.g. request-clarification-core");
    const suiteVersion = textInput("e.g. 1.0.1");
    suiteRow.append(labeledField("Suite name", suiteName), labeledField("Suite version", suiteVersion));

    const casesContainer = node("div");
    const rows = [];

    function addCase(purpose) {
      const row = node("div", "case-row");
      const caseId = textInput(purpose + "-case-id");
      const purposeControl = selectControl([[purpose, purpose === "target" ? "Target" : "Regression"]]);
      purposeControl.disabled = true;
      const candidate = selectControl([["pass", "Candidate pass"], ["fail", "Candidate fail"]]);
      const notes = textInput("Review notes");
      const remove = node("button", "button secondary", "Remove");
      remove.type = "button";
      const model = {purpose, caseId, candidate, notes, row};
      remove.addEventListener("click", () => {
        const index = rows.indexOf(model);
        if (index >= 0) rows.splice(index, 1);
        row.remove();
      });
      row.append(
        labeledField("Case ID", caseId),
        labeledField("Purpose", purposeControl),
        labeledField("Candidate", candidate),
        labeledField("Notes", notes),
        remove
      );
      rows.push(model);
      casesContainer.append(row);
    }

    addCase("target");
    addCase("regression");

    const controls = node("div", "row-2");
    const addTarget = node("button", "button secondary", "Add target case");
    addTarget.type = "button";
    addTarget.addEventListener("click", () => addCase("target"));
    const addRegression = node("button", "button secondary", "Add regression case");
    addRegression.type = "button";
    addRegression.addEventListener("click", () => addCase("regression"));
    controls.append(addTarget, addRegression);

    const submit = node("button", "button", "Record regression evidence");
    submit.type = "button";
    submit.addEventListener("click", () => submitAction(submit, async () => {
      const payloadCases = rows.map(row => ({
        case_id: row.caseId.value.trim(),
        purpose: row.purpose,
        baseline_result: row.purpose === "target" ? "fail" : "pass",
        candidate_result: row.candidate.value,
        notes: row.notes.value.trim()
      }));
      await requestJson("/requests/" + item.request_id + "/skill-regression-tests", {
        method: "POST",
        body: JSON.stringify({
          proposal_id: item.proposal.proposal_id,
          revision_id: item.revision ? item.revision.revision_id : null,
          suite_name: suiteName.value.trim(),
          suite_version: suiteVersion.value.trim(),
          cases: payloadCases
        })
      });
    }, item));

    form.append(suiteRow, casesContainer, controls, submit);
    box.append(form);
    return box;
  }

  function buildActionBox(item) {
    const actions = item.supported_actions || [];
    if (actions.includes("create_improvement_proposal")) return proposalForm(item);
    if (actions.includes("record_regression_test")) return regressionForm(item);
    if (actions.includes("create_improvement_revision")) return revisionForm(item);

    if (item.training_stage === "ready_for_promotion_review") {
      return actionIntro(
        "Ready for promotion review",
        "Regression evidence passed. Promotion is deliberately unavailable until the controlled promotion capability is implemented."
      );
    }
    if (item.training_stage === "accepted") {
      return actionIntro(
        "No improvement required",
        "The human evaluation passed. No training change is required for this case."
      );
    }
    return actionIntro("No action available", item.blocked_reason || "This case has no available action.");
  }

  connectButton.addEventListener("click", async () => {
    const input = byId("api-key");
    const candidate = input.value.trim();
    if (!candidate) {
      setStatus("Enter an operator API key.", "error");
      return;
    }
    apiKey = candidate;
    input.value = "";
    connectButton.disabled = true;
    disconnectButton.disabled = false;
    refreshButton.disabled = false;
    try {
      await loadCases();
    } catch (error) {
      apiKey = "";
      connectButton.disabled = false;
      disconnectButton.disabled = true;
      refreshButton.disabled = true;
      cases = [];
      renderList();
      setStatus(error.message, "error");
    }
  });

  disconnectButton.addEventListener("click", () => {
    apiKey = "";
    cases = [];
    selectedEvaluationId = null;
    connectButton.disabled = false;
    disconnectButton.disabled = true;
    refreshButton.disabled = true;
    renderList();
    detail.replaceChildren(node("div", "empty", "Select a training case to review the evidence and available actions."));
    setStatus("Disconnected.");
  });

  refreshButton.addEventListener("click", () => {
    loadCases(selectedEvaluationId).catch(error => setStatus(error.message, "error"));
  });

  byId("stage-filter").addEventListener("change", () => {
    if (apiKey) loadCases().catch(error => setStatus(error.message, "error"));
  });

  byId("skill-filter").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && apiKey) {
      loadCases().catch(error => setStatus(error.message, "error"));
    }
  });
})();
</script>
</body>
</html>
"""


def training_ui_response():
    return HTMLResponse(
        content=TRAINING_UI_HTML,
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "Referrer-Policy": "no-referrer",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": (
                "default-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; "
                "connect-src 'self'; "
                "img-src 'self' data:; "
                "base-uri 'none'; "
                "frame-ancestors 'none'"
            ),
        },
    )
