"use strict";

const byId = (id) => document.getElementById(id);
const form = byId("folder-form");
const folder = byId("folder");
const libraryStatus = byId("library-status");
const query = byId("query");
const captionsOnly = byId("captions-only");
const hideNotFound = byId("hide-not-found");
const sort = byId("sort");
const audio = byId("audio");
const playbackStatus = byId("playback-status");
const slots = new Map();
const pageSize = 50;
const filenameOrder = new Intl.Collator("ja", { numeric: true });
const captionStatuses = {
  not_found: "台詞が見つかりません",
  not_applicable: "台詞の照合対象外",
};
let clips = [];
let page = 0;

function clipCaption(clip) {
  return clip.text || captionStatuses[clip.status] || "台詞なし";
}

function durationLabel(clip) {
  return clip.duration === null ? "—" : clip.duration.toFixed(2);
}

function compareClips(first, second) {
  if (sort.value !== "filename") {
    if (first.duration === null && second.duration !== null) return 1;
    if (first.duration !== null && second.duration === null) return -1;
    if (first.duration !== null && second.duration !== null) {
      const difference = first.duration - second.duration;
      if (difference) return sort.value === "shortest" ? difference : -difference;
    }
  }
  return filenameOrder.compare(first.filename, second.filename);
}

function play(clip) {
  byId("playing-caption").textContent = clipCaption(clip);
  byId("playing-name").textContent = clip.filename;
  playbackStatus.textContent = "";
  if (audio.getAttribute("src") !== clip.url) audio.src = clip.url;
  audio.currentTime = 0;
  audio.play().catch((error) => {
    if (error.name !== "AbortError" && audio.getAttribute("src") === clip.url) {
      playbackStatus.textContent = "音声を再生できませんでした。";
    }
  });
}

function pin(slot, clip) {
  const card = document.querySelector(`[data-slot="${slot}"]`);
  slots.set(slot, clip);
  card.querySelector("button").disabled = false;
  card.querySelector(".slot-caption").textContent = clipCaption(clip);
  card.querySelector(".slot-name").textContent =
    clip.duration === null ? clip.filename : `${clip.filename} · ${durationLabel(clip)} 秒`;
}

function trackButton(label, filename, action) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.setAttribute("aria-label", `${label}：${filename}`);
  button.addEventListener("click", action);
  return button;
}

function render() {
  const words = query.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const matches = clips.filter((clip) =>
    (!captionsOnly.checked || clip.text.trim()) &&
    (!hideNotFound.checked || clip.status !== "not_found") &&
    words.every((word) => clip.searchable.includes(word))
  ).sort(compareClips);

  const pageCount = Math.max(1, Math.ceil(matches.length / pageSize));
  page = Math.max(0, Math.min(pageCount - 1, page));
  const rows = document.createDocumentFragment();

  for (const clip of matches.slice(page * pageSize, (page + 1) * pageSize)) {
    const row = document.createElement("tr");
    const caption = document.createElement("p");
    const filename = document.createElement("p");
    caption.className = "caption";
    caption.textContent = clipCaption(clip);
    filename.className = "muted";
    filename.textContent = clip.filename;
    filename.title = `${clip.archive}/${clip.filename}`;
    row.insertCell().append(caption, filename);
    row.insertCell().textContent = durationLabel(clip);
    const actions = document.createElement("div");
    actions.className = "actions";
    actions.append(
      trackButton("再生", clip.filename, () => play(clip)),
      trackButton("A に登録", clip.filename, () => pin("A", clip)),
      trackButton("B に登録", clip.filename, () => pin("B", clip)),
    );
    row.insertCell().append(actions);
    row.addEventListener("dblclick", (event) => {
      if (!event.target.closest("button")) play(clip);
    });
    rows.append(row);
  }

  byId("clips").replaceChildren(rows);
  byId("empty").hidden = matches.length > 0;
  byId("count").textContent = `${matches.length.toLocaleString()} / ${clips.length.toLocaleString()} 件`;
  byId("page").textContent = `${page + 1} / ${pageCount}`;
  byId("prev").disabled = page === 0;
  byId("next").disabled = page >= pageCount - 1;
}

async function openFolder() {
  const submit = form.querySelector("button[type=submit]");
  submit.disabled = true;
  libraryStatus.textContent = "音声フォルダを読み込み中…";
  try {
    const response = await fetch("/api/library", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder: folder.value }),
    });
    const library = await response.json();
    if (!response.ok) throw new Error(library.error || "読み込みに失敗しました。");
    clips = library.clips.map((clip) => ({
      ...clip,
      searchable: `${clip.archive}/${clip.filename} ${clip.text}`.toLowerCase(),
    }));
    folder.value = library.folder;
    query.value = "";
    page = 0;
    render();
    libraryStatus.textContent = library.errors ? `読み込めなかった CSV：${library.errors} 件` : "";
  } catch (error) {
    libraryStatus.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  openFolder();
});
for (const [element, event] of [
  [query, "input"],
  [captionsOnly, "change"],
  [hideNotFound, "change"],
  [sort, "change"],
]) {
  element.addEventListener(event, () => { page = 0; render(); });
}
byId("prev").addEventListener("click", () => { page -= 1; render(); });
byId("next").addEventListener("click", () => { page += 1; render(); });
for (const card of document.querySelectorAll("[data-slot]")) {
  card.querySelector("button").addEventListener("click", () => play(slots.get(card.dataset.slot)));
}
audio.addEventListener("error", () => { playbackStatus.textContent = "音声を読み込めませんでした。"; });

render();
fetch("/api/settings")
  .then((response) => response.json())
  .then((settings) => {
    folder.value = settings.folder;
    return openFolder();
  })
  .catch(() => { libraryStatus.textContent = "ビューアーに接続できませんでした。"; });
