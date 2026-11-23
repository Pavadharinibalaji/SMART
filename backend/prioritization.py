"""Academic Context, Urgency Detection, and Intelligent Prioritization Module for SMART.

Provides deterministic, explainable rules for:
1. Academic relevance and intent classification (assignment, exam, lab, project, seminar,
   attendance, scholarship, placement, competition, workshop, administrative, announcement).
2. Explainable academic importance assessment (HIGH, MEDIUM, LOW, UNASSESSED) independent of urgency.
3. Real-time dynamic urgency detection (CRITICAL, HIGH, MEDIUM, LOW, NO_DEADLINE, NEEDS_REVIEW).
4. Composite explainable prioritization combining urgency, importance, actionability, and certainty.
5. Task relationship and lineage validation.
"""

from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any, Optional

ALLOWED_IMPORTANCE_LEVELS = {"HIGH", "MEDIUM", "LOW", "UNASSESSED"}
ALLOWED_URGENCY_LEVELS = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "NO_DEADLINE", "NEEDS_REVIEW"}
ALLOWED_PRIORITY_LEVELS = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


# ==============================================================================
# 1. Academic Relevance & Intent Classification
# ==============================================================================

def classify_academic_intent(
    category: str,
    title: str = "",
    text: str = "",
    actionability_type: str = "action_required",
) -> tuple[str, list[str]]:
    """Determine fine-grained academic intent while maintaining category compatibility.

    Categories:
    - assignment: homework, coursework, problem sets, submissions
    - exam: midterms, finals, semester exams, internal tests, quizzes, viva
    - laboratory: lab manuals, practicals, lab records, experiment reports
    - project: capstones, project milestones, demos, proposals, theses
    - seminar: presentations, guest lectures, department talks
    - attendance: shortages, condonations, roll calls, minimum percentages
    - scholarship: grants, fee waivers, financial aid, fellowships
    - placement: campus drives, recruitment, internship offers, interview rounds
    - competition: hackathons, coding contests, symposiums, paper presentations
    - workshop: hands-on workshops, training sessions, bootcamps
    - administrative: fees, hall tickets, registration, ID cards, circulars
    - academic_announcement: general timetable changes, class cancellations, notices
    """
    combined = f"{title} {text}".lower()
    reasons: list[str] = []

    # Priority 1: High-stakes examination & test markers
    if re.search(r"\b(?:semester\s+(?:exam|examination)|university\s+exam|midterm|internal\s+(?:assessment|test|exam)|quiz(?:zes)?|viva\s+voce|theory\s+exam|practical\s+exam)\b", combined):
        reasons.append("Identified as an examination or formal assessment requirement.")
        return "exam", reasons

    # Priority 2: Laboratory practicals and record work
    if re.search(r"\b(?:lab\s+(?:record|manual|submission|report|exercise|observation|practical)|chemistry\s+lab|physics\s+lab|computing\s+lab|hardware\s+lab)\b", combined):
        reasons.append("Identified as laboratory coursework or experimental submission.")
        return "laboratory", reasons

    # Priority 3: Project milestones & proposals
    if re.search(r"\b(?:project\s+(?:proposal|report|submission|demo|evaluation|presentation|phase\s*\d+|review)|capstone|thesis|dissertation)\b", combined):
        reasons.append("Identified as a major academic project milestone or deliverable.")
        return "project", reasons

    # Priority 4: Attendance requirements & warnings
    if re.search(r"\b(?:attendance\s+(?:shortage|percentage|condonation|requirement|eligibility)|lack\s+of\s+attendance|detained|detention)\b", combined):
        reasons.append("Identified as institutional attendance eligibility or condonation notice.")
        return "attendance", reasons

    # Priority 5: Placement & internship drives
    if re.search(r"\b(?:placement\s+drive|campus\s+(?:recruitment|interview)|recruitment\s+drive|internship\s+(?:opportunity|drive|offer)|job\s+application|package\s+(?:of\s+)?\d+\s*lpa)\b", combined):
        reasons.append("Identified as career, internship, or campus placement opportunity.")
        return "placement", reasons

    # Priority 6: Scholarships and financial aid
    if re.search(r"\b(?:scholarship|financial\s+aid|merit\s+award|tuition\s+waiver|fellowship\s+grant)\b", combined):
        reasons.append("Identified as an academic scholarship or financial assistance opportunity.")
        return "scholarship", reasons

    # Priority 7: Competitions, hackathons, symposiums
    if re.search(r"\b(?:hackathon|coding\s+(?:contest|challenge)|symposium|paper\s+presentation|quiz\s+competition)\b", combined):
        reasons.append("Identified as an academic competition, hackathon, or symposium.")
        return "competition", reasons

    # Priority 8: Technical workshops & training
    if re.search(r"\b(?:workshop|hands-on\s+training|bootcamp|technical\s+training)\b", combined):
        reasons.append("Identified as an interactive technical workshop or skill development session.")
        return "workshop", reasons

    # Priority 9: Seminars & guest lectures
    if re.search(r"\b(?:seminar|guest\s+lecture|invited\s+talk|colloquium|webinar)\b", combined):
        reasons.append("Identified as an academic seminar or educational presentation.")
        return "seminar", reasons

    # Priority 10: Administrative notices & fee deadlines
    if re.search(r"\b(?:tuition\s+fees?|exam\s+fees?|fee\s+payment|hall\s+tickets?|admit\s+cards?|course\s+registration|id\s+card|semester\s+registration|circular)\b", combined):
        reasons.append("Identified as an institutional administrative requirement.")
        return "administrative", reasons

    # Priority 11: General assignments & homework
    if category == "Assignment" or re.search(r"\b(?:assignment|homework|coursework|problem\s+set|tutorial\s+sheet|submit|submission)\b", combined):
        reasons.append("Identified as a student assignment or routine course deliverable.")
        return "assignment", reasons

    # Priority 12: General events
    if category == "Event":
        reasons.append("Identified as an institutional event or gathering.")
        return "academic_event", reasons

    # Default: General Academic Announcement
    reasons.append("General institutional or academic announcement.")
    return "academic_announcement", reasons


# ==============================================================================
# 2. Academic Importance Assessment
# ==============================================================================

def assess_academic_importance(
    category: str,
    academic_intent: str,
    title: str = "",
    text: str = "",
    is_actionable: bool = True,
    status: str = "pending",
) -> tuple[str, list[str]]:
    """Determine explainable, objective academic importance independent of deadline timing.

    Levels:
    - HIGH: Direct impact on course completion, grading, graduation, or career.
            (Final/semester exams, high-weightage submissions, mandatory attendance condonation,
             placements with mandatory registration).
    - MEDIUM: Core regular academic coursework and assessment.
              (Standard assignments, lab manuals, quizzes, project milestone proposals).
    - LOW: Optional activities, casual clubs, or supplemental participation.
           (Optional webinars, guest lectures, extracurriculars without grading credit).
    - UNASSESSED: Generic announcements where grading weight or academic criticality cannot be inferred.
    """
    clean_status = (status or "").lower()
    combined = f"{title} {text}".lower()
    reasons: list[str] = []

    # 1. Superseded / Cancelled tasks
    if clean_status in ("cancelled", "superseded"):
        reasons.append(f"Task is {clean_status}; academic importance is marked LOW as deliverable is inactive.")
        return "LOW", reasons

    # 2. High-stakes academic imperatives
    # Major exams
    if academic_intent == "exam" and re.search(r"\b(?:semester\s+exam|final\s+exam|university\s+exam|end-sem|mid-?term|comprehensive\s+viva)\b", combined):
        reasons.append("High importance: Major formal examination impacting course completion and GPA.")
        return "HIGH", reasons

    # Explicit grade weightage / mandatory statements
    if re.search(r"\b(?:counts?\s+for|\bweights?|\bweightage\b|\bmarks?\b|\bcredits?\b|strictly\s+mandatory|mandatory\s+for\s+passing|compulsory\s+for\s+all)\b", combined):
        reasons.append("High importance: Deliverable carries explicit grading weight, credits, or mandatory completion status.")
        return "HIGH", reasons

    # Major capstone / final thesis
    if academic_intent == "project" and re.search(r"\b(?:final\s+(?:report|demo|submission|defense)|thesis|capstone|dissertation)\b", combined):
        reasons.append("High importance: Culminating capstone, thesis, or final project evaluation.")
        return "HIGH", reasons

    # Critical attendance shortage notices
    if academic_intent == "attendance" and re.search(r"\b(?:shortage|detained|detention|condonation|ineligible)\b", combined):
        reasons.append("High importance: Institutional attendance shortage warning impacting exam eligibility.")
        return "HIGH", reasons

    # Campus placements & recruitment drives
    if academic_intent == "placement":
        reasons.append("High importance: Direct career, internship, or campus recruitment opportunity.")
        return "HIGH", reasons

    # 3. Medium-stakes core coursework
    if academic_intent in ("assignment", "laboratory", "project", "exam"):
        reasons.append("Medium importance: Standard academic course deliverable or continuous assessment.")
        return "MEDIUM", reasons

    if academic_intent in ("workshop", "scholarship", "administrative"):
        reasons.append("Medium importance: Relevant academic development or institutional requirement.")
        return "MEDIUM", reasons

    # 4. Low-stakes or optional items
    if re.search(r"\b(?:optional|voluntary|open\s+to\s+interested|extra\s+curricular|club\s+meeting|casual)\b", combined):
        reasons.append("Low importance: Optional activity or supplemental student participation.")
        return "LOW", reasons

    if academic_intent in ("competition", "seminar", "academic_event"):
        reasons.append("Low importance: Co-curricular enrichment or non-mandatory presentation.")
        return "LOW", reasons

    # 5. Non-actionable announcements
    if not is_actionable or category == "Announcement":
        reasons.append("Unassessed importance: Informational announcement with no grading or submission weight specified.")
        return "UNASSESSED", reasons

    return "UNASSESSED", ["Importance unassessed: Insufficient indicators to establish grading weight."]


# ==============================================================================
# 3. Urgency Detection
# ==============================================================================

def assess_task_urgency(
    due_date: str | None,
    date_status: str | None,
    status: str = "pending",
    current_date: date | None = None,
    text: str = "",
) -> tuple[str, list[str], int | None]:
    """Calculate dynamic, explainable temporal urgency relative to the current calendar date.

    Levels:
    - CRITICAL: Overdue (<0 days), due today (0 days), or due tomorrow (1 day).
    - HIGH: Due within 2 to 3 days.
    - MEDIUM: Due within 4 to 7 days.
    - LOW: Due in more than 7 days, or inactive.
    - NO_DEADLINE: No explicit deadline specified.
    - NEEDS_REVIEW: Ambiguous date or unresolved temporal expression.
    """
    clean_status = (status or "").lower()
    ref_date = current_date or date.today()
    reasons: list[str] = []

    # 1. Inactive items
    if clean_status in ("cancelled", "superseded", "completed", "dismissed"):
        reasons.append(f"Task is {clean_status}; temporal urgency is inactive.")
        return "LOW", reasons, None

    # 2. Date needs review / unresolved
    if date_status == "needs_review":
        reasons.append("Temporal urgency is unconfirmed because the date expression requires human review.")
        return "NEEDS_REVIEW", reasons, None

    # 3. No deadline
    if not due_date or date_status == "not_found":
        reasons.append("No explicit deadline specified; task cannot be scheduled with temporal urgency.")
        return "NO_DEADLINE", reasons, None

    # 4. Date calculation
    try:
        target_date = datetime.strptime(str(due_date).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        reasons.append(f"Invalid date format '{due_date}'; marked for review.")
        return "NEEDS_REVIEW", reasons, None

    delta_days = (target_date - ref_date).days

    # Explicit urgent language in announcement (urgent, immediately, emergency)
    has_urgent_lang = bool(re.search(r"\b(?:urgently?|immediately|without\s+delay|at\s+the\s+earliest)\b", text, re.I))

    # Overdue
    if delta_days < 0:
        overdue_by = abs(delta_days)
        reasons.append(f"Critical urgency: Task is overdue by {overdue_by} day(s) (deadline was {due_date}).")
        return "CRITICAL", reasons, delta_days

    # Due Today
    if delta_days == 0:
        reasons.append(f"Critical urgency: Confirmed deadline is TODAY ({due_date}). Immediate action required.")
        return "CRITICAL", reasons, delta_days

    # Due Tomorrow
    if delta_days == 1:
        reasons.append(f"Critical urgency: Confirmed deadline is TOMORROW ({due_date}). Urgent completion required.")
        return "CRITICAL", reasons, delta_days

    # Approaching within 2-3 days
    if 2 <= delta_days <= 3:
        note = " (explicit urgent directive flagged in source text)" if has_urgent_lang else ""
        reasons.append(f"High urgency: Confirmed deadline is approaching in {delta_days} days ({due_date}){note}.")
        return "HIGH", reasons, delta_days

    # Within a week (4-7 days)
    if 4 <= delta_days <= 7:
        if has_urgent_lang:
            reasons.append(f"High urgency: Due in {delta_days} days ({due_date}), boosted by explicit urgency language.")
            return "HIGH", reasons, delta_days
        reasons.append(f"Medium urgency: Deadline in {delta_days} days ({due_date}).")
        return "MEDIUM", reasons, delta_days

    # More than a week (>7 days)
    reasons.append(f"Low urgency: Deadline is {delta_days} days away ({due_date}); ample time remaining.")
    return "LOW", reasons, delta_days


# ==============================================================================
# 4. Composite Explainable Prioritization Engine
# ==============================================================================

def calculate_priority(
    urgency: str,
    importance: str,
    is_actionable: bool | None = True,
    status: str = "pending",
    date_status: str | None = None,
    delta_days: int | None = None,
    review_required: bool = False,
) -> tuple[str, list[str]]:
    """Synthesize urgency, importance, actionability, and certainty into an explainable priority.

    Levels:
    - CRITICAL: Overdue deliverables, deadlines today or tomorrow, or high-importance items due within 3 days.
    - HIGH: Important tasks due within a week, imminent deadlines (2-3 days), or high-importance review flags.
    - MEDIUM: Core deliverables with moderate deadlines, or important items with distant/no deadlines.
    - LOW: Inactive tasks, informational announcements, optional activities, or low-urgency tasks.
    """
    clean_status = (status or "").lower()
    reasons: list[str] = []

    # 1. Inactive status -> LOW
    if clean_status in ("cancelled", "superseded", "completed", "dismissed"):
        reasons.append(f"Low priority: Task is {clean_status} and no longer requires active scheduling.")
        return "LOW", reasons

    # 2. Informational announcements -> LOW
    if is_actionable is False:
        reasons.append("Low priority: Informational announcement with no required student deliverable.")
        return "LOW", reasons

    # 3. Overdue -> CRITICAL
    if delta_days is not None and delta_days < 0:
        reasons.append(f"Critical priority: Actionable task is overdue by {abs(delta_days)} day(s). Immediate resolution needed.")
        return "CRITICAL", reasons

    # 4. Urgent deadlines (today or tomorrow) -> CRITICAL
    if urgency == "CRITICAL":
        target_desc = "today" if delta_days == 0 else ("tomorrow" if delta_days == 1 else "imminent")
        reasons.append(f"Critical priority: Submission deadline is {target_desc}.")
        return "CRITICAL", reasons

    # 5. High Importance + Approaching Deadline -> CRITICAL or HIGH
    if importance == "HIGH":
        if urgency == "HIGH":
            reasons.append(f"Critical priority: High-importance academic requirement due in {delta_days} days.")
            return "CRITICAL", reasons
        if urgency == "MEDIUM":
            reasons.append(f"High priority: High-importance academic requirement due in {delta_days} days.")
            return "HIGH", reasons
        if urgency in ("LOW", "NO_DEADLINE"):
            reasons.append("Medium priority: Major academic requirement, but deadline is not immediate.")
            return "MEDIUM", reasons
        if urgency == "NEEDS_REVIEW":
            reasons.append("High priority: Major academic requirement with an unconfirmed deadline requiring human verification.")
            return "HIGH", reasons

    # 6. High Urgency (2-3 days) with MEDIUM or LOW importance -> HIGH
    if urgency == "HIGH":
        reasons.append(f"High priority: Confirmed submission deadline approaching in {delta_days} days.")
        return "HIGH", reasons

    # 7. Ambiguous timing requiring human confirmation -> HIGH / MEDIUM
    if date_status == "needs_review" or review_required:
        reasons.append("Medium priority: Item flagged for human review to verify deadline details.")
        return "MEDIUM", reasons

    # 8. Medium Urgency (4-7 days) -> MEDIUM
    if urgency == "MEDIUM":
        reasons.append(f"Medium priority: Active task due in {delta_days} days.")
        return "MEDIUM", reasons

    # 9. Low Urgency or No Deadline -> LOW
    if urgency == "NO_DEADLINE":
        reasons.append("Low priority: Active task without a confirmed deadline.")
        return "LOW", reasons

    reasons.append("Low priority: Ample preparation time remaining before deadline.")
    return "LOW", reasons


# ==============================================================================
# 5. Enrichment Helper
# ==============================================================================

def enrich_task_with_prioritization(
    item: dict[str, Any],
    current_date: date | None = None,
) -> dict[str, Any]:
    """Pure transformation enriching an academic item dictionary with dynamic prioritization context.

    Adds:
    - academic_intent
    - academic_intent_reasons
    - importance (preserves user-persisted/custom value if valid; otherwise assesses)
    - importance_reasons
    - urgency
    - urgency_reasons
    - delta_days
    - priority
    - priority_reasons
    """
    enriched = dict(item)

    category = enriched.get("category") or "Announcement"
    title = enriched.get("title") or ""
    text = enriched.get("source_text") or enriched.get("description") or ""
    act_type = enriched.get("actionability_type") or "action_required"
    is_actionable = enriched.get("is_actionable")
    if is_actionable is None:
        is_actionable = False if category == "Announcement" else True

    status = enriched.get("status") or "pending"
    due_date = enriched.get("due_date")
    date_status = enriched.get("date_status")
    review_req = bool(enriched.get("review_required"))

    # 1. Academic Intent
    intent, intent_reasons = classify_academic_intent(
        category=category,
        title=title,
        text=text,
        actionability_type=act_type,
    )
    enriched["academic_intent"] = intent
    enriched["academic_intent_reasons"] = intent_reasons

    # 2. Importance
    existing_importance = enriched.get("importance")
    if existing_importance and str(existing_importance).upper() in ALLOWED_IMPORTANCE_LEVELS and str(existing_importance).upper() != "UNASSESSED":
        importance = str(existing_importance).upper()
        importance_reasons = ["Importance explicitly specified or preserved from task record."]
    else:
        importance, importance_reasons = assess_academic_importance(
            category=category,
            academic_intent=intent,
            title=title,
            text=text,
            is_actionable=is_actionable,
            status=status,
        )
    enriched["importance"] = importance
    enriched["importance_reasons"] = importance_reasons

    # 3. Urgency
    urgency, urgency_reasons, delta_days = assess_task_urgency(
        due_date=due_date,
        date_status=date_status,
        status=status,
        current_date=current_date,
        text=text,
    )
    enriched["urgency"] = urgency
    enriched["urgency_reasons"] = urgency_reasons
    enriched["delta_days"] = delta_days

    # 4. Priority
    priority, priority_reasons = calculate_priority(
        urgency=urgency,
        importance=importance,
        is_actionable=is_actionable,
        status=status,
        date_status=date_status,
        delta_days=delta_days,
        review_required=review_req,
    )
    enriched["priority"] = priority
    enriched["priority_reasons"] = priority_reasons

    return enriched
