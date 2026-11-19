/**
 * highlightEvidence utility for SMART 2.0 (Phase 3.3.1).
 *
 * Performs exact, occurrence-aware substring matching between source_text and evidence_text,
 * with full Unicode code-point to UTF-16 code-unit coordinate compatibility.
 *
 * Occurrence Disambiguation & Unicode Compatibility Policy:
 * 1. When explicit occurrence offsets (startIndex, endIndex) are provided:
 *    - Supports both native UTF-16 code-unit offsets and Python Unicode code-point offsets.
 *    - Offsets must be valid non-negative integers where 0 <= startIndex < endIndex.
 *    - If sourceText.slice(startIndex, endIndex) === evidenceText, uses UTF-16 coordinates directly.
 *    - Otherwise, translates code-point coordinates to UTF-16 code units (handling surrogate pairs
 *      for non-BMP characters like emojis: 😀, 🎉, 🚀, 📢, 📝, etc.).
 *    - If translated slice sourceText.slice(u16Start, u16End) === evidenceText, partitions source exactly.
 *    - If offsets are provided but invalid or inconsistent with evidenceText, mismatchWarning
 *      is flagged without silently falling back to an incorrect occurrence.
 * 2. When occurrence offsets are missing (null, undefined):
 *    - Backward-compatible fallback searches for the first occurrence via String.prototype.indexOf.
 *    - If found, partitions around that occurrence.
 *    - If not found, flags mismatchWarning.
 * 3. Never attempts fuzzy matching, normalization tampering, or evidence invention.
 */

/**
 * Convert a Unicode code-point offset (0-based character count) to a JavaScript UTF-16 code-unit offset.
 * Correctly accounts for non-BMP surrogate pairs (0xD800-0xDFFF) such as emojis.
 *
 * @param {string} str - Source string
 * @param {number} codePointIndex - 0-based code-point offset
 * @returns {number} 0-based UTF-16 code-unit offset
 */
export function codePointToUtf16Offset(str, codePointIndex) {
  if (codePointIndex <= 0) return 0;
  let cpCount = 0;
  for (let i = 0; i < str.length; i++) {
    if (cpCount === codePointIndex) {
      return i;
    }
    const code = str.charCodeAt(i);
    if (code >= 0xd800 && code <= 0xdbff && i + 1 < str.length) {
      const next = str.charCodeAt(i + 1);
      if (next >= 0xdc00 && next <= 0xdfff) {
        i++; // skip low surrogate in surrogate pair
      }
    }
    cpCount++;
  }
  if (cpCount === codePointIndex) {
    return str.length;
  }
  return null;
}

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
 * Highlight exact evidence substring within the original source message, with occurrence disambiguation.
 *
 * @param {string|null|undefined} sourceText - Full original WhatsApp message
 * @param {string|null|undefined} evidenceText - Extracted evidence substring
 * @param {number|Object|null|undefined} [optionsOrStartIndex] - Start offset (number) or options object { startIndex, endIndex }
 * @param {number|null|undefined} [maybeEndIndex] - End offset (number) when startIndex is passed as 3rd param
 * @returns {HighlightResult}
 */
export function highlightEvidence(sourceText, evidenceText, optionsOrStartIndex, maybeEndIndex) {
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

  // Parse offset parameters (supports positional args or options object)
  let startIndex = null;
  let endIndex = null;

  if (typeof optionsOrStartIndex === "number") {
    startIndex = optionsOrStartIndex;
    endIndex = typeof maybeEndIndex === "number" ? maybeEndIndex : null;
  } else if (optionsOrStartIndex && typeof optionsOrStartIndex === "object") {
    startIndex = optionsOrStartIndex.startIndex ?? optionsOrStartIndex.evidence_start_index ?? null;
    endIndex = optionsOrStartIndex.endIndex ?? optionsOrStartIndex.evidence_end_index ?? null;
  }

  const hasOffsets =
    startIndex !== null &&
    endIndex !== null &&
    startIndex !== undefined &&
    endIndex !== undefined;

  // Branch A: Explicit occurrence offsets provided
  if (hasOffsets) {
    const isValidInt =
      typeof startIndex === "number" &&
      typeof endIndex === "number" &&
      Number.isInteger(startIndex) &&
      Number.isInteger(endIndex) &&
      !Number.isNaN(startIndex) &&
      !Number.isNaN(endIndex);

    if (isValidInt && startIndex >= 0 && endIndex > startIndex) {
      // Authoritative Unicode code-point interpretation:
      // The SMART API contract defines occurrence offsets as Python Unicode code-point
      // coordinates. Translate code-point indices to JavaScript UTF-16 code-unit indices
      // to correctly handle non-BMP characters (surrogate pairs like emojis).
      // Direct UTF-16-first matching is unsafe because a code-point offset could accidentally
      // collide with a different identical occurrence earlier in the message.
      const u16Start = codePointToUtf16Offset(sourceText, startIndex);
      const u16End = codePointToUtf16Offset(sourceText, endIndex);
      if (
        u16Start !== null &&
        u16End !== null &&
        u16Start >= 0 &&
        u16Start < u16End &&
        u16End <= sourceText.length
      ) {
        const cpSlice = sourceText.slice(u16Start, u16End);
        if (cpSlice === evidenceText) {
          return createPartitionResult(sourceText, u16Start, u16End, cpSlice);
        }
      }
    }

    // Offsets were provided, but either invalid, negative, out-of-range, or inconsistent with evidenceText.
    // Avoid silently highlighting the wrong occurrence; flag mismatch warning.
    return {
      matched: false,
      mismatchWarning: true,
      hasSource: true,
      hasEvidence: true,
      segments: [{ text: sourceText, isMatch: false }],
    };
  }

  // Branch B: Offsets not provided — legacy backward-compatible fallback to indexOf
  const matchIndex = sourceText.indexOf(evidenceText);
  if (matchIndex === -1) {
    return {
      matched: false,
      mismatchWarning: true,
      hasSource: true,
      hasEvidence: true,
      segments: [{ text: sourceText, isMatch: false }],
    };
  }

  return createPartitionResult(sourceText, matchIndex, matchIndex + evidenceText.length, evidenceText);
}

function createPartitionResult(sourceText, start, end, matchedText) {
  const segments = [];
  if (start > 0) {
    segments.push({
      text: sourceText.slice(0, start),
      isMatch: false,
    });
  }
  segments.push({
    text: matchedText,
    isMatch: true,
  });
  if (end < sourceText.length) {
    segments.push({
      text: sourceText.slice(end),
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
