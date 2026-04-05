import { api } from "./core/api.js";
import { emptyState, escapeHtml, formatTime, jsonBlock, statusBadge, textBlock } from "./core/ui.js";
import { overviewSection } from "./sections/overview.js";
import { resultsSection } from "./sections/results.js";
import { runsSection } from "./sections/runs.js";
import { smsLogsSection } from "./sections/smsLogs.js";
import { sourcesSection } from "./sections/sources.js";
import { tasksSection } from "./sections/tasks.js";
import { templatesSection } from "./sections/templates.js";
import { topicsSection } from "./sections/topics.js";

const sections = [
  overviewSection,
  sourcesSection,
  topicsSection,
  templatesSection,
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
  cacheDom() {
    dom.primaryNav = document.querySelector("#primary-nav");
    dom.secondaryNav = document.querySelector("#secondary-nav");
    dom.secondaryTitle = document.querySelector("#secondary-title");
    dom.sectionHeader = document.querySelector("#section-header");
    dom.contentArea = document.querySelector("#content-area");
    dom.flash = document.querySelector("#flash");
    dom.healthPill = document.querySelector("#health-pill");
    dom.drawer = document.querySelector("#detail-drawer");
    dom.drawerBackdrop = document.querySelector("#drawer-backdrop");
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
    dom.drawerBackdrop.addEventListener("click", () => this.closeDrawer());
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
      if (!state.selectedTopicId && topics[0]) {
        state.selectedTopicId = topics[0].id;
      }
      if (state.selectedTopicId && !topics.some((item) => item.id === state.selectedTopicId)) {
        state.selectedTopicId = topics[0]?.id || null;
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
    dom.healthPill.className = `health-pill ${state.healthOk === null ? "" : state.healthOk ? "ok" : "bad"}`;

    dom.primaryNav.innerHTML = sections.map((section) => `
      <button class="nav-chip ${state.route.primary === section.key ? "active" : ""}" type="button" data-primary="${section.key}">
        <strong>${escapeHtml(section.label)}</strong>
        <span>${escapeHtml(section.description)}</span>
      </button>
    `).join("");
    dom.primaryNav.querySelectorAll("[data-primary]").forEach((button) => {
      button.addEventListener("click", () => {
        this.navigate(button.dataset.primary, getDefaultTab(button.dataset.primary));
      });
    });

    const section = sectionMap[state.route.primary];
    dom.secondaryTitle.textContent = section.label;
    dom.secondaryNav.innerHTML = section.tabs.map((tab) => `
      <button class="subnav-link ${state.route.secondary === tab.key ? "active" : ""}" type="button" data-secondary="${tab.key}">
        <strong>${escapeHtml(tab.label)}</strong>
        <span>${escapeHtml(tab.hint)}</span>
      </button>
    `).join("");
    dom.secondaryNav.querySelectorAll("[data-secondary]").forEach((button) => {
      button.addEventListener("click", () => {
        this.navigate(state.route.primary, button.dataset.secondary);
      });
    });

    const metaPills = [];
    if (state.selectedSourceId && state.route.primary !== "sources") {
      metaPills.push(`<span class="meta-pill">当前数据源: ${escapeHtml(this.getCurrentSource()?.source_name || `#${state.selectedSourceId}`)}</span>`);
    }
    if (state.selectedTopicId && state.route.primary !== "topics") {
      metaPills.push(`<span class="meta-pill">当前主题: ${escapeHtml(this.getCurrentTopic()?.theme_name || `#${state.selectedTopicId}`)}</span>`);
    }
    if (state.selectedTaskId && state.route.primary !== "tasks") {
      metaPills.push(`<span class="meta-pill">当前任务: ${escapeHtml(this.getCurrentTask()?.task_name || `#${state.selectedTaskId}`)}</span>`);
    }
    dom.sectionHeader.innerHTML = `
      <div>
        <h2>${escapeHtml(section.label)}</h2>
        <p>${escapeHtml(section.description)}</p>
      </div>
      <div class="meta">${metaPills.join("")}</div>
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
      dom.flash.classList.add("hidden");
      return;
    }
    dom.flash.textContent = String(message);
    dom.flash.className = `flash ${isError ? "error" : ""}`;
    window.clearTimeout(this.flashTimer);
    this.flashTimer = window.setTimeout(() => {
      dom.flash.classList.add("hidden");
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
    state.drawer.bodyHtml = '<div class="detail-block">正在加载详情...</div>';
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
      }
      this.renderDrawer();
    } catch (error) {
      state.drawer.title = "详情加载失败";
      state.drawer.eyebrow = "详情";
      state.drawer.bodyHtml = `<div class="detail-block">${escapeHtml(error.message)}</div>`;
      this.renderDrawer();
      this.flash(error.message, true);
    }
  },
  renderDrawer() {
    if (!state.drawer.open) {
      dom.drawer.classList.add("hidden");
      dom.drawerBackdrop.classList.add("hidden");
      dom.drawer.setAttribute("aria-hidden", "true");
      return;
    }
    dom.drawerTitle.textContent = state.drawer.title;
    dom.drawerEyebrow.textContent = state.drawer.eyebrow;
    dom.drawerBody.innerHTML = state.drawer.bodyHtml;
    dom.drawer.classList.remove("hidden");
    dom.drawerBackdrop.classList.remove("hidden");
    dom.drawer.setAttribute("aria-hidden", "false");
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
  renderThemeResultDrawer(detail) {
    return `
      <div class="detail-block">
        <h3>基本信息</h3>
        <div class="detail-grid two">
          <div class="detail-item"><strong>数据源</strong>${escapeHtml(detail.source_name)}</div>
          <div class="detail-item"><strong>主题</strong>${escapeHtml(detail.topic_name)}</div>
          <div class="detail-item"><strong>警情编号</strong>${escapeHtml(detail.case_no || "-")}</div>
          <div class="detail-item"><strong>发送状态</strong>${statusBadge(detail.send_status)}</div>
          <div class="detail-item"><strong>Oracle EID</strong><span class="mono">${escapeHtml(detail.oracle_eid || "-")}</span></div>
          <div class="detail-item"><strong>接收人</strong>${escapeHtml(detail.receiver_mobiles.join(", ") || "-")}</div>
        </div>
      </div>
      <div class="detail-block">
        <h3>短信内容</h3>
        ${textBlock(detail.rendered_message || "")}
      </div>
      <div class="detail-block">
        <h3>命中规则</h3>
        ${textBlock((detail.matched_rule_ids || []).join(", ") || "无")}
      </div>
      <div class="detail-block">
        <h3>原始数据</h3>
        ${jsonBlock(detail.raw_result)}
      </div>
    `;
  },
  renderThemeSmsLogDrawer(detail) {
    return `
      <div class="detail-block">
        <h3>发送概要</h3>
        <div class="detail-grid two">
          <div class="detail-item"><strong>数据源</strong>${escapeHtml(detail.source_name)}</div>
          <div class="detail-item"><strong>主题</strong>${escapeHtml(detail.topic_name)}</div>
          <div class="detail-item"><strong>手机号</strong>${escapeHtml(detail.mobile)}</div>
          <div class="detail-item"><strong>发送状态</strong>${statusBadge(detail.status)}</div>
          <div class="detail-item"><strong>Oracle EID</strong><span class="mono">${escapeHtml(detail.oracle_eid || "-")}</span></div>
          <div class="detail-item"><strong>关联命中状态</strong>${statusBadge(detail.result_send_status || "-")}</div>
        </div>
      </div>
      <div class="detail-block">
        <div class="panel-header" style="margin-bottom:12px;">
          <div><h3>短信内容</h3><p>支持复制后外部复核。</p></div>
          <div><button class="small-button" type="button" data-action="copy-text" data-target="#sms-log-content">复制短信内容</button></div>
        </div>
        <pre id="sms-log-content" class="text-block">${escapeHtml(detail.content || "")}</pre>
      </div>
      <div class="detail-block">
        <h3>失败原因 / 回执</h3>
        <div class="detail-grid two">
          <div class="detail-item"><strong>失败原因</strong>${escapeHtml(detail.error_message || "-")}</div>
          <div class="detail-item"><strong>平台回执</strong>${escapeHtml(detail.provider_msg_id || "-")}</div>
        </div>
      </div>
      <div class="detail-block">
        <div class="panel-header" style="margin-bottom:12px;">
          <div><h3>关联命中数据</h3><p>这里可以继续追到原始命中记录。</p></div>
          ${detail.topic_result_id ? `<div><button class="small-button" type="button" data-action="drawer-open-detail" data-type="theme-result" data-id="${detail.topic_result_id}">查看命中详情</button></div>` : ""}
        </div>
        ${jsonBlock(detail.raw_result)}
      </div>
    `;
  },
  renderThemeRunDrawer(detail) {
    const resultRows = (detail.results || []).slice(0, 10).map((item) => `
      <tr>
        <td>${escapeHtml(item.case_no || item.event_key)}</td>
        <td>${statusBadge(item.send_status)}</td>
        <td>${escapeHtml((item.receiver_mobiles || []).join(", ") || "-")}</td>
        <td><button class="small-button" type="button" data-action="drawer-open-detail" data-type="theme-result" data-id="${item.id}">查看详情</button></td>
      </tr>
    `).join("");
    const smsRows = (detail.sms_logs || []).slice(0, 10).map((item) => `
      <tr>
        <td>${formatTime(item.created_at)}</td>
        <td>${escapeHtml(item.mobile)}</td>
        <td>${statusBadge(item.status)}</td>
        <td><button class="small-button" type="button" data-action="drawer-open-detail" data-type="theme-sms-log" data-id="${item.id}">查看详情</button></td>
      </tr>
    `).join("");
    return `
      <div class="detail-block">
        <h3>运行摘要</h3>
        <div class="detail-grid two">
          <div class="detail-item"><strong>运行号</strong><span class="mono">${escapeHtml(detail.run_no)}</span></div>
          <div class="detail-item"><strong>状态</strong>${statusBadge(detail.status)}</div>
          <div class="detail-item"><strong>抓取数量</strong>${detail.fetched_count}</div>
          <div class="detail-item"><strong>命中数量</strong>${detail.matched_count}</div>
          <div class="detail-item"><strong>发送数量</strong>${detail.send_count}</div>
          <div class="detail-item"><strong>错误信息</strong>${escapeHtml(detail.error_message || "-")}</div>
        </div>
      </div>
      <div class="detail-block">
        <h3>命中结果（前 10 条）</h3>
        ${(detail.results || []).length ? `<div class="table-wrap"><table><thead><tr><th>警情</th><th>状态</th><th>接收人</th><th>操作</th></tr></thead><tbody>${resultRows}</tbody></table></div>` : emptyState("本次运行没有命中结果。")}
      </div>
      <div class="detail-block">
        <h3>短信日志（前 10 条）</h3>
        ${(detail.sms_logs || []).length ? `<div class="table-wrap"><table><thead><tr><th>时间</th><th>手机号</th><th>状态</th><th>操作</th></tr></thead><tbody>${smsRows}</tbody></table></div>` : emptyState("本次运行没有短信日志。")}
      </div>
    `;
  },
  renderTaskRunDrawer(detail) {
    const resultRows = (detail.results || []).slice(0, 10).map((item) => `
      <tr>
        <td>${escapeHtml(item.event_key)}</td>
        <td>${statusBadge(item.send_status)}</td>
        <td>${escapeHtml((item.receiver_mobiles || []).join(", ") || "-")}</td>
      </tr>
    `).join("");
    const smsRows = (detail.sms_logs || []).slice(0, 10).map((item) => `
      <tr>
        <td>${formatTime(item.created_at)}</td>
        <td>${escapeHtml(item.mobile)}</td>
        <td>${statusBadge(item.status)}</td>
      </tr>
    `).join("");
    return `
      <div class="detail-block">
        <h3>运行摘要</h3>
        <div class="detail-grid two">
          <div class="detail-item"><strong>运行号</strong><span class="mono">${escapeHtml(detail.run_no)}</span></div>
          <div class="detail-item"><strong>状态</strong>${statusBadge(detail.status)}</div>
          <div class="detail-item"><strong>结果数量</strong>${detail.result_count}</div>
          <div class="detail-item"><strong>命中数量</strong>${detail.hit_count}</div>
          <div class="detail-item"><strong>发送数量</strong>${detail.send_count}</div>
          <div class="detail-item"><strong>错误信息</strong>${escapeHtml(detail.error_message || "-")}</div>
        </div>
      </div>
      <div class="detail-block">
        <h3>命中结果（前 10 条）</h3>
        ${(detail.results || []).length ? `<div class="table-wrap"><table><thead><tr><th>事件键</th><th>状态</th><th>接收人</th></tr></thead><tbody>${resultRows}</tbody></table></div>` : emptyState("本次运行没有命中结果。")}
      </div>
      <div class="detail-block">
        <h3>短信日志（前 10 条）</h3>
        ${(detail.sms_logs || []).length ? `<div class="table-wrap"><table><thead><tr><th>时间</th><th>手机号</th><th>状态</th></tr></thead><tbody>${smsRows}</tbody></table></div>` : emptyState("本次运行没有短信日志。")}
      </div>
    `;
  },
};

document.addEventListener("DOMContentLoaded", () => {
  app.init().catch((error) => {
    console.error(error);
    app.flash(error.message || "前端初始化失败。", true);
  });
});
