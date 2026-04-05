export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

export function formatTime(value) {
  return value ? String(value).replace("T", " ").slice(0, 19) : "-";
}

export function truncateText(value, max = 72) {
  const text = String(value ?? "");
  if (text.length <= max) {
    return text;
  }
  return `${text.slice(0, max)}...`;
}

export function emptyState(text) {
  return `<div class="empty-state">${escapeHtml(text)}</div>`;
}

export function statusBadge(status) {
  const value = String(status ?? "");
  const tone = /fail|error/i.test(value)
    ? "failed"
    : /skip|dry|duplicate|partial/i.test(value)
      ? "warning"
      : "";
  return `<span class="status-badge ${tone}">${escapeHtml(value || "-")}</span>`;
}

export function panel(title, subtitle, content, options = {}) {
  const span = options.span ? ` span-${options.span}` : "";
  const actions = options.actions ? `<div>${options.actions}</div>` : "";
  return `
    <section class="panel${span}">
      <div class="panel-header">
        <div>
          <h3>${escapeHtml(title)}</h3>
          ${subtitle ? `<p>${escapeHtml(subtitle)}</p>` : ""}
        </div>
        ${actions}
      </div>
      ${content}
    </section>
  `;
}

export function metricCard(label, value) {
  return `
    <article class="stat-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </article>
  `;
}

export function renderPagination({ total, limit, offset, action }) {
  const start = total === 0 ? 0 : offset + 1;
  const end = Math.min(offset + limit, total);
  const previousDisabled = offset <= 0 ? "disabled" : "";
  const nextDisabled = offset + limit >= total ? "disabled" : "";
  return `
    <div class="pagination">
      <span class="muted">显示 ${start}-${end} / 共 ${total} 条</span>
      <div class="pagination-actions">
        <button class="small-button" type="button" data-action="${action}" data-direction="prev" ${previousDisabled}>上一页</button>
        <button class="small-button" type="button" data-action="${action}" data-direction="next" ${nextDisabled}>下一页</button>
      </div>
    </div>
  `;
}

export function optionList(items, getLabel, selectedValue, placeholder = "请选择") {
  const options = [`<option value="">${escapeHtml(placeholder)}</option>`];
  for (const item of items) {
    const value = String(item.id);
    const selected = String(selectedValue ?? "") === value ? "selected" : "";
    options.push(`<option value="${value}" ${selected}>${escapeHtml(getLabel(item))}</option>`);
  }
  return options.join("");
}

export function jsonBlock(value) {
  return `<pre class="json-block">${escapeHtml(JSON.stringify(value ?? {}, null, 2))}</pre>`;
}

export function textBlock(value) {
  return `<pre class="text-block">${escapeHtml(value ?? "")}</pre>`;
}

export function table(headers, rows) {
  const headerHtml = headers.map((item) => `<th>${escapeHtml(item)}</th>`).join("");
  const bodyHtml = rows.length
    ? rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")
    : `<tr><td colspan="${headers.length}">${emptyState("暂无数据")}</td></tr>`;
  return `
    <div class="table-wrap">
      <table>
        <thead><tr>${headerHtml}</tr></thead>
        <tbody>${bodyHtml}</tbody>
      </table>
    </div>
  `;
}
