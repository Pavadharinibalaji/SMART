/**
 * highlightEvidence utility for SMART 2.0.
 *
 * Performs exact, non-fuzzy substring matching between source_text and evidence_text.
 *
 * Deterministic policy:
 * - When evidence_text matches source_text, it identifies the first exact occurrence
 *   (via String.prototype.indexOf) and partitions the source into [before, match, after]
 *   segments while strictly preserving all original characters, whitespace, and punctuation.
 * - If evidence_text is non-empty but cannot be matched in source_text, mismatchWarning
 *   is flagged and the unhighlighted source is returned as a single segment.
 * - Missing or empty values (null, undefined, "") are safely handled without errors.
 * - Never attempts fuzzy matching, normalization tampering, or evidence invention.
 */

/**
 * @typedef {Object} HighlightSegment
 * @property {string} text - Segment text string
 * @property {boolean} isMatch - True if this segment is the exact matching evidence
 */

/**
 * @typedef {Object} HighlightResult
 * @property {boolean} matched - True if exact match was found in source
 * @property {boolean} mismatchWarning - True if evidence was supplied but not found in source
 * @property {boolean} hasSource - True if sourceText is a non-empty string
 * @property {boolean} hasEvidence - True if evidenceText is a non-empty string
 * @property {HighlightSegment[]} segments - Safe text segments to render
 */

/**
 * Highlight exact evidence substring within the original source message.
 *
 * @param {string|null|undefined} sourceText - Full original WhatsApp message
 * @param {string|null|undefined} evidenceText - Extracted evidence substring
 * @returns {HighlightResult}
 */
export function highlightEvidence(sourceText, evidenceText) {
  const hasSource = typeof sourceText === "string" && sourceText.length > 0;
  const hasEvidence = typeof evidenceText === "string" && evidenceText.length > 0;

  // Case 1: No source text available
  if (!hasSource) {
    return {
      matched: false,
      mismatchWarning: false,
      hasSource: false,
      hasEvidence,
      segments: [],
    };
  }

  // Case 2: Source exists, but evidence is null, undefined, or empty
  if (!hasEvidence) {
    return {
      matched: false,
      mismatchWarning: false,
      hasSource: true,
      hasEvidence: false,
      segments: [{ text: sourceText, isMatch: false }],
    };
  }

  // Case 3: Both source and evidence are non-empty strings.
  // Search for the exact substring match.
  const matchIndex = sourceText.indexOf(evidenceText);

  // Evidence mismatch: evidence was provided but does not exist in sourceText
  if (matchIndex === -1) {
    return {
      matched: false,
      mismatchWarning: true,
      hasSource: true,
      hasEvidence: true,
      segments: [{ text: sourceText, isMatch: false }],
    };
  }

  // Exact match found: partition source into safe segments
  const segments = [];

  // Segment preceding the match (if matchIndex > 0)
  if (matchIndex > 0) {
    segments.push({
      text: sourceText.slice(0, matchIndex),
      isMatch: false,
    });
  }

  // Matching evidence segment
  segments.push({
    text: sourceText.slice(matchIndex, matchIndex + evidenceText.length),
    isMatch: true,
  });

  // Segment succeeding the match (if any trailing characters remain)
  const afterIndex = matchIndex + evidenceText.length;
  if (afterIndex < sourceText.length) {
    segments.push({
      text: sourceText.slice(afterIndex),
      isMatch: false,
    });
  }

  return {
    matched: true,
    mismatchWarning: false,
    hasSource: true,
    hasEvidence: true,
    segments,
  };
}
