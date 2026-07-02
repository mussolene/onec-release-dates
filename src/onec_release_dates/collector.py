#!/usr/bin/env python3
"""Collect release dates for a fixed set of 1C configurations.

The script is intentionally small and tolerant: every failed source becomes a
skipped item, while successful sources still produce JSON and Markdown output.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import html
import http.cookiejar
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Iterable


TODAY = dt.date.today()
DEFAULT_DAYS = 365
UA = "Mozilla/5.0 1c-release-date-collector/0.1"
LOGIN_URL = "https://login.1c.ru/login"
RELEASES_URL = "https://releases.1c.ru"
COOKIE_OPENER = None
LOGIN_ATTEMPTED = False


@dataclass(frozen=True)
class Target:
    template: str
    name: str
    version: str
    group: str
    source: str
    nick: str | None = None
    version_prefix: str | None = None


TARGETS = [
    Target("AccountingCorp30_latest", "Бухгалтерия предприятия КОРП, редакция 3.0", "3.0.183.24", "УФ latest", "releases", "AccountingCorp30"),
    Target("Enterprise24_latest", "1С:ERP Управление предприятием 2, редакция 2.4", "2.4.14.181", "УФ latest", "releases", "Enterprise24"),
    Target("Enterprise25_latest", "1С:ERP Управление предприятием 2, редакция 2.5", "2.5.24.52", "УФ latest", "releases", "Enterprise25"),
    Target("ERPUH32_latest", "1С:ERP Управление холдингом, редакция 3.2", "3.2.8.11", "УФ latest", "releases", "ERPUH32"),
    Target("SmallBusiness16_latest", "Управление нашей фирмой, редакция 1.6", "1.6.27.295", "УФ latest", "releases", "SmallBusiness16"),
    Target("SmallBusiness30_latest", "Управление нашей фирмой, редакция 3.0", "3.0.12.170", "УФ latest", "releases", "SmallBusiness30"),
    Target("StateAccounting20_latest", "Бухгалтерия государственного учреждения, редакция 2.0", "2.0.105.76", "УФ latest", "releases", "StateAccounting20"),
    Target("Arenda3_latest", "Аренда и управление недвижимостью для 1С:Бухгалтерия 8, редакция 3.0", "3.0.182.33/3.3.3.326", "УФ latest", "releases", "Arenda3"),
    Target("AutoSalon60_latest", "Альфа-Авто: Автосалон+Автосервис+Автозапчасти КОРП. Редакция 6", "6.0.41.02", "УФ latest", "rarus6", version_prefix="6.0"),
    Target("AutoSalon61_latest", "Альфа-Авто: Автосалон+Автосервис+Автозапчасти КОРП. Редакция 6.1", "6.1.20.02", "УФ latest", "rarus6", version_prefix="6.1"),
    Target("Retail23_latest", "Розница, редакция 2.3", "2.3.23.50", "УФ latest", "releases", "Retail23"),
    Target("Retail30_latest", "Розница, редакция 3.0", "3.0.12.170", "УФ latest", "releases", "Retail30"),
    Target("DocMgrCorp21_latest", "Документооборот КОРП, редакция 2.1", "2.1.36.3", "УФ latest", "releases", "DocMgrCorp21"),
    Target("DocMgrCorp30_latest", "Документооборот КОРП, редакция 3.0", "3.0.18.19", "УФ latest", "releases", "DocMgrCorp30"),
    Target("Trade115_latest", "Управление торговлей 11.5", "11.5.24.52", "УФ latest", "releases", "Trade115"),
    Target("CorporatePerformanceManagement32_latest", "Управление холдингом, редакция 3.2", "3.2.10.40", "УФ latest", "releases", "CorporatePerformanceManagement32"),
    Target("AlfaAuto51_latest", "Альфа-Авто 5.1", "5.1.47.04", "ОФ latest", "rarus5", version_prefix="5.1"),
    Target("AccountingCorp20_latest", "Бухгалтерия предприятия КОРП 2.0", "2.0.67.75", "ОФ latest", "releases", "AccountingCorp20"),
    Target("ARAutomation11_latest", "Комплексная автоматизация 1.1", "1.1.115.1", "ОФ latest", "releases", "ARAutomation11"),
    Target("Enterprise13_latest", "Управление производственным предприятием 1.3", "1.3.274.2", "ОФ latest", "releases", "Enterprise13"),
    Target("Trade103_latest", "Управление торговлей 10.3", "10.3.88.3", "ОФ latest", "releases", "Trade103"),
    Target("AccountingCorp30_oldest", "Бухгалтерия предприятия КОРП, редакция 3.0", "3.0.137.39", "УФ oldest", "releases", "AccountingCorp30"),
    Target("Arenda3_oldest", "Аренда и управление недвижимостью для 1С:Бухгалтерия 8, редакция 3.0", "3.0.135.22/3.3.3.264", "УФ oldest", "releases", "Arenda3"),
    Target("Enterprise24_oldest", "1С:ERP Управление предприятием 2, редакция 2.4", "2.4.13.282", "УФ oldest", "releases", "Enterprise24"),
    Target("Enterprise25_oldest", "1С:ERP Управление предприятием 2, редакция 2.5", "2.5.12.147", "УФ oldest", "releases", "Enterprise25"),
    Target("ERPUH31_oldest", "1С:ERP Управление холдингом, редакция 3.1", "3.1.13.20", "УФ oldest", "releases", "ERPUH31"),
    Target("SmallBusiness16_oldest", "Управление нашей фирмой, редакция 1.6", "1.6.26.229", "УФ oldest", "releases", "SmallBusiness16"),
    Target("ARAutomation11_100", "КА 1.1 (1.1.100.2)", "1.1.100.2", "ОФ oldest", "releases", "ARAutomation11"),
    Target("Vanessa_Pro_BP", "Бухгалтерия предприятия КОРП, редакция 3.0", "3.0.137.39", "Технические ИБ", "releases", "AccountingCorp30"),
    Target("AccountingCorp20_demo", "Бухгалтерия предприятия КОРП 2.0", "2.0.67.75", "ОФ demo", "releases", "AccountingCorp20"),
    Target("ARAutomation11_demo", "Комплексная автоматизация 1.1", "1.1.115.1", "ОФ demo", "releases", "ARAutomation11"),
    Target("Enterprise13_demo", "Управление производственным предприятием 1.3", "1.3.255.1", "ОФ demo", "releases", "Enterprise13"),
    Target("Trade103_demo", "Управление торговлей 10.3", "10.3.88.3", "ОФ demo", "releases", "Trade103"),
]


RARUS6_YEARS = range(2021, TODAY.year + 1)
RARUS5_PAGES = [
    "https://rarus.ru/forum/forum7/topic2826/",
    "https://rarus.ru/forum/forum7/topic2826/?PAGEN_1=2",
    "https://rarus.ru/forum/forum7/topic2826/?PAGEN_1=3",
    "https://rarus.ru/forum/forum7/topic2826/?PAGEN_1=4",
]


def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.removeprefix("export ").strip()
            if key in os.environ:
                continue
            value = value.strip().strip('"').strip("'")
            os.environ[key] = value


def auth_header() -> str | None:
    user = os.getenv("RELEASES_1C_USER") or os.getenv("ITS_USER") or os.getenv("ITS_LOGIN")
    password = os.getenv("RELEASES_1C_PASSWORD") or os.getenv("ITS_PASSWORD") or os.getenv("ITS_PASS")
    if not user or not password:
        return None
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {token}"


def credentials() -> tuple[str | None, str | None]:
    return (
        os.getenv("RELEASES_1C_USER") or os.getenv("ITS_USER") or os.getenv("ITS_LOGIN"),
        os.getenv("RELEASES_1C_PASSWORD") or os.getenv("ITS_PASSWORD") or os.getenv("ITS_PASS"),
    )


def extract_input_value(page: str, name: str, default: str = "") -> str:
    patterns = [
        rf'<input[^>]+name=["\']{re.escape(name)}["\'][^>]*value=["\']([^"\']*)',
        rf'<input[^>]+value=["\']([^"\']*)["\'][^>]*name=["\']{re.escape(name)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, page, re.I)
        if match:
            return html.unescape(match.group(1) or default)
    return default


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


def releases_opener():
    global COOKIE_OPENER, LOGIN_ATTEMPTED
    if COOKIE_OPENER is not None:
        return COOKIE_OPENER
    if LOGIN_ATTEMPTED:
        return None
    LOGIN_ATTEMPTED = True

    user, password = credentials()
    if not user or not password:
        return None

    context = ssl._create_unverified_context()
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPSHandler(context=context),
    )
    status, login_page, _ = fetch_with_opener(opener, LOGIN_URL)
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
    fetch_with_opener(opener, LOGIN_URL, data=data)
    profile_status, _, profile_url = fetch_with_opener(opener, "https://login.1c.ru/user/profile")
    if profile_status == 200 and profile_url.rstrip("/").endswith("/user/profile"):
        COOKIE_OPENER = opener
        return COOKIE_OPENER
    return None


def fetch(url: str, auth: bool = False, timeout: int = 30) -> tuple[int, str]:
    if auth:
        opener = releases_opener()
        if opener is not None:
            status, body, _ = fetch_with_opener(opener, url, timeout=timeout)
            return status, body
    headers = {"User-Agent": UA}
    if auth:
        value = auth_header()
        if value:
            headers["Authorization"] = value
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
    return re.sub(r"[ \t\r\f\v]+", " ", html.unescape(raw))


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


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def prefix_for(target: Target) -> str:
    if target.version_prefix:
        return target.version_prefix + "."
    first = target.version.split("/")[0]
    parts = first.split(".")
    return ".".join(parts[:2]) + "."


def keep_version(target: Target, version: str) -> bool:
    return version.startswith(prefix_for(target))


def release(version: str, date: dt.date, source: str, url: str, extra: dict | None = None) -> dict:
    row = {
        "version": version,
        "date": date.isoformat(),
        "date_ru": date.strftime("%d.%m.%Y"),
        "source": source,
        "url": url,
    }
    if extra:
        row.update(extra)
    return row


def unique_releases(rows: Iterable[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for row in rows:
        version = row["version"]
        current = best.get(version)
        if current is None or row["date"] > current["date"]:
            best[version] = row
    return sorted(best.values(), key=lambda row: version_key(row["version"]), reverse=True)


def parse_releases_page(target: Target) -> tuple[list[dict], str | None]:
    assert target.nick
    url = f"https://releases.1c.ru/project/{urllib.parse.quote(target.nick)}?allUpdates=true#updates"
    status, raw = fetch(url, auth=True)
    if status != 200:
        return [], f"releases.1c.ru status {status}"
    text = clean_text(raw)
    rows = []
    pattern = re.compile(r"\b(\d+(?:\.\d+){2,3})\b\s+(\d{2}\.\d{2}\.\d{2,4})\b")
    for version, date_text in pattern.findall(text):
        date = parse_date(date_text)
        if date and keep_version(target, version):
            rows.append(release(version, date, "releases.1c.ru", url))
    rows = unique_releases(rows)
    return rows, None if rows else "no release rows parsed"


def parse_rarus6(target: Target) -> tuple[list[dict], str | None]:
    rows = []
    for year in RARUS6_YEARS:
        url = f"https://rarus.ru/1c-auto/releases-alfa-avto-avtosalon-avtoservis-avtozapchasti-korp-redaktsiya-6-{year}/"
        status, raw = fetch(url)
        if status != 200:
            continue
        text = clean_text(raw)
        for version, date_text in re.findall(r"Релиз\s+(6\.\d+\.\d+\.\d+)\s+от\s+(\d{2}\.\d{2}\.\d{4})", text):
            date = parse_date(date_text)
            if date and keep_version(target, version):
                rows.append(release(version, date, "rarus.ru release page", url))
    rows = unique_releases(rows)
    return rows, None if rows else "no Rarus 6 rows parsed"


def parse_rarus5(target: Target) -> tuple[list[dict], str | None]:
    rows = []
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
                version = versions[0]
                if date and keep_version(target, version):
                    rows.append(release(version, date, "rarus.ru forum", url, {"time": date_match.group(2), "message": message_id}))
    rows = unique_releases(rows)
    return rows, None if rows else "no Rarus 5 forum rows parsed"


def collect_target(target: Target) -> tuple[list[dict], str | None]:
    if target.source == "releases":
        return parse_releases_page(target)
    if target.source == "rarus6":
        return parse_rarus6(target)
    if target.source == "rarus5":
        return parse_rarus5(target)
    return [], f"unknown source {target.source}"


def row_date(row: dict) -> dt.date:
    return dt.date.fromisoformat(row["date"])


def select_year_ago_release(rows: list[dict], latest: dict, days: int) -> tuple[dt.date, dict | None]:
    cutoff = row_date(latest) - dt.timedelta(days=days)
    for row in rows:
        if row_date(row) <= cutoff:
            return cutoff, row
    return cutoff, None


def period_rows(rows: list[dict], cutoff: dt.date, baseline: dict | None) -> list[dict]:
    selected = [row for row in rows if row_date(row) >= cutoff]
    if baseline and baseline not in selected:
        selected.append(baseline)
    return selected


def summarize(target: Target, rows: list[dict], days: int) -> dict:
    latest = rows[0] if rows else None
    cutoff, baseline = select_year_ago_release(rows, latest, days) if latest else (None, None)
    period = period_rows(rows, cutoff, baseline) if cutoff else []
    return {
        "template": target.template,
        "name": target.name,
        "group": target.group,
        "source": target.source,
        "latest": latest,
        "year_ago_release": baseline,
        "period": {
            "days": days,
            "cutoff": cutoff.isoformat() if cutoff else None,
            "count": len(period),
        },
    }


def skipped_summary(target: Target, reason: str, days: int) -> dict:
    return {
        "template": target.template,
        "name": target.name,
        "group": target.group,
        "source": target.source,
        "latest": None,
        "year_ago_release": None,
        "skipped_reason": reason,
        "period": {
            "days": days,
            "cutoff": None,
            "count": 0,
        },
    }


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(cell).replace("\n", " ") for cell in row) + " |")
    return "\n".join(out)


def render_markdown(data: dict) -> str:
    summary_rows = []
    for item in data["summary"]:
        latest = item.get("latest") or {}
        year_ago = item.get("year_ago_release") or {}
        period = item["period"]
        summary_rows.append([
            item["template"],
            latest.get("version") or "skipped",
            latest.get("date_ru", ""),
            year_ago.get("version") or "skipped",
            year_ago.get("date_ru", ""),
            str(period["count"]),
            item["source"],
        ])
    release_rows = []
    for row in data["releases"]:
        release_rows.append([
            row["template"],
            row["version"],
            row["date_ru"],
            row["source"],
        ])
    skipped_rows = [[row["template"], row["reason"]] for row in data["skipped"]]
    chunks = [
        f"# 1C release dates\n\nGenerated: {data['generated_at']}\nPeriod: latest release date minus {data['period']['days']} days per target\n",
        "## Summary\n\n" + md_table(["template", "latest", "latest_date", "year_ago", "year_ago_date", "releases_in_period", "source"], summary_rows),
        "## Releases In Period\n\n" + md_table(["template", "version", "date", "source"], release_rows),
    ]
    if skipped_rows:
        chunks.append("## Skipped\n\n" + md_table(["template", "reason"], skipped_rows))
    return "\n\n".join(chunks) + "\n"


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="lookback window, default: 365")
    parser.add_argument("--json-out", default="release_dates.json")
    parser.add_argument("--md-out", default="release_dates.md")
    parser.add_argument("--only", action="append", help="template id to collect; can be repeated")
    args = parser.parse_args()

    wanted = set(args.only or [])
    targets = [target for target in TARGETS if not wanted or target.template in wanted]

    summary = []
    releases = []
    skipped = []
    for target in targets:
        rows, error = collect_target(target)
        if not rows:
            reason = error or "no rows"
            summary.append(skipped_summary(target, reason, args.days))
            skipped.append({
                "template": target.template,
                "name": target.name,
                "source": target.source,
                "reason": reason,
            })
            continue
        item = summarize(target, rows, args.days)
        if not item.get("year_ago_release"):
            reason = f"no release parsed at or before {item['period']['cutoff']}"
            item["skipped_reason"] = reason
            summary.append(item)
            skipped.append({
                "template": target.template,
                "name": target.name,
                "source": target.source,
                "reason": reason,
            })
            continue
        summary.append(item)
        cutoff = dt.date.fromisoformat(item["period"]["cutoff"])
        for row in period_rows(rows, cutoff, item.get("year_ago_release")):
            releases.append({"template": target.template, "name": target.name, **row})

    releases.sort(key=lambda row: (row["template"], row["date"], row["version"]), reverse=True)
    data = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "period": {"mode": "latest_minus_days_per_target", "days": args.days},
        "summary": summary,
        "releases": releases,
        "skipped": skipped,
    }

    with open(args.json_out, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
        fp.write("\n")
    markdown = render_markdown(data)
    with open(args.md_out, "w", encoding="utf-8") as fp:
        fp.write(markdown)
    print(markdown)
    print(f"JSON: {args.json_out}", file=sys.stderr)
    print(f"Markdown: {args.md_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
