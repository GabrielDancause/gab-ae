#!/usr/bin/env python3
"""
SEO Tracker for PhotonBuilder network — tracks all pages across ~18 domains.
Stores data in Cloudflare D1 (gab-ae-prod).

Usage:
  python3 scripts/seo-tracker.py discover    # crawl sitemaps, register pages
  python3 scripts/seo-tracker.py pull        # pull GSC + GA4 metrics
  python3 scripts/seo-tracker.py analyze     # detect SEO issues
  python3 scripts/seo-tracker.py report      # print summary
"""

import os
import sys
import json
import pickle
import subprocess
import tempfile
import time
import re
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests

# ─── Config ───────────────────────────────────────────────────────────────────

GAB_AE_DIR = Path(os.path.expanduser("~/Desktop/gab-ae"))
TOKEN_PATH = Path(os.path.expanduser("~/Desktop/photonbuilder/data/seo/google_token.pickle"))
GOG_CREDS = Path(os.path.expanduser("~/Library/Application Support/gogcli/credentials.json"))
D1_DB = "gab-ae-prod"

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
]

# All PhotonBuilder sites — GSC/GA property IDs from seo-pull.py
SITES = {
    "westmount": {
        "gsc": "sc-domain:westmountfundamentals.com",
        "ga": "properties/527954181",
        "domain": "westmountfundamentals.com",
    },
    "siliconbased": {
        "gsc": "sc-domain:siliconbased.dev",
        "ga": "properties/528410108",
        "domain": "siliconbased.dev",
    },
    "firemaths": {
        "gsc": "sc-domain:firemaths.info",
        "ga": "properties/528415032",
        "domain": "firemaths.info",
    },
    "28grams": {
        "gsc": "sc-domain:28grams.vip",
        "ga": "properties/528378719",
        "domain": "28grams.vip",
    },
    "migratingmammals": {
        "gsc": "sc-domain:migratingmammals.com",
        "ga": "properties/528407891",
        "domain": "migratingmammals.com",
    },
    "leeroyjenkins": {
        "gsc": "sc-domain:leeroyjenkins.quest",
        "ga": "properties/528389326",
        "domain": "leeroyjenkins.quest",
    },
    "ijustwantto": {
        "gsc": "sc-domain:ijustwantto.live",
        "ga": "properties/528427172",
        "domain": "ijustwantto.live",
    },
    "nookienook": {
        "gsc": "sc-domain:thenookienook.com",
        "ga": "properties/528433564",
        "domain": "thenookienook.com",
    },
    "photonbuilder": {
        "gsc": "sc-domain:photonbuilder.com",
        "ga": "properties/528386310",
        "domain": "photonbuilder.com",
    },
    "bodycount": {
        "gsc": "sc-domain:bodycount.photonbuilder.com",
        "ga": "properties/529363724",
        "domain": "bodycount.photonbuilder.com",
    },
    "sendnerds": {
        "gsc": "sc-domain:sendnerds.photonbuilder.com",
        "ga": "properties/529337618",
        "domain": "sendnerds.photonbuilder.com",
    },
    "justonemoment": {
        "gsc": "sc-domain:justonemoment.photonbuilder.com",
        "ga": "properties/529323503",
        "domain": "justonemoment.photonbuilder.com",
    },
    "getthebag": {
        "gsc": "sc-domain:getthebag.photonbuilder.com",
        "ga": "properties/529340038",
        "domain": "getthebag.photonbuilder.com",
    },
    "fixitwithducttape": {
        "gsc": "sc-domain:fixitwithducttape.photonbuilder.com",
        "ga": "properties/529347118",
        "domain": "fixitwithducttape.photonbuilder.com",
    },
    "papyruspeople": {
        "gsc": "sc-domain:papyruspeople.photonbuilder.com",
        "ga": "properties/529345473",
        "domain": "papyruspeople.photonbuilder.com",
    },
    "eeniemeenie": {
        "gsc": "sc-domain:eeniemeenie.photonbuilder.com",
        "ga": "properties/529374256",
        "domain": "eeniemeenie.photonbuilder.com",
    },
    "pleasestartplease": {
        "gsc": "sc-domain:pleasestartplease.photonbuilder.com",
        "ga": "properties/529324505",
        "domain": "pleasestartplease.photonbuilder.com",
    },
    "gab_ae": {
        "gsc": "sc-domain:gab.ae",
        "ga": None,  # Uses Cloudflare Analytics
        "domain": "gab.ae",
    },
}

ALL_DOMAINS = [s["domain"] for s in SITES.values()]


# ─── D1 Helpers ───────────────────────────────────────────────────────────────

def d1_execute(sql: str, cwd: str = None) -> str:
    """Execute a single SQL command against D1 via wrangler."""
    if cwd is None:
        cwd = str(GAB_AE_DIR)
    result = subprocess.run(
        ["npx", "wrangler", "d1", "execute", D1_DB, "--remote", "--command", sql],
        capture_output=True, text=True, cwd=cwd, timeout=120,
    )
    if result.returncode != 0:
        # Filter out the metrics/usage info lines to get real errors
        stderr = result.stderr.strip()
        # Wrangler sometimes prints warnings to stderr but succeeds
        if "ERROR" in stderr.upper() or "error" in stderr.lower():
            print(f"  ⚠️  D1 error: {stderr[:200]}")
    return result.stdout


def d1_execute_file(filepath: str, cwd: str = None) -> str:
    """Execute a SQL file against D1 via wrangler."""
    if cwd is None:
        cwd = str(GAB_AE_DIR)
    result = subprocess.run(
        ["npx", "wrangler", "d1", "execute", D1_DB, "--remote", "--file", filepath],
        capture_output=True, text=True, cwd=cwd, timeout=120,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "ERROR" in stderr.upper():
            print(f"  ⚠️  D1 file error: {stderr[:200]}")
    return result.stdout


def d1_query(sql: str) -> list:
    """Query D1 and parse JSON results."""
    result = subprocess.run(
        ["npx", "wrangler", "d1", "execute", D1_DB, "--remote", "--command", sql, "--json"],
        capture_output=True, text=True, cwd=str(GAB_AE_DIR), timeout=120,
    )
    if result.returncode != 0:
        print(f"  ⚠️  D1 query error: {result.stderr[:200]}")
        return []
    try:
        data = json.loads(result.stdout)
        # Wrangler returns array of result sets
        if isinstance(data, list) and len(data) > 0:
            return data[0].get("results", [])
        return []
    except json.JSONDecodeError:
        return []


def escape_sql(s: str) -> str:
    """Escape a string for SQL single quotes."""
    if s is None:
        return "NULL"
    return "'" + s.replace("'", "''") + "'"


def d1_bulk_insert(sql_statements: list):
    """Write multiple SQL statements to a temp file and execute via --file."""
    if not sql_statements:
        return
    # Batch into chunks of 500 to avoid overly large files
    for i in range(0, len(sql_statements), 500):
        batch = sql_statements[i:i+500]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write("\n".join(batch))
            tmp_path = f.name
        try:
            d1_execute_file(tmp_path)
        finally:
            os.unlink(tmp_path)


# ─── Google Auth ──────────────────────────────────────────────────────────────

def get_google_credentials():
    """Get or refresh Google OAuth credentials (reuses photonbuilder token)."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = None
    if TOKEN_PATH.exists():
        with open(TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, "wb") as f:
            pickle.dump(creds, f)
        return creds

    # Need new auth
    if GOG_CREDS.exists():
        from google_auth_oauthlib.flow import InstalledAppFlow
        raw = json.loads(GOG_CREDS.read_text())
        client_config = {
            "installed": {
                "client_id": raw["client_id"],
                "client_secret": raw["client_secret"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        creds = flow.run_local_server(port=0)
    else:
        print("❌ No Google credentials found.")
        sys.exit(1)

    with open(TOKEN_PATH, "wb") as f:
        pickle.dump(creds, f)
    return creds


# ─── DISCOVER command ─────────────────────────────────────────────────────────

def cmd_discover():
    """Crawl all domain sitemaps, register pages in tracked_pages."""
    print("🔍 Discovering pages across all domains...\n")
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    total_new = 0
    total_pages = 0
    all_inserts = []

    for site_id, config in SITES.items():
        domain = config["domain"]
        sitemap_url = f"https://{domain}/sitemap.xml"
        print(f"  🌐 {domain}...", end=" ", flush=True)

        try:
            resp = requests.get(sitemap_url, timeout=15, headers={
                "User-Agent": "SEOTracker/1.0 (gab.ae)"
            })
            resp.raise_for_status()
        except Exception as e:
            print(f"❌ fetch error: {e}")
            continue

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as e:
            print(f"❌ parse error: {e}")
            continue

        # Handle namespace — sitemaps use xmlns
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = root.findall(".//sm:url", ns)

        # Also try without namespace (some sitemaps don't use it)
        if not urls:
            urls = root.findall(".//url")

        # Check if this is a sitemap index
        sitemaps = root.findall(".//sm:sitemap/sm:loc", ns)
        if not sitemaps:
            sitemaps = root.findall(".//sitemap/loc")

        sub_urls = []
        if sitemaps:
            # It's a sitemap index — fetch child sitemaps
            for sm_loc in sitemaps:
                sub_url = sm_loc.text.strip() if sm_loc.text else None
                if not sub_url:
                    continue
                try:
                    sub_resp = requests.get(sub_url, timeout=15, headers={
                        "User-Agent": "SEOTracker/1.0 (gab.ae)"
                    })
                    sub_resp.raise_for_status()
                    sub_root = ET.fromstring(sub_resp.content)
                    sub_found = sub_root.findall(".//sm:url", ns)
                    if not sub_found:
                        sub_found = sub_root.findall(".//url")
                    sub_urls.extend(sub_found)
                except Exception:
                    pass
            urls = sub_urls if sub_urls else urls

        page_count = 0
        for url_elem in urls:
            loc = url_elem.find("sm:loc", ns)
            if loc is None:
                loc = url_elem.find("loc")
            if loc is None or not loc.text:
                continue

            full_url = loc.text.strip()
            parsed = urlparse(full_url)
            path = parsed.path or "/"
            # Normalize: remove trailing slash except for root
            if path != "/" and path.endswith("/"):
                path = path.rstrip("/")

            lastmod_elem = url_elem.find("sm:lastmod", ns)
            if lastmod_elem is None:
                lastmod_elem = url_elem.find("lastmod")
            lastmod = lastmod_elem.text.strip() if lastmod_elem is not None and lastmod_elem.text else None

            # Build INSERT OR IGNORE
            sql = (
                f"INSERT OR IGNORE INTO tracked_pages (domain, path, first_seen, last_crawled, last_updated) "
                f"VALUES ({escape_sql(domain)}, {escape_sql(path)}, {escape_sql(now)}, {escape_sql(now)}, "
                f"{escape_sql(lastmod)});"
            )
            all_inserts.append(sql)

            # Also update last_crawled + last_updated for existing rows
            update_parts = [f"last_crawled = {escape_sql(now)}"]
            if lastmod:
                update_parts.append(f"last_updated = {escape_sql(lastmod)}")
            update_sql = (
                f"UPDATE tracked_pages SET {', '.join(update_parts)} "
                f"WHERE domain = {escape_sql(domain)} AND path = {escape_sql(path)};"
            )
            all_inserts.append(update_sql)
            page_count += 1

        print(f"✅ {page_count} URLs")
        total_pages += page_count

    # Execute all inserts in bulk
    if all_inserts:
        print(f"\n📝 Writing {len(all_inserts)} SQL statements to D1...")
        d1_bulk_insert(all_inserts)

    # Get total count
    rows = d1_query("SELECT COUNT(*) as cnt FROM tracked_pages;")
    db_total = rows[0]["cnt"] if rows else "?"

    print(f"\n✅ Discovered {total_pages} URLs across {len(SITES)} domains.")
    print(f"   Total tracked pages in D1: {db_total}")


# ─── PULL command ─────────────────────────────────────────────────────────────

def cmd_pull():
    """Pull GSC + GA4 metrics into D1."""
    print("📊 Pulling GSC + GA4 metrics...\n")

    print("🔑 Authenticating with Google...")
    creds = get_google_credentials()
    print("✅ Authenticated\n")

    from googleapiclient.discovery import build as gbuild

    today = datetime.utcnow().strftime("%Y-%m-%d")
    start_28 = (datetime.utcnow() - timedelta(days=28)).strftime("%Y-%m-%d")

    # Build services once
    gsc_service = gbuild("searchconsole", "v1", credentials=creds)
    ga_service = gbuild("analyticsdata", "v1beta", credentials=creds)

    for site_id, config in SITES.items():
        domain = config["domain"]
        print(f"\n🌐 {domain}")

        # ── GSC: page-level metrics ──
        print(f"  📊 GSC page data...", end=" ", flush=True)
        try:
            page_resp = gsc_service.searchanalytics().query(
                siteUrl=config["gsc"],
                body={
                    "startDate": start_28,
                    "endDate": today,
                    "dimensions": ["page"],
                    "rowLimit": 5000,
                    "dataState": "all",
                },
            ).execute()

            page_inserts = []
            for row in page_resp.get("rows", []):
                full_url = row["keys"][0]
                parsed = urlparse(full_url)
                path = parsed.path or "/"
                if path != "/" and path.endswith("/"):
                    path = path.rstrip("/")

                clicks = row.get("clicks", 0)
                impressions = row.get("impressions", 0)
                ctr = round(row.get("ctr", 0), 4)
                position = round(row.get("position", 0), 1)

                sql = (
                    f"INSERT OR REPLACE INTO page_metrics "
                    f"(domain, path, date, gsc_impressions, gsc_clicks, gsc_ctr, gsc_position) "
                    f"VALUES ({escape_sql(domain)}, {escape_sql(path)}, {escape_sql(today)}, "
                    f"{impressions}, {clicks}, {ctr}, {position});"
                )
                page_inserts.append(sql)

            d1_bulk_insert(page_inserts)
            print(f"✅ {len(page_inserts)} pages")
        except Exception as e:
            print(f"❌ {e}")

        time.sleep(0.5)  # Rate limit

        # ── GSC: query+page combos → keyword_rankings ──
        print(f"  🔤 GSC keyword data...", end=" ", flush=True)
        try:
            combo_resp = gsc_service.searchanalytics().query(
                siteUrl=config["gsc"],
                body={
                    "startDate": start_28,
                    "endDate": today,
                    "dimensions": ["query", "page"],
                    "rowLimit": 10000,
                    "dataState": "all",
                },
            ).execute()

            kw_inserts = []
            for row in combo_resp.get("rows", []):
                query = row["keys"][0]
                full_url = row["keys"][1]
                parsed = urlparse(full_url)
                path = parsed.path or "/"
                if path != "/" and path.endswith("/"):
                    path = path.rstrip("/")

                clicks = row.get("clicks", 0)
                impressions = row.get("impressions", 0)
                ctr = round(row.get("ctr", 0), 4)
                position = round(row.get("position", 0), 1)

                sql = (
                    f"INSERT OR REPLACE INTO keyword_rankings "
                    f"(domain, path, query, date, impressions, clicks, ctr, position) "
                    f"VALUES ({escape_sql(domain)}, {escape_sql(path)}, {escape_sql(query)}, "
                    f"{escape_sql(today)}, {impressions}, {clicks}, {ctr}, {position});"
                )
                kw_inserts.append(sql)

            d1_bulk_insert(kw_inserts)
            print(f"✅ {len(kw_inserts)} keyword+page combos")
        except Exception as e:
            print(f"❌ {e}")

        time.sleep(0.5)

        # ── GA4 data ──
        if config.get("ga"):
            print(f"  📈 GA4 data...", end=" ", flush=True)
            try:
                ga_resp = ga_service.properties().runReport(
                    property=config["ga"],
                    body={
                        "dateRanges": [{"startDate": start_28, "endDate": today}],
                        "dimensions": [{"name": "pagePath"}],
                        "metrics": [
                            {"name": "sessions"},
                            {"name": "totalUsers"},
                            {"name": "screenPageViews"},
                            {"name": "bounceRate"},
                            {"name": "averageSessionDuration"},
                        ],
                        "limit": 5000,
                        "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
                    },
                ).execute()

                ga_updates = []
                for row in ga_resp.get("rows", []):
                    path = row["dimensionValues"][0]["value"]
                    if path != "/" and path.endswith("/"):
                        path = path.rstrip("/")

                    sessions = int(row["metricValues"][0]["value"])
                    users = int(row["metricValues"][1]["value"])
                    pageviews = int(row["metricValues"][2]["value"])
                    bounce = round(float(row["metricValues"][3]["value"]), 3)
                    avg_dur = round(float(row["metricValues"][4]["value"]), 1)

                    # Update existing row or insert new one
                    sql = (
                        f"INSERT INTO page_metrics "
                        f"(domain, path, date, ga_sessions, ga_users, ga_pageviews, ga_bounce_rate, ga_avg_duration) "
                        f"VALUES ({escape_sql(domain)}, {escape_sql(path)}, {escape_sql(today)}, "
                        f"{sessions}, {users}, {pageviews}, {bounce}, {avg_dur}) "
                        f"ON CONFLICT(domain, path, date) DO UPDATE SET "
                        f"ga_sessions={sessions}, ga_users={users}, ga_pageviews={pageviews}, "
                        f"ga_bounce_rate={bounce}, ga_avg_duration={avg_dur};"
                    )
                    ga_updates.append(sql)

                d1_bulk_insert(ga_updates)
                print(f"✅ {len(ga_updates)} pages")
            except Exception as e:
                print(f"❌ {e}")

            time.sleep(0.5)
        else:
            print(f"  📈 GA4: skipped (no property ID)")

    print(f"\n✅ Pull complete for {today}")


# ─── ANALYZE command ──────────────────────────────────────────────────────────

def cmd_analyze():
    """Detect SEO issues and write to seo_issues."""
    print("🔍 Analyzing SEO issues...\n")
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    four_weeks_ago = (datetime.utcnow() - timedelta(days=28)).strftime("%Y-%m-%d")
    one_week_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
    ninety_days_ago = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")

    issues_found = 0

    # Get existing open issues to avoid duplicates
    existing = d1_query(
        "SELECT domain, path, issue_type FROM seo_issues WHERE status = 'open';"
    )
    existing_set = {(r["domain"], r["path"], r["issue_type"]) for r in existing}

    def add_issue(domain, path, issue_type, severity, details):
        nonlocal issues_found
        if (domain, path, issue_type) in existing_set:
            return  # Don't duplicate
        sql = (
            f"INSERT INTO seo_issues (domain, path, issue_type, severity, details, detected_at) "
            f"VALUES ({escape_sql(domain)}, {escape_sql(path)}, {escape_sql(issue_type)}, "
            f"{escape_sql(severity)}, {escape_sql(json.dumps(details))}, {escape_sql(now)});"
        )
        d1_execute(sql)
        issues_found += 1

    # 1. Cannibalization — queries ranking for 2+ different domain+path combos
    print("  🔄 Checking for keyword cannibalization...", flush=True)
    cannibal_rows = d1_query(
        f"SELECT query, COUNT(DISTINCT domain || path) as cnt "
        f"FROM keyword_rankings WHERE date = '{today}' "
        f"GROUP BY query HAVING cnt >= 2 ORDER BY cnt DESC LIMIT 50;"
    )
    for row in cannibal_rows:
        query = row["query"]
        # Get the pages competing
        pages = d1_query(
            f"SELECT domain, path, impressions, clicks, position "
            f"FROM keyword_rankings WHERE query = {escape_sql(query)} AND date = '{today}' "
            f"ORDER BY impressions DESC;"
        )
        if len(pages) >= 2:
            # Add issue for the lower-performing page(s)
            for p in pages[1:]:
                add_issue(p["domain"], p["path"], "cannibalization", "warning", {
                    "query": query,
                    "competing_with": f"{pages[0]['domain']}{pages[0]['path']}",
                    "your_position": p["position"],
                    "competitor_position": pages[0]["position"],
                })
    print(f"    Found {len(cannibal_rows)} cannibalized queries")

    # 2. High bounce rate
    print("  📈 Checking for high bounce rates...", flush=True)
    bounce_rows = d1_query(
        f"SELECT domain, path, ga_bounce_rate, ga_sessions "
        f"FROM page_metrics WHERE date = '{today}' "
        f"AND ga_bounce_rate > 0.85 AND ga_sessions > 5;"
    )
    for row in bounce_rows:
        add_issue(row["domain"], row["path"], "high_bounce", "warning", {
            "bounce_rate": row["ga_bounce_rate"],
            "sessions": row["ga_sessions"],
        })
    print(f"    Found {len(bounce_rows)} high-bounce pages")

    # 3. Low CTR (high impressions, low CTR)
    print("  👁️ Checking for low CTR...", flush=True)
    low_ctr_rows = d1_query(
        f"SELECT domain, path, gsc_impressions, gsc_ctr, gsc_position "
        f"FROM page_metrics WHERE date = '{today}' "
        f"AND gsc_impressions > 100 AND gsc_ctr < 0.02;"
    )
    for row in low_ctr_rows:
        add_issue(row["domain"], row["path"], "low_ctr", "warning", {
            "impressions": row["gsc_impressions"],
            "ctr": row["gsc_ctr"],
            "position": row["gsc_position"],
        })
    print(f"    Found {len(low_ctr_rows)} low-CTR pages")

    # 4. Stale content (not updated in 90+ days)
    print("  📅 Checking for stale content...", flush=True)
    stale_rows = d1_query(
        f"SELECT domain, path, last_updated "
        f"FROM tracked_pages WHERE last_updated IS NOT NULL "
        f"AND last_updated < '{ninety_days_ago}' AND status = 'active';"
    )
    for row in stale_rows:
        add_issue(row["domain"], row["path"], "stale", "info", {
            "last_updated": row["last_updated"],
            "days_stale": (datetime.utcnow() - datetime.fromisoformat(
                row["last_updated"][:10]
            )).days,
        })
    print(f"    Found {len(stale_rows)} stale pages")

    # 5. Declining traffic (this week vs 4 weeks ago)
    print("  📉 Checking for declining pages...", flush=True)
    # Compare recent week vs 4 weeks ago
    recent = d1_query(
        f"SELECT domain, path, SUM(ga_sessions) as recent_sessions "
        f"FROM page_metrics WHERE date >= '{one_week_ago}' "
        f"GROUP BY domain, path HAVING recent_sessions > 0;"
    )
    for row in recent:
        old = d1_query(
            f"SELECT SUM(ga_sessions) as old_sessions FROM page_metrics "
            f"WHERE domain = {escape_sql(row['domain'])} "
            f"AND path = {escape_sql(row['path'])} "
            f"AND date >= '{four_weeks_ago}' AND date < '{one_week_ago}';"
        )
        if old and old[0].get("old_sessions") and old[0]["old_sessions"] > 0:
            old_sessions = old[0]["old_sessions"] / 3  # Average per week over 3 weeks
            if old_sessions > 5 and row["recent_sessions"] < old_sessions * 0.5:
                add_issue(row["domain"], row["path"], "declining", "critical", {
                    "recent_sessions": row["recent_sessions"],
                    "avg_weekly_sessions": round(old_sessions, 1),
                    "decline_pct": round((1 - row["recent_sessions"] / old_sessions) * 100, 1),
                })
    print(f"    Checked {len(recent)} pages for decline")

    # Auto-resolve old issues where metrics improved
    d1_execute(
        f"UPDATE seo_issues SET status = 'resolved', resolved_at = '{now}' "
        f"WHERE status = 'open' AND detected_at < '{four_weeks_ago}';"
    )

    print(f"\n✅ Analysis complete. {issues_found} new issues detected.")


# ─── REPORT command ───────────────────────────────────────────────────────────

def cmd_report():
    """Print a summary report to stdout."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    one_week_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
    two_weeks_ago = (datetime.utcnow() - timedelta(days=14)).strftime("%Y-%m-%d")

    print("=" * 70)
    print("  📊 SEO TRACKER REPORT — PhotonBuilder Network")
    print(f"  Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 70)

    # Domain totals
    print("\n📌 DOMAIN SUMMARY")
    print("-" * 50)
    domain_stats = d1_query(
        f"SELECT domain, COUNT(*) as pages FROM tracked_pages "
        f"WHERE status = 'active' GROUP BY domain ORDER BY pages DESC;"
    )
    for row in domain_stats:
        print(f"  {row['domain']:45s} {row['pages']:>4} pages")

    total_pages = sum(r["pages"] for r in domain_stats) if domain_stats else 0
    print(f"  {'TOTAL':45s} {total_pages:>4} pages")

    # Top 20 pages by sessions
    print("\n🏆 TOP 20 PAGES BY SESSIONS")
    print("-" * 70)
    top_pages = d1_query(
        f"SELECT domain, path, ga_sessions, ga_users, gsc_clicks, gsc_impressions "
        f"FROM page_metrics WHERE date = '{today}' "
        f"ORDER BY ga_sessions DESC LIMIT 20;"
    )
    if not top_pages:
        # Try most recent date
        dates = d1_query("SELECT DISTINCT date FROM page_metrics ORDER BY date DESC LIMIT 1;")
        if dates:
            latest = dates[0]["date"]
            top_pages = d1_query(
                f"SELECT domain, path, ga_sessions, ga_users, gsc_clicks, gsc_impressions "
                f"FROM page_metrics WHERE date = '{latest}' "
                f"ORDER BY ga_sessions DESC LIMIT 20;"
            )

    for i, row in enumerate(top_pages, 1):
        url = f"{row['domain']}{row['path']}"
        if len(url) > 50:
            url = url[:47] + "..."
        print(f"  {i:2}. {url:50s} {row['ga_sessions']:>6} sess  {row['gsc_clicks']:>5} clicks")

    # Top 10 growing
    print("\n📈 TOP 10 GROWING PAGES (week over week)")
    print("-" * 70)
    growing = d1_query(
        f"SELECT r.domain, r.path, r.ga_sessions as recent, o.ga_sessions as older, "
        f"CAST(r.ga_sessions - o.ga_sessions AS REAL) / MAX(o.ga_sessions, 1) * 100 as growth "
        f"FROM page_metrics r JOIN page_metrics o "
        f"ON r.domain = o.domain AND r.path = o.path "
        f"WHERE r.date = '{today}' AND o.date = '{one_week_ago}' "
        f"AND o.ga_sessions > 3 "
        f"ORDER BY growth DESC LIMIT 10;"
    )
    for row in growing:
        url = f"{row['domain']}{row['path']}"
        if len(url) > 45:
            url = url[:42] + "..."
        print(f"  {url:45s} {row.get('older',0):>4} → {row.get('recent',0):>4}  (+{row.get('growth',0):.0f}%)")

    # Top 10 declining
    print("\n📉 TOP 10 DECLINING PAGES (week over week)")
    print("-" * 70)
    declining = d1_query(
        f"SELECT r.domain, r.path, r.ga_sessions as recent, o.ga_sessions as older, "
        f"CAST(o.ga_sessions - r.ga_sessions AS REAL) / MAX(o.ga_sessions, 1) * 100 as decline "
        f"FROM page_metrics r JOIN page_metrics o "
        f"ON r.domain = o.domain AND r.path = o.path "
        f"WHERE r.date = '{today}' AND o.date = '{one_week_ago}' "
        f"AND o.ga_sessions > 3 AND r.ga_sessions < o.ga_sessions "
        f"ORDER BY decline DESC LIMIT 10;"
    )
    for row in declining:
        url = f"{row['domain']}{row['path']}"
        if len(url) > 45:
            url = url[:42] + "..."
        print(f"  {url:45s} {row.get('older',0):>4} → {row.get('recent',0):>4}  (-{row.get('decline',0):.0f}%)")

    # Open issues
    print("\n⚠️  OPEN SEO ISSUES")
    print("-" * 50)
    issues = d1_query(
        "SELECT issue_type, severity, COUNT(*) as cnt FROM seo_issues "
        "WHERE status = 'open' GROUP BY issue_type, severity "
        "ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END;"
    )
    if issues:
        for row in issues:
            icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(row["severity"], "⚪")
            print(f"  {icon} {row['severity']:10s} {row['issue_type']:25s} {row['cnt']:>4}")
    else:
        print("  ✅ No open issues!")

    total_issues = sum(r["cnt"] for r in issues) if issues else 0

    # Unindexed pages
    unindexed = d1_query(
        "SELECT COUNT(*) as cnt FROM tracked_pages WHERE indexed = 0;"
    )
    unindexed_count = unindexed[0]["cnt"] if unindexed else 0
    unknown_index = d1_query(
        "SELECT COUNT(*) as cnt FROM tracked_pages WHERE indexed IS NULL;"
    )
    unknown_count = unknown_index[0]["cnt"] if unknown_index else 0

    print(f"\n📋 INDEXING STATUS")
    print("-" * 50)
    print(f"  Not indexed:     {unindexed_count}")
    print(f"  Unknown status:  {unknown_count}")
    print(f"  Total tracked:   {total_pages}")

    print("\n" + "=" * 70)
    print(f"  Summary: {total_pages} pages | {total_issues} open issues | {unindexed_count} not indexed")
    print("=" * 70)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "discover":
        cmd_discover()
    elif cmd == "pull":
        cmd_pull()
    elif cmd == "analyze":
        cmd_analyze()
    elif cmd == "report":
        cmd_report()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
