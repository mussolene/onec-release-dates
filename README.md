# onec-release-dates

Small collector for 1C configuration release dates.

The tool builds two outputs:

- machine-readable JSON with summary, release rows, and skipped targets;
- Markdown report with the same overview for quick reading.

The current collector uses:

- `releases.1c.ru/project/<nick>?allUpdates=true#updates` for standard 1C configurations;
- Rarus release pages for Alfa-Auto 6.x;
- Rarus forum pages for Alfa-Auto 5.1.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

For `releases.1c.ru`, create a local `.env`:

```bash
cp .env.example .env
```

Then fill in local credentials. Do not commit `.env`.

## Usage

```bash
onec-release-dates \
  --json-out reports/1c-release-dates.json \
  --md-out reports/1c-release-dates.md
```

Or run the module directly:

```bash
python -m onec_release_dates.collector \
  --json-out reports/1c-release-dates.json \
  --md-out reports/1c-release-dates.md
```

The year baseline is calculated per target:

1. take the latest parsed release for that target;
2. subtract 365 days from that release date;
3. select the first parsed release at or before that cutoff date;
4. if no release rows or no year-baseline release can be parsed, render the target as `skipped`.

## Reports

Current generated examples are stored in:

- `reports/1c-release-dates.md`
- `reports/1c-release-dates.json`

## Development

```bash
python -m pytest
python -m py_compile src/onec_release_dates/collector.py
```
