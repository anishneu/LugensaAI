# Contributing

Thanks for looking. This is a personal project, so the bar is "it helps and it keeps the project's rules", not a formal process.

## The rules that matter most

These come from what the project is for, and a change that breaks one will not be merged however useful it looks:

1. **Never invent evidence.** No made-up sources, quotes, timestamps or statistics anywhere in the product. With nothing configured
   the app says so; it does not fall back to sample data. Invented fixtures live only under `backend/tests` and a test enforces that.
2. **Keep it free to run.** No billed model API. Paid or key-gated sources (Tavily, Google Places) stay optional and off by default.
3. **Say what could not be confirmed.** A fallback, a failure or a filtered-out result is recorded in the response's `limitations`,
   not hidden.
4. **The claim verifier stays deterministic** and never becomes an LLM call.
5. **No secrets in commits.** Keys go in `backend/.env` (gitignored). Do not paste a key into an issue, a test or a log.

## Setting up

```bash
# backend
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# frontend, in another terminal
cd frontend
npm install
npm run dev
```

Nothing needs a key to run; see the README's Configuration table for what each optional variable enables.

## Before you open a pull request

Run what CI runs:

```bash
cd backend
pytest                                                      # offline; makes no network call and spends no credit
pip install ruff && ruff check . --select E9,F63,F7,F82,F401,F841 --exclude .venv

cd ../frontend
npm run lint && npx tsc -b && npm run build
npx playwright install chromium && npm run test:e2e        # browser tests, backend mocked
```

- Add a test for what you change. The backend suite must stay offline and deterministic (an autouse fixture forces real keys off);
  the browser tests mock every backend call.
- If you change how something behaves, update the README or the relevant file under `docs/` in the same pull request. The docs
  say what was measured and what was not, and they should stay true.
- Keep a change focused: one thing per pull request is easier to review than five.

## Branches and commits

Work on `develop` (or a branch from it) and open a pull request into `main`. Write commit messages that say what changed and why,
in plain words. Please do not add automated attribution lines or co-author trailers to commits.

## Reporting a bug

Use the bug template. The most useful things to include are the place you searched, the exact question, and the `limitations` text
from the response (it usually says what went wrong). Do not include keys. For a security problem, see [SECURITY.md](SECURITY.md).
