const state = {
  scripts: [],
  templates: [],
  tasks: [],
  runs: [],
  contacts: [],
  selectedTaskId: null,
  editingTemplateId: null,
  editingTaskId: null,
  editingRuleId: null,
};

const dom = {};
window.state = state;
window.dom = dom;

document.addEventListener("DOMContentLoaded", () => {
  bindDom();
  bindEvents();
  loadAll();
});

function bindDom() {
  dom.healthPill = document.querySelector("#health-pill");
  dom.flash = document.querySelector("#flash");
  dom.summaryText = document.querySelector("#summary-text");
  dom.statScripts = document.querySelector("#stat-scripts");
  dom.statTemplates = document.querySelector("#stat-templates");
  dom.statTasks = document.querySelector("#stat-tasks");
  dom.statRuns = document.querySelector("#stat-runs");
  dom.scriptForm = document.querySelector("#script-form");
  dom.scriptList = document.querySelector("#script-list");
  dom.templateForm = document.querySelector("#template-form");
  dom.templateList = document.querySelector("#template-list");
  dom.taskForm = document.querySelector("#task-form");
  dom.taskList = document.querySelector("#task-list");
  dom.taskCurrent = document.querySelector("#task-current");
  dom.ruleForm = document.querySelector("#rule-form");
  dom.ruleList = document.querySelector("#rule-list");
  dom.runList = document.querySelector("#run-list");
  dom.contactForm = document.querySelector("#contact-form");
  dom.contactList = document.querySelector("#contact-list");
  dom.scriptSelect = document.querySelector("#task-script-id");
  dom.scriptVersionSelect = document.querySelector("#task-script-version-id");
  dom.templateSelect = document.querySelector("#task-template-id");
  if (window.bindThemeDom) {
    window.bindThemeDom();
  }
}

function bindEvents() {
  document.querySelector("#refresh-all").addEventListener("click", loadAll);
  dom.scriptForm.addEventListener("submit", submitScript);
  dom.templateForm.addEventListener("submit", submitTemplate);
  dom.taskForm.addEventListener("submit", submitTask);
  dom.ruleForm.addEventListener("submit", submitRule);
  dom.contactForm.addEventListener("submit", submitContacts);
  dom.scriptSelect.addEventListener("change", updateVersionSelect);
  document.querySelector("#template-reset").addEventListener("click", resetTemplateForm);
  document.querySelector("#task-reset").addEventListener("click", resetTaskForm);
  document.querySelector("#rule-reset").addEventListener("click", resetRuleForm);
  document.querySelector("#task-run-dry").addEventListener("click", () => runTask(true));
  document.querySelector("#task-run-live").addEventListener("click", () => runTask(false));
  dom.templateList.addEventListener("click", handleTemplateListClick);
  dom.taskList.addEventListener("click", handleTaskListClick);
  dom.ruleList.addEventListener("click", handleRuleListClick);
  dom.runList.addEventListener("click", handleRunListClick);
  if (window.bindThemeEvents) {
    window.bindThemeEvents();
  }
}

async function loadAll() {
  await loadHealth();
  await Promise.all([loadScripts(), loadTemplates(), loadTasks()]);
  if (window.loadThemeSources) {
    await window.loadThemeSources();
  }
  await loadRuns();
  if (window.loadThemeRuns) {
    await window.loadThemeRuns();
  }
  renderSummary();
}

async function loadHealth() {
  try {
    await api("/health");
    dom.healthPill.textContent = "服务正常";
    dom.healthPill.className = "pill pill-ok";
  } catch (error) {
    dom.healthPill.textContent = "服务异常";
    dom.healthPill.className = "pill pill-bad";
    flash(error.message, true);
  }
}

async function loadScripts() {
  state.scripts = await api("/api/scripts");
  renderScripts();
  updateScriptSelects();
}

async function loadTemplates() {
  state.templates = await api("/api/message-templates");
  renderTemplates();
  updateTemplateSelect();
  if (window.updateThemeTemplateSelect) {
    window.updateThemeTemplateSelect();
  }
}

async function loadTasks() {
  state.tasks = await api("/api/tasks");
  if (!state.selectedTaskId && state.tasks.length) state.selectedTaskId = state.tasks[0].id;
  if (state.selectedTaskId && !state.tasks.some((item) => item.id === state.selectedTaskId)) {
    state.selectedTaskId = state.tasks[0] ? state.tasks[0].id : null;
  }
  renderTasks();
  renderRules();
}

async function loadRuns() {
  const query = state.selectedTaskId ? `?task_id=${state.selectedTaskId}` : "";
  state.runs = await api(`/api/task-runs${query}`);
  renderRuns();
}

function currentTask() {
  return state.tasks.find((item) => item.id === state.selectedTaskId) || null;
}

function renderSummary() {
  dom.statScripts.textContent = state.scripts.length;
  dom.statTemplates.textContent = state.templates.length;
  dom.statTasks.textContent = state.tasks.length;
  dom.statRuns.textContent = state.runs.length;
  dom.summaryText.textContent = state.selectedTaskId
    ? `当前选中任务 ${state.selectedTaskId}，最近任务运行 ${state.runs.length} 条`
    : "当前未选中自定义任务";
  if (window.renderThemeSummary) {
    window.renderThemeSummary();
  }
}

function renderScripts() {
  if (!state.scripts.length) return dom.scriptList.innerHTML = emptyHtml("暂无脚本");
  dom.scriptList.innerHTML = state.scripts.map((script) => `
    <article class="list-item">
      <h3>${escapeHtml(script.script_name)}</h3>
      <div class="item-meta">
        编码: ${escapeHtml(script.script_code)}<br>
        入口: ${escapeHtml(script.entry_file)}#${escapeHtml(script.entry_func || "run")}<br>
        版本: ${(script.versions || []).map((v) => escapeHtml(v.version_no)).join(", ") || "暂无"}
      </div>
    </article>
  `).join("");
}

function renderTemplates() {
  if (!state.templates.length) return dom.templateList.innerHTML = emptyHtml("暂无模板");
  dom.templateList.innerHTML = state.templates.map((template) => `
    <article class="list-item ${state.editingTemplateId === template.id ? "selected" : ""}">
      <h3>${escapeHtml(template.template_name)}</h3>
      <div class="item-meta">编码: ${escapeHtml(template.template_code)}<br>状态: ${template.enabled ? "启用" : "停用"}<br>内容: ${escapeHtml(template.template_content)}</div>
      <div class="item-actions"><button class="small-button" data-action="edit-template" data-id="${template.id}" type="button">编辑</button></div>
    </article>
  `).join("");
}

function renderTasks() {
  const task = currentTask();
  dom.taskCurrent.textContent = task ? `当前任务: ${task.task_name}` : "当前未选中自定义任务";
  if (!state.tasks.length) return dom.taskList.innerHTML = emptyHtml("暂无自定义任务");
  dom.taskList.innerHTML = state.tasks.map((taskItem) => {
    const schedule = (taskItem.schedules || [])[0];
    return `
      <article class="list-item ${taskItem.id === state.selectedTaskId ? "selected" : ""}">
        <div class="panel-head"><h3>${escapeHtml(taskItem.task_name)}</h3><span class="status ${taskItem.enabled ? "" : "failed"}">${taskItem.enabled ? "启用" : "停用"}</span></div>
        <div class="item-meta">script_id=${taskItem.script_id} / version_id=${taskItem.script_version_id}<br>模板: ${taskItem.message_template_id || "未绑定"}<br>频率: ${schedule ? `${schedule.interval_value} ${schedule.interval_unit}` : "未配置"}<br>规则数: ${(taskItem.rules || []).length}</div>
        <div class="item-actions">
          <button class="small-button" data-action="select-task" data-id="${taskItem.id}" type="button">选中</button>
          <button class="small-button" data-action="edit-task" data-id="${taskItem.id}" type="button">编辑</button>
          <button class="small-button" data-action="${taskItem.enabled ? "disable-task" : "enable-task"}" data-id="${taskItem.id}" type="button">${taskItem.enabled ? "停用" : "启用"}</button>
        </div>
      </article>
    `;
  }).join("");
}

function renderRules() {
  const task = currentTask();
  if (!task) return dom.ruleList.innerHTML = emptyHtml("请先选中自定义任务");
  if (!(task.rules || []).length) return dom.ruleList.innerHTML = emptyHtml("当前任务暂无接收规则");
  dom.ruleList.innerHTML = (task.rules || []).map((rule) => renderRuleCard(rule, state.editingRuleId)).join("");
}

function renderRuns() {
  if (!state.runs.length) return dom.runList.innerHTML = emptyHtml("暂无任务运行记录");
  dom.runList.innerHTML = state.runs.map((run) => `
    <article class="list-item">
      <div class="panel-head"><h4>${escapeHtml(run.run_no)}</h4><span class="status ${String(run.status).includes("fail") ? "failed" : ""}">${escapeHtml(run.status)}</span></div>
      <div class="item-meta">任务: ${run.task_id} / 结果: ${run.result_count} / 命中: ${run.hit_count} / 发送: ${run.send_count}<br>开始: ${escapeHtml(formatTime(run.started_at))}<br>结束: ${escapeHtml(formatTime(run.finished_at))}</div>
      <div class="item-actions"><button class="small-button" data-action="view-run" data-id="${run.id}" type="button">查看详情</button></div>
    </article>
  `).join("");
}

function renderContacts(items = state.contacts) {
  if (!items.length) return dom.contactList.innerHTML = emptyHtml("暂无联系人结果");
  dom.contactList.innerHTML = items.map((contact) => `
    <article class="list-item">
      <h4>${escapeHtml(contact.xm || contact.sspcs || contact.xq || "未命名联系人")}</h4>
      <div class="item-meta">sspcsdm: ${escapeHtml(contact.sspcsdm || "-")} / xqdm: ${escapeHtml(contact.xqdm || "-")}<br>单位级别: ${escapeHtml(contact.unit_level || "-")} / 手机: ${escapeHtml((contact.phones || []).map((item) => item.mobile).join(","))}</div>
    </article>
  `).join("");
}

function renderRuleCard(rule, editingId) {
  return `<article class="list-item ${editingId === rule.id ? "selected" : ""}"><h4>${escapeHtml(rule.rule_name)}</h4><div class="item-meta">类型: ${escapeHtml(rule.rule_type)} / 优先级: ${rule.priority}<br>源字段: ${escapeHtml(rule.source_field || "-")} / 目标字段: ${escapeHtml(rule.target_match_field)}<br>上级匹配: self=${rule.include_self} county=${rule.include_county} city=${rule.include_city}<br>固定接收人: ${escapeHtml((rule.fixed_receivers || []).join(","))}</div><div class="item-actions"><button class="small-button" data-action="edit-rule" data-id="${rule.id}" type="button">编辑</button><button class="small-button" data-action="delete-rule" data-id="${rule.id}" type="button">删除</button></div></article>`;
}

function updateScriptSelects() {
  dom.scriptSelect.innerHTML = ['<option value="">请选择脚本</option>'].concat(state.scripts.map((script) => `<option value="${script.id}">${escapeHtml(script.script_name)} (${escapeHtml(script.script_code)})</option>`)).join("");
  if (!dom.scriptSelect.value && state.scripts.length) dom.scriptSelect.value = String(state.scripts[0].id);
  updateVersionSelect();
}

function updateVersionSelect() {
  const scriptId = Number(dom.scriptSelect.value || 0);
  const script = state.scripts.find((item) => item.id === scriptId);
  const versions = script ? script.versions || [] : [];
  dom.scriptVersionSelect.innerHTML = ['<option value="">请选择版本</option>'].concat(versions.map((version) => `<option value="${version.id}">${escapeHtml(version.version_no)}</option>`)).join("");
  if (versions.length) dom.scriptVersionSelect.value = String(versions[0].id);
}

function updateTemplateSelect() {
  dom.templateSelect.innerHTML = ['<option value="">不使用模板</option>'].concat(state.templates.map((template) => `<option value="${template.id}">${escapeHtml(template.template_name)}</option>`)).join("");
}

async function submitScript(event) {
  event.preventDefault();
  try {
    const result = await api("/api/scripts/upload", { method: "POST", body: new FormData(dom.scriptForm) });
    dom.scriptForm.reset();
    flash(`脚本上传成功: script_id=${result.script_id}, version_id=${result.script_version_id}`);
    await loadScripts();
  } catch (error) { flash(error.message, true); }
}

async function submitTemplate(event) {
  event.preventDefault();
  try {
    const form = new FormData(dom.templateForm);
    const payload = { template_name: form.get("template_name"), template_code: form.get("template_code"), template_content: form.get("template_content"), render_example: form.get("render_example") || "", enabled: form.get("enabled") === "on" };
    if (state.editingTemplateId) await api(`/api/message-templates/${state.editingTemplateId}`, jsonRequest("PUT", payload));
    else await api("/api/message-templates", jsonRequest("POST", payload));
    flash(state.editingTemplateId ? "模板更新成功" : "模板创建成功");
    resetTemplateForm();
    await loadTemplates();
  } catch (error) { flash(error.message, true); }
}

async function submitTask(event) {
  event.preventDefault();
  try {
    const form = new FormData(dom.taskForm);
    const payload = { task_name: form.get("task_name"), script_id: Number(form.get("script_id")), script_version_id: Number(form.get("script_version_id")), message_template_id: form.get("message_template_id") ? Number(form.get("message_template_id")) : null, enabled: form.get("enabled") === "on", dedup_key_expr: String(form.get("dedup_key_expr") || "").trim(), dedup_window_minutes: Number(form.get("dedup_window_minutes") || 0), runtime_config: parseJson(form.get("runtime_config"), {}) };
    const schedule = { interval_value: Number(form.get("schedule_interval_value") || 0), interval_unit: form.get("schedule_interval_unit"), enabled: true };
    let taskId = state.editingTaskId;
    if (taskId) {
      await api(`/api/tasks/${taskId}`, jsonRequest("PUT", payload));
      await api(`/api/tasks/${taskId}/schedule`, jsonRequest("PUT", schedule));
    } else {
      const created = await api("/api/tasks", jsonRequest("POST", { ...payload, schedule }));
      taskId = created.id;
      state.selectedTaskId = taskId;
    }
    flash(`任务 ${taskId} 保存成功`);
    resetTaskForm();
    await loadTasks();
    await loadRuns();
    renderSummary();
  } catch (error) { flash(error.message, true); }
}

async function submitRule(event) {
  event.preventDefault();
  if (!state.selectedTaskId) return flash("请先选中自定义任务", true);
  try {
    const payload = buildRulePayload(dom.ruleForm);
    if (state.editingRuleId) await api(`/api/rules/${state.editingRuleId}`, jsonRequest("PUT", payload));
    else await api(`/api/tasks/${state.selectedTaskId}/rules`, jsonRequest("POST", payload));
    flash("任务接收规则保存成功");
    resetRuleForm();
    await loadTasks();
  } catch (error) { flash(error.message, true); }
}

async function submitContacts(event) {
  event.preventDefault();
  try {
    const form = new FormData(dom.contactForm);
    const params = new URLSearchParams();
    ["keyword", "sspcsdm", "xqdm"].forEach((key) => { const value = String(form.get(key) || "").trim(); if (value) params.set(key, value); });
    const result = await api(params.toString() ? `/api/contacts?${params.toString()}` : "/api/contacts");
    state.contacts = result.items || [];
    renderContacts();
    flash(`联系人查询完成，共 ${result.total} 条`);
  } catch (error) { flash(error.message, true); }
}

async function runTask(dryRun) {
  if (!state.selectedTaskId) return flash("请先选中自定义任务", true);
  try {
    const run = await api(`/api/tasks/${state.selectedTaskId}/run`, jsonRequest("POST", { dry_run: dryRun, context_override: {} }));
    flash(`${dryRun ? "任务演练" : "任务执行"}已触发，run_id=${run.id}`);
    await loadRuns();
    renderSummary();
  } catch (error) { flash(error.message, true); }
}

async function handleTemplateListClick(event) {
  const button = event.target.closest("button[data-action='edit-template']");
  if (!button) return;
  const template = state.templates.find((item) => item.id === Number(button.dataset.id));
  if (!template) return;
  state.editingTemplateId = template.id;
  fillForm(dom.templateForm, { template_name: template.template_name, template_code: template.template_code, template_content: template.template_content, render_example: template.render_example });
  dom.templateForm.elements.enabled.checked = template.enabled;
  renderTemplates();
}

async function handleTaskListClick(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const taskId = Number(button.dataset.id);
  if (button.dataset.action === "select-task") {
    state.selectedTaskId = taskId;
    await loadTasks();
    await loadRuns();
    return renderSummary();
  }
  if (button.dataset.action === "edit-task") {
    const task = state.tasks.find((item) => item.id === taskId);
    if (!task) return;
    state.selectedTaskId = task.id;
    state.editingTaskId = task.id;
    fillTaskForm(task);
    return;
  }
  const action = button.dataset.action === "enable-task" ? "enable" : "disable";
  await api(`/api/tasks/${taskId}/${action}`, jsonRequest("POST", {}));
  flash(`任务 ${taskId} 已${action === "enable" ? "启用" : "停用"}`);
  await loadTasks();
  await loadRuns();
  renderSummary();
}

async function handleRuleListClick(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const task = currentTask();
  if (!task) return;
  const rule = (task.rules || []).find((item) => item.id === Number(button.dataset.id));
  if (!rule) return;
  if (button.dataset.action === "edit-rule") {
    state.editingRuleId = rule.id;
    fillRuleForm(dom.ruleForm, rule);
    return renderRules();
  }
  await api(`/api/rules/${rule.id}`, { method: "DELETE" });
  flash(`任务规则 ${rule.id} 已删除`);
  await loadTasks();
  resetRuleForm();
}

async function handleRunListClick(event) {
  const button = event.target.closest("button[data-action='view-run']");
  if (!button) return;
  try { flash(JSON.stringify(await api(`/api/task-runs/${button.dataset.id}`), null, 2)); }
  catch (error) { flash(error.message, true); }
}

function fillTaskForm(task) {
  fillForm(dom.taskForm, { task_name: task.task_name, dedup_key_expr: task.dedup_key_expr, dedup_window_minutes: task.dedup_window_minutes, runtime_config: JSON.stringify(task.runtime_config || {}, null, 2) });
  dom.taskForm.elements.enabled.checked = task.enabled;
  dom.scriptSelect.value = String(task.script_id);
  updateVersionSelect();
  dom.scriptVersionSelect.value = String(task.script_version_id);
  dom.templateSelect.value = task.message_template_id ? String(task.message_template_id) : "";
  const schedule = (task.schedules || [])[0];
  if (schedule) fillForm(dom.taskForm, { schedule_interval_value: schedule.interval_value, schedule_interval_unit: schedule.interval_unit });
}

function fillRuleForm(form, rule) {
  fillForm(form, { rule_name: rule.rule_name, rule_type: rule.rule_type, source_field: rule.source_field, priority: rule.priority, target_mobile_field: rule.target_mobile_field, fixed_receivers: (rule.fixed_receivers || []).join("\n"), filter_json: JSON.stringify(rule.filter_json || {}, null, 2) });
  form.elements.target_match_field.value = rule.target_match_field;
  form.elements.enabled.checked = rule.enabled;
  form.elements.include_self.checked = rule.include_self;
  form.elements.include_county.checked = rule.include_county;
  form.elements.include_city.checked = rule.include_city;
}

function buildRulePayload(form) {
  const data = new FormData(form);
  return { rule_name: data.get("rule_name"), rule_type: data.get("rule_type"), priority: Number(data.get("priority") || 100), enabled: data.get("enabled") === "on", source_field: data.get("source_field") || "", target_table: "jcgkzx_autotask.org_contact", target_match_field: data.get("target_match_field"), target_mobile_field: data.get("target_mobile_field") || "mobile", include_self: data.get("include_self") === "on", include_county: data.get("include_county") === "on", include_city: data.get("include_city") === "on", filter_json: parseJson(data.get("filter_json"), {}), fixed_receivers: splitLines(data.get("fixed_receivers")) };
}

function fillForm(form, values) { Object.entries(values).forEach(([key, value]) => { if (form.elements[key]) form.elements[key].value = value ?? ""; }); }
function resetTemplateForm() { state.editingTemplateId = null; dom.templateForm.reset(); dom.templateForm.elements.enabled.checked = true; renderTemplates(); }
function resetTaskForm() { state.editingTaskId = null; dom.taskForm.reset(); fillForm(dom.taskForm, { dedup_window_minutes: 720, schedule_interval_value: 20, schedule_interval_unit: "minute", runtime_config: "{}" }); dom.taskForm.elements.enabled.checked = true; updateScriptSelects(); updateTemplateSelect(); renderTasks(); }
function resetRuleForm() { state.editingRuleId = null; dom.ruleForm.reset(); fillForm(dom.ruleForm, { priority: 100, target_mobile_field: "mobile", filter_json: "{}" }); dom.ruleForm.elements.enabled.checked = true; dom.ruleForm.elements.include_self.checked = true; renderRules(); }
function flash(message, isError = false) { dom.flash.textContent = message; dom.flash.style.borderColor = isError ? "rgba(167, 60, 44, 0.32)" : "rgba(13, 107, 87, 0.12)"; dom.flash.style.background = isError ? "#f7ebe8" : "#ecf4f1"; }
function emptyHtml(text) { return `<article class="list-item"><div class="item-meta">${escapeHtml(text)}</div></article>`; }
function escapeHtml(value) { return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;"); }
function parseJson(value, fallback) { try { const text = String(value || "").trim(); return JSON.parse(text || JSON.stringify(fallback)); } catch (error) { throw new Error(`JSON 解析失败: ${error.message}`); } }
function splitLines(value) { return String(value || "").split(/[\n,]/).map((item) => item.trim()).filter(Boolean); }
function formatTime(value) { return value ? String(value).replace("T", " ").slice(0, 19) : "-"; }
function jsonRequest(method, payload) { return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }; }
async function api(path, options = {}) { const response = await fetch(path, options); if (response.status === 204) return null; const text = await response.text(); let data = null; if (text) { try { data = JSON.parse(text); } catch (error) { if (!response.ok) throw new Error(text); data = text; } } if (!response.ok) throw new Error(data && data.detail ? data.detail : `请求失败: ${response.status}`); return data; }

window.api = api;
window.escapeHtml = escapeHtml;
window.emptyHtml = emptyHtml;
window.flash = flash;
window.formatTime = formatTime;
window.jsonRequest = jsonRequest;
window.parseJson = parseJson;
window.splitLines = splitLines;
window.fillForm = fillForm;
window.renderRuleCard = renderRuleCard;
window.buildRulePayload = buildRulePayload;
window.fillRuleForm = fillRuleForm;
window.renderSummary = renderSummary;
