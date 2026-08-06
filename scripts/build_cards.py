#!/usr/bin/env python3
"""
Build the Scale Us branded SVG cards for the GitHub profile README.

Why this exists instead of github-readme-stats / github-profile-trophy:
  1. Those public instances are frequently over quota (503 / 402). A profile that
     depends on them shows broken images — verified 2026-08-05, including on
     several very popular profiles.
  2. They can only read PUBLIC repos. This account is 40 private repos, so every
     public widget reports ~0. This script authenticates and reports the truth.

Usage:  GITHUB_TOKEN=ghp_xxx python3 scripts/build_cards.py
Cards are written to assets/ as static SVG. Re-run (or let the weekly workflow
run) to refresh the numbers.
"""

import json
import os
import sys
import urllib.request
import urllib.error
from collections import Counter
from datetime import date, datetime, timedelta, timezone

USER = "Jasminder-Chhabra"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

# ---------------------------------------------------------------- brand tokens
# Straight from scale-design-system/tokens/tokens.json (the violet "atlas" system).
INK_950, INK_900, INK_800, INK_700 = "#0A0A12", "#1B1530", "#2A2342", "#3E3658"
INK_400, INK_300 = "#A39BB3", "#CBC5D6"
VIOLET, VIOLET_DEEP, VIOLET_MID = "#7C3AED", "#4C1D95", "#6D28D9"
MINT, PAPER_0, PAPER_200 = "#EDE9FE", "#FBFAF6", "#E5DFD0"
CORAL, AMBER, SKY, CYAN = "#EC4899", "#F59E0B", "#3B82F6", "#06B6D4"

SERIF = "Georgia,'Times New Roman',serif"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Helvetica,Arial,sans-serif"
MONO = "ui-monospace,'SF Mono','JetBrains Mono',Menlo,Consolas,monospace"


# ---------------------------------------------------------------------- github
def gh(url, token):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "scaleus-profile-cards",
    })
    return json.load(urllib.request.urlopen(req, timeout=30))


def gql(query, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": f"Bearer {token}", "User-Agent": "scaleus-profile-cards"},
    )
    return json.load(urllib.request.urlopen(req, timeout=30))


def streaks(token, created_year):
    """Day-by-day calendar → streaks and consistency, computed here rather than
    trusted to a third-party widget. streak-stats.demolab.com was reporting an
    8-day current streak against a real 55, and a total ~700 short."""
    days = {}
    this_year = datetime.now(timezone.utc).year
    for y in range(created_year, this_year + 1):
        q = ('query{viewer{contributionsCollection(from:"%d-01-01T00:00:00Z",'
             'to:"%d-12-31T23:59:59Z"){contributionCalendar{weeks{contributionDays'
             "{date contributionCount}}}}}}" % (y, y))
        cal = gql(q, token)["data"]["viewer"]["contributionsCollection"]["contributionCalendar"]
        for wk in cal["weeks"]:
            for d in wk["contributionDays"]:
                days[d["date"]] = d["contributionCount"]

    today = datetime.now(timezone.utc).date()
    days = {k: v for k, v in days.items() if date.fromisoformat(k) <= today}
    keys = sorted(days)
    if not keys:
        return {}

    best = cur = 0
    best_from = best_to = cur_from = None
    prev = None
    for k in keys:
        d = date.fromisoformat(k)
        if days[k] > 0:
            if prev is not None and (d - prev).days == 1 and cur > 0:
                cur += 1
            else:
                cur, cur_from = 1, k
            if cur > best:
                best, best_from, best_to = cur, cur_from, k
        else:
            cur = 0
        prev = d

    # Walk back from the latest day; an empty today doesn't break the streak yet.
    walk = date.fromisoformat(keys[-1])
    if days.get(today.isoformat(), 0) == 0:
        walk -= timedelta(days=1)
    live = 0
    live_from = None
    while walk.isoformat() in days and days[walk.isoformat()] > 0:
        live += 1
        live_from = walk.isoformat()
        walk -= timedelta(days=1)

    active = sum(1 for v in days.values() if v > 0)
    return {
        "current_streak": live,
        "current_streak_from": live_from,
        "longest_streak": best,
        "longest_from": best_from,
        "longest_to": best_to,
        "active_days": active,
        "tracked_days": len(keys),
        "best_day": max(days.values()),
        "first_day": keys[0],
    }


def collect(token):
    """Pull real numbers. Falls back to the committed metrics.json if the API is
    unavailable, so a failed refresh never blanks the profile."""
    user = gh("https://api.github.com/user", token)
    created_year = int(user["created_at"][:4])
    this_year = datetime.now(timezone.utc).year

    contributions = commits = prs = 0
    years = {}
    for y in range(created_year, this_year + 1):
        q = (
            'query{viewer{contributionsCollection(from:"%d-01-01T00:00:00Z",'
            'to:"%d-12-31T23:59:59Z"){totalCommitContributions '
            'restrictedContributionsCount totalPullRequestContributions '
            "contributionCalendar{totalContributions}}}}" % (y, y)
        )
        c = gql(q, token)["data"]["viewer"]["contributionsCollection"]
        total = c["contributionCalendar"]["totalContributions"]
        years[y] = total
        contributions += total
        commits += c["totalCommitContributions"]
        prs += c["totalPullRequestContributions"]

    repos = gh("https://api.github.com/user/repos?per_page=100&sort=pushed", token)
    langs = Counter()
    for r in repos:
        try:
            langs.update(gh(r["languages_url"], token))
        except urllib.error.HTTPError:
            pass

    return {
        "generated": datetime.now(timezone.utc).strftime("%d %b %Y"),
        "contributions": contributions,
        "contributions_this_year": years.get(this_year, 0),
        "commits": commits,
        "prs": prs,
        # Count the listing rather than trusting user.total_private_repos — that
        # counter reads 0 for fine-grained tokens even when the repos are visible.
        "private_repos": sum(1 for r in repos if r["private"]),
        "public_repos": sum(1 for r in repos if not r["private"]),
        "since": created_year,
        "code_bytes": sum(langs.values()),
        "languages": langs.most_common(20),
        "years": years,
        **streaks(token, created_year),
    }


# Lifetime totals only ever grow. If a refresh reports LESS than what is already
# committed, the token was degraded (fine-grained PATs silently return public-only
# figures from contributionsCollection) — not that the work disappeared. Keep the
# larger value so a weak token can never quietly shrink the card.
MONOTONIC = ("contributions", "contributions_this_year", "commits", "prs",
             "private_repos", "public_repos", "code_bytes",
             "longest_streak", "active_days", "tracked_days", "best_day")


def merge(fresh, previous):
    if not previous:
        return fresh
    degraded = []
    for k in MONOTONIC:
        old, new = previous.get(k, 0), fresh.get(k, 0)
        if new < old:
            degraded.append(f"{k} {new}<{old}")
            fresh[k] = old
    if len(fresh.get("languages") or []) < len(previous.get("languages") or []):
        degraded.append("languages")
        fresh["languages"] = previous["languages"]
    if degraded:
        print("warn: token returned degraded data, kept committed values for: "
              + ", ".join(degraded), file=sys.stderr)
        print("      → use a CLASSIC token with the full `repo` scope for METRICS_TOKEN.",
              file=sys.stderr)
    return fresh


# ------------------------------------------------------------------ svg pieces
def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def defs(uid):
    """Shared gradients + the faint grid used on scaleus.in OG images."""
    return f"""
  <defs>
    <linearGradient id="g{uid}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{VIOLET}"/><stop offset="100%" stop-color="{VIOLET_DEEP}"/>
    </linearGradient>
    <radialGradient id="blob{uid}" cx="50%" cy="50%">
      <stop offset="0%" stop-color="{VIOLET}" stop-opacity=".55"/>
      <stop offset="100%" stop-color="{VIOLET}" stop-opacity="0"/>
    </radialGradient>
    <pattern id="grid{uid}" width="26" height="26" patternUnits="userSpaceOnUse">
      <path d="M26 0H0V26" fill="none" stroke="{PAPER_0}" stroke-opacity=".045" stroke-width="1"/>
    </pattern>
  </defs>"""


def shell(w, h, uid, title):
    """Dark violet card body — deliberately the same on GitHub light AND dark
    themes, so it reads as brand rather than as a theming accident."""
    return f"""  <rect width="{w}" height="{h}" rx="16" fill="{INK_900}"/>
  <rect width="{w}" height="{h}" rx="16" fill="url(#grid{uid})"/>
  <circle cx="{w-40}" cy="-10" r="150" fill="url(#blob{uid})"/>
  <rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="15.5" fill="none"
        stroke="{VIOLET}" stroke-opacity=".22"/>
  <title>{esc(title)}</title>"""


def fmt(n):
    return f"{n:,}"


# ------------------------------------------------------------------- the cards
def hero(m):
    w, h, u = 1000, 260, "H"
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="Jasminder Singh, Founder and CEO of Scale Us Technologies">',
        defs(u),
        f'  <rect width="{w}" height="{h}" rx="18" fill="{INK_950}"/>',
        f'  <rect width="{w}" height="{h}" rx="18" fill="url(#grid{u})"/>',
        f'  <circle cx="880" cy="40" r="230" fill="url(#blob{u})"/>',
        f'  <circle cx="120" cy="250" r="180" fill="url(#blob{u})" opacity=".5"/>',
        # thin arcs, echoing the scaleus.in OG template
        f'  <path d="M700 260 A200 200 0 0 1 900 60" fill="none" stroke="{VIOLET}" stroke-opacity=".3" stroke-width="1.5"/>',
        f'  <path d="M660 260 A240 240 0 0 1 900 20" fill="none" stroke="{VIOLET}" stroke-opacity=".18" stroke-width="1.5"/>',
        f'  <rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="17.5" fill="none" stroke="{VIOLET}" stroke-opacity=".25"/>',
    ]
    # eyebrow pill
    parts += [
        f'  <rect x="56" y="52" width="212" height="30" rx="15" fill="{VIOLET}" fill-opacity=".16" stroke="{VIOLET}" stroke-opacity=".45"/>',
        f'  <circle cx="76" cy="67" r="4" fill="{AMBER}"><animate attributeName="opacity" values="1;.25;1" dur="2.4s" repeatCount="indefinite"/></circle>',
        f'  <text x="90" y="72" font-family="{MONO}" font-size="12" letter-spacing="1.6" fill="{MINT}">SCALE US TECHNOLOGIES</text>',
    ]
    # name + role
    parts += [
        f'  <text x="56" y="140" font-family="{SERIF}" font-size="52" fill="{PAPER_0}">Jasminder Singh</text>',
        f'  <text x="56" y="180" font-family="{SERIF}" font-size="30" font-style="italic" fill="{VIOLET}">Founder &amp; CEO — I ship the whole stack.</text>',
        f'  <text x="56" y="216" font-family="{SANS}" font-size="15" fill="{INK_300}">'
        f'AI voice agents · WhatsApp Business API · SaaS platforms · Flutter apps · self-hosted infra</text>',
    ]
    # Right-hand stat rail. Laid out as rows (not a horizontal ticker) so it can
    # never collide with the tagline, whatever font the renderer substitutes.
    parts.append(f'  <line x1="672" y1="52" x2="672" y2="208" stroke="{VIOLET}" stroke-opacity=".3"/>')
    # Verified by hand: every URL returns 200 and every store listing resolves.
    stats = [("9", "products in the suite"), ("20", "live production sites"), ("15", "apps on the stores")]
    for i, (n, lbl) in enumerate(stats):
        cy = 96 + i * 46
        parts += [
            f'  <text x="742" y="{cy}" font-family="{SERIF}" font-size="34" fill="{PAPER_0}" text-anchor="end">{n}</text>',
            f'  <text x="756" y="{cy-2}" font-family="{SANS}" font-size="13.5" fill="{INK_300}">{lbl}</text>',
        ]
    parts.append("</svg>")
    return "\n".join(parts)


def stats_card(m):
    w, h, u = 500, 300, "S"
    tiles = [
        (fmt(m["contributions"]), "CONTRIBUTIONS", VIOLET),
        (fmt(m["commits"]), "COMMITS", CORAL),
        (fmt(m["prs"]), "PULL REQUESTS", AMBER),
        (fmt(m["contributions_this_year"]), "THIS YEAR", MINT),
        (fmt(m["private_repos"] + m["public_repos"]), "REPOSITORIES", SKY),
        (f'{m["code_bytes"]/1e6:.0f} MB', "SOURCE CODE", CYAN),
    ]
    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="GitHub statistics including private repositories">',
        defs(u), shell(w, h, u, "GitHub stats (private repos included)"),
        f'  <text x="28" y="42" font-family="{SERIF}" font-size="22" fill="{PAPER_0}">By the numbers</text>',
        f'  <text x="28" y="63" font-family="{MONO}" font-size="10" letter-spacing="1.2" fill="{VIOLET}">'
        f'INCLUDING {m["private_repos"]} PRIVATE REPOSITORIES</text>',
        f'  <line x1="28" y1="78" x2="{w-28}" y2="78" stroke="{INK_700}"/>',
    ]
    for i, (val, lbl, col) in enumerate(tiles):
        cx = 28 + (i % 3) * 152
        cy = 108 + (i // 3) * 92
        p += [
            f'  <rect x="{cx}" y="{cy-24}" width="140" height="74" rx="10" fill="{INK_800}" fill-opacity=".7" stroke="{col}" stroke-opacity=".28"/>',
            f'  <rect x="{cx}" y="{cy-24}" width="3.5" height="74" rx="2" fill="{col}"/>',
            f'  <text x="{cx+16}" y="{cy+10}" font-family="{SERIF}" font-size="27" fill="{PAPER_0}">{val}</text>',
            f'  <text x="{cx+16}" y="{cy+34}" font-family="{MONO}" font-size="9" letter-spacing="1" fill="{INK_400}">{lbl}</text>',
        ]
    p.append(f'  <text x="{w-28}" y="{h-14}" font-family="{MONO}" font-size="9" fill="{INK_700}" text-anchor="end">updated {m["generated"]}</text>')
    p.append("</svg>")
    return "\n".join(p)


def lang_card(m):
    w, h, u = 500, 300, "L"
    palette = [VIOLET, CORAL, AMBER, SKY, CYAN, INK_400]
    total = m["code_bytes"] or 1
    top = m["languages"][:5]
    shown = sum(v for _, v in top)
    rows = [(k, v / total * 100) for k, v in top]
    if total - shown > 0:
        rows.append(("Other", (total - shown) / total * 100))

    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="Language breakdown across all repositories">',
        defs(u), shell(w, h, u, "Languages across all repos"),
        f'  <text x="28" y="42" font-family="{SERIF}" font-size="22" fill="{PAPER_0}">What it&#8217;s written in</text>',
        f'  <text x="28" y="63" font-family="{MONO}" font-size="10" letter-spacing="1.2" fill="{VIOLET}">{m["code_bytes"]/1e6:.0f} MB ACROSS EVERY REPO, PUBLIC + PRIVATE</text>',
        f'  <line x1="28" y1="78" x2="{w-28}" y2="78" stroke="{INK_700}"/>',
    ]
    # stacked bar
    bar_x, bar_w, bar_y = 28, w - 56, 98
    off = 0.0
    p.append(f'  <clipPath id="bc{u}"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="16" rx="8"/></clipPath>')
    p.append(f'  <g clip-path="url(#bc{u})">')
    for i, (name, pct) in enumerate(rows):
        seg = bar_w * pct / 100
        p.append(f'    <rect x="{bar_x+off:.1f}" y="{bar_y}" width="{seg:.1f}" height="16" '
                 f'fill="{palette[i%len(palette)]}"/>')
        off += seg
    p.append("  </g>")

    # legend, two columns
    for i, (name, pct) in enumerate(rows):
        cx = 30 + (i % 2) * 232
        cy = 152 + (i // 2) * 40
        col = palette[i % len(palette)]
        p += [
            f'  <circle cx="{cx+6}" cy="{cy-4}" r="5.5" fill="{col}"/>',
            f'  <text x="{cx+22}" y="{cy}" font-family="{SANS}" font-size="14" font-weight="600" fill="{PAPER_0}">{esc(name)}</text>',
            f'  <text x="{cx+200}" y="{cy}" font-family="{MONO}" font-size="12.5" fill="{col}" text-anchor="end">{pct:.1f}%</text>',
        ]
    p.append(f'  <text x="28" y="{h-16}" font-family="{SANS}" font-size="11" fill="{INK_400}">'
             f'Laravel/Blade monoliths, Node + TypeScript services, Flutter apps.</text>')
    p.append("</svg>")
    return "\n".join(p)


def experience_card(m):
    """The track record that predates this account. Figures are the ones Scale Us
    publishes on scaleus.in/about — nothing here is derived from GitHub."""
    w, h, u = 1000, 190, "X"
    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="Track record: 600+ projects delivered, 50,000+ hours of code, teams in 60+ countries, 4.9 star rating">',
        defs(u),
        f'  <rect width="{w}" height="{h}" rx="16" fill="{INK_950}"/>',
        f'  <rect width="{w}" height="{h}" rx="16" fill="url(#grid{u})"/>',
        f'  <circle cx="60" cy="180" r="170" fill="url(#blob{u})" opacity=".6"/>',
        f'  <rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="15.5" fill="none" stroke="{VIOLET}" stroke-opacity=".22"/>',
        f'  <text x="44" y="52" font-family="{SERIF}" font-size="26" fill="{PAPER_0}">Fifteen years before the first commit</text>',
        f'  <text x="44" y="76" font-family="{SANS}" font-size="13.5" fill="{INK_300}">'
        f'This account opens in 2023. The work doesn&#8217;t &#8212; most of it shipped long before I moved the whole operation onto Git.</text>',
        f'  <line x1="44" y1="98" x2="{w-44}" y2="98" stroke="{INK_700}"/>',
    ]
    tiles = [("600+", "projects delivered", VIOLET), ("50K+", "hours of code", CORAL),
             ("60+", "countries served", AMBER), ("20+", "AI products live", SKY),
             ("4.9/5", "client rating", CYAN)]
    for i, (val, lbl, col) in enumerate(tiles):
        cx = 44 + i * 186
        p += [
            f'  <rect x="{cx}" y="118" width="4" height="44" rx="2" fill="{col}"/>',
            f'  <text x="{cx+16}" y="144" font-family="{SERIF}" font-size="30" fill="{PAPER_0}">{val}</text>',
            f'  <text x="{cx+16}" y="162" font-family="{MONO}" font-size="9.5" letter-spacing=".9" fill="{INK_400}">{lbl.upper()}</text>',
        ]
    p.append("</svg>")
    return "\n".join(p)


def streak_card(m):
    """Replaces the third-party streak widget, which was reporting a stale total
    and an 8-day current streak against a real 55."""
    w, h, u = 1000, 190, "K"

    def pretty(iso):
        if not iso:
            return ""
        d = date.fromisoformat(iso)
        return d.strftime("%-d %b %Y") if os.name != "nt" else d.strftime("%d %b %Y")

    active, tracked = m.get("active_days", 0), m.get("tracked_days", 1) or 1
    pct = round(active / tracked * 100)
    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="Contribution consistency: {fmt(m["contributions"])} total, {m.get("current_streak",0)}-day current streak, {m.get("longest_streak",0)}-day longest streak">',
        defs(u),
        f'  <rect width="{w}" height="{h}" rx="16" fill="{INK_900}"/>',
        f'  <rect width="{w}" height="{h}" rx="16" fill="url(#grid{u})"/>',
        f'  <circle cx="{w-60}" cy="0" r="170" fill="url(#blob{u})" opacity=".7"/>',
        f'  <rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="15.5" fill="none" stroke="{VIOLET}" stroke-opacity=".22"/>',
        f'  <text x="32" y="44" font-family="{SERIF}" font-size="23" fill="{PAPER_0}">Consistency</text>',
        f'  <text x="32" y="65" font-family="{MONO}" font-size="10" letter-spacing="1.2" fill="{VIOLET}">'
        f'COMPUTED FROM THE GITHUB API, NOT A THIRD-PARTY WIDGET</text>',
        f'  <line x1="32" y1="80" x2="{w-32}" y2="80" stroke="{INK_700}"/>',
    ]
    tiles = [
        (fmt(m["contributions"]), "TOTAL CONTRIBUTIONS", f'since {pretty(m.get("first_day"))}', VIOLET),
        (str(m.get("current_streak", 0)), "DAY CURRENT STREAK", f'from {pretty(m.get("current_streak_from"))}', CORAL),
        (str(m.get("longest_streak", 0)), "DAY LONGEST STREAK", f'{pretty(m.get("longest_from"))}', AMBER),
        (f"{pct}%", "OF DAYS ACTIVE", f'{fmt(active)} of {fmt(tracked)} days', SKY),
        (fmt(m.get("best_day", 0)), "BUSIEST SINGLE DAY", "peak output", CYAN),
    ]
    for i, (val, lbl, sub, col) in enumerate(tiles):
        cx = 32 + i * 188
        p += [
            f'  <rect x="{cx}" y="100" width="4" height="58" rx="2" fill="{col}"/>',
            f'  <text x="{cx+15}" y="128" font-family="{SERIF}" font-size="30" fill="{PAPER_0}">{val}</text>',
            f'  <text x="{cx+15}" y="145" font-family="{MONO}" font-size="8.5" letter-spacing=".8" fill="{INK_400}">{lbl}</text>',
            f'  <text x="{cx+15}" y="158" font-family="{SANS}" font-size="9.5" fill="{INK_700}">{esc(sub)}</text>',
        ]
    p.append("</svg>")
    return "\n".join(p)


def main():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    metrics_path = os.path.join(OUT, "metrics.json")

    previous = None
    if os.path.exists(metrics_path):
        with open(metrics_path) as fh:
            previous = json.load(fh)
        previous["languages"] = [tuple(x) for x in previous["languages"]]

    m = None
    if token:
        try:
            m = merge(collect(token), previous)
        except Exception as e:  # noqa: BLE001 - never let a refresh blank the profile
            print(f"warn: live fetch failed ({e}); reusing committed metrics", file=sys.stderr)
    if m is None:
        m = previous
    if m is None:
        sys.exit("no token and no committed metrics.json — cannot build cards")

    os.makedirs(OUT, exist_ok=True)
    with open(metrics_path, "w") as fh:
        json.dump(m, fh, indent=2)
    cards = (("hero", hero(m)), ("stats", stats_card(m)),
             ("languages", lang_card(m)), ("experience", experience_card(m)),
             ("streak", streak_card(m)))
    for name, svg in cards:
        with open(os.path.join(OUT, f"{name}.svg"), "w") as fh:
            fh.write(svg)
        print(f"wrote assets/{name}.svg")


if __name__ == "__main__":
    main()
