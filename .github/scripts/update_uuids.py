#!/usr/bin/env python3
"""
GitHubの全期間Contribution数だけUUID v4を発行し、README.mdに表示する。
Contributionが増えたら不足分だけuuids.txtに追記する。
"""

import asyncio
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

JST = timezone(timedelta(hours=9))

LATEST_DISPLAY_COUNT = 10
REPO_ROOT = Path(__file__).parent.parent.parent
UUIDS_FILE = REPO_ROOT / "uuids.txt"
README_FILE = REPO_ROOT / "README.md"

ACCOUNT_CREATED_YEAR = 2025


async def fetch_year_contributions(page, username: str, year: int) -> int:
    url = f"https://github.com/{username}?tab=overview&from={year}-01-01&to={year}-12-31"
    await page.goto(url, wait_until="networkidle")

    h2 = page.locator("h2#js-contribution-activity-description")
    await h2.wait_for(timeout=15000)

    # レンダリング済みのHTMLをBeautifulSoupに渡す
    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")
    
    h2_elem = soup.find("h2", id="js-contribution-activity-description")
    match = re.search(r"([\d,]+)\s+contributions?", h2_elem.text.strip())
    
    return int(match.group(1).replace(",", ""))


async def get_total_contributions() -> int:
    current_year = datetime.now(timezone.utc).year
    total = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for year in range(ACCOUNT_CREATED_YEAR, current_year + 1):
            total += await fetch_year_contributions(page, "netakiryosuke", year)

        await browser.close()

    return total
        

def load_uuids() -> list[str]:
    """既存のUUIDをuuids.txtから読み込む。"""
    if not UUIDS_FILE.exists():
        return []
    lines = UUIDS_FILE.read_text().splitlines()
    return [line.strip() for line in lines if line.strip()]


def append_uuids(uuids: list[str], count: int) -> list[str]:
    """不足分のUUID v4を生成して追記し、全件を返す。"""
    shortage = count - len(uuids)
    if shortage <= 0:
        return uuids

    new_uuids = [str(uuid.uuid4()) for _ in range(shortage)]
    with UUIDS_FILE.open("a") as f:
        for u in new_uuids:
            f.write(u + "\n")

    return uuids + new_uuids


def check_duplicates(uuids: list[str]) -> list[str]:
    """uuids.txt内の重複UUIDを返す。"""
    seen: set[str] = set()
    duplicates: list[str] = []
    for u in uuids:
        if u in seen:
            duplicates.append(u)
        else:
            seen.add(u)
    return duplicates


def find_closest_pair(uuids: list[str]) -> tuple[int, int, int, int]:
    """ハミング類似度が最大のペアを返す。
    返り値: (インデックスi, インデックスj, 一致文字数, UUID長)
    インデックスはuuids.txt上の行番号（0始まり）に対応。
    """
    # ハイフン除去した32文字で比較
    normalized = [u.replace("-", "") for u in uuids]
    uuid_len = len(normalized[0]) if normalized else 32

    best_matches = 0
    best_i = 0
    best_j = 1

    for i in range(len(normalized)):
        a = normalized[i]
        for j in range(i + 1, len(normalized)):
            b = normalized[j]
            matches = sum(ca == cb for ca, cb in zip(a, b))
            if matches > best_matches:
                best_matches = matches
                best_i = i
                best_j = j

    return best_i, best_j, best_matches, uuid_len


def generate_readme(uuids: list[str], total_contributions: int, duplicates: list[str], closest: tuple[int, int, int, int]) -> str:
    """README.mdの内容を生成する。"""
    now = datetime.now(JST).strftime("%Y-%m-%d")
    total_uuids = len(uuids)

    # 新しく発行された順（末尾が最新）を逆順にして最新を先頭に表示する
    display_uuids = list(reversed(uuids))
    latest = display_uuids[:LATEST_DISPLAY_COUNT]
    rest = display_uuids[LATEST_DISPLAY_COUNT:]

    dup_status = "✅ なし" if not duplicates else f"⚠️ {len(duplicates)}件"

    lines = [
        "## Hi there 👋",
        "",
        "このアカウントの GitHub Contribution の数だけUUID v4を発行します。",
        "",
        "毎日更新を行い、衝突した場合このアカウントを削除します。",
        "",
        f"> Contribution数: {total_contributions}  ",
        f"> 発行UUID数: {total_uuids}  ",
        f"> 衝突: {dup_status}  ",
        f"> 最終更新: {now}",
        "",
    ]

    if duplicates:
        lines += [
            "---",
            "",
            "## ⚠️ 衝突しました。アカウントを削除してください。",
            "",
            "以下のUUIDが衝突しています：",
            "",
        ]
        for dup in duplicates:
            lines.append(f"- `{dup}`")
        lines.append("")
        lines.append("---")
        lines.append("")

    # 最新10件はそのまま表示
    lines.append("### 直近 10 件の UUID")
    for u in latest:
        lines.append(f"`{u}`  ")
    lines.append("")

    # 残りは折りたたみ
    if rest:
        lines.append("<details>")
        lines.append(f"<summary>過去のUUID（{len(rest)}件）</summary>")
        lines.append("")
        for u in rest:
            lines.append(f"`{u}`  ")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    # 最近接ペア（ハミング類似度が最大のペア）を表示
    if total_uuids >= 2:
        ci, cj, matches, uuid_len = closest
        ua = uuids[ci]
        ub = uuids[cj]
        lines.append("<details>")
        lines.append(f"<summary>最も似ていたUUIDペア（{uuid_len}文字中{matches}文字一致）</summary>")
        lines.append("")
        lines.append(f"- #{ci + 1}: `{ua}`")
        lines.append(f"- #{cj + 1}: `{ub}`")
        lines.append("")
        # どの位置が一致しているか可視化（ハイフン除去で比較）
        na, nb = ua.replace("-", ""), ub.replace("-", "")
        highlight = "".join("^" if a == b else " " for a, b in zip(na, nb))
        lines.append("```")
        lines.append(na)
        lines.append(nb)
        lines.append(highlight)
        lines.append("```")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        import sys
        print(
            "警告: GH_TOKEN / GITHUB_TOKEN が未設定です。"
            "gh CLI のログイン済みセッションを使用します。",
            file=sys.stderr,
        )

    print("Contribution数を取得中...")
    total = asyncio.run(get_total_contributions())
    print(f"  -> {total} contributions")

    uuids = load_uuids()
    print(f"既存UUID数: {len(uuids)}")

    uuids = append_uuids(uuids, total)
    print(f"UUID数（追記後）: {len(uuids)}")

    duplicates = check_duplicates(uuids)
    if duplicates:
        print(f"⚠️  衝突UUID検知: {duplicates}")
    else:
        print("衝突なし ✅")

    print("最近接ペアを探索中...")
    closest = find_closest_pair(uuids)
    ci, cj, matches, uuid_len = closest
    print(f"  -> #{ci + 1} と #{cj + 1} が {uuid_len}文字中 {matches}文字一致")

    readme = generate_readme(uuids, total, duplicates, closest)
    README_FILE.write_text(readme)
    print("README.md を更新しました")


if __name__ == "__main__":
    main()
