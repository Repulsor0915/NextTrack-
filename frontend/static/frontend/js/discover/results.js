import {
  RECOMMENDATIONS_PER_PAGE,
  describeMethod,
  formatPercent,
  formatScore,
  recommendationPage,
  spotifyTrackLinks,
} from "../model.js";
import { make } from "./dom.js";

export function createResults({ elements, state }) {
  function setState(kind, title, description) {
    const container = elements["results-state"];
    container.className = `results-state ${kind}`;
    container.replaceChildren();
    const visual = make("div", "empty-visual");
    const disc = make("div", "empty-disc");
    disc.append(make("span", "", kind === "error" ? "!" : "♪"));
    visual.append(disc);
    container.append(visual, make("h3", "", title), make("p", "", description));
    container.hidden = false;
    elements["results-content"].hidden = true;
  }

  function metric(label, value) {
    const block = make("div", "metric");
    block.append(make("span", "", label), make("strong", "", value));
    return block;
  }

  function appendEvidenceSection(panel, heading, text) {
    const section = make("section", "reason-section");
    section.append(make("h4", "", heading), make("p", "", text));
    panel.append(section);
  }

  function appendListeningSection(panel, track) {
    const section = make("section", "listen-section");
    section.append(make("h4", "", "Listen on Spotify"));
    const links = spotifyTrackLinks(track.id);
    if (!links) {
      section.append(make("p", "listen-note", "A Spotify player is not available for this track ID."));
      panel.append(section);
      return;
    }

    const player = make("iframe", "spotify-player");
    player.src = links.embed;
    player.title = `Spotify player for ${track.title} by ${track.artist}`;
    player.loading = "lazy";
    player.allow = "autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture";
    player.setAttribute("allowfullscreen", "");
    section.append(player);

    const note = make("p", "listen-note", "Playback is provided by Spotify. Availability may vary. ");
    const openLink = make("a", "spotify-open", "Open in Spotify");
    openLink.href = links.track;
    openLink.target = "_blank";
    openLink.rel = "noopener noreferrer";
    note.append(openLink);
    section.append(note);
    panel.append(section);
  }

  function appendFeatureSection(panel, heading, features) {
    if (!features || !Object.keys(features).length) return;
    const section = make("section", "reason-section");
    section.append(make("h4", "", heading));
    const grid = make("div", "evidence-grid");
    for (const [name, feature] of Object.entries(features)) {
      const cell = make("div", "evidence-item");
      cell.append(make("strong", "", name));
      cell.append(make("span", "", `Actual ${formatScore(feature.actual)} · target ${formatScore(feature.target)}`));
      cell.append(make("span", "", `Closeness ${formatPercent(feature.closeness)}`));
      grid.append(cell);
    }
    section.append(
      grid,
      make("p", "evidence-note", "Values are normalized. Per-feature closeness is descriptive, not an exact contribution to the total score."),
    );
    panel.append(section);
  }

  function renderReason(item) {
    const panel = elements["reason-panel"];
    const evidence = item.explanation_evidence || {};
    const mmr = evidence.mmr;
    panel.replaceChildren();
    const header = make("div", "reason-head");
    const heading = make("div");
    heading.append(make("p", "reason-kicker", "WHY THIS TRACK"));
    const title = make("h3", "", item.track.title);
    title.id = "reason-title";
    heading.append(title);
    header.append(heading, make("span", "reason-badge", `#${item.rank} in your list`));
    panel.append(header, make("p", "reason-subtitle", item.explanation?.summary || "Recommendation evidence"));
    appendListeningSection(panel, item.track);

    const metrics = make("div", "metric-grid");
    metrics.append(metric("Relevance", item.score === null ? "Not scored" : formatScore(item.score)));
    metrics.append(metric("Base rank", evidence.base_rank ?? "—"));
    metrics.append(metric("Final rank", evidence.final_rank ?? item.rank));
    panel.append(metrics);

    if (item.explanation?.evidence?.length) {
      const section = make("section", "reason-section");
      section.append(make("h4", "", "From this recommendation run"));
      const list = make("ul");
      item.explanation.evidence.forEach((fact) => list.append(make("li", "", fact)));
      section.append(list);
      panel.append(section);
    }
    if (evidence.history?.closest_track) {
      const closest = evidence.history.closest_track;
      const track = state.responseHistory.find((entry) => entry.id === closest.track_id);
      appendEvidenceSection(
        panel,
        "Listening trail",
        `Closest selected track: ${track?.title || closest.track_id} (${formatScore(closest.similarity)} similarity). This is one track, not the whole history profile.`,
      );
    }
    appendFeatureSection(panel, "History profile features", evidence.history?.features);
    appendFeatureSection(panel, "Mood profile features", evidence.mood?.features);
    if (mmr) {
      const supportId = mmr.supporting_track?.track_id;
      const support = state.response?.recommendations?.find((entry) => entry.track.id === supportId)?.track.title
        || (supportId ? "an earlier pick" : null);
      if (mmr.diversity_strength === 0) {
        appendEvidenceSection(panel, "Variety reranking", "Variety strength was 0, so the base relevance order was preserved.");
      } else {
        let detail = `MMR selection score ${formatScore(mmr.selection_score)}; diversity gain ${formatScore(mmr.diversity_gain)}. This selection score is not the relevance score.`;
        if (support) detail += ` Most similar earlier pick: ${support} (${formatScore(mmr.supporting_track.similarity)} similarity).`;
        if (mmr.ranking_changed) detail += ` Moved from relevance rank ${evidence.base_rank} to final rank ${evidence.final_rank}.`;
        else detail += " This track kept its relevance position.";
        appendEvidenceSection(panel, "Variety reranking", detail);
      }
    }
    panel.hidden = false;
  }

  function renderPage() {
    const recommendations = state.response?.recommendations || [];
    const { page, totalPages, firstIndex, items } = recommendationPage(recommendations, state.currentPage);
    state.currentPage = page;
    const list = elements["recommendation-list"];
    list.replaceChildren();

    items.forEach((item, position) => {
      const index = firstIndex + position;
      const row = make("li");
      const button = make("button", `recommendation-card${index === state.selectedResult ? " active" : ""}`);
      button.type = "button";
      button.setAttribute("aria-label", `View reason for ${item.track.title} by ${item.track.artist}`);
      button.append(make("span", "rank-number", String(item.rank).padStart(2, "0")));
      button.append(make("span", `cover-art tone-${index % 5}`, "N·"));
      const info = make("span", "recommendation-info");
      info.append(make("span", "recommendation-title", item.track.title));
      info.append(make("span", "recommendation-artist", item.track.artist));
      info.append(make("span", "recommendation-summary", item.explanation?.summary || ""));
      button.append(info);
      const score = make("span", "recommendation-score");
      score.append(make("strong", "", formatScore(item.score)));
      score.append(make("small", "", item.score === null ? "UNSCORED" : "RELEVANCE"));
      if (item.explanation_evidence?.rank_change) {
        const change = item.explanation_evidence.rank_change;
        score.append(make("em", change > 0 ? "rank-up" : "rank-down", `${change > 0 ? "↑" : "↓"} ${Math.abs(change)} rank`));
      }
      button.append(score);
      button.addEventListener("click", () => {
        state.selectedResult = index;
        list.querySelectorAll(".recommendation-card").forEach((card, cardPosition) => {
          card.classList.toggle("active", cardPosition === position);
        });
        renderReason(item);
      });
      row.append(button);
      list.append(row);
    });

    const pagination = elements["recommendation-pagination"];
    pagination.hidden = totalPages <= 1;
    elements["recommendation-previous"].disabled = page === 1;
    elements["recommendation-next"].disabled = page === totalPages;
    elements["recommendation-page-label"].textContent = `Page ${page} of ${totalPages}`;
    if (items.length) renderReason(recommendations[state.selectedResult] || items[0]);
  }

  function render(data) {
    state.response = data;
    state.selectedResult = 0;
    state.currentPage = 1;
    elements["results-stale"].hidden = true;
    elements["results-state"].hidden = true;
    elements["results-content"].hidden = false;
    const count = data.recommendations.length;
    const method = describeMethod(data.meta);
    const reranked = data.meta?.reranker === "mmr" && data.meta?.diversity_strength > 0;
    elements["results-meta"].textContent = `${count} tracks · ${method}${reranked ? " + variety" : ""} · ${data.meta?.processing_ms ?? "—"} ms`;
    if (count) renderPage();
    else setState("", "No recommendations returned", "Try another mood or a wider tempo range.");
  }

  elements["recommendation-previous"].addEventListener("click", () => {
    state.currentPage -= 1;
    state.selectedResult = (state.currentPage - 1) * RECOMMENDATIONS_PER_PAGE;
    renderPage();
  });
  elements["recommendation-next"].addEventListener("click", () => {
    state.currentPage += 1;
    state.selectedResult = (state.currentPage - 1) * RECOMMENDATIONS_PER_PAGE;
    renderPage();
  });

  return { render, setState };
}
