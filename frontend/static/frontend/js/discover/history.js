import { MAX_HISTORY } from "../model.js";
import { make } from "./dom.js";

export function createHistory({ elements, state, onChange }) {
  function historyButton(symbol, label, action, index, disabled = false) {
    const button = make("button", "icon-button", symbol);
    button.type = "button";
    button.title = label;
    button.setAttribute("aria-label", label);
    button.dataset.action = action;
    button.dataset.index = String(index);
    button.disabled = disabled;
    return button;
  }

  function render() {
    elements["history-count"].textContent = `${state.history.length} / ${MAX_HISTORY}`;
    elements["history-empty"].hidden = state.history.length > 0;
    const list = elements["history-list"];
    list.replaceChildren();

    state.history.forEach((track, index) => {
      const item = make("li", "history-item");
      item.append(make("span", "history-index", String(index + 1).padStart(2, "0")));
      const labels = make("span", "history-text");
      labels.append(make("span", "history-title", track.title));
      labels.append(make("span", "history-artist", track.artist));
      item.append(labels);

      const actions = make("span", "history-actions");
      actions.append(
        historyButton("↑", `Move ${track.title} earlier`, "up", index, index === 0),
        historyButton("↓", `Move ${track.title} later`, "down", index, index === state.history.length - 1),
        historyButton("×", `Remove ${track.title}`, "remove", index),
      );
      item.append(actions);
      list.append(item);
    });
  }

  function add(track) {
    if (state.history.length >= MAX_HISTORY) {
      elements["search-hint"].textContent = "Remove a history track before adding another.";
      return false;
    }
    state.history.push(track);
    render();
    onChange();
    return true;
  }

  elements["history-list"].addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const index = Number(button.dataset.index);
    if (button.dataset.action === "remove") {
      state.history.splice(index, 1);
    } else {
      const other = index + (button.dataset.action === "up" ? -1 : 1);
      [state.history[index], state.history[other]] = [state.history[other], state.history[index]];
    }
    render();
    onChange();
  });

  return { add, render };
}
