# Devin Remediation Bot

Event-driven automation that remediates GitHub issues in [`namohkwan/superset`](https://github.com/namohkwan/superset) with the [Devin API](https://docs.devin.ai/api-reference/overview).

A labelled issue becomes a Devin session, the session becomes a pull request, and every run is tracked until it reaches a terminal state. Two entry points exist, and both execute the same orchestration path:

| Mode | Entry point | Typical use |
| --- | --- | --- |
| Manual / simulation | `python -m app.cli run --issue <n>` | Driving one issue at a time, and rehearsing webhook payloads offline |
| Webhook | `POST /webhook` | Production trigger: an `issues` event carrying the `devin-fix` label |

## Architecture

```
                 manual trigger                         webhook trigger
             python -m app.cli run                  POST /webhook (GitHub)
                        │                                     │
                        │                            HMAC X-Hub-Signature-256
                        ▼                                     ▼
                ┌───────────────────────────────────────────────────┐
  presentation  │            app/cli.py      app/api/*.py           │
                └───────────────────────────┬───────────────────────┘
                                            │ run_for_issue(number)
                ┌───────────────────────────▼───────────────────────┐
  core          │  app/core/orchestrator.py  +  app/core/prompts.py │
                └───────┬───────────────────────────────┬───────────┘
                        │                               │
        ┌───────────────▼──────────────┐   ┌────────────▼───────────┐
 adapters│ github_client  devin_client │   │ store/ (SQLite behind  │
        │ (HTTP only, no logic)        │   │ RemediationStore ABC)  │
        └───────────────┬──────────────┘   └────────────────────────┘
                        │
              GitHub REST   Devin API
```

Flow: a trigger passes an issue number to the orchestrator → the GitHub adapter fetches the issue → a prompt is rendered → the Devin adapter creates a session → the run is persisted → `app/services/poller.py` polls the session until `structured_output` reports `pr_url` and `result`, which the dashboard renders at `/status`.

### Dependency rules

Dependencies flow in one direction: **presentation → core → adapters / store**.

- `app/api/` and `app/cli.py` talk to `app/core/orchestrator.py` and nothing else, which is what keeps the two trigger modes from drifting apart.
- The orchestrator receives its adapters and store through constructor injection, so tests substitute fakes without patching module globals.
- `app/adapters/` performs external HTTP calls only, confining Devin and GitHub API changes to a single package.
- `app/store/` persists runs behind the `RemediationStore` interface; SQLite is an implementation detail, not a dependency of the core.
- `app/config.py` is the only module that reads the environment.

### Folder structure

```
app/
├── config.py            # central env/secrets loading + fail-fast validation
├── main.py              # FastAPI entrypoint; registers routers only
├── cli.py               # manual/simulation trigger mode
├── api/
│   ├── webhook.py       # POST /webhook — issues events, HMAC verification
│   └── dashboard.py     # GET /status (HTML), GET /poll (JSON), GET /healthz
├── adapters/
│   ├── github_client.py # get_issue(number)
│   └── devin_client.py  # create_session(prompt), get_session(session_id)
├── core/
│   ├── prompts.py       # remediation prompt template
│   └── orchestrator.py  # shared orchestration, constructor injection
├── store/
│   ├── models.py        # RemediationRun, RunStatus
│   └── sqlite_store.py  # RemediationStore interface + SQLite implementation
├── services/
│   ├── poller.py        # background refresh of in-flight sessions
│   └── reporting.py     # serialization for dashboard/CLI output
└── templates/status.html
tests/                   # mirrors app/, adapters mocked
samples/labeled_event.json
```

## Security notice

- **Never commit real keys.** All secrets are injected through environment variables and read exclusively in `app/config.py`. No other module reads the environment or contains a credential.
- The root `.gitignore` excludes `.env`, `*.env`, `.env.local`, `*.db`, and `__pycache__/`. `.env.example` contains placeholders only.
- Secrets are never logged. `Settings.describe()` returns a redacted view (`***configured***`) and is what startup logging and the dashboard use.
- `/webhook` verifies the `X-Hub-Signature-256` HMAC with `GITHUB_WEBHOOK_SECRET` and rejects unsigned or forged deliveries with `401`.
- If a credential is ever exposed, revoke and reissue it immediately: Devin API keys at https://app.devin.ai/settings/api-keys, GitHub tokens at https://github.com/settings/tokens, and the webhook secret in the repository's webhook settings.

## Credentials

| Variable | Where to get it |
| --- | --- |
| `DEVIN_API_KEY` | https://app.devin.ai/settings/api-keys → **Create new API key**. Copy it once; it is not shown again. |
| `GITHUB_TOKEN` | https://github.com/settings/personal-access-tokens → fine-grained token scoped to `namohkwan/superset` with **Issues: Read** (add **Pull requests: Read** to inspect resulting PRs). A classic token needs `repo`. |
| `GITHUB_WEBHOOK_SECRET` | Generate locally, e.g. `python -c "import secrets; print(secrets.token_hex(32))"`, and paste the same value into the GitHub webhook configuration. |
| `TARGET_REPO` | `namohkwan/superset` |

## Setup

```bash
git clone https://github.com/namohkwan/devin-remediation-bot.git
cd devin-remediation-bot
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env    # then fill in real values; .env is git-ignored
```

Missing or blank required variables abort startup with an explicit message:

```
Configuration error: Missing required environment variable(s): DEVIN_API_KEY, ...
```

## Manual mode

```bash
# Remediate a single issue end to end
python -m app.cli run --issue 101

# Replay a stored GitHub event payload without exposing a public endpoint
python -m app.cli simulate --event samples/labeled_event.json

# Inspect all recorded runs as JSON
python -m app.cli status

# Poll Devin for in-flight sessions first, then print
python -m app.cli status --refresh

# Follow progress in the terminal until every run reaches a terminal state
python -m app.cli watch --interval 15
python -m app.cli watch --issue 1
```

`run` returns as soon as the Devin session is created, printing the persisted run with its `session_id` and session URL. The outcome (`pr_url`, `result`) arrives later: re-run `status --refresh`, follow it live with `watch`, or open `/status`, where the background poller updates runs automatically.

`watch` polls on the given interval and prints a timestamped line whenever a run changes, exiting once all watched runs have succeeded or failed (exit code 1 if any failed).

Run statuses are `pending`, `running`, `awaiting_input` (Devin is blocked on a reply — the session is alive and its pull request, if any, is already recorded), `succeeded`, and `failed`.

## Webhook mode

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Register the webhook in `namohkwan/superset` → **Settings → Webhooks → Add webhook**:

- **Payload URL**: `https://<your-host>/webhook` (for local testing, expose port 8000 with a tunnel such as `cloudflared tunnel --url http://localhost:8000`)
- **Content type**: `application/json`
- **Secret**: the same value as `GITHUB_WEBHOOK_SECRET`
- **Events**: *Let me select individual events* → **Issues**

Adding the `devin-fix` label to an issue sends an `issues`/`labeled` event; the bot verifies the signature and starts a Devin session. Every other action, label, and event type is ignored.

### Why a human-triaged label, not every new issue

The webhook deliberately triggers on `labeled` rather than `opened`, so a person decides which issues the bot picks up:

- **Explicit approval boundary.** Whether an issue is safe to automate depends on context the payload does not carry — priority, security impact, release timing, and whether the reported behavior is even a bug. The label records that judgement, and GitHub's issue timeline shows who granted it and when.
- **Cost and noise control.** Starting a session for every new issue spends Devin time on duplicates, questions, and support requests. The label keeps sessions proportional to issues actually worth automating.
- **Scoped to work Devin does well.** Self-contained fixes (dependency bumps, small refactors, well-specified bugs) succeed far more often than open-ended design work; a human filter keeps the success rate — and reviewer trust — high.

Automated triage is a natural extension: handle `action == "opened"`, run a classification prompt first, and have Devin *suggest* labels while a person still approves the remediation. That inverts the trust model, so it belongs after the label-gated flow has a track record.

## Docker

```bash
cp .env.example .env    # fill in real values
docker compose up --build
```

`docker-compose.yml` reads secrets from the local `.env` and stores the SQLite database in a named volume, so no credentials or database files enter the image or the repository.

## Dashboard

- `GET /status` — HTML dashboard listing every run with its issue, trigger, status, Devin session link, and pull request URL (auto-refreshes every 30 seconds).
- `GET /poll` — refreshes in-flight sessions and returns the same report as JSON.
- `GET /healthz` — liveness probe.

## Devin integration

- `create_session(prompt)` → `POST https://api.devin.ai/v1/sessions` with `Authorization: Bearer $DEVIN_API_KEY` and body `{"prompt": ..., "idempotent": true}`. The idempotency flag means a repeated trigger for the same issue rejoins the existing session instead of duplicating work.
- `get_session(session_id)` → `GET https://api.devin.ai/v1/session/{session_id}`, read for `status_enum`, any attached pull request, and `structured_output`.

The prompt instructs Devin to work in `namohkwan/superset`, implement the fix, run the relevant tests and lint checks, open a pull request titled `Fix #<issue_number>`, and report `{"pr_url": ..., "result": "pass|fail"}` through `structured_output`. A terminal session reporting `pass` marks the run succeeded; anything else marks it failed.

## Tests

```bash
pytest
```

The suite mirrors `app/` and stubs both external APIs at the transport boundary: orchestration call order and persistence (`test_orchestrator.py`), adapter request shape and response parsing (`test_devin_client.py`, `test_github_client.py`), store CRUD (`test_store.py`), fail-fast configuration (`test_config.py`), webhook HMAC and label filtering plus dashboard rendering (`test_webhook.py`), and the CLI trigger mode (`test_cli.py`).
