import { api, jsonRequest, parseJson, splitLines } from "../core/api.js";
import { emptyState, escapeHtml, jsonBlock, optionList, panel, statusBadge } from "../core/ui.js";

function sourceFilter(app) {
  return `
    <div class="field-block">
      <label for="topic-source-filter">数据源</label>
      <select id="topic-source-filter" data-action="topic-source-filter">
        ${optionList(app.state.themeSources, (item) => `${item.source_name} (${item.source_code})`, app.state.selectedSourceId, "请选择数据源")}
      </select>
    </div>
  `;
}

function topicSelector(app, id = "topic-select", current = app.state.selectedTopicId) {
  const topics = app.getAvailableTopics();
  return `
    <div class="field-block">
      <label for="${id}">主题</label>
      <select id="${id}" data-action="topic-select">
        ${optionList(topics, (item) => `${item.theme_name} (${item.theme_code})`, current, "请选择主题")}
      </select>
    </div>
  `;
}

function renderTopicCards(app) {
  const topics = app.getAvailableTopics();
  if (!topics.length) {
    return emptyState("当前数据源下还没有主题。");
  }
  return `
    <div class="card-list">
      ${topics.map((topic) => `
        <article class="card-item ${app.state.selectedTopicId === topic.id ? "active" : ""}">
          <div class="card-head">
            <div>
              <h4>${escapeHtml(topic.theme_name)}</h4>
              <div class="card-meta">编码: <span class="mono">${escapeHtml(topic.theme_code)}</span></div>
            </div>
            ${statusBadge(topic.enabled ? "启用" : "停用")}
          </div>
          <div class="card-meta">
            模板: ${topic.message_template_id || "未绑定"}<br>
            去重: ${escapeHtml(topic.dedup_mode)}${topic.dedup_window_minutes ? ` / ${topic.dedup_window_minutes} 分钟` : ""}<br>
            接收规则: ${(topic.receiver_rules || []).length}
          </div>
          <div class="card-actions">
            <button class="small-button" type="button" data-action="topic-select-card" data-id="${topic.id}">选中</button>
            <button class="small-button" type="button" data-action="topic-edit" data-id="${topic.id}">编辑</button>
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

function renderTopicForm(app) {
  const topic = app.state.topicEditorCreating ? null : app.getCurrentTopic();
  const templates = app.state.templates;
  return `
    <div class="banner">${app.state.topicEditorCreating ? "当前正在新建主题，请先选择数据源，再填写主题表单。" : topic ? `当前主题: ${escapeHtml(topic.theme_name)} / ${escapeHtml(topic.theme_code)}` : "当前未选中主题"}</div>
    <form id="topic-form" class="form-stack">
      <div class="form-grid two">
        ${sourceFilter(app)}
        <div class="field-block">
          <label for="message_template_id">短信模板</label>
          <select id="message_template_id" name="message_template_id">
            <option value="">不使用模板</option>
            ${templates.map((item) => `<option value="${item.id}" ${topic?.message_template_id === item.id ? "selected" : ""}>${escapeHtml(item.template_name)}</option>`).join("")}
          </select>
        </div>
      </div>
      <div class="form-grid two">
        <div class="field-block">
          <label for="theme_name">主题名称</label>
          <input id="theme_name" name="theme_name" type="text" value="${escapeHtml(topic?.theme_name || "")}" required>
        </div>
        <div class="field-block">
          <label for="theme_code">主题编码</label>
          <input id="theme_code" name="theme_code" type="text" value="${escapeHtml(topic?.theme_code || "")}" required>
        </div>
      </div>
      <div class="form-grid three">
        <div class="field-block">
          <label for="priority">优先级</label>
          <input id="priority" name="priority" type="number" value="${topic?.priority || 100}">
        </div>
        <div class="field-block">
          <label for="dedup_mode">去重模式</label>
          <select id="dedup_mode" name="dedup_mode">
            <option value="permanent" ${(topic?.dedup_mode || "permanent") === "permanent" ? "selected" : ""}>永久不重发</option>
            <option value="window" ${topic?.dedup_mode === "window" ? "selected" : ""}>时间窗口去重</option>
          </select>
        </div>
        <div class="field-block">
          <label for="dedup_window_minutes">时间窗口(分钟)</label>
          <input id="dedup_window_minutes" name="dedup_window_minutes" type="number" min="1" value="${topic?.dedup_window_minutes || ""}">
        </div>
      </div>
      <div class="field-block">
        <label for="dedup_key_template">去重键模板</label>
        <input id="dedup_key_template" name="dedup_key_template" type="text" value="${escapeHtml(topic?.dedup_key_template || "{event_key}")}">
      </div>
      <div class="field-block">
        <label for="filter_expr">命中过滤 JSON</label>
        <textarea id="filter_expr" name="filter_expr" rows="12">${escapeHtml(JSON.stringify(topic?.filter_expr || {}, null, 2))}</textarea>
      </div>
      <div class="checkbox-row">
        <label class="checkbox"><input name="enabled" type="checkbox" ${topic?.enabled ?? true ? "checked" : ""}><span>启用主题</span></label>
      </div>
      <div class="inline-actions">
        <button class="button" type="submit">${topic ? "更新主题" : "创建主题"}</button>
        <button class="button button-secondary" type="button" data-action="topic-reset">新建主题</button>
      </div>
    </form>
  `;
}

function renderRuleCards(app) {
  const topic = app.getCurrentTopic();
  if (!topic || !(topic.receiver_rules || []).length) {
    return emptyState("当前主题暂无接收规则。");
  }
  return `
    <div class="card-list">
      ${topic.receiver_rules.map((rule) => `
        <article class="card-item ${app.state.editingTopicRuleId === rule.id ? "active" : ""}">
          <div class="card-head">
            <div>
              <h4>${escapeHtml(rule.rule_name)}</h4>
              <div class="card-meta">类型: ${escapeHtml(rule.rule_type)}</div>
            </div>
            ${statusBadge(rule.enabled ? "启用" : "停用")}
          </div>
          <div class="card-meta">
            匹配字段: ${escapeHtml(rule.source_field || "-")} → ${escapeHtml(rule.target_match_field)}<br>
            固定接收人: ${escapeHtml((rule.fixed_receivers || []).join(", ") || "-")}
          </div>
          <div class="card-actions">
            <button class="small-button" type="button" data-action="topic-rule-edit" data-id="${rule.id}">编辑规则</button>
            <button class="small-button danger" type="button" data-action="topic-rule-delete" data-id="${rule.id}">删除规则</button>
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

function renderRuleForm(app) {
  const topic = app.getCurrentTopic();
  const rule = topic?.receiver_rules?.find((item) => item.id === app.state.editingTopicRuleId) || null;
  return `
    <div class="banner">${topic ? `当前主题: ${escapeHtml(topic.theme_name)}` : "请先选中主题，再配置接收规则。"}</div>
    <form id="topic-rule-form" class="form-stack">
      <div class="form-grid two">
        ${sourceFilter(app)}
        ${topicSelector(app)}
      </div>
      <div class="form-grid two">
        <div class="field-block">
          <label for="rule_name">规则名称</label>
          <input id="rule_name" name="rule_name" type="text" value="${escapeHtml(rule?.rule_name || "")}" required>
        </div>
        <div class="field-block">
          <label for="rule_type">规则类型</label>
          <select id="rule_type" name="rule_type">
            <option value="fixed_receivers" ${(rule?.rule_type || "fixed_receivers") === "fixed_receivers" ? "selected" : ""}>固定接收人</option>
            <option value="field_match" ${rule?.rule_type === "field_match" ? "selected" : ""}>字段直接匹配</option>
            <option value="field_match_with_ancestors" ${rule?.rule_type === "field_match_with_ancestors" ? "selected" : ""}>字段匹配并带上级单位</option>
          </select>
        </div>
      </div>
      <div class="form-grid three">
        <div class="field-block">
          <label for="source_field">源字段</label>
          <input id="source_field" name="source_field" type="text" value="${escapeHtml(rule?.source_field || "")}">
        </div>
        <div class="field-block">
          <label for="target_match_field">目标字段</label>
          <select id="target_match_field" name="target_match_field">
            ${["sspcsdm", "xqdm", "county_code", "city_code"].map((item) => `<option value="${item}" ${(rule?.target_match_field || "sspcsdm") === item ? "selected" : ""}>${escapeHtml(item)}</option>`).join("")}
          </select>
        </div>
        <div class="field-block">
          <label for="priority">优先级</label>
          <input id="priority" name="priority" type="number" value="${rule?.priority || 100}">
        </div>
      </div>
      <div class="field-block">
        <label for="target_mobile_field">手机号字段</label>
        <input id="target_mobile_field" name="target_mobile_field" type="text" value="${escapeHtml(rule?.target_mobile_field || "mobile")}">
      </div>
      <div class="field-block">
        <label for="fixed_receivers">固定手机号</label>
        <textarea id="fixed_receivers" name="fixed_receivers" rows="4">${escapeHtml((rule?.fixed_receivers || []).join("\n"))}</textarea>
      </div>
      <div class="field-block">
        <label for="filter_json">联系人过滤 JSON</label>
        <textarea id="filter_json" name="filter_json" rows="4">${escapeHtml(JSON.stringify(rule?.filter_json || {}, null, 2))}</textarea>
      </div>
      <div class="checkbox-row">
        <label class="checkbox"><input name="enabled" type="checkbox" ${rule?.enabled ?? true ? "checked" : ""}><span>启用规则</span></label>
        <label class="checkbox"><input name="include_self" type="checkbox" ${rule?.include_self ?? true ? "checked" : ""}><span>包含本级</span></label>
        <label class="checkbox"><input name="include_county" type="checkbox" ${rule?.include_county ? "checked" : ""}><span>包含县级</span></label>
        <label class="checkbox"><input name="include_city" type="checkbox" ${rule?.include_city ? "checked" : ""}><span>包含市级</span></label>
      </div>
      <div class="inline-actions">
        <button class="button" type="submit">${rule ? "更新规则" : "创建规则"}</button>
        <button class="button button-secondary" type="button" data-action="topic-rule-reset">新建规则</button>
      </div>
    </form>
  `;
}

export const topicsSection = {
  key: "topics",
  label: "主题管理",
  description: "把主题、过滤条件和接收规则拆开维护，避免和数据源配置混排。",
  tabs: [
    { key: "list", label: "主题列表", hint: "按数据源查看主题" },
    { key: "editor", label: "主题编辑", hint: "编辑过滤与去重" },
    { key: "rules", label: "接收规则", hint: "维护固定接收人与字段匹配规则" },
  ],
  async load(app) {
    if (app.state.route.secondary !== "editor") {
      app.state.topicEditorCreating = false;
    }
    await app.reloadThemeSources();
    await app.reloadTemplates();
  },
  render(app) {
    const tab = app.state.route.secondary;
    if (tab === "editor") {
      return `<div class="content-grid">
        ${panel("主题表单", "主题与数据源解耦，通过当前选中的数据源进行归属。", renderTopicForm(app), { span: 8 })}
        ${panel("当前主题列表", "编辑前先确认当前数据源下有哪些主题。", renderTopicCards(app), { span: 4 })}
      </div>`;
    }
    if (tab === "rules") {
      return `<div class="content-grid">
        ${panel("接收规则表单", "这里专门管理当前主题的短信接收策略。", renderRuleForm(app), { span: 7 })}
        ${panel("接收规则列表", "规则只属于当前主题，不再和任务规则混在一起。", renderRuleCards(app), { span: 5 })}
      </div>`;
    }
    return `<div class="content-grid">
      ${panel("主题筛选", "先选数据源，再看对应主题。", sourceFilter(app), { span: 4 })}
      ${panel("主题列表", "默认展示当前数据源下的全部主题。", renderTopicCards(app), { span: 8 })}
    </div>`;
  },
  bind(app) {
    document.querySelectorAll("[data-action='topic-source-filter']").forEach((select) => {
      select.addEventListener("change", async () => {
        await app.setSelectedSource(Number(select.value || 0) || null);
        app.render();
      });
    });

    document.querySelectorAll("[data-action='topic-select']").forEach((select) => {
      select.addEventListener("change", async () => {
        app.state.topicEditorCreating = false;
        await app.setSelectedTopic(Number(select.value || 0) || null);
        app.render();
      });
    });

    document.querySelectorAll("[data-action='topic-select-card']").forEach((button) => {
      button.addEventListener("click", async () => {
        app.state.topicEditorCreating = false;
        await app.setSelectedTopic(Number(button.dataset.id));
        app.render();
      });
    });

    document.querySelectorAll("[data-action='topic-edit']").forEach((button) => {
      button.addEventListener("click", async () => {
        app.state.topicEditorCreating = false;
        await app.setSelectedTopic(Number(button.dataset.id));
        app.navigate("topics", "editor");
      });
    });

    document.querySelectorAll("[data-action='topic-reset']").forEach((button) => {
      button.addEventListener("click", () => {
        app.state.topicEditorCreating = true;
        app.state.selectedTopicId = null;
        app.render();
      });
    });

    const topicForm = document.querySelector("#topic-form");
    if (topicForm) {
      topicForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
          const payload = new FormData(topicForm);
          const sourceId = Number(document.querySelector("#topic-source-filter").value || app.state.selectedSourceId || 0);
          if (!sourceId) {
            throw new Error("请先选择数据源。");
          }
          const dedupMode = String(payload.get("dedup_mode") || "permanent");
          const windowMinutes = String(payload.get("dedup_window_minutes") || "").trim();
          const body = {
            theme_name: payload.get("theme_name"),
            theme_code: payload.get("theme_code"),
            message_template_id: payload.get("message_template_id") ? Number(payload.get("message_template_id")) : null,
            enabled: payload.get("enabled") === "on",
            priority: Number(payload.get("priority") || 100),
            filter_expr: parseJson(payload.get("filter_expr"), {}),
            dedup_mode: dedupMode,
            dedup_window_minutes: dedupMode === "window" && windowMinutes ? Number(windowMinutes) : null,
            dedup_key_template: payload.get("dedup_key_template") || "{event_key}",
          };

          const currentTopic = app.state.topicEditorCreating ? null : app.getCurrentTopic();
          if (currentTopic) {
            await api(`/api/theme-topics/${currentTopic.id}`, jsonRequest("PUT", body));
            app.flash("主题已更新。");
          } else {
            const created = await api(`/api/theme-sources/${sourceId}/topics`, jsonRequest("POST", body));
            app.state.selectedTopicId = created.id;
            app.state.topicEditorCreating = false;
            app.flash("主题已创建。");
          }
          app.state.selectedSourceId = sourceId;
          await app.reloadThemeSources();
          app.render();
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    }

    const ruleForm = document.querySelector("#topic-rule-form");
    if (ruleForm) {
      ruleForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
          const topicId = Number(document.querySelector("#topic-select").value || app.state.selectedTopicId || 0);
          if (!topicId) {
            throw new Error("请先选择主题。");
          }
          const payload = new FormData(ruleForm);
          const body = {
            rule_name: payload.get("rule_name"),
            rule_type: payload.get("rule_type"),
            priority: Number(payload.get("priority") || 100),
            enabled: payload.get("enabled") === "on",
            source_field: payload.get("source_field") || "",
            target_table: "jcgkzx_autotask.org_contact",
            target_match_field: payload.get("target_match_field"),
            target_mobile_field: payload.get("target_mobile_field") || "mobile",
            include_self: payload.get("include_self") === "on",
            include_county: payload.get("include_county") === "on",
            include_city: payload.get("include_city") === "on",
            filter_json: parseJson(payload.get("filter_json"), {}),
            fixed_receivers: splitLines(payload.get("fixed_receivers")),
          };
          if (app.state.editingTopicRuleId) {
            await api(`/api/theme-receiver-rules/${app.state.editingTopicRuleId}`, jsonRequest("PUT", body));
            app.flash("接收规则已更新。");
          } else {
            await api(`/api/theme-topics/${topicId}/receiver-rules`, jsonRequest("POST", body));
            app.flash("接收规则已创建。");
          }
          app.state.selectedTopicId = topicId;
          app.state.editingTopicRuleId = null;
          await app.reloadThemeSources();
          app.render();
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    }

    document.querySelectorAll("[data-action='topic-rule-edit']").forEach((button) => {
      button.addEventListener("click", () => {
        app.state.editingTopicRuleId = Number(button.dataset.id);
        app.render();
      });
    });

    document.querySelectorAll("[data-action='topic-rule-delete']").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          await api(`/api/theme-receiver-rules/${button.dataset.id}`, { method: "DELETE" });
          app.flash("接收规则已删除。");
          app.state.editingTopicRuleId = null;
          await app.reloadThemeSources();
          app.render();
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    });

    document.querySelectorAll("[data-action='topic-rule-reset']").forEach((button) => {
      button.addEventListener("click", () => {
        app.state.editingTopicRuleId = null;
        app.render();
      });
    });
  },
};
