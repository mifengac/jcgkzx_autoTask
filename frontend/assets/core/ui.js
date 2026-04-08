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
  return `<article><p><em>${escapeHtml(text)}</em></p></article>`;
}

export function statusBadge(status) {
  const value = String(status ?? "");
  const body = escapeHtml(value || "-");
  if (/fail|error/i.test(value)) {
    return `<mark>${body}</mark>`;
  }
  if (/skip|dry|duplicate|partial/i.test(value)) {
    return `<small><strong>${body}</strong></small>`;
  }
  return `<small>${body}</small>`;
}

export function panel(title, subtitle, content, options = {}) {
  const spanMap = {
    4: "span 4",
    5: "span 5",
    7: "span 7",
    8: "span 8",
    12: "span 12",
  };
  const gridStyle = options.span && spanMap[options.span]
    ? ` style="grid-column:${spanMap[options.span]};"`
    : "";
  const actions = options.actions ? `<div>${options.actions}</div>` : "";
  return `
    <article${gridStyle}>
      <header>
        <div>
          <h3>${escapeHtml(title)}</h3>
          ${subtitle ? `<p>${escapeHtml(subtitle)}</p>` : ""}
        </div>
        ${actions}
      </header>
      ${content}
    </article>
  `;
}

export function metricCard(label, value) {
  return `
    <article>
      <small>${escapeHtml(label)}</small>
      <h3>${escapeHtml(value)}</h3>
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
  return `<pre>${escapeHtml(JSON.stringify(value ?? {}, null, 2))}</pre>`;
}

export function textBlock(value) {
  return `<pre>${escapeHtml(value ?? "")}</pre>`;
}

export function table(headers, rows) {
  const headerHtml = headers.map((item) => `<th>${escapeHtml(item)}</th>`).join("");
  const bodyHtml = rows.length
    ? rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")
    : `<tr><td colspan="${headers.length}">${emptyState("暂无数据")}</td></tr>`;
  return `
    <figure>
      <table>
        <thead><tr>${headerHtml}</tr></thead>
        <tbody>${bodyHtml}</tbody>
      </table>
    </figure>
  `;
}
