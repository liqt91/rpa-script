# ADR 0005 — Gitea-Based Desktop Update Check (Plan A)

- **Status:** accepted
- **Date:** 2026-06-10
- **Deciders:** project owner

## Context

The desktop app is distributed as a single PyInstaller exe. Users currently have no way to know when a newer build is available unless they manually check the release page. We want a lightweight "Plan A" update flow:

1. Check the latest release version at startup.
2. Notify the user when a newer version exists.
3. Let the user download the new exe and replace the old one manually.

The project already has a Gitea instance, so we can reuse it as the update source instead of introducing a new artifact store.

## Decision

Use Gitea releases as the update source. The app queries `GET {GITEA_BASE_URL}/api/v1/repos/{owner}/{repo}/releases/latest`, parses `tag_name` as semver, and compares it to a local `VERSION` file.

- Configuration is env-only: `GITEA_BASE_URL`, `GITEA_REPO_OWNER`, `GITEA_REPO_NAME`.
- The HTTP call uses a hard 10-second timeout and follows redirects.
- The backend endpoint (`/api/system/update`) returns `{current, latest, has_update, download_url, release_url, published_at, error}`.
- The admin UI fetches this endpoint on load and shows a banner when `has_update` is true.
- The download link points to the first release asset; if no asset exists, it falls back to the release page.
- Public releases only; no auth token is required or stored.

## Consequences

Positive:

- No new infrastructure: the existing Gitea instance becomes the release channel.
- Keeps the desktop build self-contained: no auto-downloader, no installer, no signature dance.
- Missing or misconfigured env vars degrade silently (`has_update: false`), so self-hosted or dev builds are unaffected.

Negative:

- Users must manually download and replace the exe; no silent update.
- If Gitea is down or the network is slow, the banner simply does not appear (no retry).
- Releases must be public; private releases would require a token and out-of-band distribution.

## Alternatives considered

- **GitHub Releases:** rejected because the project already runs a private Gitea instance and we want to keep builds off public GitHub.
- **Auto-download + self-replace:** rejected for MVP scope; signature verification, elevation, and rollback are non-trivial on Windows.
- **Check version by downloading a static `latest.txt`:** rejected because Gitea already provides a structured release API with assets and published dates.
