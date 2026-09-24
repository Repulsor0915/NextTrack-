import { apiErrorMessage } from "./model.js";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function requestJson(path, options = {}) {
  let response;
  try {
    response = await fetch(path, { credentials: "same-origin", ...options });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError("Could not connect to NextTrack. Check that the server is running.", 0);
  }
  let body;
  try {
    body = await response.json();
  } catch {
    throw new ApiError("The server returned an unreadable response.", response.status);
  }
  if (!response.ok) throw new ApiError(apiErrorMessage(response.status, body), response.status);
  return body;
}

export const getCatalogue = () => requestJson("/api/v1/catalogue/");

export function searchTracks(query, signal) {
  const params = new URLSearchParams({ q: query, page_size: "8" });
  return requestJson(`/api/v1/tracks/?${params}`, { signal });
}

export function recommend(payload) {
  return requestJson("/api/v1/recommendations/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function suggestTrack(payload) {
  return requestJson("/api/v1/track-suggestions/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
