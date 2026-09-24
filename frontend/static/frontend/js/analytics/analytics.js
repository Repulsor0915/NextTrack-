const METHOD_LABELS = Object.freeze({
  random: "Random",
  cbf: "Basic CBF",
  context_no_mmr: "Context · no MMR",
  context_mmr: "Context + MMR",
});
const METHOD_ORDER = ["random", "cbf", "context_no_mmr", "context_mmr"];

function label(method) {
  return METHOD_LABELS[method] ?? method;
}

function decimal(value) {
  return value == null ? "—" : Number(value).toFixed(4);
}

function percent(value) {
  return value == null ? "—" : `${(Number(value) * 100).toFixed(1)}%`;
}

function milliseconds(value) {
  return value == null ? "—" : Math.round(Number(value)).toLocaleString();
}

function integer(value) {
  return Number(value).toLocaleString();
}

function textElement(tag, className, value) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = value;
  return element;
}

function tableCell(row, value, header = false) {
  const cell = textElement(header ? "th" : "td", "", value);
  if (header) cell.scope = "row";
  row.append(cell);
}

function renderStats(snapshot) {
  const stats = [
    [integer(snapshot.catalogue.track_count), "catalogue tracks"],
    [snapshot.protocol.run_count, "recorded runs"],
    [snapshot.protocol.scenario_count, "synthetic scenarios"],
    [snapshot.protocol.candidate_count, "fixed candidates"],
    [snapshot.protocol.random_seed_count, "Random seeds"],
    [`Top ${snapshot.protocol.top_n}`, "tracks per list"],
  ];
  const target = document.getElementById("study-stats");
  for (const [value, description] of stats) {
    const card = document.createElement("div");
    card.className = "study-stat";
    card.append(textElement("strong", "", value), textElement("span", "", description));
    target.append(card);
  }
  document.getElementById("snapshot-provenance").textContent =
    `Catalogue ${snapshot.catalogue.version} · SHA-256 ${snapshot.catalogue.sha256.slice(0, 16)}… · evaluation manifest ${snapshot.provenance.evaluation_manifest_sha256.slice(0, 16)}…`;
}

function renderMethods(snapshot) {
  const target = document.getElementById("method-rows");
  for (const method of snapshot.methods) {
    const row = document.createElement("tr");
    tableCell(row, label(method.method), true);
    tableCell(row, `${method.run_count} / ${method.scenario_count}`);
    tableCell(row, decimal(method.mean_history_match));
    tableCell(row, decimal(method.mean_mood_match));
    tableCell(row, decimal(method.mean_intra_list_diversity));
    tableCell(row, percent(method.mean_artist_metadata_coverage));
    tableCell(row, percent(method.pool_coverage));
    target.append(row);
  }
}

function renderFindings(snapshot) {
  const transition = new Map(snapshot.transition.map((row) => [row.method, row]));
  const methods = new Map(snapshot.methods.map((row) => [row.method, row]));
  const paired = snapshot.pairwise.find((row) =>
    row.left_method === "context_no_mmr" && row.right_method === "context_mmr"
  );
  const performance = snapshot.warm_performance.find((row) =>
    row.scope === "full_catalogue" && row.method === "context_mmr"
  );
  const cbf = transition.get("cbf");
  const context = transition.get("context_mmr");
  const before = methods.get("context_no_mmr");
  const after = methods.get("context_mmr");
  if (!cbf || !context || !before || !after || !paired || !performance) {
    throw new Error("The verified findings are incomplete.");
  }
  const knownArtistFraction =
    1 - snapshot.catalogue.missing_artist_count / snapshot.catalogue.track_count;
  const findings = [
    {
      title: "Mood follows an explicit request",
      value: `${decimal(cbf.mean_mood_match)} → ${decimal(context.mean_mood_match)}`,
      body: `Across four conflicting-history scenarios, Context + MMR improved the mood-fit proxy over Basic CBF. History fit moved from ${decimal(cbf.mean_history_match)} to ${decimal(context.mean_history_match)}. These values are audio-feature proxies, not listener ratings.`,
    },
    {
      title: "MMR changes the list modestly",
      value: `${decimal(before.mean_intra_list_diversity)} → ${decimal(after.mean_intra_list_diversity)}`,
      body: `Mean intra-list diversity increased across 12 scenarios. Mean history fit moved from ${decimal(before.mean_history_match)} to ${decimal(after.mean_history_match)}; paired Top-10 Jaccard was ${decimal(paired.mean_top10_jaccard)}.`,
    },
    {
      title: "Artist conclusions have limited coverage",
      value: `${percent(knownArtistFraction)} known`,
      body: `${integer(snapshot.catalogue.missing_artist_count)} tracks have no artist metadata. Artist diversity is calculated only over known artists, while artist metadata coverage is reported separately for every method.`,
    },
    {
      title: "Full-catalogue speed needs work",
      value: `${milliseconds(performance.p50_ms)} ms p50`,
      body: `The same-process Context + MMR call had a p95 of ${milliseconds(performance.p95_ms)} ms on the local SQLite setup. HTTP, browser rendering, and concurrent users were not measured.`,
    },
  ];
  const target = document.getElementById("finding-cards");
  for (const finding of findings) {
    const card = document.createElement("article");
    card.className = "finding-card";
    card.append(
      textElement("h3", "", finding.title),
      textElement("strong", "finding-value", finding.value),
      textElement("p", "", finding.body),
    );
    target.append(card);
  }
}

function renderPairwise(snapshot) {
  const target = document.getElementById("pairwise-rows");
  const wantedPairs = [
    ["context_no_mmr", "context_mmr"],
    ["cbf", "context_mmr"],
    ["random", "context_mmr"],
  ];
  for (const [left, right] of wantedPairs) {
    const comparison = snapshot.pairwise.find((row) =>
      row.left_method === left && row.right_method === right
    );
    if (!comparison) throw new Error(`Pairwise data is missing for ${left}/${right}.`);
    const card = document.createElement("article");
    card.className = "pairwise-card";
    card.append(
      textElement("h3", "", `${label(left)} ↔ ${label(right)}`),
      textElement("strong", "pairwise-value", decimal(comparison.mean_top10_jaccard)),
      textElement("span", "pairwise-unit", "mean Top-10 Jaccard"),
    );
    const bar = document.createElement("div");
    bar.className = "pairwise-bar";
    bar.setAttribute("role", "img");
    bar.setAttribute("aria-label", `${percent(comparison.mean_top10_jaccard)} mean overlap`);
    const fill = document.createElement("span");
    fill.style.width = percent(comparison.mean_top10_jaccard);
    bar.append(fill);
    card.append(
      bar,
      textElement(
        "p", "",
        `${comparison.mean_overlap_count.toFixed(2)} shared tracks on average · ${comparison.scenario_count} scenarios · ${comparison.comparison_count} paired comparisons`,
      ),
    );
    target.append(card);
  }
}

function renderLatency(snapshot) {
  const byScope = new Map(snapshot.warm_performance.map((row) =>
    [`${row.scope}:${row.method}`, row]
  ));
  const target = document.getElementById("latency-rows");
  for (const method of METHOD_ORDER) {
    const fixed = byScope.get(`fixed_pool:${method}`);
    const full = byScope.get(`full_catalogue:${method}`);
    if (!fixed || !full) throw new Error(`Latency data is missing for ${method}.`);
    const row = document.createElement("tr");
    tableCell(row, label(method), true);
    for (const value of [fixed.p50_ms, fixed.p95_ms, full.p50_ms, full.p95_ms]) {
      tableCell(row, milliseconds(value));
    }
    target.append(row);
  }
}

function renderFigures(snapshot, assetBaseUrl) {
  const targets = {
    configuration: "configuration-figures",
    comparison: "comparison-figures",
    latency: "latency-figures",
  };
  for (const figure of snapshot.figures) {
    const target = document.getElementById(targets[figure.group]);
    if (!target) throw new Error(`Unknown figure group: ${figure.group}.`);
    const card = document.createElement("figure");
    card.className = "analytics-figure";
    const frame = document.createElement("div");
    frame.className = "figure-frame";
    const picture = document.createElement("img");
    picture.src = new URL(figure.path, assetBaseUrl).href;
    picture.alt = `${figure.title}. ${figure.caption}`;
    picture.loading = "lazy";
    frame.append(picture);
    const caption = document.createElement("figcaption");
    const fullSize = textElement("a", "figure-open", "Open full-size chart ↗");
    fullSize.href = picture.src;
    fullSize.target = "_blank";
    fullSize.rel = "noopener noreferrer";
    caption.append(
      textElement("h3", "", figure.title),
      textElement("p", "", figure.caption),
      fullSize,
    );
    card.append(frame, caption);
    target.append(card);
  }
}

async function loadSnapshot() {
  const content = document.getElementById("analytics-content");
  const snapshotUrl = content?.dataset.snapshotUrl;
  if (!snapshotUrl) throw new Error("The analytics snapshot URL is missing.");
  const response = await fetch(snapshotUrl);
  if (!response.ok) throw new Error(`Snapshot request failed (${response.status}).`);
  const snapshot = await response.json();
  if (snapshot.schema_version !== "nexttrack-analytics-snapshot-v2") {
    throw new Error("Unsupported analytics snapshot version.");
  }
  return { snapshot, assetBaseUrl: new URL(".", response.url || snapshotUrl) };
}

try {
  const { snapshot, assetBaseUrl } = await loadSnapshot();
  renderStats(snapshot);
  renderFindings(snapshot);
  renderMethods(snapshot);
  renderPairwise(snapshot);
  renderLatency(snapshot);
  renderFigures(snapshot, assetBaseUrl);
  document.getElementById("analytics-state").hidden = true;
  document.getElementById("analytics-content").hidden = false;
} catch (error) {
  const state = document.getElementById("analytics-state");
  state.classList.add("error");
  state.textContent = "The verified analytics snapshot could not be loaded. Check the published assets and try again.";
  console.error(error);
}
