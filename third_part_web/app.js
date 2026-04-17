const STORAGE_KEYS = {
  settings: "third_part_web.settings",
  candidates: "third_part_web.candidates",
};

const settingsFormEls = {
  baseUrl: document.getElementById("base-url"),
  authMode: document.getElementById("auth-mode"),
  apiKey: document.getElementById("api-key"),
  clientId: document.getElementById("client-id"),
  status: document.getElementById("settings-status"),
};

const candidateEls = {
  form: document.getElementById("candidate-form"),
  name: document.getElementById("candidate-name"),
  email: document.getElementById("candidate-email"),
  phone: document.getElementById("candidate-phone"),
  whatsapp: document.getElementById("candidate-whatsapp"),
  list: document.getElementById("candidate-list"),
  count: document.getElementById("candidate-count"),
  recipientList: document.getElementById("send-candidate-list"),
  selectAll: document.getElementById("select-all-candidates"),
  selectedCount: document.getElementById("selected-count"),
};

const sendEls = {
  form: document.getElementById("send-form"),
  message: document.getElementById("message-content"),
  response: document.getElementById("response-output"),
};

const authFields = Array.from(document.querySelectorAll(".auth-field"));

const DEFAULT_SETTINGS = {
  baseUrl: "http://127.0.0.1:8000/api/v1/integration",
  authMode: "apiKey",
  apiKey: "",
  clientId: "1",
};

let envSettingsCache = {};

function readJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function loadSettings() {
  return mergeSettings(DEFAULT_SETTINGS, envSettingsCache, readJson(STORAGE_KEYS.settings, {}));
}

function loadCandidates() {
  return readJson(STORAGE_KEYS.candidates, []).map((candidate) => ({
    id: candidate.id,
    name: candidate.name || "",
    email: candidate.email || "",
    phone: candidate.phone || "",
    whatsapp: candidate.whatsapp || "",
  }));
}

function saveSettings() {
  const payload = {
    baseUrl: settingsFormEls.baseUrl.value.trim(),
    authMode: settingsFormEls.authMode.value,
    apiKey: settingsFormEls.apiKey.value.trim(),
    clientId: settingsFormEls.clientId.value.trim(),
  };
  writeJson(STORAGE_KEYS.settings, payload);
  settingsFormEls.status.textContent = "Settings saved in this browser.";
}

function saveCandidates(candidates) {
  writeJson(STORAGE_KEYS.candidates, candidates);
}

function updateAuthModeVisibility() {
  const mode = settingsFormEls.authMode.value;
  authFields.forEach((field) => {
    field.classList.toggle("hidden", field.dataset.mode !== mode);
  });
}

function renderCandidates() {
  const candidates = loadCandidates();
  candidateEls.count.textContent = `${candidates.length} saved`;

  if (!candidates.length) {
    candidateEls.list.className = "candidate-list empty-state";
    candidateEls.list.textContent = "No candidates added yet.";
    candidateEls.recipientList.className = "recipient-list empty-state";
    candidateEls.recipientList.textContent = "No candidates added yet.";
    candidateEls.selectAll.checked = false;
    candidateEls.selectAll.disabled = true;
    candidateEls.selectedCount.textContent = "0 selected";
    return;
  }

  candidateEls.list.className = "candidate-list";
  candidateEls.list.innerHTML = candidates
    .map((candidate) => {
      return `
        <article class="candidate-card">
          <strong>${escapeHtml(candidate.name)}</strong>
          <div class="candidate-meta">
            <div>Email: ${escapeHtml(candidate.email)}</div>
            <div>Phone: ${escapeHtml(candidate.phone || "-")}</div>
            <div>WhatsApp: ${escapeHtml(candidate.whatsapp || "-")}</div>
          </div>
          <div class="candidate-chip">
            <span>local contact only</span>
            <button class="candidate-remove" type="button" data-candidate-id="${candidate.id}">Remove</button>
          </div>
        </article>
      `;
    })
    .join("");

  candidateEls.recipientList.className = "recipient-list";
  candidateEls.recipientList.innerHTML = candidates
    .map(
      (candidate) => `
        <label class="recipient-option">
          <input class="recipient-checkbox" type="checkbox" value="${candidate.id}" />
          <span class="recipient-copy">
            <strong>${escapeHtml(candidate.name)}</strong>
            <small>${escapeHtml(candidate.email || "No email")} | ${escapeHtml(candidate.phone || candidate.whatsapp || "No phone/WhatsApp")}</small>
          </span>
        </label>
      `
    )
    .join("");
  candidateEls.selectAll.disabled = false;

  candidateEls.list.querySelectorAll(".candidate-remove").forEach((button) => {
    button.addEventListener("click", () => {
      const updated = loadCandidates().filter((item) => item.id !== button.dataset.candidateId);
      saveCandidates(updated);
      renderCandidates();
    });
  });

  candidateEls.recipientList.querySelectorAll(".recipient-checkbox").forEach((checkbox) => {
    checkbox.addEventListener("change", syncSelectionUi);
  });

  syncSelectionUi();
}

function addCandidate(event) {
  event.preventDefault();
  const candidates = loadCandidates();
  const candidate = {
    id: crypto.randomUUID(),
    name: candidateEls.name.value.trim(),
    email: candidateEls.email.value.trim().toLowerCase(),
    phone: candidateEls.phone.value.trim(),
    whatsapp: candidateEls.whatsapp.value.trim(),
  };

  const next = [candidate, ...candidates.filter((item) => item.email !== candidate.email)];
  saveCandidates(next);
  candidateEls.form.reset();
  renderCandidates();
}

function clearCandidates() {
  saveCandidates([]);
  renderCandidates();
}

function resolveHeaders(settings) {
  const headers = {
    "Content-Type": "application/json",
  };

  if (settings.authMode === "apiKey") {
    if (!settings.apiKey) {
      throw new Error("API key is required in API Key mode.");
    }
    headers.Authorization = `Bearer ${settings.apiKey}`;
  } else {
    if (!settings.clientId) {
      throw new Error("Client Id is required in Dev Client Id mode.");
    }
    headers["X-Client-Id"] = settings.clientId;
  }

  return headers;
}

function buildPayload(candidate) {
  const payload = {
    message: sendEls.message.value.trim(),
  };

  if (!payload.message) {
    throw new Error("Message content is required.");
  }

  payload.to = {
    email: candidate.email || undefined,
    phone: candidate.phone || undefined,
    whatsapp_number: candidate.whatsapp || undefined,
  };

  return payload;
}

function getSelectedCandidateIds() {
  return Array.from(candidateEls.recipientList.querySelectorAll(".recipient-checkbox:checked")).map(
    (checkbox) => checkbox.value
  );
}

function syncSelectionUi() {
  const checkboxes = Array.from(candidateEls.recipientList.querySelectorAll(".recipient-checkbox"));
  const selectedCount = checkboxes.filter((checkbox) => checkbox.checked).length;

  candidateEls.selectedCount.textContent = `${selectedCount} selected`;

  if (!checkboxes.length) {
    candidateEls.selectAll.checked = false;
    candidateEls.selectAll.indeterminate = false;
    return;
  }

  candidateEls.selectAll.checked = selectedCount === checkboxes.length;
  candidateEls.selectAll.indeterminate = selectedCount > 0 && selectedCount < checkboxes.length;
}

async function sendMessage(event) {
  event.preventDefault();
  const settings = loadSettings();
  const candidates = loadCandidates();
  const selectedIds = new Set(getSelectedCandidateIds());
  const selectedCandidates = candidates.filter((item) => selectedIds.has(item.id));

  if (!selectedCandidates.length) {
    throwOutput("Please select at least one saved candidate first.");
    return;
  }

  try {
    const headers = resolveHeaders(settings);
    throwOutput(`Sending request to ${selectedCandidates.length} candidate(s)...`);

    const results = [];

    for (const candidate of selectedCandidates) {
      const payload = buildPayload(candidate);
      const response = await fetch(`${settings.baseUrl}/trigger`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      });

      const text = await response.text();
      let parsed;

      try {
        parsed = text ? JSON.parse(text) : {};
      } catch {
        parsed = { raw: text };
      }

      if (!response.ok) {
        results.push({
          candidate: candidate.name,
          status: "error",
          detail: parsed.detail || parsed.message || `Request failed with ${response.status}`,
        });
        continue;
      }

      results.push({
        candidate: candidate.name,
        status: "sent",
        detail: parsed,
      });
    }

    const successCount = results.filter((result) => result.status === "sent").length;
    const failedCount = results.length - successCount;

    throwOutput(
      JSON.stringify(
        {
          summary: {
            selected: selectedCandidates.length,
            sent: successCount,
            failed: failedCount,
          },
          results,
        },
        null,
        2
      )
    );
  } catch (error) {
    throwOutput(JSON.stringify({ error: error.message || "Unknown error" }, null, 2));
  }
}

function throwOutput(message) {
  sendEls.response.textContent = message;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function parseEnvText(raw) {
  const env = {};

  raw.split(/\r?\n/).forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      return;
    }

    const separatorIndex = trimmed.indexOf("=");
    if (separatorIndex === -1) {
      return;
    }

    const key = trimmed.slice(0, separatorIndex).trim();
    const value = trimmed.slice(separatorIndex + 1).trim();

    if (key) {
      env[key] = value;
    }
  });

  return env;
}

async function loadEnvSettings() {
  try {
    const response = await fetch("./.env", { cache: "no-store" });
    if (!response.ok) {
      return {};
    }

    const env = parseEnvText(await response.text());
    return {
      baseUrl: env.INTEGRATION_BASE_URL || env.BASE_URL || "",
      authMode: env.AUTH_MODE || "",
      apiKey: env.API_KEY || "",
      clientId: env.CLIENT_ID || "",
    };
  } catch {
    return {};
  }
}

function mergeSettings(...sources) {
  return sources.reduce((merged, source) => {
    Object.entries(source || {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        merged[key] = value;
      }
    });
    return merged;
  }, {});
}

async function boot() {
  envSettingsCache = await loadEnvSettings();
  const settings = loadSettings();
  settingsFormEls.baseUrl.value = settings.baseUrl;
  settingsFormEls.authMode.value = settings.authMode;
  settingsFormEls.apiKey.value = settings.apiKey;
  settingsFormEls.clientId.value = settings.clientId;
  updateAuthModeVisibility();
  renderCandidates();

  if (envSettingsCache.apiKey) {
    settingsFormEls.status.textContent =
      "API settings loaded from .env. Browser-saved values will still take priority when present.";
  }

  document.getElementById("save-settings").addEventListener("click", saveSettings);
  settingsFormEls.authMode.addEventListener("change", updateAuthModeVisibility);
  candidateEls.form.addEventListener("submit", addCandidate);
  document.getElementById("clear-candidates").addEventListener("click", clearCandidates);
  candidateEls.selectAll.addEventListener("change", () => {
    candidateEls.recipientList.querySelectorAll(".recipient-checkbox").forEach((checkbox) => {
      checkbox.checked = candidateEls.selectAll.checked;
    });
    syncSelectionUi();
  });
  sendEls.form.addEventListener("submit", sendMessage);
}

boot();
