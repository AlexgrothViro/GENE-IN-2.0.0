import assert from "node:assert/strict";
import test from "node:test";
import { OPTIONAL_EVIDENCE_DEFAULTS, optionalEvidenceParams, optionalEvidenceIssues, optionalEvidenceWizard, effectiveOptionalEvidence } from "../js/state.js";

test("untouched options omit selectors and stale paths", () => {
  assert.deepEqual(optionalEvidenceParams({ ...OPTIONAL_EVIDENCE_DEFAULTS, competitionDb: "old", remappingReference: "old" }), {});
  assert.deepEqual(optionalEvidenceIssues(OPTIONAL_EVIDENCE_DEFAULTS), []);
});

test("each selected feature requires its own pair of inputs", () => {
  assert.equal(optionalEvidenceIssues({ competitionEnabled: true }).length, 1);
  assert.equal(optionalEvidenceIssues({ remappingEnabled: true }).length, 1);
  assert.equal(optionalEvidenceIssues({ competitionEnabled: true, remappingEnabled: true }).length, 2);
});

test("selected inputs survive history review and serialize without the other feature", () => {
  for (const params of [
    { competition_enabled: true, remapping_enabled: false, competition_db: "/files with spaces/db", competition_labels: "/labels.tsv" },
    { competition_enabled: false, remapping_enabled: true, remapping_reference: "/ref.fa", remapping_index: "/index", library_mode: "unknown" },
    { competition_enabled: true, remapping_enabled: true, competition_db: "/db", competition_labels: "/labels.tsv", remapping_reference: "/ref.fa", remapping_index: "/index", library_mode: "shotgun" },
  ]) {
    assert.deepEqual(optionalEvidenceParams(optionalEvidenceWizard(params)), params);
    assert.deepEqual(optionalEvidenceIssues(optionalEvidenceWizard(params)), []);
  }
});

test("reviewing an old run clears optional settings left over from another run", () => {
  assert.deepEqual(optionalEvidenceWizard({}), OPTIONAL_EVIDENCE_DEFAULTS);
});

test("inherit, enabled and disabled preserve both option axes", () => {
  const saved = { competition_enabled: true, remapping_enabled: true, competition_db: "/saved bank", competition_labels: "/saved labels", remapping_reference: "/saved ref", remapping_index: "/saved index", library_mode: "unknown" };
  for (const [key, parameter] of [["competitionEnabled", "competition_enabled"], ["remappingEnabled", "remapping_enabled"]]) {
    for (const state of [null, true, false]) {
      const wizard = { ...OPTIONAL_EVIDENCE_DEFAULTS, optionalDefaults: saved, [key]: state };
      const params = optionalEvidenceParams(wizard);
      assert.equal(Object.hasOwn(params, parameter), state !== null);
      if (state !== null) assert.equal(params[parameter], state);
      assert.equal(effectiveOptionalEvidence(wizard)[key], state ?? true);
      assert.deepEqual(optionalEvidenceIssues(wizard), []);
    }
  }
});

test("explicitly cleared fields stay empty and returning to inheritance removes overrides", () => {
  const wizard = { ...OPTIONAL_EVIDENCE_DEFAULTS, competitionEnabled: true, competitionDb: "", optionalDefaults: { competition_enabled: true, competition_db: "/configured", competition_labels: "/labels" } };
  assert.equal(optionalEvidenceParams(wizard).competition_db, "");
  assert.equal(optionalEvidenceIssues(wizard).length, 1);
  wizard.competitionEnabled = null;
  assert.deepEqual(optionalEvidenceParams(wizard), {});
  assert.equal(effectiveOptionalEvidence(wizard).competitionDb, "/configured");
});

test("inherited disabled configuration is displayed without emitting false", () => {
  const wizard = { ...OPTIONAL_EVIDENCE_DEFAULTS, optionalDefaults: { competition_enabled: false, remapping_enabled: false } };
  assert.equal(effectiveOptionalEvidence(wizard).competitionEnabled, false);
  assert.equal(effectiveOptionalEvidence(wizard).remappingEnabled, false);
  assert.deepEqual(optionalEvidenceParams(wizard), {});
});
