---
name: pr
description: Finish a piece of work on its issue branch: run make qc, review the diff, write the pull request from the template, push the branch and open the pull request. Never merges. Use when the user says "/pr", "open the pull request", "ship this branch", or when the work on an issue branch is done.
---

# Pull request

The pull request is where the work becomes reviewable: the checks, a review and the list of
what was not checked all land in it before the owner reads a line.

## Procedure

1. **Where am I.** The branch is `<issue number>-<slug>` and is not the default branch. The
   working tree is clean (everything committed). If not, stop and say so.
2. **Checks.** `make qc`. A failure is fixed first, or the pull request waits.
3. **Review.** Review the branch against the default branch (the `ponytail-review` skill when it
   is available). Fix what should be fixed, in a commit of its own. Keep the findings and what
   was done about each; they go in the body.
4. **Body.** Fill `.github/PULL_REQUEST_TEMPLATE.md`: what changed and why, `Closes #<n>`, the
   tests added or changed, the review findings and their outcome, and Not checked (what was
   skipped, what is uncertain, which load was assumed). The body is plain prose, no em dashes,
   nothing about the owner's private matters. End with the attribution line the session's
   reminder gives for pull requests.
5. **Show, then push.** Show the title and body to the user and wait for a yes. Then:

       git push -u origin <branch>
       gh pr create --title "<title>" --body-file <tmp> --label <label>

6. Report the pull request URL. Stop. The owner reviews and merges.

## Never

- Merge, or ask to merge. `gh pr merge` is denied in the settings and the default branch is
  protected; neither is to be worked around.
- Push to the default branch, force push, or rebase a pushed branch.
- Open a pull request without the issue. If none exists, run `/issue` first.
- Leave Not checked empty. "Nothing" is a claim that needs the same honesty as a finding.
