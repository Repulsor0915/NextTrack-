import { searchTracks } from "../api.js";
import { MAX_HISTORY } from "../model.js";
import { make } from "./dom.js";

export function createSearch({ elements, state, history }) {
  function close() {
    elements["search-results"].hidden = true;
    elements["track-search"].setAttribute("aria-expanded", "false");
    elements["track-search"].removeAttribute("aria-activedescendant");
    state.searchIndex = -1;
  }

  function highlight(index) {
    state.searchIndex = index;
    for (const [position, option] of [...elements["search-results"].children].entries()) {
      option.classList.toggle("active", position === index);
      option.setAttribute("aria-selected", String(position === index));
    }
    if (index >= 0) {
      const id = `track-option-${index}`;
      elements["track-search"].setAttribute("aria-activedescendant", id);
      document.getElementById(id)?.scrollIntoView({ block: "nearest" });
    } else {
      elements["track-search"].removeAttribute("aria-activedescendant");
    }
  }

  function addTrack(track) {
    if (!history.add(track)) return;
    elements["track-search"].value = "";
    elements["search-hint"].textContent = "Type at least two characters to search the catalogue.";
    close();
    elements["track-search"].focus();
  }

  function render(results) {
    state.searchResults = results;
    const list = elements["search-results"];
    list.replaceChildren();
    if (!results.length) {
      list.append(make("p", "search-empty", "No matching tracks found."));
      list.hidden = false;
      elements["track-search"].setAttribute("aria-expanded", "true");
      return;
    }

    results.forEach((track, index) => {
      const button = make("button", "search-option");
      button.type = "button";
      button.id = `track-option-${index}`;
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", "false");
      button.disabled = state.history.length >= MAX_HISTORY;
      button.append(make("span", "option-art", "♫"));
      const labels = make("span", "option-text");
      labels.append(make("span", "option-title", track.title));
      labels.append(make("span", "option-artist", track.artist));
      button.append(labels, make("span", "option-add", "Add +"));
      button.addEventListener("click", () => addTrack(track));
      list.append(button);
    });
    list.hidden = false;
    elements["track-search"].setAttribute("aria-expanded", "true");
    highlight(-1);
  }

  async function run(query) {
    state.searchController?.abort();
    state.searchController = new AbortController();
    const sequence = ++state.searchSequence;
    elements["search-spinner"].classList.add("active");
    elements["search-hint"].textContent = "Searching the catalogue...";
    try {
      const data = await searchTracks(query, state.searchController.signal);
      if (sequence !== state.searchSequence) return;
      render(data.results || []);
      elements["search-hint"].textContent = data.count
        ? `${data.count.toLocaleString()} matching tracks. Select one to add it.`
        : "No matching tracks. Try another title or artist.";
    } catch (error) {
      if (error.name === "AbortError" || sequence !== state.searchSequence) return;
      close();
      elements["search-hint"].textContent = error.message;
    } finally {
      if (sequence === state.searchSequence) elements["search-spinner"].classList.remove("active");
    }
  }

  function schedule() {
    clearTimeout(state.searchTimer);
    state.searchController?.abort();
    state.searchSequence += 1;
    const query = elements["track-search"].value.trim();
    close();
    elements["search-spinner"].classList.remove("active");
    if (query.length < 2) {
      elements["search-hint"].textContent = "Type at least two characters to search the catalogue.";
      return;
    }
    if (state.history.length >= MAX_HISTORY) {
      elements["search-hint"].textContent = "Remove a history track before adding another.";
      return;
    }
    state.searchTimer = setTimeout(() => run(query), 320);
  }

  elements["track-search"].addEventListener("input", schedule);
  elements["track-search"].addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      close();
      return;
    }
    if (elements["search-results"].hidden || !state.searchResults.length) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const delta = event.key === "ArrowDown" ? 1 : -1;
      highlight((state.searchIndex + delta + state.searchResults.length) % state.searchResults.length);
    } else if (event.key === "Enter" && state.searchIndex >= 0) {
      event.preventDefault();
      addTrack(state.searchResults[state.searchIndex]);
    }
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".search-panel")) close();
  });

  return { close };
}
