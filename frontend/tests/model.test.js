import test from "node:test";
import assert from "node:assert/strict";
import {
  InputError, buildRecommendationRequest, describeMethod,
  formatDiversityStrength, formatPercent, formatScore, apiErrorMessage,
  recommendationPage, spotifyTrackLinks,
} from "../static/frontend/js/model.js";

const track = { id: "track-1", title: "One", artist: "Artist" };
const defaults = {
  history: [], mood: "", bpmMin: "", bpmMax: "",
  diversity: 0.2, algorithm: "auto", limit: 5,
};

test("Spotify links are built only from canonical track IDs", () => {
  const id = "0000vdREvCVMxbQTkS888c";
  assert.deepEqual(spotifyTrackLinks(id), {
    embed: `https://open.spotify.com/embed/track/${id}`,
    track: `https://open.spotify.com/track/${id}`,
  });
  assert.equal(spotifyTrackLinks("track-1"), null);
  assert.equal(spotifyTrackLinks("0000vdREvCVMxbQTkS888c?x=1"), null);
});

test("Auto sends the selected ordered history, mood, BPM and variety", () => {
  const payload = buildRecommendationRequest({
    ...defaults,
    history: [track, track],
    mood: "happy",
    bpmMin: "80",
    bpmMax: "150",
  });
  assert.deepEqual(payload, {
    algorithm: "auto", history: ["track-1", "track-1"], limit: 5,
    bpm: { min: 80, max: 150 }, mood: "happy", diversity_strength: 0.2,
  });
});

test("Random and Basic CBF omit ignored mood and MMR settings", () => {
  const random = buildRecommendationRequest({ ...defaults, mood: "calm", algorithm: "random" });
  assert.deepEqual(random, { algorithm: "random", history: [], limit: 5 });
  const cbf = buildRecommendationRequest({
    ...defaults, history: [track], mood: "calm", algorithm: "cbf",
  });
  assert.deepEqual(cbf, { algorithm: "cbf", history: ["track-1"], limit: 5 });
});

test("Surprise me uses the selected list size and BPM without mood or variety", () => {
  const payload = buildRecommendationRequest({
    ...defaults, algorithm: "random", history: [track], mood: "happy",
    bpmMin: "80", bpmMax: "140", limit: 10,
  });
  assert.deepEqual(payload, {
    algorithm: "random", history: ["track-1"], limit: 10,
    bpm: { min: 80, max: 140 },
  });
});

test("Explicit algorithms reject missing required signals", () => {
  assert.throws(() => buildRecommendationRequest({ ...defaults }), /Surprise me/);
  assert.throws(() => buildRecommendationRequest({ ...defaults, algorithm: "cbf" }), InputError);
  assert.throws(() => buildRecommendationRequest({ ...defaults, algorithm: "context_mmr" }), InputError);
  assert.doesNotThrow(() => buildRecommendationRequest({
    ...defaults, algorithm: "context_mmr", mood: "sad",
  }));
});

test("BPM bounds follow recommendation API validation", () => {
  for (const [bpmMin, bpmMax] of [["80", ""], ["90", "90"], ["100", "80"], ["-1", "120"]]) {
    assert.throws(() => buildRecommendationRequest({ ...defaults, mood: "happy", bpmMin, bpmMax }), InputError);
  }
  assert.deepEqual(
    buildRecommendationRequest({ ...defaults, mood: "happy", bpmMin: "0", bpmMax: "100" }).bpm,
    { min: 0, max: 100 }
  );
});

test("History and limit honor visible UI bounds", () => {
  assert.throws(() => buildRecommendationRequest({
    ...defaults, mood: "happy", history: Array(6).fill(track),
  }), InputError);
  assert.equal(buildRecommendationRequest({ ...defaults, mood: "happy", limit: 20 }).limit, 20);
  assert.throws(() => buildRecommendationRequest({ ...defaults, mood: "happy", limit: 21 }), InputError);
});

test("Null Random score is never rendered as zero", () => {
  assert.equal(formatScore(null), "—");
  assert.equal(formatScore(0), "0.0000");
  assert.equal(formatScore(0.94034), "0.9403");
  assert.equal(formatPercent(0.2), "20%");
  assert.equal(formatDiversityStrength(0.2), "0.20");
});

test("Recommendation pages show ten tracks while preserving overall ranks", () => {
  const recommendations = Array.from({ length: 20 }, (_, index) => ({ rank: index + 1 }));
  const first = recommendationPage(recommendations, 1);
  const second = recommendationPage(recommendations, 2);
  assert.deepEqual([first.page, first.totalPages, first.items.length], [1, 2, 10]);
  assert.deepEqual(second.items.map((item) => item.rank), [11, 12, 13, 14, 15, 16, 17, 18, 19, 20]);
  assert.equal(recommendationPage(recommendations, 3).page, 2);
});

test("Resolved method labels follow response metadata", () => {
  assert.equal(describeMethod({ resolved_algorithm: "random" }), "Random discovery");
  assert.equal(describeMethod({ relevance_model: "mood_cbf" }), "Mood-based match");
});

test("Known API errors receive actionable messages", () => {
  assert.match(apiErrorMessage(422, { error: { code: "NO_CANDIDATES" } }), /No tracks/);
  assert.match(apiErrorMessage(429, {}), /Too many requests/);
  assert.match(apiErrorMessage(503, {}), /catalogue/);
  assert.match(apiErrorMessage(400, { error: { code: "VALIDATION_ERROR", details: { limit: ["Too high."] } } }), /Too high/);
});
