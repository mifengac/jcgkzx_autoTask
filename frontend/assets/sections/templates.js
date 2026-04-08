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
    <article>
      <div>
        <div>
          <h4>${escapeHtml(template.template_name)}</h4>
          <div>编码: <span>${escapeHtml(template.template_code)}</span></div>
        </div>
        ${statusBadge(template.enabled ? "启用" : "停用")}
      </div>
      <div>${escapeHtml(truncateText(template.template_content, 120))}</div>
      <div role="group">
        <button class="outline" type="button" data-action="template-edit" data-id="${template.id}">编辑模板</button>
      </div>
    </article>
  `).join("");

  return `<div>${cards}</div>`;
}

function renderTemplateEditor(app) {
  const template = getEditingTemplate(app);
  const preview = template ? escapeHtml(template.render_example || "") : "{}";
  return `
    <form id="template-form">
      <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));">
        <div>
          <label for="template_name">模板名称</label>
          <input id="template_name" name="template_name" type="text" value="${escapeHtml(template?.template_name || "")}" required>
        </div>
        <div>
          <label for="template_code">模板编码</label>
          <input id="template_code" name="template_code" type="text" value="${escapeHtml(template?.template_code || "")}" required>
        </div>
      </div>
      <div>
        <label for="template_content">模板内容</label>
        <textarea id="template_content" name="template_content" rows="7" required>${escapeHtml(template?.template_content || "")}</textarea>
      </div>
      <div>
        <label for="render_example">变量预览 JSON</label>
        <textarea id="render_example" name="render_example" rows="5">${preview}</textarea>
      </div>
      <div>
        <label><input name="enabled" type="checkbox" ${template?.enabled ?? true ? "checked" : ""}><span>启用模板</span></label>
      </div>
      <div role="group">
        <button type="submit">${template ? "更新模板" : "创建模板"}</button>
        <button class="secondary" type="button" data-action="template-reset">新建模板</button>
        <button class="outline" type="button" data-action="template-preview">本地预览</button>
      </div>
    </form>
    <div id="template-preview-box">
      <h3>模板预览</h3>
      ${textBlock(template?.template_content || "点击“本地预览”查看渲染效果。")}
    </div>
  `;
}

export const templatesSection = {
  key: "templates",
  label: "短信模板",
  description: "管理短信模板。",
  tabs: [
    { key: "list", label: "模板列表", hint: "查看模板" },
    { key: "editor", label: "模板编辑", hint: "编辑预览" },
  ],
  async load(app) {
    await app.reloadTemplates();
  },
  render(app) {
    const tab = app.state.route.secondary;
    if (tab === "editor") {
      return `
        <div class="grid" style="grid-template-columns: repeat(12, minmax(0, 1fr)); align-items:start;">
          ${panel("模板编辑与预览", "编辑并预览。", renderTemplateEditor(app), { span: 12 })}
        </div>
      `;
    }

    return `
      <div class="grid" style="grid-template-columns: repeat(12, minmax(0, 1fr)); align-items:start;">
        ${panel("模板总览", "统一管理模板。", renderTemplateList(app), { span: 12 })}
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
