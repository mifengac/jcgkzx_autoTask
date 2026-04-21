import { api } from "./core/api.js?v=20260421-ui2";
import { emptyState, escapeHtml, formatTime, jsonBlock, statusBadge, table, textBlock, truncateText } from "./core/ui.js?v=20260421-ui2";
import { contactsSection } from "./sections/contacts.js?v=20260421-ui2";
import { overviewSection } from "./sections/overview.js?v=20260421-ui2";
import { resultsSection } from "./sections/results.js?v=20260421-ui2";
import { runsSection } from "./sections/runs.js?v=20260421-ui2";
import { smsLogsSection } from "./sections/smsLogs.js?v=20260421-ui2";
import { sourcesSection } from "./sections/sources.js?v=20260421-ui2";
import { tasksSection } from "./sections/tasks.js?v=20260421-ui2";
import { templatesSection } from "./sections/templates.js?v=20260421-ui2";
import { topicsSection } from "./sections/topics.js?v=20260421-ui2";

const sections = [
  overviewSection,
  sourcesSection,
  topicsSection,
  templatesSection,
  contactsSection,
  resultsSection,
  smsLogsSection,
  runsSection,
  tasksSection,
];

const sectionMap = Object.fromEntries(sections.map((section) => [section.key, section]));

const state = {
  healthOk: null,
  route: { primary: "overview", secondary: "home" },
  scripts: [],
  templates: [],
  tasks: [],
  themeSources: [],
  themeSourceDetailsById: {},
  themeSourceDetail: null,
  selectedSourceId: null,
  selectedTopicId: null,
  selectedTaskId: null,
  topicEditorCreating: false,
  editingSourceId: null,
  editingTaskId: null,
  editingTemplateId: null,
  editingTopicRuleId: null,
  editingTaskRuleId: null,
  overview: {
    themeRuns: [],
    taskRuns: [],
    failedSmsLogs: [],
  },
  themeResultPage: {
    items: [],
    total: 0,
    limit: 20,
    offset: 0,
    filters: {
      source_id: null,
      topic_id: null,
      send_status: "",
      keyword: "",
      start_time: "",
      end_time: "",
    },
  },
  themeSmsLogPage: {
    items: [],
    total: 0,
    limit: 20,
    offset: 0,
    filters: {
      source_id: null,
      topic_id: null,
      status: "",
      mobile: "",
    },
  },
  themeRunPage: {
    items: [],
    total: 0,
    limit: 20,
    offset: 0,
    filters: {
      source_id: null,
      topic_id: null,
      status: "",
    },
  },
  taskRunPage: {
    items: [],
    taskId: null,
  },
  contacts: {
    items: [],
    total: 0,
    query: {
      keyword: "",
      sspcsdm: "",
      xqdm: "",
    },
  },
  contactDirectory: {
    items: [],
    total: 0,
    query: {
      keyword: "",
      sspcsdm: "",
      xqdm: "",
      rwzt: "",
      unit_level: "",
      source_system: "",
      status: "all",
      mobile: "",
      limit: 100,
      offset: 0,
    },
  },
  contactImportResult: null,
  editingContactId: null,
  contactDetail: null,
  drawer: {
    open: false,
    title: "详情",
    eyebrow: "",
    bodyHtml: "",
  },
};

const dom = {};

function getDefaultTab(primary) {
  return sectionMap[primary]?.tabs?.[0]?.key || "home";
}

function parseHash() {
  const raw = window.location.hash.replace(/^#/, "").trim();
  if (!raw) {
    return { primary: "overview", secondary: "home" };
  }
  const [primaryRaw, secondaryRaw] = raw.split("/");
  const primary = sectionMap[primaryRaw] ? primaryRaw : "overview";
  const secondary = sectionMap[primary].tabs.some((item) => item.key === secondaryRaw)
    ? secondaryRaw
    : getDefaultTab(primary);
  return { primary, secondary };
}

function toDateTimeLocal(value) {
  if (!value) {
    return "";
  }
  return String(value).replace("T", " ").slice(0, 16).replace(" ", "T");
}

function buildQuery(params) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") {
      return;
    }
    query.set(key, String(value));
  });
  return query.toString();
}

const app = {
  state,
  dom,
  async init() {
    this.cacheDom();
    this.bindGlobalEvents();
    await this.loadBootstrap();
    this.syncRoute();
    await this.renderRoute();
  },
  async render() {
    return this.renderRoute();
  },
  cacheDom() {
    dom.primaryNav = document.querySelector("#primary-nav");
    dom.secondaryNav = document.querySelector("#secondary-nav");
    dom.secondaryTitle = document.querySelector("#secondary-title");
    dom.sectionHeader = document.querySelector("#section-header");
    dom.contentArea = document.querySelector("#content-area");
    dom.flash = document.querySelector("#flash");
    dom.healthPill = document.querySelector("#health-pill");
    dom.drawer = document.querySelector("#detail-drawer");
    dom.drawerTitle = document.querySelector("#drawer-title");
    dom.drawerEyebrow = document.querySelector("#drawer-eyebrow");
    dom.drawerBody = document.querySelector("#drawer-body");
  },
  bindGlobalEvents() {
    document.querySelector("#refresh-all").addEventListener("click", async () => {
      await this.loadBootstrap();
      await this.renderRoute();
      this.flash("全部数据已刷新。");
    });
    document.querySelector("#drawer-close").addEventListener("click", () => this.closeDrawer());
    dom.drawer.addEventListener("close", () => {
      state.drawer.open = false;
      state.drawer.bodyHtml = "";
    });
    window.addEventListener("hashchange", async () => {
      this.syncRoute();
      await this.renderRoute();
    });
  },
  syncRoute() {
    state.route = parseHash();
  },
  navigate(primary, secondary = getDefaultTab(primary)) {
    const hash = `#${primary}/${secondary}`;
    if (window.location.hash === hash) {
      this.syncRoute();
      this.renderRoute();
      return;
    }
    window.location.hash = hash;
  },
  async loadBootstrap() {
    const results = await Promise.allSettled([
      this.loadHealth(),
      this.reloadScripts(),
      this.reloadTemplates(),
      this.reloadTasks(),
      this.reloadThemeSources(),
    ]);
    const rejected = results.find((item) => item.status === "rejected");
    if (rejected) {
      this.flash(rejected.reason?.message || "部分数据加载失败。", true);
    }
  },
  async loadHealth() {
    try {
      await api("/health");
      state.healthOk = true;
    } catch (error) {
      state.healthOk = false;
      this.flash(error.message, true);
    }
  },
  async reloadScripts() {
    state.scripts = await api("/api/scripts");
  },
  async reloadTemplates() {
    state.templates = await api("/api/message-templates");
  },
  async reloadTasks() {
    state.tasks = await api("/api/tasks");
    if (!state.selectedTaskId && state.tasks[0]) {
      state.selectedTaskId = state.tasks[0].id;
    }
    if (state.selectedTaskId && !state.tasks.some((item) => item.id === state.selectedTaskId)) {
      state.selectedTaskId = state.tasks[0]?.id || null;
    }
    if (!state.taskRunPage.taskId && state.selectedTaskId) {
      state.taskRunPage.taskId = state.selectedTaskId;
    }
  },
  async ensureThemeSourceDetail(sourceId) {
    if (!sourceId) {
      state.themeSourceDetail = null;
      state.selectedTopicId = null;
      return null;
    }
    const detail = await api(`/api/theme-sources/${sourceId}`);
    state.themeSourceDetailsById[sourceId] = detail;
    if (sourceId === state.selectedSourceId) {
      state.themeSourceDetail = detail;
      const topics = detail.topics || [];
      if (!state.selectedTopicId && topics[0] && !state.topicEditorCreating) {
        state.selectedTopicId = topics[0].id;
      }
      if (state.selectedTopicId && !topics.some((item) => item.id === state.selectedTopicId)) {
        state.selectedTopicId = state.topicEditorCreating ? null : topics[0]?.id || null;
      }
    }
    return detail;
  },
  async reloadThemeSources() {
    state.themeSources = await api("/api/theme-sources");
    if (!state.selectedSourceId && state.themeSources[0]) {
      state.selectedSourceId = state.themeSources[0].id;
    }
    if (state.selectedSourceId && !state.themeSources.some((item) => item.id === state.selectedSourceId)) {
      state.selectedSourceId = state.themeSources[0]?.id || null;
    }
    await this.ensureThemeSourceDetail(state.selectedSourceId);
  },
  async setSelectedSource(sourceId) {
    state.selectedSourceId = sourceId || null;
    await this.ensureThemeSourceDetail(state.selectedSourceId);
  },
  async setSelectedTopic(topicId) {
    state.selectedTopicId = topicId || null;
    state.topicEditorCreating = false;
    if (!state.selectedSourceId) {
      return;
    }
    await this.ensureThemeSourceDetail(state.selectedSourceId);
  },
  async setSelectedTask(taskId) {
    state.selectedTaskId = taskId || null;
    if (state.selectedTaskId && !state.taskRunPage.taskId) {
      state.taskRunPage.taskId = state.selectedTaskId;
    }
  },
  getCurrentSource() {
    return state.themeSourceDetail;
  },
  getCurrentTopic() {
    return state.themeSourceDetail?.topics?.find((item) => item.id === state.selectedTopicId) || null;
  },
  getCurrentTask() {
    return state.tasks.find((item) => item.id === state.selectedTaskId) || null;
  },
  getAvailableTopics() {
    return state.themeSourceDetail?.topics || [];
  },
  getTopicsForSource(sourceId) {
    if (!sourceId) {
      return [];
    }
    if (sourceId === state.selectedSourceId) {
      return this.getAvailableTopics();
    }
    return state.themeSourceDetailsById[sourceId]?.topics || [];
  },
  async refreshThemeResults() {
    const page = state.themeResultPage;
    const query = buildQuery({
      ...page.filters,
      start_time: page.filters.start_time ? `${page.filters.start_time}:00` : "",
      end_time: page.filters.end_time ? `${page.filters.end_time}:00` : "",
      limit: page.limit,
      offset: page.offset,
    });
    const data = await api(`/api/theme-results?${query}`);
    state.themeResultPage = { ...state.themeResultPage, ...data, filters: { ...state.themeResultPage.filters } };
  },
  async refreshThemeSmsLogs() {
    const page = state.themeSmsLogPage;
    const query = buildQuery({
      ...page.filters,
      limit: page.limit,
      offset: page.offset,
    });
    const data = await api(`/api/theme-sms-logs?${query}`);
    state.themeSmsLogPage = { ...state.themeSmsLogPage, ...data, filters: { ...state.themeSmsLogPage.filters } };
  },
  async refreshThemeRuns(overrides = null) {
    if (overrides) {
      state.themeRunPage.filters = {
        ...state.themeRunPage.filters,
        ...Object.fromEntries(
          Object.entries(overrides).filter(([key]) => !["limit", "offset"].includes(key))
        ),
      };
      if (overrides.limit !== undefined) {
        state.themeRunPage.limit = overrides.limit;
      }
      if (overrides.offset !== undefined) {
        state.themeRunPage.offset = overrides.offset;
      }
    }
    const query = buildQuery({
      ...state.themeRunPage.filters,
      limit: state.themeRunPage.limit,
      offset: state.themeRunPage.offset,
    });
    const items = await api(`/api/theme-runs?${query}`);
    state.themeRunPage.items = items;
    state.themeRunPage.total = items.length;
  },
  async refreshTaskRuns() {
    const query = buildQuery({
      task_id: state.taskRunPage.taskId || state.selectedTaskId,
      limit: 50,
    });
    state.taskRunPage.items = await api(`/api/task-runs?${query}`);
  },
  async loadContacts(query = state.contacts.query) {
    state.contacts.query = { ...state.contacts.query, ...query };
    const queryString = buildQuery(state.contacts.query);
    const data = await api(queryString ? `/api/contacts?${queryString}` : "/api/contacts");
    state.contacts.items = data.items || [];
    state.contacts.total = data.total || 0;
  },
  async loadContactDirectory(query = state.contactDirectory.query) {
    state.contactDirectory.query = { ...state.contactDirectory.query, ...query };
    const queryString = buildQuery(state.contactDirectory.query);
    const data = await api(queryString ? `/api/contacts?${queryString}` : "/api/contacts");
    state.contactDirectory.items = data.items || [];
    state.contactDirectory.total = data.total || 0;
  },
  async loadContactDetail(contactId) {
    if (!contactId) {
      state.contactDetail = null;
      return null;
    }
    state.contactDetail = await api(`/api/contacts/${contactId}`);
    return state.contactDetail;
  },
  async loadOverviewData() {
    const [themeRuns, taskRuns, failedSmsLogs] = await Promise.all([
      api("/api/theme-runs?limit=5"),
      api("/api/task-runs?limit=5"),
      api("/api/theme-sms-logs?status=failed&limit=5&offset=0"),
    ]);
    state.overview.themeRuns = themeRuns;
    state.overview.taskRuns = taskRuns;
    state.overview.failedSmsLogs = failedSmsLogs.items || [];
  },
  getOverviewStats() {
    const sourceCount = state.themeSources.length;
    const topicCount = state.themeSources.reduce((sum, item) => sum + Number(item.topic_count || 0), 0);
    return {
      sourceCount,
      topicCount,
      templateCount: state.templates.length,
      taskCount: state.tasks.length,
      themeRunCount: state.overview.themeRuns.length,
      taskRunCount: state.overview.taskRuns.length,
      failedSmsCount: state.overview.failedSmsLogs.length,
      alertCount: state.overview.failedSmsLogs.length,
    };
  },
  resetThemeResultFilters() {
    state.themeResultPage = {
      ...state.themeResultPage,
      offset: 0,
      filters: {
        source_id: null,
        topic_id: null,
        send_status: "",
        keyword: "",
        start_time: "",
        end_time: "",
      },
    };
  },
  resetThemeSmsLogFilters() {
    state.themeSmsLogPage = {
      ...state.themeSmsLogPage,
      offset: 0,
      filters: {
        source_id: null,
        topic_id: null,
        status: "",
        mobile: "",
      },
    };
  },
  resetThemeRunFilters() {
    state.themeRunPage = {
      ...state.themeRunPage,
      offset: 0,
      filters: {
        source_id: null,
        topic_id: null,
        status: "",
      },
    };
  },
  renderShell() {
    dom.healthPill.textContent = state.healthOk === null ? "检查中" : state.healthOk ? "服务正常" : "服务异常";
    dom.healthPill.dataset.state = state.healthOk === null ? "checking" : state.healthOk ? "ok" : "bad";

    dom.primaryNav.innerHTML = `
      <ul>
        ${sections.map((section) => `
          <li>
            <button class="${state.route.primary === section.key ? "contrast" : "secondary"}" type="button" data-primary="${section.key}">
              ${escapeHtml(section.label)}
            </button>
          </li>
        `).join("")}
      </ul>
    `;
    dom.primaryNav.querySelectorAll("[data-primary]").forEach((button) => {
      button.addEventListener("click", () => {
        this.navigate(button.dataset.primary, getDefaultTab(button.dataset.primary));
      });
    });

    const section = sectionMap[state.route.primary];
    dom.secondaryTitle.textContent = section.label;
    dom.secondaryNav.innerHTML = `
      <ul>
        ${section.tabs.map((tab) => `
          <li>
            <button class="${state.route.secondary === tab.key ? "contrast" : "outline"}" type="button" data-secondary="${tab.key}">
              ${escapeHtml(tab.label)}
            </button>
          </li>
        `).join("")}
      </ul>
    `;
    dom.secondaryNav.querySelectorAll("[data-secondary]").forEach((button) => {
      button.addEventListener("click", () => {
        this.navigate(state.route.primary, button.dataset.secondary);
      });
    });

    const metaPills = [];
    if (state.selectedSourceId && state.route.primary !== "sources") {
      metaPills.push(`<li><small>当前数据源: ${escapeHtml(this.getCurrentSource()?.source_name || `#${state.selectedSourceId}`)}</small></li>`);
    }
    if (state.selectedTopicId && state.route.primary !== "topics") {
      metaPills.push(`<li><small>当前主题: ${escapeHtml(this.getCurrentTopic()?.theme_name || `#${state.selectedTopicId}`)}</small></li>`);
    }
    if (state.selectedTaskId && state.route.primary !== "tasks") {
      metaPills.push(`<li><small>当前任务: ${escapeHtml(this.getCurrentTask()?.task_name || `#${state.selectedTaskId}`)}</small></li>`);
    }
    dom.sectionHeader.innerHTML = `
      <header>
        <h2>${escapeHtml(section.label)}</h2>
        <p>${escapeHtml(section.description)}</p>
      </header>
      ${metaPills.length ? `<nav aria-label="context"><ul>${metaPills.join("")}</ul></nav>` : ""}
    `;
  },
  async renderRoute() {
    const section = sectionMap[state.route.primary];
    try {
      await section.load?.(this);
      this.renderShell();
      dom.contentArea.innerHTML = section.render(this);
      section.bind?.(this);
      this.renderDrawer();
    } catch (error) {
      dom.contentArea.innerHTML = emptyState(error.message);
      this.flash(error.message, true);
    }
  },
  flash(message, isError = false) {
    if (!message) {
      dom.flash.hidden = true;
      dom.flash.innerHTML = "";
      return;
    }
    dom.flash.hidden = false;
    dom.flash.innerHTML = `
      <article ${isError ? 'aria-invalid="true"' : ''}>
        <strong>${isError ? "错误" : "提示"}</strong>
        <p>${escapeHtml(String(message))}</p>
      </article>
    `;
    window.clearTimeout(this.flashTimer);
    this.flashTimer = window.setTimeout(() => {
      dom.flash.hidden = true;
      dom.flash.innerHTML = "";
    }, 4200);
  },
  closeDrawer() {
    state.drawer.open = false;
    state.drawer.bodyHtml = "";
    this.renderDrawer();
  },
  async openDrawer(type, id) {
    state.drawer.open = true;
    state.drawer.title = "加载中...";
    state.drawer.eyebrow = "详情";
    state.drawer.bodyHtml = '<div>正在加载详情...</div>';
    this.renderDrawer();
    try {
      if (type === "theme-result") {
        const detail = await api(`/api/theme-results/${id}`);
        state.drawer.title = `${detail.topic_name} / ${detail.case_no || detail.event_key}`;
        state.drawer.eyebrow = "命中结果";
        state.drawer.bodyHtml = this.renderThemeResultDrawer(detail);
      } else if (type === "theme-sms-log") {
        const detail = await api(`/api/theme-sms-logs/${id}`);
        state.drawer.title = `${detail.topic_name} / ${detail.mobile}`;
        state.drawer.eyebrow = "短信发送记录";
        state.drawer.bodyHtml = this.renderThemeSmsLogDrawer(detail);
      } else if (type === "theme-run") {
        const detail = await api(`/api/theme-runs/${id}`);
        state.drawer.title = detail.run_no;
        state.drawer.eyebrow = "数据源运行";
        state.drawer.bodyHtml = this.renderThemeRunDrawer(detail);
      } else if (type === "task-run") {
        const detail = await api(`/api/task-runs/${id}`);
        state.drawer.title = detail.run_no;
        state.drawer.eyebrow = "自定义任务运行";
        state.drawer.bodyHtml = this.renderTaskRunDrawer(detail);
      } else if (type === "contact") {
        const detail = await api(`/api/contacts/${id}`);
        state.drawer.title = detail.xm || detail.sspcs || `#${detail.id}`;
        state.drawer.eyebrow = "联系人详情";
        state.drawer.bodyHtml = this.renderContactDrawer(detail);
      }
      this.renderDrawer();
    } catch (error) {
      state.drawer.title = "详情加载失败";
      state.drawer.eyebrow = "详情";
      state.drawer.bodyHtml = `<div>${escapeHtml(error.message)}</div>`;
      this.renderDrawer();
      this.flash(error.message, true);
    }
  },
  renderDrawer() {
    if (!state.drawer.open) {
      if (dom.drawer.open) {
        dom.drawer.close();
      }
      return;
    }
    dom.drawerTitle.textContent = state.drawer.title;
    dom.drawerEyebrow.textContent = state.drawer.eyebrow;
    dom.drawerBody.innerHTML = state.drawer.bodyHtml;
    if (!dom.drawer.open) {
      dom.drawer.showModal();
    }
    this.bindDrawerActions();
  },
  bindDrawerActions() {
    dom.drawerBody.querySelectorAll("[data-action='copy-text']").forEach((button) => {
      button.addEventListener("click", async () => {
        const target = dom.drawerBody.querySelector(button.dataset.target);
        if (!target) {
          return;
        }
        try {
          await navigator.clipboard.writeText(target.textContent || "");
          this.flash("短信内容已复制。");
        } catch (error) {
          this.flash("复制失败，请手动复制。", true);
        }
      });
    });
    dom.drawerBody.querySelectorAll("[data-action='drawer-open-detail']").forEach((button) => {
      button.addEventListener("click", () => {
        this.openDrawer(button.dataset.type, Number(button.dataset.id));
      });
    });
  },
  renderDetailFacts(items, cols = "two") {
    const visibleItems = items.filter((item) => item.value !== undefined && item.value !== null && item.value !== "");
    if (!visibleItems.length) {
      return emptyState("暂无信息。");
    }
    return `
      <div class="drawer-detail-grid">
        ${visibleItems.map((item) => `
          <div>
            <strong>${escapeHtml(item.label)}</strong>
            ${item.value}
          </div>
        `).join("")}
      </div>
    `;
  },
  renderDrawerCard({ title, status, meta = [], summary = "", actionHtml = "" }) {
    return `
      <article>
        <div class="card-head">
          <h4>${title}</h4>
          ${status || ""}
        </div>
        ${meta.length ? `
          <div>
            ${meta.map((item) => `
              <div>
                <strong>${escapeHtml(item.label)}</strong>
                ${item.value}
              </div>
            `).join("")}
          </div>
        ` : ""}
        ${summary ? `<div>${summary}</div>` : ""}
        ${actionHtml ? `<div>${actionHtml}</div>` : ""}
      </article>
    `;
  },
  renderDrawerCardList(items, emptyText, renderer) {
    if (!items.length) {
      return emptyState(emptyText);
    }
    return `<div>${items.map((item) => renderer(item)).join("")}</div>`;
  },
  renderThemeResultDrawer(detail) {
    const receiverText = escapeHtml((detail.receiver_mobiles || []).join(", ") || "-");
    const matchedRules = escapeHtml((detail.matched_rule_ids || []).join(", ") || "无");
    return `
      <div class="drawer-detail-grid">
        <div>
          <h3>基本信息</h3>
          ${this.renderDetailFacts([
            { label: "数据源", value: escapeHtml(detail.source_name || "-") },
            { label: "主题", value: escapeHtml(detail.topic_name || "-") },
            { label: "警情编号", value: escapeHtml(detail.case_no || detail.event_key || "-") },
            { label: "发送状态", value: statusBadge(detail.send_status) },
            { label: "Oracle EID", value: `<span>${escapeHtml(detail.oracle_eid || "-")}</span>` },
            { label: "事件键", value: `<span>${escapeHtml(detail.event_key || "-")}</span>` },
          ])}
        </div>
        <div>
          <h3>接收信息</h3>
          ${this.renderDetailFacts([
            { label: "接收人", value: receiverText },
            { label: "命中规则", value: matchedRules },
            { label: "数据源 ID", value: escapeHtml(String(detail.source_id ?? "-")) },
            { label: "主题 ID", value: escapeHtml(String(detail.topic_id ?? "-")) },
          ])}
        </div>
      </div>
      <div class="drawer-detail-grid">
        <div>
          <h3>短信内容</h3>
          ${textBlock(detail.rendered_message || "")}
        </div>
        <div>
          <h3>原始数据</h3>
          ${jsonBlock(detail.raw_result)}
        </div>
      </div>
    `;
  },
  renderThemeSmsLogDrawer(detail) {
    return `
      <div class="drawer-detail-grid">
        <div>
          <h3>发送概要</h3>
          ${this.renderDetailFacts([
            { label: "数据源", value: escapeHtml(detail.source_name || "-") },
            { label: "主题", value: escapeHtml(detail.topic_name || "-") },
            { label: "手机号", value: escapeHtml(detail.mobile || "-") },
            { label: "发送状态", value: statusBadge(detail.status) },
            { label: "Oracle EID", value: `<span>${escapeHtml(detail.oracle_eid || "-")}</span>` },
            { label: "命中状态", value: statusBadge(detail.result_send_status || "-") },
          ])}
        </div>
        <div>
          <h3>失败与回执</h3>
          ${this.renderDetailFacts([
            { label: "失败原因", value: escapeHtml(detail.error_message || "-") },
            { label: "平台回执", value: escapeHtml(detail.provider_msg_id || "-") },
            { label: "命中结果 ID", value: escapeHtml(String(detail.topic_result_id ?? "-")) },
            { label: "发送时间", value: escapeHtml(formatTime(detail.created_at)) },
          ])}
        </div>
      </div>
      <div class="drawer-detail-grid">
        <div>
          <div style="margin-bottom:10px;">
            <div><h3>短信内容</h3><p>支持复制。</p></div>
            <div><button class="outline" type="button" data-action="copy-text" data-target="#sms-log-content">复制</button></div>
          </div>
          <pre id="sms-log-content">${escapeHtml(detail.content || "")}</pre>
        </div>
        <div>
          <div style="margin-bottom:10px;">
            <div><h3>关联命中</h3><p>可继续追溯。</p></div>
            ${detail.topic_result_id ? `<div><button class="outline" type="button" data-action="drawer-open-detail" data-type="theme-result" data-id="${detail.topic_result_id}">命中详情</button></div>` : ""}
          </div>
          ${jsonBlock(detail.raw_result)}
        </div>
      </div>
    `;
  },
  renderThemeRunDrawer(detail) {
    const resultCards = this.renderDrawerCardList(
      (detail.results || []).slice(0, 10),
      "本次运行没有命中结果。",
      (item) => this.renderDrawerCard({
        title: escapeHtml(item.case_no || item.event_key || `#${item.id}`),
        status: statusBadge(item.send_status),
        meta: [
          { label: "接收人", value: escapeHtml((item.receiver_mobiles || []).join(", ") || "-") },
          { label: "Oracle EID", value: `<span>${escapeHtml(item.oracle_eid || "-")}</span>` },
          { label: "规则", value: escapeHtml((item.matched_rule_ids || []).join(", ") || "无") },
        ],
        summary: escapeHtml(truncateText(item.rendered_message || item.content_preview || item.event_key || "无摘要", 160)),
        actionHtml: item.id
          ? `<button class="outline" type="button" data-action="drawer-open-detail" data-type="theme-result" data-id="${item.id}">详情</button>`
          : "",
      })
    );
    const smsCards = this.renderDrawerCardList(
      (detail.sms_logs || []).slice(0, 10),
      "本次运行没有短信日志。",
      (item) => this.renderDrawerCard({
        title: escapeHtml(item.mobile || `#${item.id}`),
        status: statusBadge(item.status),
        meta: [
          { label: "发送时间", value: escapeHtml(formatTime(item.created_at)) },
          { label: "Oracle EID", value: `<span>${escapeHtml(item.oracle_eid || "-")}</span>` },
          { label: "回执", value: escapeHtml(item.provider_msg_id || "-") },
        ],
        summary: escapeHtml(truncateText(item.error_message || item.content_preview || item.content || "无内容", 160)),
        actionHtml: item.id
          ? `<button class="outline" type="button" data-action="drawer-open-detail" data-type="theme-sms-log" data-id="${item.id}">详情</button>`
          : "",
      })
    );
    return `
      <div>
        <h3>运行摘要</h3>
        ${this.renderDetailFacts([
          { label: "运行号", value: `<span>${escapeHtml(detail.run_no)}</span>` },
          { label: "状态", value: statusBadge(detail.status) },
          { label: "抓取数量", value: escapeHtml(String(detail.fetched_count ?? "-")) },
          { label: "命中数量", value: escapeHtml(String(detail.matched_count ?? "-")) },
          { label: "发送数量", value: escapeHtml(String(detail.send_count ?? "-")) },
          { label: "错误信息", value: escapeHtml(detail.error_message || "-") },
        ])}
      </div>
      <div>
        <h3>命中结果（前 10 条）</h3>
        ${resultCards}
      </div>
      <div>
        <h3>短信日志（前 10 条）</h3>
        ${smsCards}
      </div>
    `;
  },
  renderTaskRunDrawer(detail) {
    const syncPayload = (detail.results || [])
      .map((item) => item?.raw_result)
      .find((raw) => raw && typeof raw === "object" && (
        Object.prototype.hasOwnProperty.call(raw, "fetched_record_count")
        || Object.prototype.hasOwnProperty.call(raw, "written_record_count")
        || Object.prototype.hasOwnProperty.call(raw, "target_table")
      )) || null;
    const resultCards = this.renderDrawerCardList(
      (detail.results || []).slice(0, 10),
      "本次运行没有命中结果。",
      (item) => this.renderDrawerCard({
        title: escapeHtml(item.case_no || item.event_key || `#${item.id}`),
        status: statusBadge(item.send_status),
        meta: [
          { label: "接收人", value: escapeHtml((item.receiver_mobiles || []).join(", ") || "-") },
          { label: "事件键", value: `<span>${escapeHtml(item.event_key || "-")}</span>` },
          { label: "结果状态", value: escapeHtml(item.status || "-") },
        ],
        summary: escapeHtml(truncateText(
          item.rendered_message
            || item.raw_result?.message_text
            || item.raw_result?.error_message
            || "无摘要",
          160
        )),
      })
    );
    const smsCards = this.renderDrawerCardList(
      (detail.sms_logs || []).slice(0, 10),
      "本次运行没有短信日志。",
      (item) => this.renderDrawerCard({
        title: escapeHtml(item.mobile || `#${item.id}`),
        status: statusBadge(item.status),
        meta: [
          { label: "发送时间", value: escapeHtml(formatTime(item.created_at)) },
          { label: "回执", value: escapeHtml(item.provider_msg_id || "-") },
          { label: "EID", value: `<span>${escapeHtml(item.oracle_eid || "-")}</span>` },
        ],
        summary: escapeHtml(truncateText(item.error_message || item.content || "无内容", 160)),
      })
    );
    const syncSummaryBlock = syncPayload ? `
      <div>
        <h3>同步摘要</h3>
        ${this.renderDetailFacts([
          { label: "同步状态", value: statusBadge(syncPayload.status || "-") },
          { label: "目标表", value: `<span>${escapeHtml(syncPayload.target_table || "-")}</span>` },
          { label: "抓取数量", value: escapeHtml(String(syncPayload.fetched_record_count ?? "-")) },
          { label: "写入数量", value: escapeHtml(String(syncPayload.written_record_count ?? "-")) },
          { label: "开始时间", value: escapeHtml(formatTime(syncPayload.start_time)) },
          { label: "结束时间", value: escapeHtml(formatTime(syncPayload.end_time)) },
        ])}
        <div style="margin-top:10px;">
          <strong>同步说明</strong>
          ${textBlock(syncPayload.message_text || JSON.stringify(syncPayload, null, 2))}
        </div>
      </div>
    ` : "";
    return `
      ${syncSummaryBlock}
      <div>
        <h3>运行摘要</h3>
        ${this.renderDetailFacts([
          { label: "运行号", value: `<span>${escapeHtml(detail.run_no)}</span>` },
          { label: "状态", value: statusBadge(detail.status) },
          { label: "结果数量", value: escapeHtml(String(detail.result_count ?? "-")) },
          { label: "命中数量", value: escapeHtml(String(detail.hit_count ?? "-")) },
          { label: "发送数量", value: escapeHtml(String(detail.send_count ?? "-")) },
          { label: "错误信息", value: escapeHtml(detail.error_message || "-") },
        ])}
      </div>
      <div>
        <h3>命中结果（前 10 条）</h3>
        ${resultCards}
      </div>
      <div>
        <h3>短信日志（前 10 条）</h3>
        ${smsCards}
      </div>
    `;
  },
  renderContactDrawer(detail) {
    const sourceLabel = detail.source_system === "manual_ui"
      ? "手工维护"
      : detail.source_system === "ywdata.b_dxpt_mdjfyj"
        ? "导入联系人"
        : detail.source_system;
    const phoneRows = (detail.phones || []).length
      ? detail.phones.map((phone) => `
        <tr>
          <td>${escapeHtml(phone.phone_raw || "-")}</td>
          <td>${escapeHtml(phone.mobile || "-")}</td>
          <td>${statusBadge(phone.status)}</td>
          <td>${phone.is_primary ? "是" : "否"}</td>
        </tr>
      `).join("")
      : "";
    return `
      <div>
        <h3>联系人概况</h3>
        <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr)); align-items:start;">
          <div><strong>姓名</strong>${escapeHtml(detail.xm || "-")}</div>
          <div><strong>职务</strong>${escapeHtml(detail.zw || "-")}</div>
          <div><strong>派出所</strong>${escapeHtml(detail.sspcs || "-")}</div>
          <div><strong>派出所代码</strong><span>${escapeHtml(detail.sspcsdm || "-")}</span></div>
          <div><strong>县区</strong>${escapeHtml(detail.xq || "-")}</div>
          <div><strong>县区代码</strong><span>${escapeHtml(detail.xqdm || "-")}</span></div>
          <div><strong>来源</strong>${escapeHtml(sourceLabel || "-")}</div>
          <div><strong>状态</strong>${statusBadge(detail.status)}</div>
          <div><strong>任务状态</strong>${escapeHtml(detail.rwzt || "-")}</div>
          <div><strong>单位层级</strong>${escapeHtml(detail.unit_level || "-")}</div>
          <div><strong>创建时间</strong>${escapeHtml(formatTime(detail.created_at))}</div>
          <div><strong>更新时间</strong>${escapeHtml(formatTime(detail.updated_at))}</div>
        </div>
      </div>
      <div>
        <h3>手机号</h3>
        ${(detail.phones || []).length
          ? `<div><table><thead><tr><th>原始号码</th><th>标准手机号</th><th>状态</th><th>主号</th></tr></thead><tbody>${phoneRows}</tbody></table></div>`
          : emptyState("暂无手机号")}
      </div>
      <div>
        <h3>备注</h3>
        ${textBlock(detail.remark || "")}
      </div>
    `;
  },
};

Object.assign(app, {
  renderShell() {
    dom.healthPill.textContent = state.healthOk === null ? "检查中" : state.healthOk ? "服务正常" : "服务异常";
    dom.healthPill.dataset.state = state.healthOk === null ? "checking" : state.healthOk ? "ok" : "bad";

    const section = sectionMap[state.route.primary];
    const activeTab = section.tabs.find((tab) => tab.key === state.route.secondary) || section.tabs[0];
    const sectionIndex = sections.findIndex((item) => item.key === section.key) + 1;

    dom.primaryNav.innerHTML = `
      <ul class="console-nav-list">
        ${sections.map((item) => `
          <li>
            <button class="console-nav-button${state.route.primary === item.key ? " is-active" : ""}" type="button" data-primary="${item.key}">
              <span class="console-nav-button__label">${escapeHtml(item.label)}</span>
            </button>
          </li>
        `).join("")}
      </ul>
    `;
    dom.primaryNav.querySelectorAll("[data-primary]").forEach((button) => {
      button.addEventListener("click", () => {
        this.navigate(button.dataset.primary, getDefaultTab(button.dataset.primary));
      });
    });

    dom.secondaryTitle.textContent = section.label;
    dom.secondaryNav.innerHTML = `
      <ul class="console-nav-list">
        ${section.tabs.map((tab) => `
          <li>
            <button class="console-nav-button console-nav-button--secondary${state.route.secondary === tab.key ? " is-active" : ""}" type="button" data-secondary="${tab.key}">
              <span class="console-nav-button__label">${escapeHtml(tab.label)}</span>
            </button>
          </li>
        `).join("")}
      </ul>
    `;
    dom.secondaryNav.querySelectorAll("[data-secondary]").forEach((button) => {
      button.addEventListener("click", () => {
        this.navigate(state.route.primary, button.dataset.secondary);
      });
    });

    const metaPills = [
      `<span class="context-pill">当前子页 · ${escapeHtml(activeTab.label)}</span>`,
    ];
    if (state.selectedSourceId && state.route.primary !== "sources") {
      metaPills.push(`<span class="context-pill">当前数据源 · ${escapeHtml(this.getCurrentSource()?.source_name || `#${state.selectedSourceId}`)}</span>`);
    }
    if (state.selectedTopicId && state.route.primary !== "topics") {
      metaPills.push(`<span class="context-pill">当前主题 · ${escapeHtml(this.getCurrentTopic()?.theme_name || `#${state.selectedTopicId}`)}</span>`);
    }
    if (state.selectedTaskId && state.route.primary !== "tasks") {
      metaPills.push(`<span class="context-pill">当前任务 · ${escapeHtml(this.getCurrentTask()?.task_name || `#${state.selectedTaskId}`)}</span>`);
    }

    dom.sectionHeader.innerHTML = `
      <div class="console-section-card__body">
        <div>
          <p class="section-kicker">章节 ${String(sectionIndex).padStart(2, "0")}</p>
          <h2>${escapeHtml(section.label)}</h2>
          <div class="console-section-tabs" aria-label="当前章节视图">
            ${section.tabs.map((tab) => `
              <button class="console-tab-button${state.route.secondary === tab.key ? " is-active" : ""}" type="button" data-secondary="${tab.key}">
                ${escapeHtml(tab.label)}
              </button>
            `).join("")}
          </div>
        </div>
        <div class="console-stack">
          <p class="console-section-card__lead">${escapeHtml(section.description)}</p>
          <div class="console-section-card__meta">${metaPills.filter(Boolean).join("")}</div>
        </div>
      </div>
    `;
    dom.sectionHeader.querySelectorAll("[data-secondary]").forEach((button) => {
      button.addEventListener("click", () => {
        this.navigate(state.route.primary, button.dataset.secondary);
      });
    });
  },
  flash(message, isError = false) {
    if (!message) {
      dom.flash.hidden = true;
      dom.flash.innerHTML = "";
      return;
    }
    dom.flash.hidden = false;
    dom.flash.innerHTML = `
      <article class="flash-card${isError ? " flash-card--error" : ""}" ${isError ? 'aria-invalid="true"' : ""}>
        <p class="flash-card__eyebrow">${isError ? "Error State" : "System Notice"}</p>
        <strong>${isError ? "错误提醒" : "系统提示"}</strong>
        <p>${escapeHtml(String(message))}</p>
      </article>
    `;
    window.clearTimeout(this.flashTimer);
    this.flashTimer = window.setTimeout(() => {
      dom.flash.hidden = true;
      dom.flash.innerHTML = "";
    }, 4200);
  },
  async openDrawer(type, id) {
    state.drawer.open = true;
    state.drawer.title = "加载中...";
    state.drawer.eyebrow = "详情";
    state.drawer.bodyHtml = '<div class="empty-state"><p><em>正在加载详情...</em></p></div>';
    this.renderDrawer();
    try {
      if (type === "theme-result") {
        const detail = await api(`/api/theme-results/${id}`);
        state.drawer.title = `${detail.topic_name} / ${detail.case_no || detail.event_key}`;
        state.drawer.eyebrow = "命中结果";
        state.drawer.bodyHtml = this.renderThemeResultDrawer(detail);
      } else if (type === "theme-sms-log") {
        const detail = await api(`/api/theme-sms-logs/${id}`);
        state.drawer.title = `${detail.topic_name} / ${detail.mobile}`;
        state.drawer.eyebrow = "短信发送记录";
        state.drawer.bodyHtml = this.renderThemeSmsLogDrawer(detail);
      } else if (type === "theme-run") {
        const detail = await api(`/api/theme-runs/${id}`);
        state.drawer.title = detail.run_no;
        state.drawer.eyebrow = "数据源运行";
        state.drawer.bodyHtml = this.renderThemeRunDrawer(detail);
      } else if (type === "task-run") {
        const detail = await api(`/api/task-runs/${id}`);
        state.drawer.title = detail.run_no;
        state.drawer.eyebrow = "自定义任务运行";
        state.drawer.bodyHtml = this.renderTaskRunDrawer(detail);
      } else if (type === "contact") {
        const detail = await api(`/api/contacts/${id}`);
        state.drawer.title = detail.xm || detail.sspcs || `#${detail.id}`;
        state.drawer.eyebrow = "联系人详情";
        state.drawer.bodyHtml = this.renderContactDrawer(detail);
      }
      this.renderDrawer();
    } catch (error) {
      state.drawer.title = "详情加载失败";
      state.drawer.eyebrow = "详情";
      state.drawer.bodyHtml = emptyState(error.message);
      this.renderDrawer();
      this.flash(error.message, true);
    }
  },
  renderDrawer() {
    if (!state.drawer.open) {
      if (dom.drawer.open) {
        dom.drawer.close();
      }
      return;
    }
    dom.drawerTitle.textContent = state.drawer.title;
    dom.drawerEyebrow.textContent = state.drawer.eyebrow;
    dom.drawerBody.innerHTML = `<div class="drawer-content">${state.drawer.bodyHtml}</div>`;
    if (!dom.drawer.open) {
      dom.drawer.showModal();
    }
    this.bindDrawerActions();
  },
  bindDrawerActions() {
    dom.drawerBody.querySelectorAll("[data-action='copy-text']").forEach((button) => {
      button.addEventListener("click", async () => {
        const target = dom.drawerBody.querySelector(button.dataset.target);
        if (!target) {
          return;
        }
        try {
          await navigator.clipboard.writeText(target.textContent || "");
          this.flash("短信内容已复制。");
        } catch (error) {
          this.flash("复制失败，请手动复制。", true);
        }
      });
    });
    dom.drawerBody.querySelectorAll("[data-action='drawer-open-detail']").forEach((button) => {
      button.addEventListener("click", () => {
        this.openDrawer(button.dataset.type, Number(button.dataset.id));
      });
    });
  },
  renderDetailFacts(items) {
    const visibleItems = items.filter((item) => item.value !== undefined && item.value !== null && item.value !== "");
    if (!visibleItems.length) {
      return emptyState("暂无信息。");
    }
    return `
      <div class="fact-grid">
        ${visibleItems.map((item) => `
          <div class="fact-item">
            <strong>${escapeHtml(item.label)}</strong>
            ${item.value}
          </div>
        `).join("")}
      </div>
    `;
  },
  renderDrawerCard({ title, status, meta = [], summary = "", actionHtml = "" }) {
    return `
      <article class="drawer-card">
        <div class="drawer-card__head">
          <h4>${title}</h4>
          ${status || ""}
        </div>
        ${meta.length ? `
          <div class="drawer-card__meta">
            ${meta.map((item) => `
              <div>
                <strong>${escapeHtml(item.label)}</strong>
                ${item.value}
              </div>
            `).join("")}
          </div>
        ` : ""}
        ${summary ? `<div class="drawer-card__summary">${summary}</div>` : ""}
        ${actionHtml ? `<div class="drawer-card__actions">${actionHtml}</div>` : ""}
      </article>
    `;
  },
  renderDrawerCardList(items, emptyText, renderer) {
    if (!items.length) {
      return emptyState(emptyText);
    }
    return `<div class="drawer-card-list">${items.map((item) => renderer(item)).join("")}</div>`;
  },
  renderThemeResultDrawer(detail) {
    const receiverText = escapeHtml((detail.receiver_mobiles || []).join(", ") || "-");
    const matchedRules = escapeHtml((detail.matched_rule_ids || []).join(", ") || "无");
    return `
      <div class="detail-grid">
        <section class="detail-section">
          <h3>基本信息</h3>
          ${this.renderDetailFacts([
            { label: "数据源", value: escapeHtml(detail.source_name || "-") },
            { label: "主题", value: escapeHtml(detail.topic_name || "-") },
            { label: "警情编号", value: escapeHtml(detail.case_no || detail.event_key || "-") },
            { label: "发送状态", value: statusBadge(detail.send_status) },
            { label: "Oracle EID", value: `<span>${escapeHtml(detail.oracle_eid || "-")}</span>` },
            { label: "事件键", value: `<span>${escapeHtml(detail.event_key || "-")}</span>` },
          ])}
        </section>
        <section class="detail-section">
          <h3>接收信息</h3>
          ${this.renderDetailFacts([
            { label: "接收人", value: receiverText },
            { label: "命中规则", value: matchedRules },
            { label: "数据源 ID", value: escapeHtml(String(detail.source_id ?? "-")) },
            { label: "主题 ID", value: escapeHtml(String(detail.topic_id ?? "-")) },
          ])}
        </section>
      </div>
      <div class="detail-grid">
        <section class="detail-section">
          <h3>短信内容</h3>
          ${textBlock(detail.rendered_message || "")}
        </section>
        <section class="detail-section">
          <h3>原始数据</h3>
          ${jsonBlock(detail.raw_result)}
        </section>
      </div>
    `;
  },
  renderThemeSmsLogDrawer(detail) {
    return `
      <div class="detail-grid">
        <section class="detail-section">
          <h3>发送概要</h3>
          ${this.renderDetailFacts([
            { label: "数据源", value: escapeHtml(detail.source_name || "-") },
            { label: "主题", value: escapeHtml(detail.topic_name || "-") },
            { label: "手机号", value: escapeHtml(detail.mobile || "-") },
            { label: "发送状态", value: statusBadge(detail.status) },
            { label: "Oracle EID", value: `<span>${escapeHtml(detail.oracle_eid || "-")}</span>` },
            { label: "命中状态", value: statusBadge(detail.result_send_status || "-") },
          ])}
        </section>
        <section class="detail-section">
          <h3>失败与回执</h3>
          ${this.renderDetailFacts([
            { label: "失败原因", value: escapeHtml(detail.error_message || "-") },
            { label: "平台回执", value: escapeHtml(detail.provider_msg_id || "-") },
            { label: "命中结果 ID", value: escapeHtml(String(detail.topic_result_id ?? "-")) },
            { label: "发送时间", value: escapeHtml(formatTime(detail.created_at)) },
          ])}
        </section>
      </div>
      <div class="detail-grid">
        <section class="detail-section">
          <div class="section-actions">
            <div class="section-actions__copy">
              <h3>短信内容</h3>
              <p>支持复制，便于转发核对。</p>
            </div>
            <div><button class="outline" type="button" data-action="copy-text" data-target="#sms-log-content">复制</button></div>
          </div>
          <pre id="sms-log-content" class="console-pre">${escapeHtml(detail.content || "")}</pre>
        </section>
        <section class="detail-section">
          <div class="section-actions">
            <div class="section-actions__copy">
              <h3>关联命中</h3>
              <p>可以继续追溯到命中结果。</p>
            </div>
            ${detail.topic_result_id ? `<div><button class="outline" type="button" data-action="drawer-open-detail" data-type="theme-result" data-id="${detail.topic_result_id}">命中详情</button></div>` : ""}
          </div>
          ${jsonBlock(detail.raw_result)}
        </section>
      </div>
    `;
  },
  renderThemeRunDrawer(detail) {
    const resultCards = this.renderDrawerCardList(
      (detail.results || []).slice(0, 10),
      "本次运行没有命中结果。",
      (item) => this.renderDrawerCard({
        title: escapeHtml(item.case_no || item.event_key || `#${item.id}`),
        status: statusBadge(item.send_status),
        meta: [
          { label: "接收人", value: escapeHtml((item.receiver_mobiles || []).join(", ") || "-") },
          { label: "Oracle EID", value: `<span>${escapeHtml(item.oracle_eid || "-")}</span>` },
          { label: "规则", value: escapeHtml((item.matched_rule_ids || []).join(", ") || "无") },
        ],
        summary: escapeHtml(truncateText(item.rendered_message || item.content_preview || item.event_key || "无摘要", 160)),
        actionHtml: item.id
          ? `<button class="outline" type="button" data-action="drawer-open-detail" data-type="theme-result" data-id="${item.id}">详情</button>`
          : "",
      })
    );
    const smsCards = this.renderDrawerCardList(
      (detail.sms_logs || []).slice(0, 10),
      "本次运行没有短信日志。",
      (item) => this.renderDrawerCard({
        title: escapeHtml(item.mobile || `#${item.id}`),
        status: statusBadge(item.status),
        meta: [
          { label: "发送时间", value: escapeHtml(formatTime(item.created_at)) },
          { label: "Oracle EID", value: `<span>${escapeHtml(item.oracle_eid || "-")}</span>` },
          { label: "回执", value: escapeHtml(item.provider_msg_id || "-") },
        ],
        summary: escapeHtml(truncateText(item.error_message || item.content_preview || item.content || "无内容", 160)),
        actionHtml: item.id
          ? `<button class="outline" type="button" data-action="drawer-open-detail" data-type="theme-sms-log" data-id="${item.id}">详情</button>`
          : "",
      })
    );

    return `
      <section class="detail-section">
        <h3>运行摘要</h3>
        ${this.renderDetailFacts([
          { label: "运行号", value: `<span>${escapeHtml(detail.run_no)}</span>` },
          { label: "状态", value: statusBadge(detail.status) },
          { label: "抓取数量", value: escapeHtml(String(detail.fetched_count ?? "-")) },
          { label: "命中数量", value: escapeHtml(String(detail.matched_count ?? "-")) },
          { label: "发送数量", value: escapeHtml(String(detail.send_count ?? "-")) },
          { label: "错误信息", value: escapeHtml(detail.error_message || "-") },
        ])}
      </section>
      <section class="detail-section">
        <h3>命中结果（前 10 条）</h3>
        ${resultCards}
      </section>
      <section class="detail-section">
        <h3>短信日志（前 10 条）</h3>
        ${smsCards}
      </section>
    `;
  },
  renderTaskRunDrawer(detail) {
    const syncPayload = (detail.results || [])
      .map((item) => item?.raw_result)
      .find((raw) => raw && typeof raw === "object" && (
        Object.prototype.hasOwnProperty.call(raw, "fetched_record_count")
        || Object.prototype.hasOwnProperty.call(raw, "written_record_count")
        || Object.prototype.hasOwnProperty.call(raw, "target_table")
      )) || null;

    const resultCards = this.renderDrawerCardList(
      (detail.results || []).slice(0, 10),
      "本次运行没有命中结果。",
      (item) => this.renderDrawerCard({
        title: escapeHtml(item.case_no || item.event_key || `#${item.id}`),
        status: statusBadge(item.send_status),
        meta: [
          { label: "接收人", value: escapeHtml((item.receiver_mobiles || []).join(", ") || "-") },
          { label: "事件键", value: `<span>${escapeHtml(item.event_key || "-")}</span>` },
          { label: "结果状态", value: escapeHtml(item.status || "-") },
        ],
        summary: escapeHtml(truncateText(
          item.rendered_message
            || item.raw_result?.message_text
            || item.raw_result?.error_message
            || "无摘要",
          160
        )),
      })
    );
    const smsCards = this.renderDrawerCardList(
      (detail.sms_logs || []).slice(0, 10),
      "本次运行没有短信日志。",
      (item) => this.renderDrawerCard({
        title: escapeHtml(item.mobile || `#${item.id}`),
        status: statusBadge(item.status),
        meta: [
          { label: "发送时间", value: escapeHtml(formatTime(item.created_at)) },
          { label: "回执", value: escapeHtml(item.provider_msg_id || "-") },
          { label: "EID", value: `<span>${escapeHtml(item.oracle_eid || "-")}</span>` },
        ],
        summary: escapeHtml(truncateText(item.error_message || item.content || "无内容", 160)),
      })
    );

    const syncSummaryBlock = syncPayload ? `
      <section class="detail-section">
        <h3>同步摘要</h3>
        ${this.renderDetailFacts([
          { label: "同步状态", value: statusBadge(syncPayload.status || "-") },
          { label: "目标表", value: `<span>${escapeHtml(syncPayload.target_table || "-")}</span>` },
          { label: "抓取数量", value: escapeHtml(String(syncPayload.fetched_record_count ?? "-")) },
          { label: "写入数量", value: escapeHtml(String(syncPayload.written_record_count ?? "-")) },
          { label: "开始时间", value: escapeHtml(formatTime(syncPayload.start_time)) },
          { label: "结束时间", value: escapeHtml(formatTime(syncPayload.end_time)) },
        ])}
        <div class="console-stack">
          <strong>同步说明</strong>
          ${textBlock(syncPayload.message_text || JSON.stringify(syncPayload, null, 2))}
        </div>
      </section>
    ` : "";

    return `
      ${syncSummaryBlock}
      <section class="detail-section">
        <h3>运行摘要</h3>
        ${this.renderDetailFacts([
          { label: "运行号", value: `<span>${escapeHtml(detail.run_no)}</span>` },
          { label: "状态", value: statusBadge(detail.status) },
          { label: "结果数量", value: escapeHtml(String(detail.result_count ?? "-")) },
          { label: "命中数量", value: escapeHtml(String(detail.hit_count ?? "-")) },
          { label: "发送数量", value: escapeHtml(String(detail.send_count ?? "-")) },
          { label: "错误信息", value: escapeHtml(detail.error_message || "-") },
        ])}
      </section>
      <section class="detail-section">
        <h3>命中结果（前 10 条）</h3>
        ${resultCards}
      </section>
      <section class="detail-section">
        <h3>短信日志（前 10 条）</h3>
        ${smsCards}
      </section>
    `;
  },
  renderContactDrawer(detail) {
    const sourceLabel = detail.source_system === "manual_ui"
      ? "手工维护"
      : detail.source_system === "ywdata.b_dxpt_mdjfyj"
        ? "导入联系人"
        : detail.source_system;

    return `
      <section class="detail-section">
        <h3>联系人概况</h3>
        ${this.renderDetailFacts([
          { label: "姓名", value: escapeHtml(detail.xm || "-") },
          { label: "职务", value: escapeHtml(detail.zw || "-") },
          { label: "派出所", value: escapeHtml(detail.sspcs || "-") },
          { label: "派出所代码", value: `<span>${escapeHtml(detail.sspcsdm || "-")}</span>` },
          { label: "县区", value: escapeHtml(detail.xq || "-") },
          { label: "县区代码", value: `<span>${escapeHtml(detail.xqdm || "-")}</span>` },
          { label: "来源", value: escapeHtml(sourceLabel || "-") },
          { label: "状态", value: statusBadge(detail.status) },
          { label: "任务状态", value: escapeHtml(detail.rwzt || "-") },
          { label: "单位层级", value: escapeHtml(detail.unit_level || "-") },
          { label: "创建时间", value: escapeHtml(formatTime(detail.created_at)) },
          { label: "更新时间", value: escapeHtml(formatTime(detail.updated_at)) },
        ])}
      </section>
      <section class="detail-section">
        <h3>手机号</h3>
        ${(detail.phones || []).length
          ? table(
            ["原始号码", "标准手机号", "状态", "主号"],
            detail.phones.map((phone) => [
              escapeHtml(phone.phone_raw || "-"),
              escapeHtml(phone.mobile || "-"),
              statusBadge(phone.status),
              phone.is_primary ? "是" : "否",
            ])
          )
          : emptyState("暂无手机号")}
      </section>
      <section class="detail-section">
        <h3>备注</h3>
        ${textBlock(detail.remark || "")}
      </section>
    `;
  },
});

document.addEventListener("DOMContentLoaded", () => {
  app.init().catch((error) => {
    console.error(error);
    app.flash(error.message || "前端初始化失败。", true);
  });
});
