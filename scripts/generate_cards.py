import os
import requests

HEADERS = None
GRAPHQL_URL = "https://api.github.com/graphql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 5, orderBy: {field: SIZE, direction: DESC}) {
          edges {
            size
            node { name color }
          }
        }
      }
    }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""


def fetch_data(token, username):
    headers = {"Authorization": f"bearer {token}"}
    resp = requests.post(
        GRAPHQL_URL,
        json={"query": QUERY, "variables": {"login": username}},
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]["user"]


def compute_totals(user):
    total_stars = sum(r["stargazerCount"] for r in user["repositories"]["nodes"])
    total_repos = user["repositories"]["totalCount"]
    followers = user["followers"]["totalCount"]
    total_contribs = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    return total_stars, total_repos, followers, total_contribs


def compute_languages(user):
    lang_totals = {}
    lang_colors = {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            lang_totals[name] = lang_totals.get(name, 0) + edge["size"]
            lang_colors[name] = edge["node"]["color"] or "#858585"
    total = sum(lang_totals.values()) or 1
    sorted_langs = sorted(lang_totals.items(), key=lambda x: x[1], reverse=True)[:6]
    return [(name, size / total * 100, lang_colors[name]) for name, size in sorted_langs]


def compute_streaks(user):
    days = []
    for week in user["contributionsCollection"]["contributionCalendar"]["weeks"]:
        for day in week["contributionDays"]:
            days.append((day["date"], day["contributionCount"]))
    days.sort()

    best = current_run = 0
    for _, count in days:
        if count > 0:
            current_run += 1
            best = max(best, current_run)
        else:
            current_run = 0

    streak = 0
    for _, count in reversed(days):
        if count > 0:
            streak += 1
        else:
            break

    return streak, best


def svg_card(title, rows, width=420, height=190):
    lines = [
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">',
        "<style>",
        "@keyframes fadeInUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }",
        ".row { opacity: 0; animation: fadeInUp 0.6s ease-out forwards; }",
        ".title { opacity: 0; animation: fadeInUp 0.5s ease-out forwards; }",
        "</style>",
        f'<rect width="{width}" height="{height}" rx="10" fill="#0d1117" stroke="#30363d"/>',
        f'<text class="title" x="20" y="32" font-family="Segoe UI, sans-serif" font-size="18" font-weight="700" fill="#58a6ff">{title}</text>',
    ]
    y = 65
    for i, (label, value) in enumerate(rows):
        delay = 0.15 + i * 0.12
        lines.append(f'<g class="row" style="animation-delay:{delay:.2f}s">')
        lines.append(f'<text x="20" y="{y}" font-family="Segoe UI, sans-serif" font-size="14" fill="#8b949e">{label}</text>')
        lines.append(f'<text x="{width-20}" y="{y}" font-family="Segoe UI, sans-serif" font-size="14" font-weight="600" fill="#c9d1d9" text-anchor="end">{value}</text>')
        lines.append("</g>")
        y += 28
    lines.append("</svg>")
    return "\n".join(lines)


def lang_svg(languages, width=420, height=190):
    lines = [
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">',
        "<style>",
        "@keyframes fadeInUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }",
        ".legend-row { opacity: 0; animation: fadeInUp 0.6s ease-out forwards; }",
        ".title { opacity: 0; animation: fadeInUp 0.5s ease-out forwards; }",
        "</style>",
        f'<rect width="{width}" height="{height}" rx="10" fill="#0d1117" stroke="#30363d"/>',
        '<text class="title" x="20" y="32" font-family="Segoe UI, sans-serif" font-size="18" font-weight="700" fill="#58a6ff">Most Used Languages</text>',
    ]
    bar_y = 55
    x = 20
    bar_width = width - 40
    for _, pct, color in languages:
        seg = bar_width * (pct / 100)
        lines.append(
            f'<rect x="{x:.1f}" y="{bar_y}" width="0" height="10" rx="4" fill="{color}">'
            f'<animate attributeName="width" from="0" to="{seg:.1f}" dur="1s" begin="0.1s" fill="freeze" calcMode="spline" keySplines="0.25 0.1 0.25 1"/>'
            f'</rect>'
        )
        x += seg

    ly = 90
    for i, (name, pct, color) in enumerate(languages):
        delay = 0.5 + i * 0.12
        lines.append(f'<g class="legend-row" style="animation-delay:{delay:.2f}s">')
        lines.append(f'<circle cx="28" cy="{ly-4}" r="5" fill="{color}"/>')
        lines.append(f'<text x="40" y="{ly}" font-family="Segoe UI, sans-serif" font-size="13" fill="#c9d1d9">{name} {pct:.1f}%</text>')
        lines.append("</g>")
        ly += 20
    lines.append("</svg>")
    return "\n".join(lines)


def streak_svg(current, longest, total, width=420, height=140):
    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
  <style>
    @keyframes fadeInUp {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    @keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.55; }} }}
    .col {{ opacity: 0; animation: fadeInUp 0.6s ease-out forwards; }}
    .flame {{ animation: pulse 1.8s ease-in-out infinite; transform-origin: center; }}
  </style>
  <rect width="{width}" height="{height}" rx="10" fill="#0d1117" stroke="#30363d"/>

  <g class="col" style="animation-delay:0.05s">
    <text x="{width*0.17:.0f}" y="55" font-family="Segoe UI, sans-serif" font-size="30" font-weight="700" fill="#58a6ff" text-anchor="middle">{total}</text>
    <text x="{width*0.17:.0f}" y="78" font-family="Segoe UI, sans-serif" font-size="12" fill="#8b949e" text-anchor="middle">Total</text>
  </g>

  <g class="col" style="animation-delay:0.2s">
    <circle class="flame" cx="{width*0.5:.0f}" cy="45" r="16" fill="none" stroke="#f78166" stroke-width="2"/>
    <text x="{width*0.5:.0f}" y="55" font-family="Segoe UI, sans-serif" font-size="30" font-weight="700" fill="#f78166" text-anchor="middle">{current}</text>
    <text x="{width*0.5:.0f}" y="78" font-family="Segoe UI, sans-serif" font-size="12" fill="#8b949e" text-anchor="middle">Current Streak</text>
  </g>

  <g class="col" style="animation-delay:0.35s">
    <text x="{width*0.83:.0f}" y="55" font-family="Segoe UI, sans-serif" font-size="30" font-weight="700" fill="#3fb950" text-anchor="middle">{longest}</text>
    <text x="{width*0.83:.0f}" y="78" font-family="Segoe UI, sans-serif" font-size="12" fill="#8b949e" text-anchor="middle">Longest Streak</text>
  </g>

  <line x1="{width*0.33:.0f}" y1="20" x2="{width*0.33:.0f}" y2="{height-20}" stroke="#30363d"/>
  <line x1="{width*0.66:.0f}" y1="20" x2="{width*0.66:.0f}" y2="{height-20}" stroke="#30363d"/>
</svg>"""


def main():
    token = os.environ["GH_TOKEN"]
    username = os.environ["GH_USERNAME"]

    user = fetch_data(token, username)
    total_stars, total_repos, followers, total_contribs = compute_totals(user)
    languages = compute_languages(user)
    current, longest = compute_streaks(user)

    os.makedirs("profile", exist_ok=True)

    stats = svg_card(
        "GitHub Stats",
        [
            ("Total Stars", total_stars),
            ("Public Repos", total_repos),
            ("Followers", followers),
            ("Total Contributions", total_contribs),
        ],
    )
    with open("profile/stats.svg", "w") as f:
        f.write(stats)

    with open("profile/top-langs.svg", "w") as f:
        f.write(lang_svg(languages))

    with open("profile/streak.svg", "w") as f:
        f.write(streak_svg(current, longest, total_contribs))

    print("Cards generated successfully.")


if __name__ == "__main__":
    main()
