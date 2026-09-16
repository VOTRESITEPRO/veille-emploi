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
python veille.py --fusionne         # cross-listing dedup pass over today's already-written
                                     # data/candidats_<date>_<source>.json files (run after
                                     # the --source calls, collects nothing itself)
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
2. **Exact-key cross-source dedup** (`cle_dedoublon` + the loop in `main()`) — offers within a single
   `main()` invocation are matched on normalized title + company (`slug()` strips accents/punctuation/
   stopwords). APEC never returns a company name in search results, so its key falls back to
   `source:id_source`, meaning APEC listings never dedupe here against other sources. When two sources
   report the same offer, France Travail's copy wins (more complete description). In practice the daily
   routine calls `veille.py` once per source, so this loop only ever sees one source's offers at a time —
   it's a no-op for the routine's real usage and exists mainly for a manual `--source all` run. The
   fuzzy cross-listing pass below (step 6) is what actually catches duplicates across the routine's three
   separate calls.
3. **30-day history filter** (`state/vues.json`, `charger_state`/`ecrire_state`) — keyed by the same
   `cle_dedoublon()`, this is what prevents the same offer from being re-surfaced day after day (HelloWork
   and APEC have no reliable source-side "posted after date X" filter, so this is the only dedup across
   runs for them). Entries older than 30 days are purged on write. `--no-state` bypasses this for retuning.
4. **Hard filters** (`filtrer`) — title regex exclusions, department/commune allowlist, salary floor,
   max required experience. A missing data point never causes rejection (absence isn't treated as a
   negative signal) — only an explicit disqualifying value does. Every rejection carries a `motif_rejet`.
5. **Output** — `data/candidats_<date>_<source>.json` (gitignored, per-execution working file) containing
   stats, retained offers, and rejected-with-reason. `main()` exits non-zero only if *every* requested
   source failed.
6. **Fuzzy cross-listing dedup** (`--fusionne`, `fusionner_offres`/`_similaires`) — a separate pass, run by
   the routine after the three `--source` calls, over the day's already-written per-source files. Two
   listings (same source or different sources) are grouped as the same real posting when they're in the
   same `ville()` and either the title is a near match (Jaccard on `mots_titre()`) *and* the descriptions
   are similar enough (`difflib.SequenceMatcher` ratio on the shared prefix), or — only when a description
   is too short to compare reliably — the titles are exactly identical. An identical title alone is
   deliberately **not** sufficient when both descriptions are usable: two unrelated postings can share a
   generic title (e.g. two different employers both titled "Product Owner ERP SaaS F/H"), so the
   description is what actually decides. Thresholds live in `config.yaml`'s
   `dedoublonnage_inter_sources`. Output is `data/candidats_<date>_fusionne.json`: one entry per group
   (the member with the longest description, carrying the others as a `doublons: [{source, url}, ...]`
   list), which is what the routine scores from. The per-source files are untouched.

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

The scoring grid (revised 2026-09-14) is out of 95, retention threshold 50, across four scored axes —
`adequation_role` (0-40, exclusive), `proximite_geographique` (0-25, exclusive, distances from Couëron
rather than Nantes-Métropole membership), `socle_technique` (0-20, exclusive), `conditions` (0-10,
cumulative) — plus uncapped cumulative `signaux_negatifs` penalties. Sector (`secteur`) and
employer type (`employeur`: ESN vs. client final) were deliberately removed as scoring axes: the routine
still surfaces them, but only as informational tags on retained offers, never as points — it's not the
watcher's place to presume an unfamiliar sector is disqualifying. Salary no longer scores upward either;
it only acts negatively, pre-scoring, via the `filtres_durs.salaire_min_annuel` hard filter.

## Persistence model

No external services (no Drive, no DB). The daily routine commits and pushes `out/synthese_*.md` and
`state/vues.json` itself after each run. `data/*.json` is gitignored working state, never committed. If
editing files by hand, `git pull` first — the routine may have pushed that same morning.

If the routine's execution environment forces it to push to a branch and open a PR rather than pushing
directly to `main`, the routine merges (squash) that PR itself immediately, without waiting for human
review — an unattended daily job can't depend on someone remembering to click "Merge". This only applies
to the routine's own generated output (`out/`, `state/vues.json`, `.claude/`), never to actual code
changes.
