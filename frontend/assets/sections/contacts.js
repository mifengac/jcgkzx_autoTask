import { api, jsonRequest } from "../core/api.js";
import { emptyState, escapeHtml, formatTime, metricCard, panel, statusBadge, table } from "../core/ui.js";

function contactDisplayName(contact) {
  return contact?.xm || contact?.sspcs || `#${contact?.id || "-"}`;
}

function sourceLabel(sourceSystem) {
  if (sourceSystem === "manual_ui") {
    return "手工维护";
  }
  if (sourceSystem === "ywdata.b_dxpt_mdjfyj") {
    return "导入联系人";
  }
  return sourceSystem || "-";
}

function isReadOnlyContact(contact) {
  return Boolean(contact && contact.source_system !== "manual_ui");
}

function getEditingContact(app) {
  return app.state.contactDetail;
}

function renderDirectorySummary(app) {
  const items = app.state.contactDirectory.items || [];
  const manualCount = items.filter((item) => item.source_system === "manual_ui").length;
  const importedCount = items.filter((item) => item.source_system !== "manual_ui").length;
  const activeCount = items.filter((item) => item.status === "active").length;
  return `
    <div class="stat-grid">
      ${metricCard("当前列表", items.length)}
      ${metricCard("手工联系人", manualCount)}
      ${metricCard("导入联系人", importedCount)}
      ${metricCard("启用联系人", activeCount)}
    </div>
    <div class="banner" style="margin-top:12px;">
      联系人主数据统一写入 org_contact / org_contact_phone。导入联系人只读，手工联系人来源标记为 manual_ui。
    </div>
  `;
}

function renderDirectoryFilters(app) {
  const query = app.state.contactDirectory.query;
  return `
    <form id="contact-directory-filter-form" class="form-stack">
      <div class="filter-grid">
        <div class="field-block">
          <label for="contact_dir_keyword">关键字</label>
          <input id="contact_dir_keyword" name="keyword" type="text" value="${escapeHtml(query.keyword || "")}">
        </div>
        <div class="field-block">
          <label for="contact_dir_sspcsdm">sspcsdm</label>
          <input id="contact_dir_sspcsdm" name="sspcsdm" type="text" value="${escapeHtml(query.sspcsdm || "")}">
        </div>
        <div class="field-block">
          <label for="contact_dir_xqdm">xqdm</label>
          <input id="contact_dir_xqdm" name="xqdm" type="text" value="${escapeHtml(query.xqdm || "")}">
        </div>
        <div class="field-block">
          <label for="contact_dir_rwzt">任务状态</label>
          <input id="contact_dir_rwzt" name="rwzt" type="text" value="${escapeHtml(query.rwzt || "")}">
        </div>
        <div class="field-block">
          <label for="contact_dir_mobile">手机号</label>
          <input id="contact_dir_mobile" name="mobile" type="text" value="${escapeHtml(query.mobile || "")}">
        </div>
        <div class="field-block">
          <label for="contact_dir_unit_level">单位层级</label>
          <select id="contact_dir_unit_level" name="unit_level">
            <option value="" ${!query.unit_level ? "selected" : ""}>全部</option>
            <option value="city" ${query.unit_level === "city" ? "selected" : ""}>市级</option>
            <option value="county" ${query.unit_level === "county" ? "selected" : ""}>县级</option>
            <option value="station" ${query.unit_level === "station" ? "selected" : ""}>派出所</option>
            <option value="unknown" ${query.unit_level === "unknown" ? "selected" : ""}>未知</option>
          </select>
        </div>
        <div class="field-block">
          <label for="contact_dir_source_system">来源</label>
          <select id="contact_dir_source_system" name="source_system">
            <option value="" ${!query.source_system ? "selected" : ""}>全部</option>
            <option value="manual_ui" ${query.source_system === "manual_ui" ? "selected" : ""}>手工维护</option>
            <option value="ywdata.b_dxpt_mdjfyj" ${query.source_system === "ywdata.b_dxpt_mdjfyj" ? "selected" : ""}>导入联系人</option>
          </select>
        </div>
        <div class="field-block">
          <label for="contact_dir_status">状态</label>
          <select id="contact_dir_status" name="status">
            <option value="all" ${query.status === "all" ? "selected" : ""}>全部</option>
            <option value="active" ${query.status === "active" ? "selected" : ""}>启用</option>
            <option value="inactive" ${query.status === "inactive" ? "selected" : ""}>停用</option>
          </select>
        </div>
      </div>
      <div class="inline-actions">
        <button class="button" type="submit">查询联系人</button>
        <button class="button button-secondary" type="button" data-action="contact-directory-reset">重置筛选</button>
        <button class="button button-ghost" type="button" data-action="contact-create">新建联系人</button>
      </div>
    </form>
  `;
}

function renderDirectoryTable(app) {
  const items = app.state.contactDirectory.items || [];
  if (!items.length) {
    return emptyState("当前筛选条件下没有联系人。");
  }

  return table(
    ["姓名", "职务", "派出所", "县区", "任务状态", "手机号", "来源", "状态", "更新时间", "操作"],
    items.map((item) => {
      const readonly = isReadOnlyContact(item);
      const actionButtons = [
        `<button class="small-button" type="button" data-action="contact-view" data-id="${item.id}">查看</button>`,
        `<button class="small-button" type="button" data-action="contact-edit" data-id="${item.id}" ${readonly ? "disabled" : ""}>编辑</button>`,
        `<button class="small-button ${item.status === "active" ? "warn" : ""}" type="button" data-action="contact-toggle-status" data-status="${item.status === "active" ? "inactive" : "active"}" data-id="${item.id}" ${readonly ? "disabled" : ""}>${item.status === "active" ? "停用" : "启用"}</button>`,
      ].join(" ");
      return [
        `<strong>${escapeHtml(contactDisplayName(item))}</strong>`,
        escapeHtml(item.zw || "-"),
        escapeHtml(item.sspcs || "-"),
        escapeHtml(item.xq || "-"),
        escapeHtml(item.rwzt || "-"),
        escapeHtml((item.phones || []).map((phone) => phone.mobile).join(", ") || "-"),
        `${escapeHtml(sourceLabel(item.source_system))}${readonly ? '<br><span class="muted">导入只读</span>' : ""}`,
        statusBadge(item.status),
        escapeHtml(formatTime(item.updated_at)),
        actionButtons,
      ];
    })
  );
}

function renderPhoneRow(phone, index, readonly) {
  const disabled = readonly ? "disabled" : "";
  return `
    <div class="phone-row" data-phone-row>
      <div class="phone-row-grid">
        <div class="field-block">
          <label>原始号码</label>
          <input name="phone_raw" type="text" value="${escapeHtml(phone.phone_raw || "")}" ${disabled}>
        </div>
        <div class="field-block">
          <label>状态</label>
          <select name="phone_status" ${disabled}>
            <option value="active" ${phone.status === "active" ? "selected" : ""}>启用</option>
            <option value="inactive" ${phone.status === "inactive" ? "selected" : ""}>停用</option>
          </select>
        </div>
        <div class="field-block">
          <label>主号</label>
          <label class="checkbox">
            <input type="radio" name="primary_phone_index" value="${index}" ${phone.is_primary ? "checked" : ""} ${disabled}>
            <span>设为主号</span>
          </label>
        </div>
        ${readonly ? "" : `<div class="field-block"><label>操作</label><button class="small-button danger" type="button" data-action="contact-phone-remove">移除号码</button></div>`}
      </div>
    </div>
  `;
}

function renderEditor(app) {
  const contact = getEditingContact(app);
  const readonly = isReadOnlyContact(contact);
  const disabled = readonly ? "disabled" : "";
  const statusValue = contact?.status || "active";
  const unitLevel = contact?.unit_level || "unknown";
  const phones = (contact?.phones?.length ? contact.phones : [{ phone_raw: "", status: "active", is_primary: true }]);

  return `
    <div class="banner">
      ${contact
        ? `当前联系人: ${escapeHtml(contactDisplayName(contact))} / ${escapeHtml(sourceLabel(contact.source_system))}${readonly ? " / 导入只读" : ""}`
        : "创建手工联系人，保存后会写入 source_system=manual_ui。"}
    </div>
    ${readonly ? `<div class="banner readonly-note">该联系人来自导入数据源，只能查看，不能在此页面修改。</div>` : ""}
    <form id="contact-editor-form" class="form-stack">
      <div class="form-grid two">
        <div class="field-block">
          <label for="contact_xm">姓名</label>
          <input id="contact_xm" name="xm" type="text" value="${escapeHtml(contact?.xm || "")}" ${disabled}>
        </div>
        <div class="field-block">
          <label for="contact_zw">职务</label>
          <input id="contact_zw" name="zw" type="text" value="${escapeHtml(contact?.zw || "")}" ${disabled}>
        </div>
      </div>
      <div class="form-grid three">
        <div class="field-block">
          <label for="contact_rwzt">任务状态</label>
          <input id="contact_rwzt" name="rwzt" type="text" value="${escapeHtml(contact?.rwzt || "")}" ${disabled}>
        </div>
        <div class="field-block">
          <label for="contact_status">联系人状态</label>
          <select id="contact_status" name="status" ${disabled}>
            <option value="active" ${statusValue === "active" ? "selected" : ""}>启用</option>
            <option value="inactive" ${statusValue === "inactive" ? "selected" : ""}>停用</option>
          </select>
        </div>
        <div class="field-block">
          <label for="contact_unit_level">单位层级</label>
          <select id="contact_unit_level" name="unit_level" ${disabled}>
            <option value="city" ${unitLevel === "city" ? "selected" : ""}>市级</option>
            <option value="county" ${unitLevel === "county" ? "selected" : ""}>县级</option>
            <option value="station" ${unitLevel === "station" ? "selected" : ""}>派出所</option>
            <option value="unknown" ${unitLevel === "unknown" ? "selected" : ""}>未知</option>
          </select>
        </div>
      </div>
      <div class="form-grid two">
        <div class="field-block">
          <label for="contact_sspcs">派出所</label>
          <input id="contact_sspcs" name="sspcs" type="text" value="${escapeHtml(contact?.sspcs || "")}" ${disabled}>
        </div>
        <div class="field-block">
          <label for="contact_sspcsdm">派出所代码</label>
          <input id="contact_sspcsdm" name="sspcsdm" type="text" value="${escapeHtml(contact?.sspcsdm || "")}" ${disabled}>
        </div>
      </div>
      <div class="form-grid two">
        <div class="field-block">
          <label for="contact_xq">县区</label>
          <input id="contact_xq" name="xq" type="text" value="${escapeHtml(contact?.xq || "")}" ${disabled}>
        </div>
        <div class="field-block">
          <label for="contact_xqdm">县区代码</label>
          <input id="contact_xqdm" name="xqdm" type="text" value="${escapeHtml(contact?.xqdm || "")}" ${disabled}>
        </div>
      </div>
      <div class="form-grid two">
        <div class="field-block">
          <label for="contact_county_code">county_code</label>
          <input id="contact_county_code" name="county_code" type="text" value="${escapeHtml(contact?.county_code || "")}" ${disabled}>
        </div>
        <div class="field-block">
          <label for="contact_city_code">city_code</label>
          <input id="contact_city_code" name="city_code" type="text" value="${escapeHtml(contact?.city_code || "")}" ${disabled}>
        </div>
      </div>
      <div class="field-block">
        <label for="contact_remark">备注</label>
        <textarea id="contact_remark" name="remark" rows="4" ${disabled}>${escapeHtml(contact?.remark || "")}</textarea>
      </div>
      <div class="detail-block">
        <div class="panel-header" style="margin-bottom:12px;">
          <div>
            <h3>手机号</h3>
            <p>支持多个手机号，后端会自动规范化并确保只有一个主号。</p>
          </div>
          ${readonly ? "" : `<div><button class="small-button" type="button" data-action="contact-phone-add">新增号码</button></div>`}
        </div>
        <div id="contact-phone-list" class="phone-list">
          ${phones.map((phone, index) => renderPhoneRow(phone, index, readonly)).join("")}
        </div>
      </div>
      <div class="inline-actions">
        ${readonly ? "" : `<button class="button" type="submit">${contact ? "保存联系人" : "创建联系人"}</button>`}
        <button class="button button-secondary" type="button" data-action="contact-create">新建联系人</button>
        <button class="button button-ghost" type="button" data-action="contact-directory-open">返回目录</button>
      </div>
    </form>
  `;
}

function collectPhonePayload(form) {
  const selectedPrimary = Number(form.querySelector("input[name='primary_phone_index']:checked")?.value ?? -1);
  return [...form.querySelectorAll("[data-phone-row]")]
    .map((row, index) => ({
      phone_raw: row.querySelector("[name='phone_raw']")?.value || "",
      status: row.querySelector("[name='phone_status']")?.value || "active",
      is_primary: index === selectedPrimary,
    }))
    .filter((item) => String(item.phone_raw || "").trim());
}

function reindexPhoneRows(container) {
  [...container.querySelectorAll("[data-phone-row]")].forEach((row, index) => {
    const radio = row.querySelector("input[type='radio'][name='primary_phone_index']");
    if (radio) {
      radio.value = String(index);
    }
  });
}

function appendPhoneRow(container) {
  const index = container.querySelectorAll("[data-phone-row]").length;
  container.insertAdjacentHTML("beforeend", renderPhoneRow({
    phone_raw: "",
    status: "active",
    is_primary: index === 0,
  }, index, false));
  reindexPhoneRows(container);
}

export const contactsSection = {
  key: "contacts",
  label: "联系人管理",
  description: "集中维护短信联系人主数据，导入联系人只读，手工联系人可直接配置并供规则复用。",
  tabs: [
    { key: "directory", label: "联系人目录", hint: "筛选、查看、启停联系人" },
    { key: "editor", label: "联系人编辑", hint: "维护手工联系人和手机号" },
  ],
  async load(app) {
    if (app.state.route.secondary === "editor") {
      if (app.state.editingContactId) {
        await app.loadContactDetail(app.state.editingContactId);
      } else {
        app.state.contactDetail = null;
      }
      return;
    }
    await app.loadContactDirectory();
  },
  render(app) {
    if (app.state.route.secondary === "editor") {
      return `
        <div class="content-grid">
          ${panel("联系人编辑", "手工联系人支持创建和更新，导入联系人仅支持查看。", renderEditor(app), { span: 12 })}
        </div>
      `;
    }

    return `
      <div class="content-grid">
        ${panel("联系人概况", "联系人目录只负责主数据管理，任务规则页保留轻量只读查询。", renderDirectorySummary(app), { span: 4 })}
        ${panel("联系人目录", "支持按来源、状态、单位代码和手机号筛选。", `${renderDirectoryFilters(app)}<div style="margin-top:16px;">${renderDirectoryTable(app)}</div>`, { span: 8 })}
      </div>
    `;
  },
  bind(app) {
    const filterForm = document.querySelector("#contact-directory-filter-form");
    if (filterForm) {
      filterForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const payload = new FormData(filterForm);
        try {
          await app.loadContactDirectory({
            keyword: payload.get("keyword") || "",
            sspcsdm: payload.get("sspcsdm") || "",
            xqdm: payload.get("xqdm") || "",
            rwzt: payload.get("rwzt") || "",
            unit_level: payload.get("unit_level") || "",
            source_system: payload.get("source_system") || "",
            status: payload.get("status") || "all",
            mobile: payload.get("mobile") || "",
            limit: app.state.contactDirectory.query.limit || 100,
          });
          app.render();
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    }

    document.querySelectorAll("[data-action='contact-directory-reset']").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          await app.loadContactDirectory({
            keyword: "",
            sspcsdm: "",
            xqdm: "",
            rwzt: "",
            unit_level: "",
            source_system: "",
            status: "all",
            mobile: "",
            limit: 100,
          });
          app.flash("联系人筛选已重置。");
          app.render();
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    });

    document.querySelectorAll("[data-action='contact-create']").forEach((button) => {
      button.addEventListener("click", () => {
        app.state.editingContactId = null;
        app.state.contactDetail = null;
        app.navigate("contacts", "editor");
      });
    });

    document.querySelectorAll("[data-action='contact-directory-open']").forEach((button) => {
      button.addEventListener("click", () => {
        app.navigate("contacts", "directory");
      });
    });

    document.querySelectorAll("[data-action='contact-view']").forEach((button) => {
      button.addEventListener("click", () => {
        app.openDrawer("contact", Number(button.dataset.id));
      });
    });

    document.querySelectorAll("[data-action='contact-edit']").forEach((button) => {
      button.addEventListener("click", async () => {
        if (button.disabled) {
          return;
        }
        try {
          app.state.editingContactId = Number(button.dataset.id);
          await app.loadContactDetail(app.state.editingContactId);
          app.navigate("contacts", "editor");
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    });

    document.querySelectorAll("[data-action='contact-toggle-status']").forEach((button) => {
      button.addEventListener("click", async () => {
        if (button.disabled) {
          return;
        }
        try {
          await api(
            `/api/contacts/${button.dataset.id}`,
            jsonRequest("PUT", { status: button.dataset.status })
          );
          await app.loadContactDirectory();
          if (app.state.editingContactId === Number(button.dataset.id)) {
            await app.loadContactDetail(app.state.editingContactId);
          }
          app.flash(`联系人已${button.dataset.status === "active" ? "启用" : "停用"}。`);
          app.render();
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    });

    const editorForm = document.querySelector("#contact-editor-form");
    if (editorForm && !isReadOnlyContact(app.state.contactDetail)) {
      editorForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
          const payload = new FormData(editorForm);
          const body = {
            xm: payload.get("xm") || null,
            zw: payload.get("zw") || null,
            rwzt: payload.get("rwzt") || null,
            xq: payload.get("xq") || null,
            xqdm: payload.get("xqdm") || null,
            sspcs: payload.get("sspcs") || null,
            sspcsdm: payload.get("sspcsdm") || null,
            county_code: payload.get("county_code") || null,
            city_code: payload.get("city_code") || null,
            unit_level: payload.get("unit_level") || "unknown",
            status: payload.get("status") || "active",
            remark: payload.get("remark") || "",
            phones: collectPhonePayload(editorForm),
          };
          if (app.state.editingContactId) {
            await api(`/api/contacts/${app.state.editingContactId}`, jsonRequest("PUT", body));
            app.flash("联系人已更新。");
          } else {
            const created = await api("/api/contacts", jsonRequest("POST", body));
            app.state.editingContactId = created.id;
            app.flash("联系人已创建。");
          }
          await app.loadContactDirectory();
          if (app.state.editingContactId) {
            await app.loadContactDetail(app.state.editingContactId);
          }
          app.render();
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    }

    const phoneList = document.querySelector("#contact-phone-list");
    if (phoneList && !isReadOnlyContact(app.state.contactDetail)) {
      document.querySelectorAll("[data-action='contact-phone-add']").forEach((button) => {
        button.addEventListener("click", () => {
          appendPhoneRow(phoneList);
        });
      });
      phoneList.addEventListener("click", (event) => {
        const button = event.target.closest("[data-action='contact-phone-remove']");
        if (!button) {
          return;
        }
        button.closest("[data-phone-row]")?.remove();
        reindexPhoneRows(phoneList);
      });
    }
  },
};
