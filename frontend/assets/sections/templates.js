import { api, jsonRequest, parseJson } from "../core/api.js";
import { emptyState, escapeHtml, optionList, panel, statusBadge, textBlock, truncateText } from "../core/ui.js";

function getEditingTemplate(app) {
  return app.state.templates.find((item) => item.id === app.state.editingTemplateId) || null;
}

function renderTemplatePreview(form) {
  const content = String(form.get("template_content") || "");
  const variables = parseJson(form.get("render_example"), {});
  return content.replaceAll(/\{([^}]+)\}/g, (_match, key) => {
    const value = variables[key.trim()];
    return value === undefined || value === null ? "" : String(value);
  });
}

function renderTemplateList(app) {
  if (!app.state.templates.length) {
    return emptyState("暂无短信模板。");
  }

  const cards = app.state.templates.map((template) => `
    <article class="card-item ${app.state.editingTemplateId === template.id ? "active" : ""}">
      <div class="card-head">
        <div>
          <h4>${escapeHtml(template.template_name)}</h4>
          <div class="card-meta">编码: <span class="mono">${escapeHtml(template.template_code)}</span></div>
        </div>
        ${statusBadge(template.enabled ? "启用" : "停用")}
      </div>
      <div class="card-meta">${escapeHtml(truncateText(template.template_content, 120))}</div>
      <div class="card-actions">
        <button class="small-button" type="button" data-action="template-edit" data-id="${template.id}">编辑模板</button>
      </div>
    </article>
  `).join("");

  return `<div class="card-list">${cards}</div>`;
}

function renderTemplateEditor(app) {
  const template = getEditingTemplate(app);
  const preview = template ? escapeHtml(template.render_example || "") : "{}";
  return `
    <form id="template-form" class="form-stack">
      <div class="form-grid two">
        <div class="field-block">
          <label for="template_name">模板名称</label>
          <input id="template_name" name="template_name" type="text" value="${escapeHtml(template?.template_name || "")}" required>
        </div>
        <div class="field-block">
          <label for="template_code">模板编码</label>
          <input id="template_code" name="template_code" type="text" value="${escapeHtml(template?.template_code || "")}" required>
        </div>
      </div>
      <div class="field-block">
        <label for="template_content">模板内容</label>
        <textarea id="template_content" name="template_content" rows="7" required>${escapeHtml(template?.template_content || "")}</textarea>
      </div>
      <div class="field-block">
        <label for="render_example">变量预览 JSON</label>
        <textarea id="render_example" name="render_example" rows="5">${preview}</textarea>
      </div>
      <div class="checkbox-row">
        <label class="checkbox"><input name="enabled" type="checkbox" ${template?.enabled ?? true ? "checked" : ""}><span>启用模板</span></label>
      </div>
      <div class="inline-actions">
        <button class="button" type="submit">${template ? "更新模板" : "创建模板"}</button>
        <button class="button button-secondary" type="button" data-action="template-reset">新建模板</button>
        <button class="button button-ghost" type="button" data-action="template-preview">本地预览</button>
      </div>
    </form>
    <div id="template-preview-box" class="detail-block">
      <h3>模板预览</h3>
      ${textBlock(template?.template_content || "点击“本地预览”查看渲染效果。")}
    </div>
  `;
}

export const templatesSection = {
  key: "templates",
  label: "短信模板",
  description: "管理模板内容、变量预览和模板测试，不再和主题或规则混排。",
  tabs: [
    { key: "list", label: "模板列表", hint: "查看现有模板" },
    { key: "editor", label: "模板编辑", hint: "编辑与预览" },
  ],
  async load(app) {
    await app.reloadTemplates();
  },
  render(app) {
    const tab = app.state.route.secondary;
    if (tab === "editor") {
      return `
        <div class="content-grid">
          ${panel("模板编辑与预览", "创建、更新模板，并即时验证变量渲染。", renderTemplateEditor(app), { span: 12 })}
        </div>
      `;
    }

    return `
      <div class="content-grid">
        ${panel("模板总览", "所有短信模板都在这里集中管理。", renderTemplateList(app), { span: 12 })}
      </div>
    `;
  },
  bind(app) {
    const form = document.querySelector("#template-form");
    if (form) {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
          const payload = new FormData(form);
          const requestBody = {
            template_name: payload.get("template_name"),
            template_code: payload.get("template_code"),
            template_content: payload.get("template_content"),
            render_example: payload.get("render_example") || "",
            enabled: payload.get("enabled") === "on",
          };
          if (app.state.editingTemplateId) {
            await api(`/api/message-templates/${app.state.editingTemplateId}`, jsonRequest("PUT", requestBody));
            app.flash("短信模板已更新。");
          } else {
            await api("/api/message-templates", jsonRequest("POST", requestBody));
            app.flash("短信模板已创建。");
          }
          app.state.editingTemplateId = null;
          await app.reloadTemplates();
          app.render();
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    }

    document.querySelectorAll("[data-action='template-edit']").forEach((button) => {
      button.addEventListener("click", () => {
        app.state.editingTemplateId = Number(button.dataset.id);
        app.navigate("templates", "editor");
      });
    });

    document.querySelectorAll("[data-action='template-reset']").forEach((button) => {
      button.addEventListener("click", () => {
        app.state.editingTemplateId = null;
        app.render();
      });
    });

    document.querySelectorAll("[data-action='template-preview']").forEach((button) => {
      button.addEventListener("click", () => {
        try {
          const formData = new FormData(document.querySelector("#template-form"));
          const preview = renderTemplatePreview(formData);
          document.querySelector("#template-preview-box").innerHTML = `<h3>模板预览</h3>${textBlock(preview)}`;
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    });
  },
};
