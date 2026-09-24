import { suggestTrack } from "../api.js";

export function bindSuggestions(elements) {
  elements["suggestion-toggle"].addEventListener("click", () => {
    const expanded = elements["suggestion-toggle"].getAttribute("aria-expanded") === "true";
    elements["suggestion-toggle"].setAttribute("aria-expanded", String(!expanded));
    elements["suggestion-form"].hidden = expanded;
  });

  elements["suggestion-form"].addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = elements["suggestion-form"];
    const status = elements["suggestion-status"];
    const submit = elements["suggestion-submit"];
    const fields = new FormData(form);
    const payload = {
      title: String(fields.get("title") || "").trim(),
      artist: String(fields.get("artist") || "").trim(),
      album_name: String(fields.get("album_name") || "").trim(),
      reference_url: String(fields.get("reference_url") || "").trim(),
    };
    if (!payload.title || !payload.artist) {
      status.textContent = "Enter both a song title and an artist.";
      status.classList.add("error");
      return;
    }

    submit.disabled = true;
    status.textContent = "Sending suggestion...";
    status.classList.remove("error");
    try {
      await suggestTrack(payload);
      form.reset();
      status.textContent = "Thanks! Your suggestion is waiting for admin review.";
    } catch (error) {
      status.textContent = error.message;
      status.classList.add("error");
    } finally {
      submit.disabled = false;
    }
  });
}
