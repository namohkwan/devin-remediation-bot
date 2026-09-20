"""Prompt construction for remediation sessions."""

from __future__ import annotations

from app.adapters.github_client import GitHubIssue

MAX_BODY_CHARS = 6000

PROMPT_TEMPLATE = """You are remediating a GitHub issue in the repository {repo}.

Issue #{number}: {title}

Issue body:
{body}

Instructions:
1. Clone and work exclusively in {repo}.
2. Reproduce and diagnose the problem described above, then implement a
   minimal, focused fix that matches the surrounding conventions.
3. Run the relevant tests and lint checks for the code you touched and make
   them pass.
4. Open a pull request against the default branch titled exactly:
   "Fix #{number}"
5. When finished, write the following JSON object into structured_output:
   {{"pr_url": "<url of the pull request>", "result": "pass|fail"}}
   Use "pass" only if the fix is complete and the tests and lint checks you
   ran succeeded; otherwise use "fail".
"""


def build_remediation_prompt(issue: GitHubIssue, repo: str) -> str:
    """Render the Devin prompt for ``issue`` in ``repo``."""
    body = (issue.body or "").strip() or "(no description provided)"
    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS] + "\n... (truncated)"
    return PROMPT_TEMPLATE.format(
        repo=repo,
        number=issue.number,
        title=issue.title.strip() or f"Issue {issue.number}",
        body=body,
    )
