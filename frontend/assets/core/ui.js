export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

export function formatTime(value) {
  if (!value) {
    return "-";
  }

  const text = String(value).trim();
  if (!text) {
    return "-";
  }

  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(text)) {
    return text;
  }

  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) {
    return text.replace("T", " ").slice(0, 19);
  }

  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(parsed);
}

export function truncateText(value, max = 72) {
  const text = String(value ?? "");
  if (text.length <= max) {
    return text;
  }
  return `${text.slice(0, max)}...`;
}

export function emptyState(text) {
  return `
    <div class="empty-state">
      <p><em>${escapeHtml(text)}</em></p>
    </div>
  `;
}

export function statusBadge(status) {
  const value = String(status ?? "");
  const body = escapeHtml(value || "-");
  let modifier = "";

  if (/(fail|error|invalid|exception|失败|异常|错误|停用)/i.test(value)) {
    modifier = " status-badge--danger";
  } else if (/(skip|dry|duplicate|partial|pending|演练|跳过|重复|等待)/i.test(value)) {
    modifier = " status-badge--warning";
  } else if (/(success|ok|sent|done|enabled|normal|成功|完成|启用|正常|已发送)/i.test(value)) {
    modifier = " status-badge--success";
  }

  return `<span class="status-badge${modifier}">${body}</span>`;
}

export function panel(title, subtitle, content, options = {}) {
  const classes = ["surface-card", "panel-card"];
  if (options.span) {
    classes.push(`panel-card--span-${options.span}`);
  }
  if (options.variant === "dark") {
    classes.push("surface-card--dark", "panel-card--dark");
  }
  if (options.className) {
    classes.push(options.className);
  }

  const actions = options.actions ? `<div class="panel-card__actions">${options.actions}</div>` : "";

  return `
    <article class="${classes.join(" ")}">
      <header class="panel-card__header">
        <div class="panel-card__heading">
          <h3>${escapeHtml(title)}</h3>
          ${subtitle ? `<p class="panel-card__subtitle">${escapeHtml(subtitle)}</p>` : ""}
        </div>
        ${actions}
      </header>
      <div class="panel-card__body">
        ${content}
      </div>
    </article>
  `;
}

export function metricCard(label, value, meta = "") {
  return `
    <article class="metric-card">
      <span class="metric-card__label">${escapeHtml(label)}</span>
      <strong class="metric-card__value">${escapeHtml(value)}</strong>
      ${meta ? `<span class="metric-card__meta">${escapeHtml(meta)}</span>` : ""}
    </article>
  `;
}

export function renderPagination({ total, limit, offset, action }) {
  const start = total === 0 ? 0 : offset + 1;
  const end = Math.min(offset + limit, total);
  const previousDisabled = offset <= 0 ? "disabled" : "";
  const nextDisabled = offset + limit >= total ? "disabled" : "";
  return `
    <nav aria-label="pagination">
      <ul>
        <li><small>显示 ${start}-${end} / 共 ${total} 条</small></li>
      </ul>
      <ul>
        <li><button type="button" data-action="${action}" data-direction="prev" ${previousDisabled}>上一页</button></li>
        <li><button type="button" data-action="${action}" data-direction="next" ${nextDisabled}>下一页</button></li>
      </ul>
    </nav>
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
  return `<pre class="console-pre">${escapeHtml(JSON.stringify(value ?? {}, null, 2))}</pre>`;
}

export function textBlock(value) {
  return `<pre class="console-pre">${escapeHtml(value ?? "")}</pre>`;
}

export function table(headers, rows) {
  const headerHtml = headers.map((item) => `<th>${escapeHtml(item)}</th>`).join("");
  const bodyHtml = rows.length
    ? rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")
    : `<tr><td colspan="${headers.length}">${emptyState("暂无数据")}</td></tr>`;
  return `
    <div class="console-table-wrap">
      <table class="console-table">
        <thead><tr>${headerHtml}</tr></thead>
        <tbody>${bodyHtml}</tbody>
      </table>
    </div>
  `;
}
