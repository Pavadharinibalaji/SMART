# SMART — Student Message Analysis and Retrieval Tool

**Turning scattered academic communications into actionable information.**

SMART is a student-focused academic communication intelligence system designed to identify, extract, and organise important academic information hidden in everyday messages.

Assignments, deadlines, exam announcements, schedule changes, and opportunities are often scattered across long WhatsApp conversations and multiple communication channels. Students end up manually searching messages, opening links, and trying to remember important dates.

I initiated SMART to explore a practical solution to this problem I experience firsthand.

## The Problem

Academic information is distributed across communication channels that were not designed to function as a unified academic information system.

- Important announcements get buried in lengthy conversations.
- Deadlines and examination updates are easy to overlook.
- Relevant links require manual searching and revisiting.
- The same information may appear across multiple sources.
- Informal messages can be ambiguous, incomplete, or contradictory.

The challenge is not simply storing reminders. It is identifying which information matters, understanding its context, and preserving enough evidence to trust the extracted result.

## The Proposed Solution

SMART aims to transform unstructured academic communications into structured, searchable, and actionable information.

The initial MVP focuses on exported WhatsApp chats. It is designed to identify academic information such as:

- Assignments and submission deadlines
- Examination announcements and schedule updates
- Academic events and important notices
- Internships, competitions, and other opportunities
- Relevant URLs and supporting message context

Each extracted item is intended to retain its original message as evidence. Ambiguous dates and uncertain classifications should be flagged for review instead of being silently treated as facts.

## How It Is Designed to Work

```text
WhatsApp Chat Export (.txt)
            |
            v
   Message Parsing
            |
            v
 Timestamp & Text Normalization
            |
            v
   Academic Information
        Extraction
      /           \
     v             v
 Rule-Based     LLM-Based
 Detection      Interpretation
      \           /
       v         v
     Validation & Deduplication
              |
              v
    Structured Academic Items
              |
              v
     Searchable Web Dashboard
```

The architecture combines deterministic processing with contextual interpretation. Rules handle predictable tasks, while an LLM can help interpret messages whose meaning depends on context. Validation is intended to prevent unsupported dates or classifications from being presented as confirmed information.

## Technical Approach

The planned MVP uses the following technologies:

| Component | Technology | Purpose |
|---|---|---|
| Backend API | Python, FastAPI | Expose processing functionality |
| Data validation | Pydantic | Validate structured extraction results |
| Message processing | Python, regex, datetime | Parse messages, links, and dates |
| Contextual extraction | LLM API | Interpret relevant messages |
| Database | SQLite | Store structured results locally |
| Web dashboard | Streamlit | Upload, search, filter, and review results |
| Testing | pytest | Validate parsing and extraction behaviour |

The technology choices prioritise a small, testable implementation that can be developed and evaluated quickly.

## Key Engineering Principles

**1. Evidence over unsupported assumptions**

Extracted information should retain the original message that supports it.

**2. Hybrid intelligence**

Use deterministic rules for predictable extraction tasks and an LLM where contextual interpretation is useful.

**3. Explicit uncertainty**

Do not invent missing deadlines or silently resolve conflicting information. Flag uncertain results for review.

**4. Source-independent design**

The long-term architecture is intended to support additional sources, such as Google Classroom and Gmail, through separate source adapters and a common processing pipeline.

**5. Privacy-conscious processing**

Begin with exported chat files and controlled sample data. Avoid exposing personal conversations or credentials in public repositories or unnecessary external API requests.

## Current Scope

The initial MVP is being developed in stages.

- [ ] WhatsApp `.txt` upload and message parsing
- [ ] Timestamp and multiline-message handling
- [ ] Academic category and link extraction
- [ ] Date detection and contextual interpretation
- [ ] Structured output validation and duplicate handling
- [ ] Source evidence and uncertainty indicators
- [ ] Searchable dashboard with filters
- [ ] Automated tests and documented evaluation

The long-term vision includes consolidating academic information across multiple communication sources. Google Classroom and Gmail integration are future extensions, not prerequisites for the initial MVP.

## Evaluation Plan

SMART will be evaluated using representative sample conversations containing relevant announcements, irrelevant messages, explicit and ambiguous dates, duplicate information, and conflicting details.

Planned evaluation measures include:

- Precision and recall of academic-information extraction
- Correctness of extracted dates and categories
- Validity of supporting source evidence
- Handling of duplicates and ambiguous messages
- Behaviour when the LLM service is unavailable

Performance and accuracy claims will be reported only after testing.

## Running the Project

Setup and execution instructions will be added as the implementation becomes runnable.

The intended local development workflow uses Python, a virtual environment, and a Streamlit web dashboard, with FastAPI providing the processing API.

## Why I Started SMART

SMART began with a problem I encountered in my own academic workflow, not an assigned project specification.

I wanted to explore whether software could do more than store information after a student manually enters it — whether it could identify useful information from existing communications, organise it, and preserve the evidence needed to trust it.

My objective is to build a practical, testable prototype, evaluate where it succeeds and fails, and improve it based on those results.

---

**Project:** SMART — Student Message Analysis and Retrieval Tool  
**Category:** Academic productivity / Information extraction  
**Status:** Initial implementation in progress  
**Author:** Pavadharini B G

*This repository documents the project as it evolves. Features, test results, and implementation status will be updated as they become available.*
