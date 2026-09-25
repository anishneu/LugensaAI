## What changed and why

<!-- One or two plain sentences. What problem does this solve? -->

## How it was checked

- [ ] `pytest` (backend) passes
- [ ] `ruff check backend --select E9,F63,F7,F82,F401,F841 --exclude backend/.venv` passes
- [ ] `npm run lint`, `npx tsc -b`, `npm run build` and `npm run test:e2e` pass (if the front end changed)
- [ ] I added or updated a test for the change

## The project's rules

- [ ] No invented evidence, timestamps or sample data anywhere in the product
- [ ] Nothing new needs a paid service or a billed model API (optional, off-by-default sources are fine)
- [ ] Anything that could not be confirmed is reported in `limitations`, not hidden
- [ ] No keys or secrets in the diff
- [ ] The README or `docs/` say what is now true

<!-- If a result or a number changed, say what was measured and what was not. -->
