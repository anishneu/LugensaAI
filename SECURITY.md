# Security policy

## Reporting a vulnerability

Please report a security problem **privately**, not in a public issue.

Use GitHub's private reporting: on this repository, open **Security → Report a vulnerability**. That reaches the maintainer
([@anishneu](https://github.com/anishneu)) without making the report public. Please include what you found, how to reproduce it
(the request, the input, the version or commit), and what you think an attacker could do with it.

This is a personal project maintained in spare time, so there is no service level, but a private report will be read and answered.
Please give a reasonable time to fix a problem before disclosing it.

## What is in scope

Lugensa AI is meant to run **on your own machine**: a FastAPI backend, a React front end, and a local model through Ollama. It has
no accounts and no login, and its CORS setting only allows the local development ports. It is not designed to be exposed to the
internet as it is; anyone doing that is responsible for putting authentication and a proper CORS policy in front of it.

Things worth reporting:

- a secret (an API key, a token) committed to the repository or its history, or written to a log or a response;
- a way to make the backend fetch an address an attacker chooses (server-side request forgery), read a file it should not, or run code;
- a way to get script or markup from a source (a web page, a Reddit post, a news headline) to run in the page, or into a downloaded
  or printed report;
- a dependency with a known vulnerability that the project's audits (`pip-audit`, `npm audit`, Dependabot) do not already flag.

Not in scope: results that are simply wrong or thin (that is a normal bug, see the issue templates), and the fact that a public
search or forum returns something unpleasant about a place.

## What the project already does

- API keys live only in the gitignored `backend/.env`; the CI runs a secret scan over the full history on every push.
- Error text from an unexpected failure is logged on the server and not returned to the caller.
- Text from sources is escaped in the printable report and rendered as text, not markup, in the app; the XML feed parser refuses
  documents that declare a DOCTYPE or entities.
- CodeQL, `pip-audit`, `npm audit` and dependency review run in CI, and Dependabot opens grouped update pull requests.

## Supported versions

Only the latest commit on `main` is maintained.
