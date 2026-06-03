# Public Docs Bilingual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reframe the GitHub-facing documentation around bilingual public onboarding while moving existing design, architecture, glossary, and planning material into `docs/internals/`.

**Architecture:** Keep `README.md` as the English GitHub landing page and add `README.zh-CN.md` as the Chinese sibling. Use mirrored `docs/en/` and `docs/zh-CN/` public trees for onboarding, user guides, concepts, SDK docs, examples, reference, roadmap, and contributing. Preserve existing historical and design documents under `docs/internals/` so they remain available without dominating the public documentation navigation.

**Tech Stack:** Markdown, GitHub-rendered relative links, existing Python project metadata, existing CLI surfaces.

---

### Task 1: Move Existing Internal Documentation

**Files:**
- Move: `docs/architecture/` to `docs/internals/architecture/`
- Move: `docs/experimental/` to `docs/internals/experimental/`
- Move: `docs/glossary/` to `docs/internals/glossary/`
- Move: `docs/strategy/` to `docs/internals/strategy/`
- Move: `docs/superpowers/specs/` to `docs/internals/specs/`
- Move: `docs/superpowers/plans/` to `docs/internals/plans/archive/`
- Move: selected root-level internal documents to `docs/internals/legacy/`

- [x] **Step 1: Create internal target directories**

Run: `mkdir -p docs/internals/{architecture,experimental,glossary,strategy,specs,plans/archive,legacy}`

Expected: directories exist.

- [x] **Step 2: Move existing documentation with `git mv`**

Run `git mv` for the directories and root-level internal docs listed above.

Expected: `git status --short` shows renames, not delete/add churn where Git can detect moves.

### Task 2: Add Public Bilingual Documentation Skeleton

**Files:**
- Create: `docs/index.md`
- Create mirrored files under `docs/en/` and `docs/zh-CN/`

- [x] **Step 1: Create public docs directories**

Run: `mkdir -p docs/en/{getting-started,user-guide,concepts,sdk,examples,reference} docs/zh-CN/{getting-started,user-guide,concepts,sdk,examples,reference}`

Expected: public docs tree exists.

- [x] **Step 2: Add public index and section pages**

Create concise landing pages for each section. Each page must include a language switch and target the current `loushang code` / `loushang.ai` reality.

Expected: public docs explain the intended reading paths without exposing architecture specs as primary navigation.

### Task 3: Rewrite Root README In English And Add Chinese README

**Files:**
- Modify: `README.md`
- Create: `README.zh-CN.md`

- [x] **Step 1: Replace existing README with English public landing page**

Include: positioning, current focus, why Loushang, current capabilities, quick start from source, documentation links, examples, roadmap, project status, acknowledgements, license.

Expected: GitHub visitors can understand and try `loushang code` without reading internal design docs.

- [x] **Step 2: Add matching Chinese README**

Mirror the English structure while using natural Chinese wording.

Expected: Chinese readers get the same information and navigation.

### Task 4: Verify Links And Repository State

**Files:**
- Inspect all changed Markdown files.

- [x] **Step 1: Check status**

Run: `git status --short`

Expected: only documentation changes and moves.

- [x] **Step 2: Check Markdown links syntactically**

Run a local script or command that extracts relative Markdown links from changed public docs and confirms target paths exist.

Expected: no missing relative links among the changed public docs.

- [x] **Step 3: Check high-level docs inventory**

Run: `find docs -maxdepth 3 -type d | sort`

Expected: public docs live under `docs/en` and `docs/zh-CN`; old design material lives under `docs/internals`.
