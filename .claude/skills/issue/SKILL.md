---
name: issue
description: Turn a block of the plan, or a piece of work the user describes, into one GitHub issue from the repository's template (goal, done when, tests to write, out of scope, one label). Use when the user says "/issue", "open an issue for this", "file that as an issue", or when a plan block is approved and needs its issue before work starts.
---

# Issue

One issue, one branch, one pull request. This skill writes the issue. Nothing starts on a
branch until its issue exists, because the issue holds the tests the owner approves.

## Procedure

1. Read the source: the plan block, or what the user described. If the goal or the done-when
   is unclear, ask one question, then write.
2. Fill the template in `.github/ISSUE_TEMPLATE/work.md`. Every section is filled; "none" is
   an acceptable value for Out of scope. The Tests section lists the tests by name and what
   each one asserts. This list is what the owner approves by leaving it in the issue.
3. Pick one label: `record` (changes what is archived or scored), `page` (the app and
   `site.py`), `plumbing` (tooling, CI, process), `docs`. If a milestone is open
   (`gh api repos/{owner}/{repo}/milestones`), put the issue on it.
4. Check the text: no em dashes, no hedging, no claim without a number or a reference, and
   nothing about the owner's private matters. The owner's own guard hook also checks the
   command; if it blocks, do not reword to get past it. Say what was blocked and stop.
5. Show the title and body to the user and wait for a yes. Then:

       gh issue create --title "<title>" --body-file <tmp> --label <label>

6. Report the issue URL and the branch name the work will use: `<number>-<slug>`.

## Rules

- One issue per invocation. A block that needs two issues is two invocations.
- The title is a verb phrase under 70 characters ("Never overwrite an issued forecast").
- Done-when is observable: a file exists, a test passes, a page shows a number. Not "works".
- Plain language. The repository is public.
