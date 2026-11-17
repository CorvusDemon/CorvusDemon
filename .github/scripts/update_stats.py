import html
import json
import math
import os
import urllib.request

PALETTE = {
    "bg": "#14070c",
    "border": "#332f52",
    "grid": "#23162b",
    "halo": "#f0bdb9",
    "cobalt": "#4172ad",
    "lilac": "#be96ae",
    "indigo": "#444a77",
    "mauve": "#867293",
}

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      totalIssueContributions
      totalRepositoryContributions
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes {
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges {
            size
            node {
              name
            }
          }
        }
      }
    }
  }
}
"""


def fetch_github_data(token: str, username: str) -> dict:
    payload = json.dumps({"query": QUERY, "variables": {"login": username}}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-stats-generator",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "errors" in data:
        raise RuntimeError(f"GraphQL error: {data['errors']}")
    return data["data"]["user"]


def compute_languages(user_data: dict) -> list[tuple[str, int]]:
    totals: dict[str, int] = {}
    for repo in user_data["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            totals[name] = totals.get(name, 0) + edge["size"]

    if not totals:
        return [("Markdown", 100)]

    top = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:5]
    total_bytes = sum(size for _, size in top)
    raw_pcts = [size * 100.0 / total_bytes for _, size in top]
    int_pcts = [max(1, int(round(p))) for p in raw_pcts]

    diff = 100 - sum(int_pcts)
    int_pcts[0] = max(1, int_pcts[0] + diff)
    return [(name, pct) for (name, _), pct in zip(top, int_pcts)]


def render_languages_svg(lang_items: list[tuple[str, int]]) -> str:
    slots = [
        {"cx": 268, "cy": 182, "r": 70, "fill": PALETTE["cobalt"], "fg": "#f6e8ea", "sub": PALETTE["halo"], "fs": 16},
        {"cx": 404, "cy": 168, "r": 54, "fill": PALETTE["lilac"],  "fg": PALETTE["bg"], "sub": PALETTE["grid"], "fs": 13.5},
        {"cx": 144, "cy": 164, "r": 44, "fill": PALETTE["indigo"], "fg": PALETTE["halo"], "sub": PALETTE["lilac"], "fs": 12.5},
        {"cx": 94,  "cy": 232, "r": 30, "fill": PALETTE["mauve"],  "fg": PALETTE["bg"], "sub": PALETTE["bg"], "fs": 10.5},
        {"cx": 182, "cy": 246, "r": 24, "fill": PALETTE["halo"],   "fg": PALETTE["bg"], "sub": PALETTE["bg"], "fs": 9.5},
    ]
    sans = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
    mono = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

    bubbles = []
    for (name, pct), s in zip(lang_items, slots):
        safe_name = html.escape(name if len(name) <= 11 else name[:10] + "…")
        bubbles.append(f'  <circle cx="{s["cx"]}" cy="{s["cy"]}" r="{s["r"]}" fill="{s["fill"]}"/>')
        if s["r"] >= 30:
            bubbles.append(
                f'  <text x="{s["cx"]}" y="{s["cy"] - 3}" font-family="{sans}" font-size="{s["fs"]}" '
                f'font-weight="700" fill="{s["fg"]}" text-anchor="middle">{safe_name}</text>'
            )
            bubbles.append(
                f'  <text x="{s["cx"]}" y="{s["cy"] + 14}" font-family="{mono}" font-size="{max(9.5, s["fs"] - 4)}" '
                f'fill="{s["sub"]}" text-anchor="middle">{pct}%</text>'
            )
        else:
            bubbles.append(
                f'  <text x="{s["cx"]}" y="{s["cy"] + 3}" font-family="{sans}" font-size="{s["fs"]}" '
                f'font-weight="700" fill="{s["fg"]}" text-anchor="middle">{safe_name}</text>'
            )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 540 320" width="540" height="320" fill="none">
  <rect x="1" y="1" width="538" height="318" rx="14" fill="{PALETTE["bg"]}" stroke="{PALETTE["border"]}" stroke-width="1.5"/>
  <text x="28" y="36" font-family="{mono}" font-size="10.5" fill="{PALETTE["cobalt"]}" letter-spacing="2">LANGUAGES</text>
  <text x="28" y="64" font-family="{sans}" font-size="22" font-weight="700" fill="{PALETTE["halo"]}">What my code is made of</text>
{chr(10).join(bubbles)}
  <text x="28" y="298" font-family="{mono}" font-size="10" fill="{PALETTE["mauve"]}">top repositories by byte share</text>
</svg>
'''


def render_radar_svg(contrib: dict) -> str:
    stats = {
        "commits": contrib["totalCommitContributions"],
        "prs": contrib["totalPullRequestContributions"],
        "reviews": contrib["totalPullRequestReviewContributions"],
        "issues": contrib["totalIssueContributions"],
        "repos": contrib["totalRepositoryContributions"],
    }
    rcx, rcy, max_r = 185, 192, 74
    angles = [-90, -18, 54, 126, 198]
    keys = ["commits", "prs", "reviews", "issues", "repos"]
    labels = [
        ("Commits",   185, 98,  "middle"),
        ("PRs",       268, 164, "start"),
        ("Reviews",   236, 266, "start"),
        ("Issues",    134, 266, "end"),
        ("New repos", 102, 164, "end"),
    ]
    sans = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
    mono = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

    grid_polys = []
    for lv in (0.25, 0.5, 0.75, 1.0):
        pts = [
            f"{rcx + max_r * lv * math.cos(math.radians(a)):.1f},{rcy + max_r * lv * math.sin(math.radians(a)):.1f}"
            for a in angles
        ]
        grid_polys.append(f'  <polygon points="{" ".join(pts)}" fill="none" stroke="{PALETTE["border"]}" stroke-width="1"/>')

    spokes = [
        f'  <line x1="{rcx}" y1="{rcy}" x2="{rcx + max_r * math.cos(math.radians(a)):.1f}" '
        f'y2="{rcy + max_r * math.sin(math.radians(a)):.1f}" stroke="{PALETTE["grid"]}" stroke-width="1"/>'
        for a in angles
    ]

    raw_vals = [max(0, stats[k]) for k in keys]
    max_val = max(raw_vals) if max(raw_vals) > 0 else 1
    denom = math.log10(max_val + 1)

    poly_pts, dots = [], []
    for a, v in zip(angles, raw_vals):
        ratio = (math.log10(v + 1) / denom) if v > 0 else 0.12
        ratio = max(0.12, min(1.0, ratio))
        px = rcx + max_r * ratio * math.cos(math.radians(a))
        py = rcy + max_r * ratio * math.sin(math.radians(a))
        poly_pts.append(f"{px:.1f},{py:.1f}")
        dots.append(f'  <circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="{PALETTE["halo"]}" stroke="{PALETTE["bg"]}" stroke-width="1.2"/>')

    label_tags = []
    for (title, lx, ly, anchor), v in zip(labels, raw_vals):
        label_tags.append(
            f'  <text x="{lx}" y="{ly}" font-family="{sans}" font-size="10.5" font-weight="700" '
            f'fill="{PALETTE["halo"]}" text-anchor="{anchor}">{title}</text>'
        )
        label_tags.append(
            f'  <text x="{lx}" y="{ly + 12}" font-family="{mono}" font-size="9.5" '
            f'fill="{PALETTE["mauve"]}" text-anchor="{anchor}">{v:,}</text>'
        )

    top_key = keys[raw_vals.index(max(raw_vals))]
    headlines = {
        "commits": ("Mostly shipping", "and writing code."),
        "prs":     ("Focused on", "pull requests."),
        "reviews": ("Mostly reviewing", "other people’s work."),
        "issues":  ("Active in", "issues & triage."),
        "repos":   ("Building & launching", "new repositories."),
    }
    h1, h2 = headlines[top_key]

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 540 320" width="540" height="320" fill="none">
  <rect x="1" y="1" width="538" height="318" rx="14" fill="{PALETTE["bg"]}" stroke="{PALETTE["border"]}" stroke-width="1.5"/>
  <text x="28" y="36" font-family="{mono}" font-size="10.5" fill="{PALETTE["cobalt"]}" letter-spacing="2">HOW I WORK</text>
  <text x="28" y="64" font-family="{sans}" font-size="22" font-weight="700" fill="{PALETTE["halo"]}">Where my time goes</text>
{chr(10).join(grid_polys)}
{chr(10).join(spokes)}
  <polygon points="{" ".join(poly_pts)}" fill="{PALETTE["cobalt"]}" fill-opacity="0.28" stroke="{PALETTE["halo"]}" stroke-width="1.8"/>
{chr(10).join(dots)}
{chr(10).join(label_tags)}
  <text x="336" y="166" font-family="{sans}" font-size="15" font-weight="700" fill="{PALETTE["halo"]}">{h1}</text>
  <text x="336" y="186" font-family="{sans}" font-size="15" font-weight="700" fill="{PALETTE["halo"]}">{h2}</text>
  <text x="336" y="212" font-family="{mono}" font-size="10" fill="{PALETTE["mauve"]}">Logarithmic scale.</text>
  <text x="336" y="226" font-family="{mono}" font-size="10" fill="{PALETTE["mauve"]}">Last 12 months of</text>
  <text x="336" y="240" font-family="{mono}" font-size="10" fill="{PALETTE["mauve"]}">public activity.</text>
</svg>
'''


def main() -> None:
    token = os.environ["GITHUB_TOKEN"]
    username = os.environ["GITHUB_USERNAME"]
    user_data = fetch_github_data(token, username)

    os.makedirs("assets", exist_ok=True)
    with open("assets/languages.svg", "w", encoding="utf-8") as f:
        f.write(render_languages_svg(compute_languages(user_data)))
    with open("assets/radar.svg", "w", encoding="utf-8") as f:
        f.write(render_radar_svg(user_data["contributionsCollection"]))


if __name__ == "__main__":
    main()
