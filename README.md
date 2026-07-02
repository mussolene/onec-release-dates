# 1C Release Dates

[![Update Data](../../actions/workflows/update-data.yml/badge.svg)](../../actions/workflows/update-data.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

Public release-date database for 1C configurations.

The project collects public release announcements, builds machine-readable JSON,
and renders a static GitHub Pages site with:

- a searchable configuration summary;
- current release and the release closest to one year before it;
- a dedicated release-history page for every discovered configuration;
- light/dark theme via the browser `prefers-color-scheme` setting.

## Sources

- Public 1C ITS news: `https://its.1c.ru/news/?ym=YYYYMM&type=`
- Rarus release pages and forum threads for Alfa-Auto releases

No ITS login, password, local environment file, or private release-access list is
required. The collector indexes every configuration link it finds in public
source pages.

## Outputs

- `reports/1c-release-dates.json` - full database with `summary` and `releases`
- `reports/1c-release-dates.md` - readable Markdown summary
- `docs/index.html` - GitHub Pages entry point
- `docs/configs/*.html` - per-configuration release histories
- `docs/data/*.json` - JSON files exposed for scripts

## Run Locally

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
onec-release-dates
```

Fetched ITS months are cached locally in `.cache/its-news.json`. Every run
refreshes the current and previous month automatically.

## GitHub Pages

GitHub Pages is served directly from the committed `docs/` directory on `main`.
The update workflow does not call the Pages deployment API.

`.github/workflows/update-data.yml` runs daily or manually. It performs an
incremental refresh from the current ITS news months only, using the committed
database as the baseline.

The data update workflow:

1. installs the package;
2. runs the collector in incremental mode;
3. runs tests;
4. commits changed generated reports/docs files back to the repository.

If GitHub-hosted runners receive a DDoS-Guard challenge from ITS, the update
job fails before writing files, so the published database is not degraded.

Enable Pages in repository settings with **Deploy from a branch**:
`main` / `docs`.

## Development

```bash
python -m pytest
python - <<'PY'
from pathlib import Path
compile(Path("src/onec_release_dates/collector.py").read_text(), "collector.py", "exec")
PY
```

The repository intentionally avoids credentials and private environment files.
Do not commit `.env`, local caches, cookies, downloaded platform archives, or
private release-access data.
