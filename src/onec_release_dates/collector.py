#!/usr/bin/env python3
"""Build a public release database and static pages from public 1C release news."""

from __future__ import annotations

import argparse
import http.cookiejar
import datetime as dt
import html
import json
import os
import re
import shutil
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterable


TODAY = dt.date.today()
DEFAULT_DAYS = 365
UA = "Mozilla/5.0 onec-release-dates/0.2"
LOGIN_URL = "https://login.1c.ru/login"
ITS_LOGIN_CALLBACK = "https://its.1c.ru/login/?action=aftercheck&provider=login"
ITS_NEWS_URL = "https://its.1c.ru/news/"
ITS_START_YEAR = 2015
ITS_CACHE_PATH = Path(".cache/its-news.json")
AUTH_OPENER = None
AUTH_ATTEMPTED = False
RARUS6_YEARS = range(2021, TODAY.year + 1)
RARUS5_PAGES = [
    "https://rarus.ru/forum/forum7/topic2826/",
    "https://rarus.ru/forum/forum7/topic2826/?PAGEN_1=2",
    "https://rarus.ru/forum/forum7/topic2826/?PAGEN_1=3",
    "https://rarus.ru/forum/forum7/topic2826/?PAGEN_1=4",
]

MONTH_ALIASES = {
    "янв": 1,
    "фев": 2,
    "мар": 3,
    "апр": 4,
    "май": 5,
    "июн": 6,
    "июл": 7,
    "авг": 8,
    "сен": 9,
    "окт": 10,
    "ноя": 11,
    "дек": 12,
}

RARUS_CONFIGS = {
    "AlfaAuto51": {
        "name": "Альфа-Авто 5.1",
        "source": "rarus.ru forum",
        "version_prefix": "5.1.",
    },
    "AutoSalon60": {
        "name": "Альфа-Авто: Автосалон+Автосервис+Автозапчасти КОРП. Редакция 6.0",
        "source": "rarus.ru release page",
        "version_prefix": "6.0.",
    },
    "AutoSalon61": {
        "name": "Альфа-Авто: Автосалон+Автосервис+Автозапчасти КОРП. Редакция 6.1",
        "source": "rarus.ru release page",
        "version_prefix": "6.1.",
    },
}

CONFIG_ID_ALIASES_BY_BRANCH = {
    ("ERP_UH32", "3.1"): "ERP_UH31",
}


def load_dotenv(path: str = ".env") -> None:
    dotenv = Path(path)
    if not dotenv.exists():
        return
    for line in dotenv.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        if key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def credentials() -> tuple[str | None, str | None]:
    return os.getenv("ITS_LOGIN"), os.getenv("ITS_PASSWORD")


def extract_input_value(page: str, name: str) -> str:
    patterns = [
        rf'<input[^>]+name=["\']{re.escape(name)}["\'][^>]*value=["\']([^"\']*)',
        rf'<input[^>]+value=["\']([^"\']*)["\'][^>]*name=["\']{re.escape(name)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, page, re.I)
        if match:
            return html.unescape(match.group(1) or "")
    return ""


def fetch_with_opener(opener, url: str, data: bytes | None = None, timeout: int = 30) -> tuple[int, str, str]:
    headers = {"User-Agent": UA}
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with opener.open(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.status, resp.read().decode(charset, "replace"), resp.geturl()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace"), exc.geturl()


def authenticated_opener():
    global AUTH_ATTEMPTED, AUTH_OPENER
    if AUTH_OPENER is not None:
        return AUTH_OPENER
    if AUTH_ATTEMPTED:
        return None
    AUTH_ATTEMPTED = True

    user, password = credentials()
    if not user or not password:
        return None

    context = ssl._create_unverified_context()
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPSHandler(context=context),
    )
    login_url = f"{LOGIN_URL}?{urllib.parse.urlencode({'service': ITS_LOGIN_CALLBACK})}"
    status, login_page, login_url = fetch_with_opener(opener, login_url)
    if status != 200:
        return None
    execution = extract_input_value(login_page, "execution")
    if not execution:
        return None

    data = urllib.parse.urlencode({
        "inviteCode": "",
        "execution": execution,
        "_eventId": "submit",
        "rememberMe": "false",
        "username": user,
        "password": password,
    }).encode()
    callback_status, callback_body, callback_url = fetch_with_opener(opener, login_url, data=data)
    if (
        callback_status == 200
        and callback_url.startswith(ITS_LOGIN_CALLBACK)
        and "DDoS-Guard" not in callback_body
    ):
        AUTH_OPENER = opener
        return AUTH_OPENER
    return None


def fetch(url: str, timeout: int = 30, auth: bool = False) -> tuple[int, str]:
    if auth:
        opener = authenticated_opener()
        if opener is not None:
            status, body, _ = fetch_with_opener(opener, url, timeout=timeout)
            return status, body
    headers = {"User-Agent": UA}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.status, resp.read().decode(charset, "replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return exc.code, body
    except urllib.error.URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            return 0, f"{type(exc).__name__}: {exc}"
        try:
            context = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.status, resp.read().decode(charset, "replace")
        except Exception as retry_exc:
            return 0, f"{type(retry_exc).__name__}: {retry_exc}"
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"


def clean_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    raw = re.sub(r"(?is)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?is)</(tr|div|p|li|h\d|td|th)>", "\n", raw)
    raw = re.sub(r"(?is)<[^>]+>", " ", raw)
    return re.sub(r"[ \t\r\f\v]+", " ", html.unescape(raw)).strip()


def parse_date(value: str) -> dt.date | None:
    parts = value.split(".")
    if len(parts) != 3:
        return None
    day, month, year = map(int, parts)
    if year < 100:
        year += 2000 if year < 70 else 1900
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def date_ru(value: dt.date | str) -> str:
    if isinstance(value, str):
        value = dt.date.fromisoformat(value)
    return value.strftime("%d.%m.%Y")


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version))


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._")
    return value or "configuration"


def version_branch(version: str) -> str:
    parts = re.findall(r"\d+", version)
    return ".".join(parts[:2]) if len(parts) >= 2 else version


def branched_config_id(source_config_id: str, version: str) -> str:
    branch = version_branch(version).replace(".", "_")
    return f"{source_config_id}_{branch}"


def branched_config_name(base_name: str, version: str) -> str:
    branch = version_branch(version)
    if branch in base_name:
        return base_name
    return f"{base_name} ({branch})"


def canonical_source_config_id(source_config_id: str, version: str) -> str:
    return CONFIG_ID_ALIASES_BY_BRANCH.get((source_config_id, version_branch(version)), source_config_id)


def normalize_release_identity(row: dict) -> dict:
    version = row["version"]
    source_config_id = canonical_source_config_id(row.get("source_config_id") or row["config_id"], version)
    normalized = dict(row)
    normalized["source_config_id"] = source_config_id
    normalized["version_branch"] = version_branch(version)
    normalized["config_id"] = branched_config_id(source_config_id, version)
    normalized["config_name"] = branched_config_name(row.get("config_name") or source_config_id, version)
    return normalized


def iter_its_months(start_year: int = ITS_START_YEAR, end: dt.date = TODAY) -> Iterable[str]:
    for year in range(end.year, start_year - 1, -1):
        last_month = end.month if year == end.year else 12
        for month in range(last_month, 0, -1):
            yield f"{year}{month:02d}"


def previous_month(value: dt.date = TODAY) -> str:
    year = value.year
    month = value.month - 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year}{month:02d}"


def parse_news_date(panel: str) -> dt.date | None:
    match = re.search(
        r'journal-date__day">(\d{1,2}).*?journal-date__month">([^<]+).*?journal-date__year">\'(\d{2})',
        panel,
        re.S,
    )
    if not match:
        return None
    month_name = match.group(2).strip().lower()[:3]
    month = MONTH_ALIASES.get(month_name)
    if not month:
        return None
    return dt.date(2000 + int(match.group(3)), month, int(match.group(1)))


def parse_news_id(panel: str) -> str | None:
    match = re.search(r'data-news-id="(\d+)"', panel) or re.search(r'id="news_(\d+)"', panel)
    return match.group(1) if match else None


def parse_news_title(panel: str) -> str:
    match = re.search(r'(?is)<div class="link-item news-item[^>]*"[^>]*>(.*?)(?:<div class="link-item__state">|</div>)', panel)
    return clean_text(match.group(1)).strip() if match else clean_text(panel)[:500]


def names_by_version(title: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    pattern = re.compile(r'\b(\d+(?:\.\d+){2,3})\b\s+"([^"]+)"')
    for version, name in pattern.findall(title):
        found.setdefault(version, []).append(name.strip())
    return found


def pop_name(candidates: dict[str, list[str]], version: str) -> str | None:
    names = candidates.get(version) or []
    if names:
        return names.pop(0)
    return None


def release_row(
    *,
    config_id: str,
    version: str,
    date: dt.date,
    source: str,
    url: str,
    config_name: str | None = None,
    extra: dict | None = None,
) -> dict:
    branch = version_branch(version)
    config_id = canonical_source_config_id(config_id, version)
    public_config_id = branched_config_id(config_id, version)
    public_config_name = branched_config_name(config_name or config_id, version)
    row = {
        "config_id": public_config_id,
        "config_name": public_config_name,
        "source_config_id": config_id,
        "version_branch": branch,
        "version": version,
        "date": date.isoformat(),
        "date_ru": date_ru(date),
        "source": source,
    }
    if extra:
        row.update(extra)
    return row


def parse_its_news_month(ym: str) -> list[dict]:
    url = f"{ITS_NEWS_URL}?ym={ym}&type="
    status, raw = fetch(url)
    if status != 200:
        return []
    panels = re.findall(r'(?is)<div class="panel">(.*?)(?=<div class="panel">|<div id="footer"|</body>|\Z)', raw)
    rows = []
    for panel in panels:
        date = parse_news_date(panel)
        if not date:
            continue
        news_id = parse_news_id(panel)
        title = parse_news_title(panel)
        name_candidates = names_by_version(title)
        news_url = f"https://its.1c.ru/news/{news_id}" if news_id else url
        for nick, version in re.findall(r'version_files\?nick=([^"&]+)(?:&amp;|&)ver=([^"&]+)', panel):
            nick = urllib.parse.unquote(nick)
            version = urllib.parse.unquote(version)
            rows.append(release_row(
                config_id=nick,
                config_name=pop_name(name_candidates, version),
                version=version,
                date=date,
                source="its.1c.ru news",
                url=news_url,
                extra={
                    "month": ym,
                    "source_kind": "its",
                },
            ))
    return rows


def load_its_cache() -> dict[str, list[dict]]:
    try:
        with ITS_CACHE_PATH.open(encoding="utf-8") as fp:
            raw = json.load(fp)
    except (OSError, json.JSONDecodeError):
        return {}
    months = raw.get("months", {})
    if not isinstance(months, dict):
        return {}
    return {str(month): normalize_cached_rows(rows) for month, rows in months.items() if isinstance(rows, list)}


def normalize_cached_rows(rows: list[dict]) -> list[dict]:
    normalized = []
    for row in rows:
        config_id = row.get("source_config_id") or row.get("nick") or row.get("config_id")
        version = row.get("version")
        date = row.get("date")
        if not config_id or not version or not date:
            continue
        title = row.get("news_title", "")
        name = row.get("config_name") or (names_by_version(title).get(version) or [config_id])[0]
        normalized.append(release_row(
            config_id=config_id,
            config_name=name,
            version=version,
            date=dt.date.fromisoformat(date),
            source=row.get("source", "its.1c.ru news"),
            url=row.get("url", ITS_NEWS_URL),
            extra={
                "month": row.get("month"),
                "source_kind": "its",
            },
        ))
    return normalized


def save_its_cache(months: dict[str, list[dict]]) -> None:
    ITS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": ITS_NEWS_URL,
        "months": dict(sorted(months.items(), reverse=True)),
    }
    with ITS_CACHE_PATH.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
        fp.write("\n")


def collect_its_releases() -> list[dict]:
    cache = load_its_cache()
    refresh_months = {TODAY.strftime("%Y%m"), previous_month()}
    rows = []
    changed = False
    for ym in iter_its_months():
        if ym in cache and ym not in refresh_months:
            rows.extend(cache[ym])
            continue
        month_rows = parse_its_news_month(ym)
        rows.extend(month_rows)
        if cache.get(ym) != month_rows:
            cache[ym] = month_rows
            changed = True
    if changed:
        save_its_cache(cache)
    return rows


def collect_rarus6_releases() -> list[dict]:
    rows = []
    for year in RARUS6_YEARS:
        url = f"https://rarus.ru/1c-auto/releases-alfa-avto-avtosalon-avtoservis-avtozapchasti-korp-redaktsiya-6-{year}/"
        status, raw = fetch(url)
        if status != 200:
            continue
        text = clean_text(raw)
        for version, date_text in re.findall(r"Релиз\s+(6\.\d+\.\d+\.\d+)\s+от\s+(\d{2}\.\d{2}\.\d{4})", text):
            date = parse_date(date_text)
            if not date:
                continue
            for config_id in ("AutoSalon60", "AutoSalon61"):
                cfg = RARUS_CONFIGS[config_id]
                if version.startswith(cfg["version_prefix"]):
                    rows.append(release_row(
                        config_id=config_id,
                        config_name=cfg["name"],
                        version=version,
                        date=date,
                        source=cfg["source"],
                        url=url,
                        extra={"source_kind": "rarus"},
                    ))
    return rows


def collect_rarus5_releases() -> list[dict]:
    rows = []
    cfg = RARUS_CONFIGS["AlfaAuto51"]
    for url in RARUS5_PAGES:
        status, raw = fetch(url)
        if status != 200:
            continue
        starts = list(re.finditer(r'(?is)<div[^>]+id=["\']?(message\d+)["\']?[^>]*>', raw))
        for index, start in enumerate(starts):
            message_id = start.group(1)
            end = starts[index + 1].start() if index + 1 < len(starts) else len(raw)
            block = raw[start.start():end]
            full = clean_text(block)
            date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})\s+в\s+(\d{2}:\d{2})", full)
            body_start = re.search(r'(?is)<div[^>]+class=["\'][^"\']*comment__description[^"\']*["\'][^>]*>', block)
            body = clean_text(block[body_start.end():] if body_start else block)
            versions = sorted(set(re.findall(r"\b5\.\d+\.\d+\.\d+\b", body)), key=version_key, reverse=True)
            if date_match and versions and re.search("релиз", body, re.I):
                date = parse_date(date_match.group(1))
                if not date:
                    continue
                rows.append(release_row(
                    config_id="AlfaAuto51",
                    config_name=cfg["name"],
                    version=versions[0],
                    date=date,
                    source=cfg["source"],
                    url=url,
                    extra={"time": date_match.group(2), "message": message_id, "source_kind": "rarus"},
                ))
    return rows


def row_date(row: dict) -> dt.date:
    return dt.date.fromisoformat(row["date"])


def unique_releases(rows: Iterable[dict]) -> list[dict]:
    best: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["config_id"], row["version"])
        current = best.get(key)
        if current is None or row["date"] > current["date"]:
            best[key] = row
    return sorted(best.values(), key=lambda row: (row["config_id"].lower(), row_date(row), version_key(row["version"])), reverse=True)


def group_releases(rows: Iterable[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["config_id"], []).append(row)
    for config_rows in grouped.values():
        config_rows.sort(key=lambda row: (row_date(row), version_key(row["version"])), reverse=True)
    return dict(sorted(grouped.items(), key=lambda item: item[0].lower()))


def display_name(config_id: str, rows: list[dict]) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        name = (row.get("config_name") or "").strip()
        if name and name != config_id:
            counts[name] = counts.get(name, 0) + 1
    if not counts:
        return config_id
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def select_year_ago_release(rows: list[dict], latest: dict, days: int) -> tuple[dt.date, dict | None]:
    stale_cutoff = TODAY - dt.timedelta(days=days)
    if row_date(latest) <= stale_cutoff:
        return row_date(latest), latest

    cutoff = row_date(latest) - dt.timedelta(days=days)
    for row in rows:
        if row_date(row) <= cutoff:
            return cutoff, row
    return cutoff, latest


def period_rows(rows: list[dict], cutoff: dt.date, baseline: dict | None) -> list[dict]:
    selected = [row for row in rows if row_date(row) >= cutoff]
    if baseline and baseline not in selected:
        selected.append(baseline)
    return selected


def build_summary(grouped: dict[str, list[dict]], days: int) -> list[dict]:
    summary = []
    for config_id, rows in grouped.items():
        latest = rows[0]
        cutoff, baseline = select_year_ago_release(rows, latest, days)
        summary.append({
            "config_id": config_id,
            "config_name": display_name(config_id, rows),
            "slug": slugify(config_id),
            "latest": latest,
            "year_ago_release": baseline,
            "period": {
                "days": days,
                "cutoff": cutoff.isoformat(),
                "count": len(period_rows(rows, cutoff, baseline)),
            },
            "release_count": len(rows),
            "sources": sorted({row["source"] for row in rows}),
        })
    return sorted(summary, key=lambda item: (item["config_name"].lower(), item["config_id"].lower()))


def collect_all(days: int) -> dict:
    releases = unique_releases([
        *collect_its_releases(),
        *collect_rarus6_releases(),
        *collect_rarus5_releases(),
    ])
    grouped = group_releases(releases)
    summary = build_summary(grouped, days)
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "period": {"mode": "latest_minus_days_per_configuration", "days": days},
        "sources": [
            {"id": "its", "name": "1C ITS news", "url": ITS_NEWS_URL},
            {"id": "rarus", "name": "Rarus release pages and forum", "url": "https://rarus.ru/"},
        ],
        "summary": summary,
        "releases": releases,
    }


def source_catalog() -> list[dict]:
    return [
        {"id": "its", "name": "1C ITS news", "url": ITS_NEWS_URL},
        {"id": "rarus", "name": "Rarus release pages and forum", "url": "https://rarus.ru/"},
    ]


def rebuild_database_from_releases(releases: list[dict], days: int, mode: str) -> dict:
    releases = unique_releases(normalize_release_identity(row) for row in releases)
    grouped = group_releases(releases)
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "period": {"mode": mode, "days": days},
        "sources": source_catalog(),
        "summary": build_summary(grouped, days),
        "releases": releases,
    }


def update_existing_database(path: Path, days: int, months: list[str] | None = None) -> dict:
    with path.open(encoding="utf-8") as fp:
        existing = json.load(fp)
    months = months or [TODAY.strftime("%Y%m"), previous_month()]
    fresh_rows = []
    for ym in dict.fromkeys(months):
        fresh_rows.extend(parse_its_news_month(ym))
    if not fresh_rows:
        raise SystemExit(f"No ITS rows parsed for incremental months: {', '.join(dict.fromkeys(months))}")
    return rebuild_database_from_releases(
        [*existing.get("releases", []), *fresh_rows],
        days,
        "incremental_current_months",
    )


def validate_public_database(data: dict) -> None:
    config_count = len(data["summary"])
    release_count = len(data["releases"])
    has_its = any(row.get("source_kind") == "its" for row in data["releases"])
    if config_count < 50 or release_count < 1000 or not has_its:
        raise SystemExit(
            "Refusing to write a degraded public database: "
            f"configs={config_count}, releases={release_count}, has_its={has_its}"
        )


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(cell).replace("\n", " ") for cell in row) + " |")
    return "\n".join(out)


def render_markdown(data: dict) -> str:
    summary_rows = []
    for item in data["summary"]:
        latest = item["latest"]
        year_ago = item.get("year_ago_release") or {}
        summary_rows.append([
            item["config_name"],
            item["config_id"],
            f"{latest['version']} / {latest['date_ru']}",
            f"{year_ago.get('version', 'skipped')} / {year_ago.get('date_ru', '')}".strip(),
            str(item["release_count"]),
            ", ".join(item["sources"]),
        ])
    chunks = [
        f"# 1C release dates\n\nGenerated: {data['generated_at']}\n\n"
        f"Configurations: {len(data['summary'])}\n\nReleases: {len(data['releases'])}\n",
        "## Configuration Summary\n\n" + md_table(
            ["configuration", "id", "current_release", "year_ago_release", "release_count", "sources"],
            summary_rows,
        ),
    ]
    return "\n\n".join(chunks) + "\n"


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def source_text(row: dict) -> str:
    return esc(row["source"])


def page_shell(title: str, body: str, prefix: str = "") -> str:
    css = f"{prefix}assets/styles.css"
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <link rel="stylesheet" href="{esc(css)}">
</head>
<body>
  <header class="topbar">
    <a class="brand" href="{esc(prefix)}index.html">1C Release Dates</a>
    <nav><a href="{esc(prefix)}data/summary.json">summary.json</a><a href="{esc(prefix)}data/releases.json">releases.json</a></nav>
  </header>
  <main>{body}</main>
</body>
</html>
"""


def render_index(data: dict) -> str:
    rows = []
    for item in data["summary"]:
        latest = item["latest"]
        year = item.get("year_ago_release") or {}
        rows.append(f"""
        <tr>
          <td><a href="configs/{esc(item['slug'])}.html">{esc(item['config_name'])}</a><span class="muted code">{esc(item['config_id'])}</span></td>
          <td><strong>{esc(latest['version'])}</strong><span class="muted">{esc(latest['date_ru'])}</span></td>
          <td><strong>{esc(year.get('version', 'skipped'))}</strong><span class="muted">{esc(year.get('date_ru', ''))}</span></td>
          <td>{esc(item['release_count'])}</td>
          <td>{esc(', '.join(item['sources']))}</td>
        </tr>""")
    body = f"""
    <section class="hero">
      <div>
        <h1>1C Release Dates</h1>
        <p>Публичная база дат релизов конфигураций 1С из новостей ITS и страниц Rarus.</p>
      </div>
      <dl class="stats">
        <div><dt>Конфигураций</dt><dd>{len(data['summary'])}</dd></div>
        <div><dt>Релизов</dt><dd>{len(data['releases'])}</dd></div>
        <div><dt>Обновлено</dt><dd>{esc(data['generated_at'])}</dd></div>
      </dl>
    </section>
    <section class="toolbar"><input id="filter" type="search" placeholder="Фильтр по конфигурации, версии или источнику" aria-label="Фильтр"></section>
    <section class="table-wrap">
      <table id="configs">
        <thead><tr><th>Конфигурация</th><th>Текущий релиз</th><th>Релиз годовой давности</th><th>Всего</th><th>Источник</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
    <script>
      const input = document.getElementById('filter');
      const rows = [...document.querySelectorAll('#configs tbody tr')];
      input.addEventListener('input', () => {{
        const q = input.value.toLowerCase();
        for (const row of rows) row.hidden = !row.textContent.toLowerCase().includes(q);
      }});
    </script>
    """
    return page_shell("1C Release Dates", body)


def render_config_page(item: dict, rows: list[dict]) -> str:
    release_rows = []
    for row in rows:
        release_rows.append(f"""
        <tr>
          <td><strong>{esc(row['version'])}</strong></td>
          <td>{esc(row['date_ru'])}</td>
          <td>{source_text(row)}</td>
        </tr>""")
    latest = item["latest"]
    year = item.get("year_ago_release") or {}
    body = f"""
    <section class="detail-head">
      <div class="detail-title">
        <a class="back" href="../index.html">← Все конфигурации</a>
        <h1>{esc(item['config_name'])}</h1>
        <p class="code">{esc(item['config_id'])}</p>
      </div>
      <div class="release-cards">
        <article><span>Текущий релиз</span><strong>{esc(latest['version'])}</strong><em>{esc(latest['date_ru'])}</em></article>
        <article><span>Релиз годовой давности</span><strong>{esc(year.get('version', 'skipped'))}</strong><em>{esc(year.get('date_ru', ''))}</em></article>
        <article><span>Всего релизов</span><strong>{esc(item['release_count'])}</strong><em>{esc(', '.join(item['sources']))}</em></article>
      </div>
    </section>
    <section class="table-wrap">
      <table>
        <thead><tr><th>Версия</th><th>Дата</th><th>Источник</th></tr></thead>
        <tbody>{''.join(release_rows)}</tbody>
      </table>
    </section>
    """
    return page_shell(f"{item['config_name']} - 1C Release Dates", body, prefix="../")


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
        fp.write("\n")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def render_site(data: dict, out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "configs").mkdir(parents=True)
    write_text(out_dir / ".nojekyll", "")
    write_text(out_dir / "assets" / "styles.css", CSS)
    write_text(out_dir / "index.html", render_index(data))
    grouped = group_releases(data["releases"])
    for item in data["summary"]:
        write_text(out_dir / "configs" / f"{item['slug']}.html", render_config_page(item, grouped[item["config_id"]]))
    write_json(out_dir / "data" / "summary.json", data["summary"])
    write_json(out_dir / "data" / "releases.json", data["releases"])


CSS = """
:root {
  color-scheme: light dark;
  --bg: #f7f7f4;
  --panel: #ffffff;
  --text: #171717;
  --muted: #6b6b63;
  --line: #deded6;
  --accent: #0f766e;
  --accent-soft: #d7f2ee;
  --shadow: 0 16px 40px rgba(20, 20, 20, .08);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #111312;
    --panel: #1a1d1b;
    --text: #f1f3ee;
    --muted: #a8aca3;
    --line: #333832;
    --accent: #5eead4;
    --accent-soft: #123b35;
    --shadow: 0 16px 44px rgba(0, 0, 0, .28);
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.topbar { position: sticky; top: 0; z-index: 5; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 24px; background: color-mix(in srgb, var(--bg) 88%, transparent); border-bottom: 1px solid var(--line); backdrop-filter: blur(16px); }
.brand { color: var(--text); font-weight: 750; }
nav { display: flex; gap: 14px; flex-wrap: wrap; }
main { width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 56px; }
.hero, .detail-head { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 24px; align-items: end; padding: 28px 0; }
.detail-head { grid-template-columns: minmax(0, 1fr) minmax(360px, 520px); align-items: start; padding: 18px 0 22px; }
h1 { margin: 0; font-size: clamp(32px, 5vw, 58px); line-height: 1.02; letter-spacing: 0; overflow-wrap: anywhere; }
.detail-head h1 { font-size: clamp(24px, 3vw, 38px); line-height: 1.12; max-width: 760px; }
p { margin: 10px 0 0; color: var(--muted); max-width: 720px; }
.stats, .release-cards { display: grid; grid-template-columns: repeat(3, minmax(130px, 1fr)); gap: 12px; margin: 0; }
.stats div, .release-cards article { padding: 16px; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); }
.detail-head .release-cards { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.detail-head .release-cards article { padding: 12px; }
dt, .release-cards span { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
dd, .release-cards strong { display: block; margin: 4px 0 0; font-size: 24px; font-weight: 750; }
.detail-head .release-cards strong { font-size: 21px; }
.release-cards em { display: block; color: var(--muted); font-style: normal; }
.toolbar { margin: 8px 0 18px; }
input[type="search"] { width: 100%; min-height: 44px; padding: 10px 14px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); color: var(--text); font: inherit; }
.table-wrap { overflow: auto; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); }
table { width: 100%; border-collapse: collapse; min-width: 760px; }
th, td { padding: 12px 14px; text-align: left; vertical-align: top; border-bottom: 1px solid var(--line); }
th { position: sticky; top: 54px; background: var(--panel); color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
tbody tr:last-child td { border-bottom: 0; }
.muted { display: block; color: var(--muted); font-size: 13px; }
.code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.back { display: inline-block; margin-bottom: 10px; }
@media (max-width: 820px) {
  .topbar, .hero, .detail-head { display: block; }
  nav { margin-top: 8px; }
  .stats, .release-cards { grid-template-columns: 1fr; margin-top: 18px; }
  main { width: min(100% - 20px, 1180px); padding-top: 18px; }
  .detail-head h1 { font-size: clamp(22px, 7vw, 30px); }
}
""".strip() + "\n"


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="year baseline window, default: 365")
    parser.add_argument("--json-out", default="reports/1c-release-dates.json")
    parser.add_argument("--md-out", default="reports/1c-release-dates.md")
    parser.add_argument("--site-out", default="docs")
    parser.add_argument("--incremental", action="store_true", help="update existing JSON with current ITS months only")
    parser.add_argument("--month", action="append", help="YYYYMM month for incremental update; can be repeated")
    args = parser.parse_args()

    if args.incremental:
        data = update_existing_database(Path(args.json_out), args.days, args.month)
    else:
        data = collect_all(args.days)
    validate_public_database(data)
    write_json(Path(args.json_out), data)
    write_text(Path(args.md_out), render_markdown(data))
    render_site(data, Path(args.site_out))
    print(f"Configurations: {len(data['summary'])}")
    print(f"Releases: {len(data['releases'])}")
    print(f"JSON: {args.json_out}", file=sys.stderr)
    print(f"Markdown: {args.md_out}", file=sys.stderr)
    print(f"Site: {args.site_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
