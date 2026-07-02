# 1C Release Dates

[![Update Pages](../../actions/workflows/update-pages.yml/badge.svg)](../../actions/workflows/update-pages.yml)
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
- `site/index.html` - GitHub Pages entry point
- `site/configs/*.html` - per-configuration release histories
- `site/data/*.json` - JSON files exposed for scripts

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

The workflow in `.github/workflows/update-pages.yml` runs daily and on manual
dispatch. It:

1. installs the package;
2. runs the collector;
3. runs tests;
4. commits changed generated reports/site files back to the repository;
5. deploys the `site/` directory to GitHub Pages.

Enable Pages in repository settings with **GitHub Actions** as the source.

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
