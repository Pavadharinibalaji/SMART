import assert from "node:assert";
import { highlightEvidence } from "./highlightEvidence.js";

console.log("Running highlightEvidence unit tests across all 12 scenarios...\n");

// 1. Exact evidence at the beginning of a message
{
  const source = "Submit assignment 1 on 10/11/2026. Please ensure all tests pass.";
  const evidence = "Submit assignment 1 on 10/11/2026";
  const res = highlightEvidence(source, evidence);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.segments.length, 2);
  assert.strictEqual(res.segments[0].text, evidence);
  assert.strictEqual(res.segments[0].isMatch, true);
  assert.strictEqual(res.segments[1].text, ". Please ensure all tests pass.");
  assert.strictEqual(res.segments[1].isMatch, false);
  console.log("[PASS] 1. Exact evidence at beginning of message");
}

// 2. Exact evidence in the middle of a message
{
  const source = "Dear students, submit your lab exercise report for the robotics workshop on 28/10/2026. Attendance is mandatory.";
  const evidence = "submit your lab exercise report for the robotics workshop on 28/10/2026";
  const res = highlightEvidence(source, evidence);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.segments.length, 3);
  assert.strictEqual(res.segments[0].text, "Dear students, ");
  assert.strictEqual(res.segments[0].isMatch, false);
  assert.strictEqual(res.segments[1].text, evidence);
  assert.strictEqual(res.segments[1].isMatch, true);
  assert.strictEqual(res.segments[2].text, ". Attendance is mandatory.");
  assert.strictEqual(res.segments[2].isMatch, false);
  console.log("[PASS] 2. Exact evidence in middle of message");
}

// 3. Exact evidence at the end of a message
{
  const source = "Notice: CN exam on 12/11/2026";
  const evidence = "CN exam on 12/11/2026";
  const res = highlightEvidence(source, evidence);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.segments.length, 2);
  assert.strictEqual(res.segments[0].text, "Notice: ");
  assert.strictEqual(res.segments[0].isMatch, false);
  assert.strictEqual(res.segments[1].text, evidence);
  assert.strictEqual(res.segments[1].isMatch, true);
  console.log("[PASS] 3. Exact evidence at end of message");
}

// 4. Evidence with punctuation
{
  const source = "Reminder: Project (Phase 2) is due; submit before 11:59 PM!";
  const evidence = "Project (Phase 2) is due;";
  const res = highlightEvidence(source, evidence);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.segments[1].text, evidence);
  assert.strictEqual(res.segments[1].isMatch, true);
  console.log("[PASS] 4. Evidence with punctuation preserved exactly");
}

// 5. Evidence containing dates
{
  const source = "Assignment due on Friday, 20 November 2026 by 5 PM.";
  const evidence = "Assignment due on Friday, 20 November 2026";
  const res = highlightEvidence(source, evidence);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.segments[0].text, evidence);
  assert.strictEqual(res.segments[0].isMatch, true);
  assert.strictEqual(res.segments[1].text, " by 5 PM.");
  console.log("[PASS] 5. Evidence containing dates");
}

// 6. Evidence containing multiple words and spaces
{
  const source = "Please   submit   lab   report   before   Friday.";
  const evidence = "submit   lab   report";
  const res = highlightEvidence(source, evidence);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.segments[1].text, "submit   lab   report");
  console.log("[PASS] 6. Evidence containing multiple words and preserved spacing");
}

// 7. Evidence repeated in the source (deterministic policy: first occurrence matched)
{
  const source = "Quiz on Monday. Reminder: Quiz on Monday for all sections.";
  const evidence = "Quiz on Monday";
  const res = highlightEvidence(source, evidence);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.segments[0].text, "Quiz on Monday");
  assert.strictEqual(res.segments[0].isMatch, true);
  assert.strictEqual(res.segments[1].text, ". Reminder: Quiz on Monday for all sections.");
  assert.strictEqual(res.segments[1].isMatch, false);
  console.log("[PASS] 7. Evidence repeated in source (first exact occurrence deterministically matched)");
}

// 8. Evidence not found (mismatch warning, no highlight)
{
  const source = "Assignment 1 was discussed yesterday.";
  const evidence = "Assignment 1 is due tomorrow";
  const res = highlightEvidence(source, evidence);
  assert.strictEqual(res.matched, false);
  assert.strictEqual(res.mismatchWarning, true);
  assert.strictEqual(res.segments.length, 1);
  assert.strictEqual(res.segments[0].text, source);
  assert.strictEqual(res.segments[0].isMatch, false);
  console.log("[PASS] 8. Evidence not found (mismatchWarning flagged, original source preserved without highlight)");
}

// 9. Empty evidence
{
  const source = "Some valid announcement text.";
  const evidence = "";
  const res = highlightEvidence(source, evidence);
  assert.strictEqual(res.matched, false);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.hasEvidence, false);
  assert.strictEqual(res.segments.length, 1);
  assert.strictEqual(res.segments[0].text, source);
  assert.strictEqual(res.segments[0].isMatch, false);
  console.log("[PASS] 9. Empty evidence handled gracefully");
}

// 10. NULL evidence
{
  const source = "Manual task without evidence.";
  const res = highlightEvidence(source, null);
  assert.strictEqual(res.matched, false);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.hasEvidence, false);
  assert.strictEqual(res.segments.length, 1);
  assert.strictEqual(res.segments[0].text, source);
  assert.strictEqual(res.segments[0].isMatch, false);
  console.log("[PASS] 10. NULL evidence handled gracefully");
}

// 11. Empty source
{
  const res = highlightEvidence("", "some evidence");
  assert.strictEqual(res.matched, false);
  assert.strictEqual(res.hasSource, false);
  assert.strictEqual(res.segments.length, 0);
  console.log("[PASS] 11. Empty source handled gracefully");
}

// 12. NULL source
{
  const res = highlightEvidence(null, "some evidence");
  assert.strictEqual(res.matched, false);
  assert.strictEqual(res.hasSource, false);
  assert.strictEqual(res.segments.length, 0);
  console.log("[PASS] 12. NULL source handled gracefully");
}

// ============================================================================
// Phase 3.3: Occurrence Disambiguation Unit Tests
// ============================================================================

// 13. Second occurrence highlighted when identical phrase appears twice
{
  const source = "CN Quiz on Friday.\nLab due Monday.\nCN Quiz on Friday.";
  const evidence = "CN Quiz on Friday.";
  // Second occurrence at index 35 to 53
  const start = 35;
  const end = 53;
  const res = highlightEvidence(source, evidence, start, end);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.segments.length, 2);
  assert.strictEqual(res.segments[0].text, "CN Quiz on Friday.\nLab due Monday.\n");
  assert.strictEqual(res.segments[0].isMatch, false);
  assert.strictEqual(res.segments[1].text, evidence);
  assert.strictEqual(res.segments[1].isMatch, true);
  console.log("[PASS] 13. Second occurrence highlighted when identical phrase appears twice");
}

// 14. Third occurrence highlighted when identical phrase appears three times
{
  const source = "Quiz 1.\nQuiz 1.\nQuiz 1.";
  const evidence = "Quiz 1.";
  // Third occurrence is at index 16 to 23
  const start = 16;
  const end = 23;
  const res = highlightEvidence(source, evidence, start, end);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.segments.length, 2);
  assert.strictEqual(res.segments[0].text, "Quiz 1.\nQuiz 1.\n");
  assert.strictEqual(res.segments[0].isMatch, false);
  assert.strictEqual(res.segments[1].text, "Quiz 1.");
  assert.strictEqual(res.segments[1].isMatch, true);
  console.log("[PASS] 14. Third occurrence highlighted when identical phrase appears three times");
}

// 15. Exact match using options object format { startIndex, endIndex }
{
  const source = "Task A is ready. Task A is ready.";
  const evidence = "Task A is ready.";
  const res = highlightEvidence(source, evidence, { startIndex: 17, endIndex: 33 });
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.segments[0].text, "Task A is ready. ");
  assert.strictEqual(res.segments[0].isMatch, false);
  assert.strictEqual(res.segments[1].text, evidence);
  assert.strictEqual(res.segments[1].isMatch, true);
  console.log("[PASS] 15. Exact match using options object format { startIndex, endIndex }");
}

// 16. Exact match using options object format { evidence_start_index, evidence_end_index }
{
  const source = "Task B is ready. Task B is ready.";
  const evidence = "Task B is ready.";
  const res = highlightEvidence(source, evidence, { evidence_start_index: 17, evidence_end_index: 33 });
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.segments[1].text, evidence);
  assert.strictEqual(res.segments[1].isMatch, true);
  console.log("[PASS] 16. Exact match using options object format { evidence_start_index, evidence_end_index }");
}

// 17. Fallback to indexOf when offsets are undefined (legacy compatibility)
{
  const source = "Legacy task text here.";
  const evidence = "task text";
  const res = highlightEvidence(source, evidence, undefined, undefined);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.segments[1].text, evidence);
  assert.strictEqual(res.segments[1].isMatch, true);
  console.log("[PASS] 17. Fallback to indexOf when offsets are undefined");
}

// 18. Fallback to indexOf when offsets are null (legacy compatibility)
{
  const source = "Another legacy task message.";
  const evidence = "legacy task";
  const res = highlightEvidence(source, evidence, null, null);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.segments[1].text, evidence);
  assert.strictEqual(res.segments[1].isMatch, true);
  console.log("[PASS] 18. Fallback to indexOf when offsets are null");
}

// 19. Negative offset flags mismatchWarning without highlighting wrong occurrence
{
  const source = "Repeat test. Repeat test.";
  const evidence = "Repeat test.";
  const res = highlightEvidence(source, evidence, -1, 12);
  assert.strictEqual(res.matched, false);
  assert.strictEqual(res.mismatchWarning, true);
  assert.strictEqual(res.segments.length, 1);
  assert.strictEqual(res.segments[0].text, source);
  assert.strictEqual(res.segments[0].isMatch, false);
  console.log("[PASS] 19. Negative offset flags mismatchWarning without highlighting wrong occurrence");
}

// 20. Out of range endIndex flags mismatchWarning without highlighting wrong occurrence
{
  const source = "Short message";
  const evidence = "message";
  const res = highlightEvidence(source, evidence, 6, 999);
  assert.strictEqual(res.matched, false);
  assert.strictEqual(res.mismatchWarning, true);
  assert.strictEqual(res.segments.length, 1);
  assert.strictEqual(res.segments[0].isMatch, false);
  console.log("[PASS] 20. Out of range endIndex flags mismatchWarning");
}

// 21. Inverted offsets (startIndex >= endIndex) flags mismatchWarning
{
  const source = "Sample text";
  const evidence = "text";
  const res = highlightEvidence(source, evidence, 10, 5);
  assert.strictEqual(res.matched, false);
  assert.strictEqual(res.mismatchWarning, true);
  assert.strictEqual(res.segments[0].isMatch, false);
  console.log("[PASS] 21. Inverted offsets flags mismatchWarning");
}

// 22. Offsets pointing to mismatched slice flags mismatchWarning without silently falling back
{
  const source = "Alpha Beta Gamma";
  const evidence = "Beta";
  // Offsets point to "Alpha" instead of "Beta"
  const res = highlightEvidence(source, evidence, 0, 5);
  assert.strictEqual(res.matched, false);
  assert.strictEqual(res.mismatchWarning, true);
  assert.strictEqual(res.segments.length, 1);
  assert.strictEqual(res.segments[0].text, source);
  assert.strictEqual(res.segments[0].isMatch, false);
  console.log("[PASS] 22. Mismatched slice offsets flag mismatchWarning without silent fallback");
}

// 23. Task 1 Regression: Single emoji before evidence (Unicode code-point to UTF-16 translation)
{
  const source = "📢 Assignment 1 due tomorrow.";
  const evidence = "Assignment 1 due tomorrow.";
  // Python code points: '📢' is 1 code point, ' ' is 1 -> startIndex = 2, length = 26 -> endIndex = 28
  const pythonStart = 2;
  const pythonEnd = 28;
  const res = highlightEvidence(source, evidence, pythonStart, pythonEnd);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.segments.length, 2);
  assert.strictEqual(res.segments[0].text, "📢 ");
  assert.strictEqual(res.segments[0].isMatch, false);
  assert.strictEqual(res.segments[1].text, evidence);
  assert.strictEqual(res.segments[1].isMatch, true);
  console.log("[PASS] 23. Single emoji before evidence (Python code-point to JS UTF-16 conversion)");
}

// 24. Task 1 Regression: Multiple emojis before evidence
{
  const source = "🚀🔥💡 Exam on Friday.";
  const evidence = "Exam on Friday.";
  // Python code points: 3 emojis (3 cp) + 1 space (1 cp) = 4 cp. Length = 15 cp -> end = 19
  const pythonStart = 4;
  const pythonEnd = 19;
  const res = highlightEvidence(source, evidence, pythonStart, pythonEnd);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.segments.length, 2);
  assert.strictEqual(res.segments[0].text, "🚀🔥💡 ");
  assert.strictEqual(res.segments[0].isMatch, false);
  assert.strictEqual(res.segments[1].text, evidence);
  assert.strictEqual(res.segments[1].isMatch, true);
  console.log("[PASS] 24. Multiple emojis before evidence");
}

// 25. Task 1 Regression: Emoji inside evidence
{
  const source = "Important: Project 📚 submission deadline.";
  const evidence = "Project 📚 submission deadline.";
  // In Python code points: 'Important: ' = 11 cp. 'Project 📚 submission deadline.' = 30 cp. end = 41
  const pythonStart = 11;
  const pythonEnd = 41;
  const res = highlightEvidence(source, evidence, pythonStart, pythonEnd);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.segments.length, 2);
  assert.strictEqual(res.segments[0].text, "Important: ");
  assert.strictEqual(res.segments[0].isMatch, false);
  assert.strictEqual(res.segments[1].text, evidence);
  assert.strictEqual(res.segments[1].isMatch, true);
  console.log("[PASS] 25. Emoji inside evidence");
}

// 26. Task 1 Regression: Non-BMP characters before and inside multiline evidence
{
  const source = "🎉 Notice:\nAssignment 📝 Part 1 is due.\nDeadline: 5pm ⏰.";
  const evidence = "Assignment 📝 Part 1 is due.\nDeadline: 5pm ⏰.";
  // '🎉 Notice:\n' = 10 cp. evidence = 44 cp. end = 54
  const pythonStart = 10;
  const pythonEnd = 54;
  const res = highlightEvidence(source, evidence, pythonStart, pythonEnd);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.segments.length, 2);
  assert.strictEqual(res.segments[0].text, "🎉 Notice:\n");
  assert.strictEqual(res.segments[0].isMatch, false);
  assert.strictEqual(res.segments[1].text, evidence);
  assert.strictEqual(res.segments[1].isMatch, true);
  console.log("[PASS] 26. Non-BMP characters before and inside multiline evidence");
}

// 27. Task 1 Regression: Mixed ASCII, emoji, and punctuation
{
  const source = "!!! [URGENT] 🚨 >> Quiz #3: chapter 5 << 🎯 !!!";
  const evidence = "Quiz #3: chapter 5";
  // '!!! [URGENT] 🚨 >> ' = 18 cp. evidence = 18 cp. end = 36
  const pythonStart = 18;
  const pythonEnd = 36;
  const res = highlightEvidence(source, evidence, pythonStart, pythonEnd);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.segments.length, 3);
  assert.strictEqual(res.segments[0].text, "!!! [URGENT] 🚨 >> ");
  assert.strictEqual(res.segments[1].text, evidence);
  assert.strictEqual(res.segments[2].text, " << 🎯 !!!");
  console.log("[PASS] 27. Mixed ASCII, emoji, and punctuation");
}

// 28. Task 1 Regression: Legacy records without offsets
{
  const source = "Legacy notification: Assignment 6 due next week.";
  const evidence = "Assignment 6 due next week.";
  const res = highlightEvidence(source, evidence, null, null);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.segments[0].text, "Legacy notification: ");
  assert.strictEqual(res.segments[1].text, evidence);
  console.log("[PASS] 28. Legacy records without offsets");
}

// 29. Task 1 Regression (Phase 3.3.2): An emoji before two identical evidence phrases
{
  const phrase = "Assignment 1 due tomorrow.";
  const source = `📢 ${phrase} Reminder: ${phrase}`;
  // Occ 1 in Python cp: start = 2, end = 28
  // Occ 2 in Python cp: start = 2 + 26 + 11 = 39, end = 39 + 26 = 65
  const pythonStartOcc2 = 39;
  const pythonEndOcc2 = 65;
  const res = highlightEvidence(source, phrase, pythonStartOcc2, pythonEndOcc2);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.segments.length, 2);
  assert.strictEqual(res.segments[0].text, `📢 ${phrase} Reminder: `);
  assert.strictEqual(res.segments[0].isMatch, false);
  assert.strictEqual(res.segments[1].text, phrase);
  assert.strictEqual(res.segments[1].isMatch, true);
  console.log("[PASS] 29. An emoji before two identical evidence phrases");
}

// 30. Task 1 Regression (Phase 3.3.2): Multiple non-BMP characters before repeated evidence
{
  const phrase = "Exam on Friday.";
  const prefix = "🚀🔥💡 "; // 3 emojis (3 cp, 6 u16) + 1 space = 4 cp, 7 u16
  const source = `${prefix}${phrase} Attention: ${phrase}`;
  // Occ 1 in Python cp: start = 4, end = 19
  // Occ 2 in Python cp: start = 4 + 15 + 12 = 31, end = 31 + 15 = 46
  const pythonStartOcc2 = 31;
  const pythonEndOcc2 = 46;
  const res = highlightEvidence(source, phrase, pythonStartOcc2, pythonEndOcc2);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.segments.length, 2);
  assert.strictEqual(res.segments[0].text, `${prefix}${phrase} Attention: `);
  assert.strictEqual(res.segments[1].text, phrase);
  console.log("[PASS] 30. Multiple non-BMP characters before repeated evidence");
}

// 31. Task 1 Regression (Phase 3.3.2): Repeated phrases separated by different-length text
{
  const phrase = "Quiz on Monday";
  const source = `Notice: ${phrase}. Midterm examination next week. Reminder: ${phrase}.`;
  // Occ 1: start = 8, end = 22
  // Occ 2: start = 65, end = 79
  const pythonStartOcc2 = 65;
  const pythonEndOcc2 = 79;
  const res = highlightEvidence(source, phrase, pythonStartOcc2, pythonEndOcc2);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.segments.length, 3);
  assert.strictEqual(res.segments[0].text, `Notice: ${phrase}. Midterm examination next week. Reminder: `);
  assert.strictEqual(res.segments[1].text, phrase);
  assert.strictEqual(res.segments[2].text, ".");
  console.log("[PASS] 31. Repeated phrases separated by different-length text");
}

// 32. Task 1 Regression (Phase 3.3.2): Code-point offset whose direct UTF-16 slice could match another occurrence
{
  const prefix = "🚀🔥💡🎉🎯"; // 5 non-BMP emojis: 5 cp, 10 u16 units
  const phrase = "Quiz";
  const source = `${prefix}Quiz Quiz`;
  // In Python cp:
  // prefix: 0..5
  // Occ 1: 5..9
  // Occ 2: 10..14 (length 4)
  // In UTF-16 units:
  // prefix: 0..10
  // Occ 1: 10..14
  // Occ 2: 15..19
  // Notice that pythonStartOcc2 == 10, which matches Occ 1 in UTF-16!
  // Direct UTF-16 matching would incorrectly highlight Occ 1.
  // Authoritative code-point resolution correctly highlights Occ 2.
  const pythonStartOcc2 = 10;
  const pythonEndOcc2 = 14;
  const res = highlightEvidence(source, phrase, pythonStartOcc2, pythonEndOcc2);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.segments.length, 2);
  assert.strictEqual(res.segments[0].text, `${prefix}Quiz `);
  assert.strictEqual(res.segments[1].text, phrase);
  console.log("[PASS] 32. Code-point offset whose direct UTF-16 slice could match another occurrence");
}

// 33. Task 1 Regression (Phase 3.3.2): Multiline repeated evidence containing emojis
{
  const block = "Workshop 📝 Part 1:\nDate: 20/11/2026 ⏰";
  const prefix = "🎉 Notice:\n";
  const sep = "\n\nRepeat notice:\n";
  const source = `${prefix}${block}${sep}${block}`;
  const pythonStartOcc2 = 64;
  const pythonEndOcc2 = 101;
  const res = highlightEvidence(source, block, pythonStartOcc2, pythonEndOcc2);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.segments.length, 2);
  assert.strictEqual(res.segments[0].text, `${prefix}${block}${sep}`);
  assert.strictEqual(res.segments[1].text, block);
  console.log("[PASS] 33. Multiline repeated evidence containing emojis");
}

console.log("\nAll 33 highlightEvidence test scenarios PASSED successfully!");
