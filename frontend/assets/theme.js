Object.assign(window.state, {
  themeSources: [],
  themeSourceDetail: null,
  themeRuns: [],
  selectedThemeSourceId: null,
  selectedThemeTopicId: null,
  editingThemeSourceId: null,
  editingThemeTopicId: null,
  editingThemeReceiverRuleId: null,
});

window.bindThemeDom = function bindThemeDom() {
  const dom = window.dom;
  dom.statThemeSources = document.querySelector("#stat-theme-sources");
  dom.statThemeTopics = document.querySelector("#stat-theme-topics");
  dom.statThemeRuns = document.querySelector("#stat-theme-runs");
  dom.themeSourceForm = document.querySelector("#theme-source-form");
  dom.themeSourceList = document.querySelector("#theme-source-list");
  dom.themeSourceCurrent = document.querySelector("#theme-source-current");
  dom.themeTopicForm = document.querySelector("#theme-topic-form");
  dom.themeTopicList = document.querySelector("#theme-topic-list");
  dom.themeTopicCurrent = document.querySelector("#theme-topic-current");
  dom.themeTopicTemplateSelect = document.querySelector("#theme-topic-template-id");
  dom.themeReceiverRuleForm = document.querySelector("#theme-receiver-rule-form");
  dom.themeReceiverRuleList = document.querySelector("#theme-receiver-rule-list");
  dom.themeRunList = document.querySelector("#theme-run-list");
};

window.bindThemeEvents = function bindThemeEvents() {
  const dom = window.dom;
  dom.themeSourceForm.addEventListener("submit", submitThemeSource);
  dom.themeTopicForm.addEventListener("submit", submitThemeTopic);
  dom.themeReceiverRuleForm.addEventListener("submit", submitThemeReceiverRule);
  document.querySelector("#theme-source-reset").addEventListener("click", resetThemeSourceForm);
  document.querySelector("#theme-source-run-dry").addEventListener("click", () => runThemeSource(true));
  document.querySelector("#theme-source-run-live").addEventListener("click", () => runThemeSource(false));
  document.querySelector("#theme-topic-reset").addEventListener("click", resetThemeTopicForm);
  document.querySelector("#theme-receiver-rule-reset").addEventListener("click", resetThemeReceiverRuleForm);
  dom.themeSourceList.addEventListener("click", handleThemeSourceListClick);
  dom.themeTopicList.addEventListener("click", handleThemeTopicListClick);
  dom.themeReceiverRuleList.addEventListener("click", handleThemeReceiverRuleListClick);
  dom.themeRunList.addEventListener("click", handleThemeRunListClick);
};

window.updateThemeTemplateSelect = function updateThemeTemplateSelect() {
  const { dom, state, escapeHtml } = window;
  dom.themeTopicTemplateSelect.innerHTML = ['<option value="">不使用模板</option>']
    .concat(state.templates.map((template) => `<option value="${template.id}">${escapeHtml(template.template_name)}</option>`))
    .join("");
};

window.loadThemeSources = async function loadThemeSources() {
  const { state, api } = window;
  state.themeSources = await api("/api/theme-sources");
  if (!state.selectedThemeSourceId && state.themeSources.length) state.selectedThemeSourceId = state.themeSources[0].id;
  if (state.selectedThemeSourceId && !state.themeSources.some((item) => item.id === state.selectedThemeSourceId)) {
    state.selectedThemeSourceId = state.themeSources[0] ? state.themeSources[0].id : null;
  }
  if (!state.selectedThemeSourceId) {
    state.themeSourceDetail = null;
    state.selectedThemeTopicId = null;
    renderThemeSources();
    renderThemeTopics();
    renderThemeReceiverRules();
    return;
  }
  state.themeSourceDetail = await api(`/api/theme-sources/${state.selectedThemeSourceId}`);
  const topics = state.themeSourceDetail.topics || [];
  if (!state.selectedThemeTopicId && topics.length) state.selectedThemeTopicId = topics[0].id;
  if (state.selectedThemeTopicId && !topics.some((item) => item.id === state.selectedThemeTopicId)) {
    state.selectedThemeTopicId = topics[0] ? topics[0].id : null;
  }
  renderThemeSources();
  renderThemeTopics();
  renderThemeReceiverRules();
};

window.loadThemeRuns = async function loadThemeRuns() {
  const { state, api } = window;
  const query = state.selectedThemeSourceId ? `?source_id=${state.selectedThemeSourceId}` : "";
  state.themeRuns = await api(`/api/theme-runs${query}`);
  renderThemeRuns();
};

window.renderThemeSummary = function renderThemeSummary() {
  const { dom, state } = window;
  dom.statThemeSources.textContent = state.themeSources.length;
  dom.statThemeTopics.textContent = state.themeSources.reduce((count, item) => count + Number(item.topic_count || 0), 0);
  dom.statThemeRuns.textContent = state.themeRuns.length;
  const themeText = state.selectedThemeSourceId ? `；主题源 ${state.selectedThemeSourceId} 最近运行 ${state.themeRuns.length} 条` : "；未选中主题源";
  dom.summaryText.textContent += themeText;
};

function currentThemeTopic() {
  const { state } = window;
  const topics = state.themeSourceDetail ? state.themeSourceDetail.topics || [] : [];
  return topics.find((item) => item.id === state.selectedThemeTopicId) || null;
}

function renderThemeSources() {
  const { dom, state, emptyHtml, escapeHtml } = window;
  const source = state.themeSourceDetail;
  dom.themeSourceCurrent.textContent = source ? `当前主题源: ${source.source_name} / ${source.source_code}` : "当前未选中主题源";
  if (!state.themeSources.length) return dom.themeSourceList.innerHTML = emptyHtml("暂无主题源");
  dom.themeSourceList.innerHTML = state.themeSources.map((item) => `
    <article class="list-item ${item.id === state.selectedThemeSourceId ? "selected" : ""}">
      <div class="panel-head"><h3>${escapeHtml(item.source_name)}</h3><span class="status ${item.enabled ? "" : "failed"}">${item.enabled ? "启用" : "停用"}</span></div>
      <div class="item-meta">编码: ${escapeHtml(item.source_code)}<br>类型: ${escapeHtml(item.source_type)}<br>频率: ${item.schedule.interval_value} ${escapeHtml(item.schedule.interval_unit)}<br>主题数: ${item.topic_count}</div>
      <div class="item-actions"><button class="small-button" data-action="select-theme-source" data-id="${item.id}" type="button">选中</button><button class="small-button" data-action="edit-theme-source" data-id="${item.id}" type="button">编辑</button></div>
    </article>
  `).join("");
}

function renderThemeTopics() {
  const { dom, state, emptyHtml, escapeHtml } = window;
  const topic = currentThemeTopic();
  dom.themeTopicCurrent.textContent = topic ? `当前主题: ${topic.theme_name} / ${topic.theme_code}` : state.themeSourceDetail ? "当前主题源未选中主题" : "请先选中主题源";
  if (!state.themeSourceDetail) return dom.themeTopicList.innerHTML = emptyHtml("请先选中主题源");
  if (!(state.themeSourceDetail.topics || []).length) return dom.themeTopicList.innerHTML = emptyHtml("当前主题源暂无主题");
  dom.themeTopicList.innerHTML = state.themeSourceDetail.topics.map((item) => `
    <article class="list-item ${item.id === state.selectedThemeTopicId ? "selected" : ""}">
      <div class="panel-head"><h3>${escapeHtml(item.theme_name)}</h3><span class="status ${item.enabled ? "" : "failed"}">${item.enabled ? "启用" : "停用"}</span></div>
      <div class="item-meta">编码: ${escapeHtml(item.theme_code)}<br>模板: ${item.message_template_id || "未绑定"} / 优先级: ${item.priority}<br>去重: ${escapeHtml(item.dedup_mode)}${item.dedup_window_minutes ? ` (${item.dedup_window_minutes} 分钟)` : ""}<br>规则数: ${(item.receiver_rules || []).length}</div>
      <div class="item-actions"><button class="small-button" data-action="select-theme-topic" data-id="${item.id}" type="button">选中</button><button class="small-button" data-action="edit-theme-topic" data-id="${item.id}" type="button">编辑</button></div>
    </article>
  `).join("");
}

function renderThemeReceiverRules() {
  const { dom, emptyHtml, renderRuleCard, state } = window;
  const topic = currentThemeTopic();
  if (!topic) return dom.themeReceiverRuleList.innerHTML = emptyHtml("请先选中主题");
  if (!(topic.receiver_rules || []).length) return dom.themeReceiverRuleList.innerHTML = emptyHtml("当前主题暂无接收规则");
  dom.themeReceiverRuleList.innerHTML = topic.receiver_rules.map((rule) => renderRuleCard(rule, state.editingThemeReceiverRuleId)).join("");
}

function renderThemeRuns() {
  const { dom, state, emptyHtml, escapeHtml, formatTime } = window;
  if (!state.themeRuns.length) return dom.themeRunList.innerHTML = emptyHtml("暂无主题运行记录");
  dom.themeRunList.innerHTML = state.themeRuns.map((run) => `
    <article class="list-item">
      <div class="panel-head"><h4>${escapeHtml(run.run_no)}</h4><span class="status ${String(run.status).includes("fail") ? "failed" : ""}">${escapeHtml(run.status)}</span></div>
      <div class="item-meta">主题源: ${run.source_id} / 抓取: ${run.fetched_count} / 命中: ${run.matched_count} / 发送: ${run.send_count}<br>开始: ${escapeHtml(formatTime(run.started_at))}<br>结束: ${escapeHtml(formatTime(run.finished_at))}</div>
      <div class="item-actions"><button class="small-button" data-action="view-theme-run" data-id="${run.id}" type="button">查看详情</button></div>
    </article>
  `).join("");
}

async function submitThemeSource(event) {
  event.preventDefault();
  const { dom, state, api, jsonRequest, parseJson, flash, renderSummary } = window;
  try {
    const form = new FormData(dom.themeSourceForm);
    const payload = { source_name: form.get("source_name"), source_code: form.get("source_code"), source_type: form.get("source_type"), enabled: form.get("enabled") === "on", source_config: parseJson(form.get("source_config"), {}), schedule: { interval_value: Number(form.get("schedule_interval_value") || 0), interval_unit: form.get("schedule_interval_unit"), timezone: form.get("schedule_timezone") || "Asia/Shanghai", start_at: null, end_at: null } };
    let sourceId = state.editingThemeSourceId;
    if (sourceId) await api(`/api/theme-sources/${sourceId}`, jsonRequest("PUT", payload));
    else { const created = await api("/api/theme-sources", jsonRequest("POST", payload)); sourceId = created.id; state.selectedThemeSourceId = sourceId; }
    flash(`主题源 ${sourceId} 保存成功`);
    resetThemeSourceForm();
    await window.loadThemeSources();
    await window.loadThemeRuns();
    renderSummary();
  } catch (error) { flash(error.message, true); }
}

async function submitThemeTopic(event) {
  event.preventDefault();
  const { dom, state, api, jsonRequest, parseJson, flash, renderSummary } = window;
  if (!state.selectedThemeSourceId) return flash("请先选中主题源", true);
  try {
    const form = new FormData(dom.themeTopicForm);
    const dedupMode = form.get("dedup_mode");
    const windowMinutes = String(form.get("dedup_window_minutes") || "").trim();
    const payload = { theme_name: form.get("theme_name"), theme_code: form.get("theme_code"), message_template_id: form.get("message_template_id") ? Number(form.get("message_template_id")) : null, enabled: form.get("enabled") === "on", priority: Number(form.get("priority") || 100), filter_expr: parseJson(form.get("filter_expr"), {}), dedup_mode: dedupMode, dedup_window_minutes: dedupMode === "window" && windowMinutes ? Number(windowMinutes) : null, dedup_key_template: String(form.get("dedup_key_template") || "").trim() || "{event_key}" };
    let topicId = state.editingThemeTopicId;
    if (topicId) await api(`/api/theme-topics/${topicId}`, jsonRequest("PUT", payload));
    else { const created = await api(`/api/theme-sources/${state.selectedThemeSourceId}/topics`, jsonRequest("POST", payload)); topicId = created.id; state.selectedThemeTopicId = topicId; }
    flash(`主题 ${topicId} 保存成功`);
    resetThemeTopicForm();
    await window.loadThemeSources();
    renderSummary();
  } catch (error) { flash(error.message, true); }
}

async function submitThemeReceiverRule(event) {
  event.preventDefault();
  const { dom, state, api, jsonRequest, buildRulePayload, flash } = window;
  const topic = currentThemeTopic();
  if (!topic) return flash("请先选中主题", true);
  try {
    const payload = buildRulePayload(dom.themeReceiverRuleForm);
    if (state.editingThemeReceiverRuleId) await api(`/api/theme-receiver-rules/${state.editingThemeReceiverRuleId}`, jsonRequest("PUT", payload));
    else await api(`/api/theme-topics/${topic.id}/receiver-rules`, jsonRequest("POST", payload));
    flash("主题接收规则保存成功");
    resetThemeReceiverRuleForm();
    await window.loadThemeSources();
  } catch (error) { flash(error.message, true); }
}

async function runThemeSource(dryRun) {
  const { state, api, jsonRequest, flash, renderSummary } = window;
  if (!state.selectedThemeSourceId) return flash("请先选中主题源", true);
  try {
    const run = await api(`/api/theme-sources/${state.selectedThemeSourceId}/run`, jsonRequest("POST", { dry_run: dryRun, context_override: {} }));
    flash(`${dryRun ? "主题演练" : "主题执行"}已触发，run_id=${run.id}`);
    await window.loadThemeRuns();
    renderSummary();
  } catch (error) { flash(error.message, true); }
}

async function handleThemeSourceListClick(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const { state, api } = window;
  const sourceId = Number(button.dataset.id);
  if (button.dataset.action === "select-theme-source") {
    state.selectedThemeSourceId = sourceId;
    state.selectedThemeTopicId = null;
    await window.loadThemeSources();
    await window.loadThemeRuns();
    return window.renderSummary();
  }
  state.selectedThemeSourceId = sourceId;
  state.themeSourceDetail = await api(`/api/theme-sources/${sourceId}`);
  state.editingThemeSourceId = sourceId;
  fillThemeSourceForm(state.themeSourceDetail);
  renderThemeSources();
  renderThemeTopics();
  renderThemeReceiverRules();
}

async function handleThemeTopicListClick(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const { state } = window;
  const topicId = Number(button.dataset.id);
  const topic = (state.themeSourceDetail?.topics || []).find((item) => item.id === topicId);
  if (!topic) return;
  state.selectedThemeTopicId = topicId;
  if (button.dataset.action === "edit-theme-topic") {
    state.editingThemeTopicId = topicId;
    fillThemeTopicForm(topic);
  }
  renderThemeTopics();
  renderThemeReceiverRules();
}

async function handleThemeReceiverRuleListClick(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const { state, api, flash } = window;
  const topic = currentThemeTopic();
  if (!topic) return;
  const rule = (topic.receiver_rules || []).find((item) => item.id === Number(button.dataset.id));
  if (!rule) return;
  if (button.dataset.action === "edit-rule") {
    state.editingThemeReceiverRuleId = rule.id;
    window.fillRuleForm(window.dom.themeReceiverRuleForm, rule);
    return renderThemeReceiverRules();
  }
  await api(`/api/theme-receiver-rules/${rule.id}`, { method: "DELETE" });
  flash(`主题规则 ${rule.id} 已删除`);
  await window.loadThemeSources();
  resetThemeReceiverRuleForm();
}

async function handleThemeRunListClick(event) {
  const button = event.target.closest("button[data-action='view-theme-run']");
  if (!button) return;
  try { window.flash(JSON.stringify(await window.api(`/api/theme-runs/${button.dataset.id}`), null, 2)); }
  catch (error) { window.flash(error.message, true); }
}

function fillThemeSourceForm(source) {
  const { dom, fillForm } = window;
  fillForm(dom.themeSourceForm, { source_name: source.source_name, source_code: source.source_code, source_type: source.source_type, schedule_interval_value: source.schedule.interval_value, schedule_interval_unit: source.schedule.interval_unit, schedule_timezone: source.schedule.timezone, source_config: JSON.stringify(source.source_config || {}, null, 2) });
  dom.themeSourceForm.elements.enabled.checked = source.enabled;
}

function fillThemeTopicForm(topic) {
  const { dom, fillForm } = window;
  fillForm(dom.themeTopicForm, { theme_name: topic.theme_name, theme_code: topic.theme_code, priority: topic.priority, dedup_mode: topic.dedup_mode, dedup_window_minutes: topic.dedup_window_minutes || "", dedup_key_template: topic.dedup_key_template, filter_expr: JSON.stringify(topic.filter_expr || {}, null, 2) });
  dom.themeTopicForm.elements.message_template_id.value = topic.message_template_id ? String(topic.message_template_id) : "";
  dom.themeTopicForm.elements.enabled.checked = topic.enabled;
}

function resetThemeSourceForm() {
  const { dom, state } = window;
  state.editingThemeSourceId = null;
  dom.themeSourceForm.reset();
  window.fillForm(dom.themeSourceForm, { source_type: "dsjfx_case_list", schedule_interval_value: 20, schedule_interval_unit: "minute", schedule_timezone: "Asia/Shanghai", source_config: "{}" });
  dom.themeSourceForm.elements.enabled.checked = true;
  renderThemeSources();
}

function resetThemeTopicForm() {
  const { dom, state } = window;
  state.editingThemeTopicId = null;
  dom.themeTopicForm.reset();
  window.fillForm(dom.themeTopicForm, { priority: 100, dedup_mode: "permanent", dedup_key_template: "{event_key}", filter_expr: "{}" });
  dom.themeTopicForm.elements.enabled.checked = true;
  window.updateThemeTemplateSelect();
  renderThemeTopics();
}

function resetThemeReceiverRuleForm() {
  const { dom, state } = window;
  state.editingThemeReceiverRuleId = null;
  dom.themeReceiverRuleForm.reset();
  window.fillForm(dom.themeReceiverRuleForm, { priority: 100, target_mobile_field: "mobile", filter_json: "{}" });
  dom.themeReceiverRuleForm.elements.enabled.checked = true;
  dom.themeReceiverRuleForm.elements.include_self.checked = true;
  renderThemeReceiverRules();
}
