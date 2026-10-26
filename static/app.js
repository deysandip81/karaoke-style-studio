const $ = (id) => document.getElementById(id);
const state = { file: null, jobId: null, caps: null, timer: null, stems: [] };

fetch("/api/capabilities").then(r => r.json()).then(c => {
  state.caps = c;
  if (!c.demucs) {
    $("backend").value = "ffmpeg";
    $("backendNote").textContent = "Demucs not installed yet — Studio engine unavailable.";
  }
  $("preset").innerHTML = c.presets.map(p => `<option value="${p.key}">${p.label}</option>`).join("");
  $("preset").value = "soft_acoustic";
  updatePresetDesc();
  syncBackend();
});

function syncBackend() {
  const demucs = $("backend").value === "demucs";
  $("model").disabled = !demucs;
  $("backendNote").textContent = demucs
    ? "Studio: 4-stem ML separation — full style control. ~1–3 min/song on Apple silicon."
    : "Fast: 2-stem ffmpeg trick — only instrumental/vocals balance, no drums/bass/other control.";
}
$("backend").addEventListener("change", syncBackend);

function updatePresetDesc() {
  const p = state.caps.presets.find(x => x.key === $("preset").value);
  $("presetDesc").textContent = p ? p.description : "";
  $("customTone").classList.toggle("hidden", $("preset").value !== "custom");
  renderStemSliders(p ? p.gains : {});
}
$("preset").addEventListener("change", updatePresetDesc);

["toneWarmth", "toneBrightness", "toneReverb", "tonePunch"].forEach(id => {
  $(id).addEventListener("input", () => { $(id + "Val").textContent = $(id).value; });
});
$("tempo").addEventListener("input", () => { $("tempoVal").textContent = $("tempo").value + "%"; });
$("semitones").addEventListener("input", () => {
  const v = parseInt($("semitones").value, 10);
  $("semitonesVal").textContent = (v > 0 ? "+" : "") + v + " st";
});

// ---------- file selection ----------
const drop = $("drop");
$("browse").addEventListener("click", (e) => { e.stopPropagation(); $("file").click(); });
drop.addEventListener("click", () => $("file").click());
$("file").addEventListener("change", (e) => pick(e.target.files[0]));
["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("hover"); }));
["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("hover"); }));
drop.addEventListener("drop", (e) => { if (e.dataTransfer.files.length) pick(e.dataTransfer.files[0]); });

function pick(f) {
  if (!f) return;
  state.file = f;
  $("fileName").textContent = `${f.name} · ${(f.size / 1048576).toFixed(1)} MB`;
  $("go").disabled = false;
}

// ---------- separate ----------
$("go").addEventListener("click", async () => {
  if (!state.file) return;
  $("go").disabled = true;
  $("results").innerHTML = "";
  $("studio").classList.add("hidden");
  $("errorPanel").classList.add("hidden");
  $("progressPanel").classList.remove("hidden");
  setProgress(0, "Uploading");

  try {
    const res = await fetch("/api/upload", {
      method: "POST",
      headers: {
        "X-Filename": encodeURIComponent(state.file.name),
        "X-Backend": $("backend").value,
        "X-Model": $("model").value,
        "Content-Type": "application/octet-stream",
      },
      body: state.file,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "upload failed");
    state.jobId = data.id;
    state.timer = setInterval(poll, 900);
  } catch (err) { fail(err.message); }
});

function setProgress(pct, stage) {
  $("fill").style.width = pct + "%";
  $("pct").textContent = Math.round(pct) + "%";
  $("stage").textContent = stage;
}

async function poll() {
  const res = await fetch("/api/job/" + state.jobId);
  const job = await res.json();
  if (!res.ok) return fail(job.error || "job lost");

  setProgress(job.progress, job.stage);
  const bits = [];
  if (job.duration) bits.push(job.duration + " s of audio");
  bits.push(job.backend === "demucs" ? "Demucs " + job.model : "ffmpeg mid/side");
  bits.push(job.elapsed + " s elapsed");
  $("meta").textContent = bits.join(" · ");

  if (job.status === "done") {
    clearInterval(state.timer);
    state.stems = job.stem_list;
    $("progressPanel").classList.add("hidden");
    $("studio").classList.remove("hidden");
    updatePresetDesc();
    $("go").disabled = false;
  } else if (job.status === "error") {
    clearInterval(state.timer);
    fail(job.error);
  }
}

function fail(msg) {
  clearInterval(state.timer);
  $("progressPanel").classList.add("hidden");
  const p = $("errorPanel");
  p.textContent = "Failed: " + msg;
  p.classList.remove("hidden");
  $("go").disabled = false;
}

// ---------- stem sliders ----------
const STEM_META = {
  drums: "Drums", bass: "Bass", other: "Other (guitars, keys, pads)", vocals: "Vocals",
};

function renderStemSliders(defaultGains) {
  const available = state.stems.map(s => s.key).filter(k => k in STEM_META);
  const keys = available.length ? available : ["no_vocals"];
  $("stemSliders").innerHTML = keys.map(k => {
    const pct = Math.round((defaultGains[k] ?? (k === "vocals" ? 0 : 1)) * 100);
    return `
      <div class="slider-row">
        <label>${STEM_META[k] || k}</label>
        <input type="range" min="0" max="150" value="${pct}" id="gain_${k}">
        <span id="gain_${k}_val">${pct}%</span>
      </div>`;
  }).join("");
  keys.forEach(k => {
    $(`gain_${k}`).addEventListener("input", () => {
      $(`gain_${k}_val`).textContent = $(`gain_${k}`).value + "%";
    });
  });
}

// ---------- render ----------
$("renderBtn").addEventListener("click", async () => {
  $("renderBtn").disabled = true;
  $("renderNote").textContent = "Rendering...";
  const keys = state.stems.map(s => s.key).filter(k => k in STEM_META);
  const gains = {};
  (keys.length ? keys : ["no_vocals"]).forEach(k => {
    const el = $(`gain_${k}`);
    if (el) gains[k] = parseInt(el.value, 10) / 100;
  });

  const body = {
    preset: $("preset").value,
    gains,
    tempo: parseInt($("tempo").value, 10) / 100,
    semitones: parseInt($("semitones").value, 10),
    tone: {
      warmth: parseInt($("toneWarmth").value, 10),
      brightness: parseInt($("toneBrightness").value, 10),
      reverb: parseInt($("toneReverb").value, 10),
      punch: parseInt($("tonePunch").value, 10),
    },
  };

  try {
    const res = await fetch(`/api/style/${state.jobId}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "render failed");
    const fmt = $("format").value;
    const url = `/api/render/${state.jobId}/${data.token}?format=${fmt}`;
    $("results").innerHTML = `
      <div class="stem key">
        <div class="stem-head"><span class="stem-name">Styled track</span><span class="tag">${$("preset").selectedOptions[0].text}</span></div>
        <audio controls preload="none" src="${url}"></audio>
        <a class="dl" href="${url}&download=1" download>Download ${fmt.toUpperCase()}</a>
      </div>` + $("results").innerHTML;
    $("renderNote").textContent = "Done — preview or download above.";
  } catch (err) {
    $("renderNote").textContent = "Failed: " + err.message;
  } finally {
    $("renderBtn").disabled = false;
  }
});
