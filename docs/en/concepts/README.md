# Concepts

English | [中文](../../zh-CN/concepts/)

Loushang is organized around complex work, not just model calls.

## Method

A method is a structured work contract for a class of tasks. It defines when the method applies, which role the agent should take, which phase the work is in, what workflow to follow, what constraints and gates apply, and what artifacts or acceptance criteria should be produced.

The long-term goal is for methods to become executable and improvable assets, not static process documents.

## Session

A session is a durable record of a coding interaction. It preserves messages, tool events, model usage, diagnostics, and enough context to resume or inspect the work later.

## Tool

A tool is an executable capability made available to the agent. Tools should be governed by policy and surfaced clearly in the transcript.

## Extension

An extension is project-level Python code that contributes behavior to a coding session. Extensions can add hooks, tools, dynamic resources, commands, and flags without changing the core product code.

## Model Provider

A model provider combines provider identity, endpoint semantics, model capabilities, authentication, defaults, compatibility rules, and pricing metadata. Loushang resolves these through a model catalog so higher layers can request a model without hardcoding every provider detail.

## Work Product

A work product is an output that matters for delivery: code changes, review notes, exports, plans, research summaries, or other artifacts. Loushang's roadmap treats work products and acceptance criteria as first-class parts of complex work.
