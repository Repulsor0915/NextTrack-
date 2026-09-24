import { getCatalogue, recommend } from "../api.js";
import { InputError, buildRecommendationRequest, formatDiversityStrength } from "../model.js";
import { collectElements } from "./dom.js";
import { createHistory } from "./history.js";
import { createResults } from "./results.js";
import { createSearch } from "./search.js";
import { bindSuggestions } from "./suggestions.js";

const elements = collectElements([
  "catalogue-status", "track-search", "search-results", "search-spinner",
  "search-hint", "history-count", "history-list", "history-empty",
  "suggestion-toggle", "suggestion-form", "suggestion-submit", "suggestion-status",
  "mood-fieldset", "mood-hint", "bpm-min", "bpm-max", "diversity",
  "diversity-value", "diversity-hint", "result-limit", "advanced-toggle",
  "advanced-panel", "algorithm", "algorithm-hint", "form-error",
  "recommend-button", "random-button", "results-state", "results-content", "results-meta",
  "results-stale", "recommendation-list", "reason-panel",
  "recommendation-pagination", "recommendation-previous", "recommendation-next",
  "recommendation-page-label",
]);

const state = {
  history: [],
  searchResults: [],
  searchIndex: -1,
  searchController: null,
  searchTimer: null,
  searchSequence: 0,
  response: null,
  responseHistory: [],
  selectedResult: 0,
  currentPage: 1,
  loading: false,
};

function showFormError(message) {
  elements["form-error"].textContent = message;
  elements["form-error"].hidden = !message;
}

function markStale() {
  showFormError("");
  if (state.response && !state.loading) elements["results-stale"].hidden = false;
}

function currentAlgorithm() {
  return elements.algorithm.value;
}

function updateAlgorithmControls() {
  const method = currentAlgorithm();
  const ignoresMood = method === "cbf";
  elements["mood-fieldset"].disabled = ignoresMood;
  elements.diversity.disabled = ignoresMood;
  const hints = {
    auto: "Auto uses your history and mood, then adds variety when content matching applies.",
    cbf: "Basic CBF uses history similarity only. It needs at least one history track.",
    context_mmr: "Context + MMR needs history or mood and can rerank for variety.",
  };
  elements["algorithm-hint"].textContent = hints[method];
  elements["mood-hint"].textContent = ignoresMood
    ? "This method does not use mood. Your choice is kept if you switch methods."
    : "Mood is matched against audio features; it is not detected from you.";
  elements["diversity-hint"].textContent = ignoresMood
    ? "This method does not use MMR variety."
    : "MMR balance weight, not a percentage of diverse tracks.";
  markStale();
}

const history = createHistory({ elements, state, onChange: markStale });
createSearch({ elements, state, history });
bindSuggestions(elements);
const results = createResults({ elements, state });

async function runRecommendation(algorithmOverride = null) {
  if (state.loading) return;
  let payload;
  try {
    payload = buildRecommendationRequest({
      history: state.history,
      mood: document.querySelector('input[name="mood"]:checked').value,
      bpmMin: elements["bpm-min"].value.trim(),
      bpmMax: elements["bpm-max"].value.trim(),
      diversity: Number(elements.diversity.value),
      algorithm: algorithmOverride ?? currentAlgorithm(),
      limit: Number(elements["result-limit"].value),
    });
  } catch (error) {
    showFormError(error instanceof InputError ? error.message : "Check your settings and try again.");
    return;
  }

  showFormError("");
  const requestHistory = state.history.map((track) => ({ ...track }));
  const isRandom = payload.algorithm === "random";
  state.loading = true;
  elements["recommend-button"].disabled = true;
  elements["random-button"].disabled = true;
  if (isRandom) elements["random-button"].textContent = "Building a random mix...";
  else elements["recommend-button"].firstElementChild.textContent = "Finding your tracks...";
  results.setState(
    "loading",
    isRandom ? "Shuffling your mix..." : "Finding your tracks...",
    isRandom ? "Selecting eligible, unplayed tracks." : "The full catalogue can take several seconds to score. Hang tight.",
  );

  try {
    const data = await recommend(payload);
    state.responseHistory = requestHistory;
    results.render(data);
  } catch (error) {
    state.response = null;
    results.setState("error", "We couldn't build this list", error.message);
  } finally {
    state.loading = false;
    elements["recommend-button"].disabled = false;
    elements["random-button"].disabled = false;
    elements["recommend-button"].firstElementChild.textContent = "Find my next tracks";
    elements["random-button"].textContent = "Surprise me · random mix";
  }
}

elements["mood-fieldset"].addEventListener("change", markStale);
for (const id of ["bpm-min", "bpm-max", "result-limit"]) {
  elements[id].addEventListener(id === "result-limit" ? "change" : "input", markStale);
}
elements.diversity.addEventListener("input", () => {
  elements["diversity-value"].textContent = formatDiversityStrength(elements.diversity.value);
  markStale();
});
elements["advanced-toggle"].addEventListener("click", () => {
  const expanded = elements["advanced-toggle"].getAttribute("aria-expanded") === "true";
  elements["advanced-toggle"].setAttribute("aria-expanded", String(!expanded));
  elements["advanced-panel"].hidden = expanded;
});
elements.algorithm.addEventListener("change", updateAlgorithmControls);
elements["recommend-button"].addEventListener("click", () => runRecommendation());
elements["random-button"].addEventListener("click", () => runRecommendation("random"));

getCatalogue().then((catalogue) => {
  const status = elements["catalogue-status"];
  status.textContent = `${Number(catalogue.record_count).toLocaleString()} tracks · ${catalogue.version}`;
  status.title = `Active catalogue: ${catalogue.version}`;
  status.classList.add("ready");
}).catch(() => {
  const status = elements["catalogue-status"];
  status.textContent = "Catalogue unavailable";
  status.classList.add("error");
});
