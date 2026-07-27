# Implementation plans

This folder records implementation roadmaps that are approved for delivery but
are not part of the completed product milestones. Each plan has its own progress
board and phase files. A phase may be marked `done` only after every required
checkbox, exit criterion, and stated validation passes.

## Active plans

| Progress | Plan | Outcome |
| --- | --- | --- |
| 5/5 phases | [Test-generation agent](test-generation-agent/README.md) | Natural-language Web UI test drafting, human review, and deterministic Playwright execution |

## Status rules

1. Start each phase as `planned` with all tasks unchecked.
2. Mark it `in progress` only while implementing it; update task checkboxes as focused work completes.
3. Mark it `done` only after its exit criterion and validation have passed, then update the plan overview in the same change.
4. Use `blocked — <reason>` for an external dependency or decision that stops delivery; do not mark incomplete work done.
