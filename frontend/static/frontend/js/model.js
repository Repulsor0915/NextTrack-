export const MAX_HISTORY = 5;
export const RECOMMENDATIONS_PER_PAGE = 10;
export const ALGORITHMS = Object.freeze(["auto", "random", "cbf", "context_mmr"]);

export function spotifyTrackLinks(trackId) {
  if (typeof trackId !== "string" || !/^[A-Za-z0-9]{22}$/.test(trackId)) return null;
  return {
    embed: `https://open.spotify.com/embed/track/${trackId}`,
    track: `https://open.spotify.com/track/${trackId}`,
  };
}

export class InputError extends Error {}

function parseBpm(value, label) {
  if (value === "") return null;
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) {
    throw new InputError(`${label} must be a non-negative number.`);
  }
  return number;
}

export function buildRecommendationRequest(settings) {
  const { history, mood, bpmMin, bpmMax, diversity, algorithm, limit } = settings;
  if (!ALGORITHMS.includes(algorithm)) throw new InputError("Choose a valid recommendation method.");
  if (mood && !["happy", "energetic", "calm", "sad"].includes(mood)) {
    throw new InputError("Choose a valid mood.");
  }
  if (!Array.isArray(history) || history.length > MAX_HISTORY || history.some((track) => !track?.id)) {
    throw new InputError("Choose no more than five valid history tracks.");
  }
  if (!Number.isInteger(limit) || limit < 1 || limit > 20) {
    throw new InputError("Choose between 1 and 20 recommendations.");
  }
  if (algorithm === "cbf" && history.length === 0) {
    throw new InputError("Basic CBF needs at least one history track.");
  }
  if (algorithm === "auto" && history.length === 0 && !mood) {
    throw new InputError("Choose a history track or mood, or use Surprise me for a random mix.");
  }
  if (algorithm === "context_mmr" && history.length === 0 && !mood) {
    throw new InputError("Context + MMR needs a history track or a mood.");
  }

  const minimum = parseBpm(bpmMin, "Minimum BPM");
  const maximum = parseBpm(bpmMax, "Maximum BPM");
  if ((minimum === null) !== (maximum === null)) {
    throw new InputError("Enter both minimum and maximum BPM, or leave both empty.");
  }
  if (minimum !== null && minimum >= maximum) {
    throw new InputError("Minimum BPM must be lower than maximum BPM.");
  }

  const payload = {
    algorithm,
    history: history.map((track) => track.id),
    limit,
  };
  if (minimum !== null) payload.bpm = { min: minimum, max: maximum };
  if (algorithm !== "random" && algorithm !== "cbf") {
    if (mood) payload.mood = mood;
    if (!Number.isFinite(diversity) || diversity < 0 || diversity > 0.4) {
      throw new InputError("Variety must be between 0% and 40%.");
    }
    payload.diversity_strength = diversity;
  }
  return payload;
}

export function formatScore(score) {
  return score === null || score === undefined ? "—" : Number(score).toFixed(4);
}

export function recommendationPage(recommendations, requestedPage) {
  const totalPages = Math.max(1, Math.ceil(recommendations.length / RECOMMENDATIONS_PER_PAGE));
  const page = Math.min(Math.max(1, requestedPage), totalPages);
  const firstIndex = (page - 1) * RECOMMENDATIONS_PER_PAGE;
  return {
    page,
    totalPages,
    firstIndex,
    items: recommendations.slice(firstIndex, firstIndex + RECOMMENDATIONS_PER_PAGE),
  };
}

export function formatPercent(value) {
  return value === null || value === undefined ? "—" : `${Math.round(Number(value) * 100)}%`;
}

export function formatDiversityStrength(value) {
  return Number(value).toFixed(2);
}

export function describeMethod(meta) {
  if (meta?.resolved_algorithm === "random") return "Random discovery";
  if (meta?.relevance_model === "history_mood_cbf") return "History + mood";
  if (meta?.relevance_model === "mood_cbf") return "Mood-based match";
  if (meta?.relevance_model === "history_cbf") return "History-based match";
  return "Recommendations";
}

export function apiErrorMessage(status, body) {
  const code = body?.error?.code;
  if (status === 429) return "Too many requests. Please wait a moment and try again.";
  if (status === 503) return "The catalogue is not available right now. Please try again later.";
  if (status === 413) return "This request is too large. Remove some inputs and try again.";
  if (status === 422 || code === "NO_CANDIDATES") {
    return "No tracks match these settings. Try a wider BPM range or fewer history tracks.";
  }
  if (code === "UNKNOWN_TRACK_ID") {
    return "A selected track is no longer in the catalogue. Remove it and try again.";
  }
  if (status === 400 && code === "VALIDATION_ERROR") {
    const details = body?.error?.details;
    const first = details && Object.values(details).flat(Infinity).find((item) => typeof item === "string");
    return first || "Check the settings and try again.";
  }
  return body?.error?.message || "The request could not be completed. Please try again.";
}
