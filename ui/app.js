(() => {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const urlInput = $("#url");
  const pasteBtn = $("#paste");
  const downloadBtn = $("#download");
  const playlist = $("#playlist");
  const cookiesToggle = $("#cookies");
  const cookieBrowserBlock = $("#cookie-browser-block");
  const qualityBlock = $("#quality-block");
  const progressWrap = $("#progress-wrap");
  const progressTrack = progressWrap.querySelector(".track");
  const progressFill = $("#progress-fill");
  const progressStatus = $("#progress-status");
  const progressPct = $("#progress-pct");
  const progressSub = $("#progress-sub");
  const result = $("#result");
  const resultTitle = $("#result-title");
  const resultPath = $("#result-path");
  const revealBtn = $("#reveal");
  const errorEl = $("#error");
  const errorCopy = $("#error-copy");
  const primaryLabel = downloadBtn.querySelector(".primary-label");

  let mode = "video";
  let resolution = "1080";
  let cookieBrowser = "chrome";
  let isLocal = true;
  let lastPath = "";
  let busy = false;

  function selectIn(scope, btn) {
    scope.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
  }

  const modeButtons = $$(".pill[data-mode]");
  modeButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      modeButtons.forEach((b) => b.setAttribute("aria-selected", "false"));
      selectIn(modeButtons, btn);
      btn.setAttribute("aria-selected", "true");
      mode = btn.dataset.mode;
      qualityBlock.classList.toggle("dimmed", mode === "audio");
    });
  });

  const resButtons = $$("#quality-block .pill[data-res]");
  resButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      selectIn(resButtons, btn);
      resolution = btn.dataset.res;
    });
  });

  const browserButtons = $$("#cookie-browser-block .pill[data-browser]");
  browserButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      selectIn(browserButtons, btn);
      cookieBrowser = btn.dataset.browser;
    });
  });

  function syncCookieUI() {
    cookieBrowserBlock.classList.toggle("dimmed", !cookiesToggle.checked);
  }
  cookiesToggle.addEventListener("change", syncCookieUI);
  syncCookieUI();

  pasteBtn.addEventListener("click", async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        urlInput.value = text.trim();
        urlInput.focus();
      }
    } catch {
      urlInput.focus();
    }
  });

  urlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !busy) startDownload();
  });

  downloadBtn.addEventListener("click", () => {
    if (!busy) startDownload();
  });

  revealBtn.addEventListener("click", async () => {
    if (!isLocal) {
      // Hosted: the file lives on the server, so hand it to the browser.
      if (lastPath) window.location.href = `/api/file?path=${encodeURIComponent(lastPath)}`;
      return;
    }
    try {
      await fetch("/api/reveal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: lastPath || "" }),
      });
    } catch {
      /* ignore */
    }
  });

  function setBusy(on) {
    busy = on;
    downloadBtn.disabled = on;
    primaryLabel.textContent = on ? "Working" : "Download";
  }

  function showError(message) {
    errorCopy.textContent = message;
    errorEl.hidden = false;
  }

  function setIndeterminate(on) {
    progressTrack.classList.toggle("indeterminate", on);
    if (on) progressFill.style.width = "";
  }

  function hideFeedback() {
    result.hidden = true;
    errorEl.hidden = true;
    progressWrap.hidden = true;
    setIndeterminate(true);
    progressPct.textContent = "0%";
    progressSub.textContent = "";
  }

  function formatBytes(n) {
    if (!n || n <= 0) return "";
    const units = ["B", "KB", "MB", "GB"];
    let i = 0;
    let v = n;
    while (v >= 1024 && i < units.length - 1) {
      v /= 1024;
      i += 1;
    }
    return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
  }

  function formatSpeed(bps) {
    if (!bps) return "";
    return `${formatBytes(bps)}/s`;
  }

  async function startDownload() {
    const url = urlInput.value.trim();
    if (!url) {
      urlInput.focus();
      showError("Paste a YouTube link into the field above, then press Download.");
      return;
    }

    hideFeedback();
    setBusy(true);
    progressWrap.hidden = false;
    progressStatus.textContent = "Connecting";

    const body = {
      url,
      mode,
      resolution: mode === "audio" ? "best" : resolution,
      playlist: playlist.checked,
      cookies_from_browser: cookiesToggle.checked ? cookieBrowser : null,
    };

    try {
      const res = await fetch("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || `Request failed (${res.status})`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";

        for (const chunk of parts) {
          const line = chunk.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          const payload = JSON.parse(line.slice(6));
          handleEvent(payload);
        }
      }
    } catch (err) {
      showError(err.message || "The download did not finish. Check the link and try again.");
      progressWrap.hidden = true;
    } finally {
      setBusy(false);
    }
  }

  function handleEvent(ev) {
    if (ev.type === "started") {
      progressStatus.textContent = "Fetching";
      return;
    }

    if (ev.type === "progress") {
      if (ev.status === "downloading") {
        const pct = typeof ev.percent === "number" ? Math.min(100, ev.percent) : null;
        progressStatus.textContent = "Downloading";
        if (pct != null) {
          setIndeterminate(false);
          progressFill.style.width = `${pct}%`;
          progressPct.textContent = `${pct.toFixed(0)}%`;
          progressTrack.setAttribute("aria-valuenow", String(Math.round(pct)));
        } else {
          setIndeterminate(true);
        }
        const bits = [];
        if (ev.speed_label) bits.push(ev.speed_label);
        else if (ev.speed) bits.push(formatSpeed(ev.speed));
        if (ev.eta_label) bits.push(`${ev.eta_label} left`);
        else if (ev.eta != null) bits.push(`${ev.eta}s left`);
        if (ev.downloaded && ev.total) {
          bits.push(`${formatBytes(ev.downloaded)} / ${formatBytes(ev.total)}`);
        }
        progressSub.textContent = bits.join(" · ");
      } else if (ev.status === "processing") {
        setIndeterminate(true);
        progressStatus.textContent = "Preparing";
        progressSub.textContent = "Making it Premiere-ready";
      } else if (ev.status === "finished") {
        setIndeterminate(false);
        progressFill.style.width = "100%";
        progressPct.textContent = "100%";
        progressTrack.setAttribute("aria-valuenow", "100");
        progressStatus.textContent = "Finishing";
        progressSub.textContent = "Processing file";
      }
      return;
    }

    if (ev.type === "done") {
      progressWrap.hidden = true;
      if (ev.ok) {
        result.hidden = false;
        resultTitle.textContent = ev.title || "Saved";
        lastPath = ev.filepath || "";
        const dims = ev.width && ev.height ? ` · ${ev.width}×${ev.height}` : "";
        resultPath.textContent = ev.note ? `Heads up: ${ev.note}` : `${lastPath}${dims}`;
        resultPath.classList.toggle("warn", !!ev.note);
      } else {
        showError(ev.error || "The download did not finish. Check the link and try again.");
      }
    }
  }

  async function loadStatus() {
    try {
      const res = await fetch("/api/status");
      const data = await res.json();
      const ff = $("#pill-ffmpeg");
      const js = $("#pill-js");
      const ver = $("#pill-ytdlp");
      const hint = $("#hd-hint");
      const statusPath = $("#status-path");

      ff.textContent = data.ffmpeg ? "HD ready" : "no ffmpeg";
      ff.classList.add(data.ffmpeg ? "ok" : "warn");

      js.textContent = data.js_runtime ? `${data.js_runtime}` : "no js runtime";
      js.classList.add(data.js_runtime ? "ok" : "warn");

      ver.textContent = `yt-dlp ${data.yt_dlp || "?"}`;

      if (hint) hint.hidden = !!data.ffmpeg;
      isLocal = data.local !== false;
      revealBtn.textContent = isLocal ? "Show" : "Save";
      revealBtn.title = isLocal
        ? "Reveal in Finder"
        : "Download the file to this device";
      if (data.downloads) {
        const pretty = isLocal
          ? data.downloads.replace(/^\/Users\/[^/]+/, "~")
          : "this device";
        if (statusPath) statusPath.textContent = isLocal ? pretty : "Save when ready";
        const actionHint = $("#action-hint");
        if (actionHint) actionHint.textContent = `Saves to ${pretty}`;
      }
    } catch {
      /* ignore */
    }
  }

  loadStatus();
})();
