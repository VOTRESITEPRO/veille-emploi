# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A daily job-listing watcher for Product Owner / Chef de projet roles around Nantes. `veille.py`
collects and hard-filters listings from three sources; a separate Claude Code routine (not part of
this repo's code) reads the resulting JSON, scores each listing against `config.yaml`'s rubric, and
writes a markdown synthesis. The split is deliberate: Python only applies binary/objective filters,
never keyword-based scoring — that's Claude's job, done by reading full descriptions.

All comments, docs, and commit messages in this repo are in French; match that when editing.

## Commands

```bash
pip install requests pyyaml beautifulsoup4    # only dependencies, no requirements.txt

python veille.py                    # full collection (all 3 sources), respects state/vues.json
python veille.py --source ft        # single source: ft | apec | hellowork | all
python veille.py --no-state         # ignore dedup history, re-surface everything (used for tuning)
python veille.py --verbose          # log per-keyword/page counts to stderr
```

There is no test suite, linter, or build step in this repo — it's a single script. Validate changes
to a source adapter by running `python veille.py --source <name> --verbose` and inspecting the
resulting `data/candidats_*.json`.

France Travail requires `FT_CLIENT_ID` / `FT_CLIENT_SECRET` in the environment (see README for how
to obtain them). Never put credentials in `config.yaml`.

## Architecture

**`veille.py`** is the only code file, structured as three independent source adapters feeding a
shared pipeline:

1. **Collect** (`collecte_ft`, `collecte_apec`, `collecte_hellowork`) — one function per source, each
   returning a list of offer dicts in a common shape (`source`, `id_source`, `titre`, `entreprise`,
   `lieu`, `url`, `description`, ...). Each adapter fails independently: an exception in one is caught
   in `main()`, recorded in `erreurs`, and the other sources still run.
   - **France Travail**: official API, OAuth2 client-credentials. Fairly stable.
   - **APEC**: undocumented internal endpoint (`POST /cms/webservices/rechercheOffre`) reverse-engineered
     from the front end — a known fragility point, expected to break ~1-2x/year. On failure it logs and
     returns an empty list rather than raising, so `main()`'s per-source error handling still records it.
   - **HelloWork**: no API either, but results are server-rendered HTML (Rails/Turbo), so it's BeautifulSoup
     parsing against `data-cy` attributes rather than a reverse-engineered endpoint. Full descriptions live
     on the offer's own page, not the results list, so `hw_fetch_detail` is only called for offers that
     already survive the hard filters — not for every raw result — to bound the extra request volume.
2. **Cross-source dedup** (`cle_dedoublon` + the loop in `main()`) — offers are matched on normalized
   title + company (`slug()` strips accents/punctuation/stopwords). APEC never returns a company name in
   search results, so its key falls back to `source:id_source`, meaning APEC listings never dedupe against
   other sources. When two sources report the same offer, France Travail's copy wins (more complete
   description).
3. **30-day history filter** (`state/vues.json`, `charger_state`/`ecrire_state`) — keyed by the same
   `cle_dedoublon()`, this is what prevents the same offer from being re-surfaced day after day (HelloWork
   and APEC have no reliable source-side "posted after date X" filter, so this is the only dedup across
   runs for them). Entries older than 30 days are purged on write. `--no-state` bypasses this for retuning.
4. **Hard filters** (`filtrer`) — title regex exclusions, department/commune allowlist, salary floor,
   max required experience. A missing data point never causes rejection (absence isn't treated as a
   negative signal) — only an explicit disqualifying value does. Every rejection carries a `motif_rejet`.
5. **Output** — `data/candidats_<date>[_<source>].json` (gitignored, per-execution working file) containing
   stats, retained offers, and rejected-with-reason. `main()` exits non-zero only if *every* requested
   source failed.

**Everything past this JSON file is out of `veille.py`'s scope** and lives in the daily routine
(`PROMPT_ROUTINE.md`, run by a separate Claude Code process, not by this script): scoring against
`config.yaml`'s `scoring`/`profil` sections, writing `out/synthese_<date>.md`, and updating the
candidate-tracking pipeline.

## The candidate pipeline is an external Artifact, not a repo file

The cumulative "all offers ever retained" tracker — where the user marks status/favorite/notes by hand —
is a published Claude Artifact at a **fixed URL**, not a file in this repo. `PROMPT_ROUTINE.md` describes
the read-merge-republish protocol in detail (read the artifact's HTML, locate the *first*
`<script type="application/json" id="state">` block only, merge in new offers without touching existing
entries' `favori`/`statut`/`notes`, republish to the *same* URL). **The one invariant that matters if you
touch anything related to this flow: never recreate the artifact.** A new artifact gets a new URL and
silently loses all hand-entered status history — a read/publish failure should be reported, not worked
around by creating a fresh one.

## Config vs. code boundary

`config.yaml` has two roles read by two different consumers:
- `requete` / `filtres_durs` — read by `veille.py`, objective/binary filters only.
- `scoring` / `profil` — read only by the routine's Claude instance for subjective scoring; `veille.py`
  never touches these sections. Don't add keyword-scoring logic to `veille.py` — that's an intentional
  non-goal (see top of this file).

## Persistence model

No external services (no Drive, no DB). The daily routine commits and pushes `out/synthese_*.md` and
`state/vues.json` itself after each run. `data/*.json` is gitignored working state, never committed. If
editing files by hand, `git pull` first — the routine may have pushed that same morning.
