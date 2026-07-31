# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

This is **not yet a codebase** — it currently contains a single planning document, `fondtale-project-brief.md`, and no source code, build tooling, tests, or git history. There is nothing to build, lint, or run yet.

When work begins here, expect the first tasks to be scaffolding a new project from scratch (choosing a stack, initializing git, setting up tooling) rather than modifying existing code. Read `fondtale-project-brief.md` in full before making technical decisions — it is the source of truth for product intent.

## What Fondtale is

Fondtale is a planned product for Russian-speaking parents: an app/site where parents record a child's growth (milestones, growth stats, quotes/phrases, interests, free-form memories with photos/video) which is later assembled into a themed keepsake book, delivered at a chosen milestone (coming of age, graduation, birthday). The brief frames it against Qeepsake (US) as the closest competitor and lays out where Fondtale intends to differentiate — thematic categories instead of a single chronological Q&A feed, explicit authorship per family contributor, and a monetization model that doesn't lock users out of their own data.

## Key open decisions (per brief section 6)

These are explicitly **unresolved** — don't assume answers when proposing implementation:

- **Tech stack/architecture**: not chosen yet. This is expected to be worked out in Claude Code going forward.
- **Format**: full app vs. website vs. Telegram bot for the initial launch — undecided.
- **User input cadence/triggers**: whether to use prompt-based nudges (Qeepsake uses SMS prompts) and how to avoid the repetitive-question complaint the brief identifies as Qeepsake's biggest weakness.
- **Monetization**: subscription model and free/paid split not defined, beyond the stated principle that users should never lose access to their own already-entered data.
- **Book/artifact design**: layout, typography, and print options not designed.
- **Infrastructure**: domain/hosting/legal-entity setup (`.com` vs `.ru` strategy is decided — see brief section 4 — but not yet implemented).

## Product structure (from the brief, section 5)

The diary is organized into thematic sections that double as chapters of the final printed book, rather than one chronological feed:

1. Child profile (name, DOB, birthplace, birth height/weight)
2. Growth & development (structured height/weight over time + dated milestones, meant to be graphed)
3. Words & phrases (standalone collection, not buried in a general feed)
4. Interests & personality (a living record that tracks change over time, not a one-off entry)
5. Memories/moments (free-form feed with tags for filtering, e.g. trip/everyday/holiday/family)
6. Family contributions (memories explicitly attributed to which family member added them)
7. Final book/capsule (assembled by theme/chapter, not export order, with a configurable delivery date)

If asked to design data models or app structure, this section is the intended shape of the domain — not an arbitrary technical choice.
