async function tryRedirectIfLoggedIn() {
  const response = await fetch("/api/auth/me", {
    method: "GET",
    credentials: "same-origin",
  });
  if (response.ok) {
    window.location.href = "/";
  }
}

function setMessage(text) {
  const message = document.querySelector("#login-message");
  if (!text) {
    message.textContent = "";
    message.hidden = true;
    return;
  }
  message.textContent = text;
  message.hidden = false;
}

async function submitLogin(form) {
  const submitButton = document.querySelector("#login-submit");
  const payload = {
    username: form.username.value.trim(),
    password: form.password.value,
  };
  submitButton.disabled = true;
  submitButton.textContent = "登录中...";
  setMessage("");
  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const text = await response.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch (_error) {
        data = null;
      }
    }
    if (!response.ok) {
      throw new Error(data?.detail || `登录失败: ${response.status}`);
    }
    window.location.href = "/";
  } catch (error) {
    setMessage(error.message || "登录失败，请稍后重试。");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "登录平台";
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  await tryRedirectIfLoggedIn();
  const form = document.querySelector("#login-form");
  document.querySelector("#username")?.focus();
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitLogin(form);
  });
});
