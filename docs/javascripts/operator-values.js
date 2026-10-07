/* Local, non-secret tutorial values. No requests, cookies, or URL parameters. */
(() => {
  "use strict";
  const fields = {
    SERVER_IP: { en: "VPS IPv4", ru: "IPv4 VPS", valid: v => /^(\d{1,3}\.){3}\d{1,3}$/.test(v) && v.split(".").every(n => Number(n) <= 255) },
    ADMIN_USER: { en: "Administrator username", ru: "Имя администратора", valid: v => /^[a-z_][a-z0-9_-]{0,31}$/.test(v) && v !== "root" },
    COOLIFY_DOMAIN: { en: "Coolify domain", ru: "Домен Coolify", valid: domain },
    APP_DOMAIN: { en: "Application domain", ru: "Домен приложения", valid: domain },
    GITHUB_OWNER: { en: "GitHub owner", ru: "Владелец GitHub", valid: v => /^[a-zA-Z0-9][a-zA-Z0-9-]{0,38}$/.test(v) },
    APPLICATION_REPOSITORY_URL: { en: "Application repository URL", ru: "URL репозитория приложения", valid: v => /^(?:https:\/\/github\.com\/|git@github\.com:)[A-Za-z0-9-]+\/[A-Za-z0-9_.-]+$/.test(v) }
  };
  function domain(v) {
    return v.length <= 253 && v.includes(".") && v.split(".").every(s => /^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$/.test(s));
  }
  function validated(values) {
    return Object.fromEntries(Object.entries(values).filter(([key, v]) => fields[key] && typeof v === "string" && fields[key].valid(v)));
  }
  function render(text, supplied) {
    const values = validated(supplied);
    // Replace input statements with quoted assignments. Validation excludes shell syntax.
    for (const [key, value] of Object.entries(values)) {
      const input = new RegExp("^(\\s*)(?:printf '%s' '[^'\\n]*'; read -r|read -r -p '[^'\\n]*') " + key + "$", "gm");
      text = text.replace(input, (_, indent) => `${indent}${key}='${value}'`);
      const psNames = { SERVER_IP: "ServerIp", ADMIN_USER: "AdminUser", APPLICATION_REPOSITORY_URL: "ApplicationRepositoryUrl" };
      if (psNames[key]) {
        const psInput = new RegExp("^(\\s*)\\$" + psNames[key] + " = Read-Host '[^'\\n]*'$", "gmi");
        text = text.replace(psInput, (_, indent) => `${indent}$${psNames[key]} = '${value}'`);
      }
      text = text.replaceAll(`YOUR_${key}`, value);
    }
    const replacements = { "coolify.example.com": values.COOLIFY_DOMAIN, "app.example.com": values.APP_DOMAIN, "YOUR_GITHUB_OWNER": values.GITHUB_OWNER, "<github-owner>": values.GITHUB_OWNER };
    for (const [placeholder, value] of Object.entries(replacements)) {
      if (value) text = text.replaceAll(placeholder, value);
    }
    return text;
  }
  if (typeof module !== "undefined") module.exports = { render, validated };
  if (typeof document === "undefined") return;
  const key = "solo-vps-operator-values-v1";
  let values = {};
  try { values = validated(JSON.parse(sessionStorage.getItem(key) || "{}")); } catch { /* unavailable storage stays in memory */ }
  const originals = new WeakMap();
  function setup() {
    const article = document.querySelector(".md-content__inner");
    if (!article || article.querySelector(".solo-operator-values")) return;
    const ru = document.documentElement.lang.startsWith("ru");
    const panel = document.createElement("details");
    panel.className = "solo-operator-values";
    const title = document.createElement("summary");
    title.textContent = ru ? "Ваши значения для команд" : "Your values for commands";
    panel.append(title);
    const note = document.createElement("p");
    note.textContent = ru ? "Данные остаются в этой вкладке и никуда не отправляются. Не вводите секреты. Без заполнения работают исходные примеры. Команды выполняйте там, где указано в инструкции." : "Values stay in this tab and are never sent. Do not enter secrets. Empty fields keep the original examples. Run each command where the guide specifies.";
    panel.append(note);
    const inputs = new Map();
    const update = () => {
      try { sessionStorage.setItem(key, JSON.stringify(values)); } catch { /* in-memory fallback */ }
      article.querySelectorAll("code").forEach(code => {
        if (!originals.has(code)) originals.set(code, code.cloneNode(true));
        const original = originals.get(code);
        const changed = render(original.textContent, values);
        // Keep syntax highlighting when a block has no substitutions.
        if (changed === original.textContent) code.replaceChildren(...Array.from(original.cloneNode(true).childNodes));
        else code.textContent = changed;
      });
    };
    for (const [name, field] of Object.entries(fields)) {
      const label = document.createElement("label");
      label.textContent = ru ? field.ru : field.en;
      const input = document.createElement("input");
      input.type = "text";
      input.autocomplete = "off";
      input.spellcheck = false;
      input.value = values[name] || "";
      input.addEventListener("input", () => {
        const value = input.value.trim();
        const ok = !value || field.valid(value);
        input.setCustomValidity(ok ? "" : (ru ? "Проверьте формат значения" : "Check the value format"));
        input.setAttribute("aria-invalid", String(!ok));
        if (value && ok) values[name] = value;
        else delete values[name];
        update();
      });
      label.append(input);
      panel.append(label);
      inputs.set(name, input);
    }
    const reset = document.createElement("button");
    reset.type = "button";
    reset.textContent = ru ? "Очистить значения" : "Clear values";
    reset.addEventListener("click", () => {
      values = {};
      for (const input of inputs.values()) { input.value = ""; input.setCustomValidity(""); input.setAttribute("aria-invalid", "false"); }
      update();
      try { sessionStorage.removeItem(key); } catch { /* storage unavailable */ }
    });
    panel.append(reset);
    const heading = article.querySelector("h1");
    if (heading) heading.after(panel); else article.prepend(panel);
    update();
  }
  document.addEventListener("DOMContentLoaded", setup);
  if (typeof document$ !== "undefined") document$.subscribe(setup);
})();
