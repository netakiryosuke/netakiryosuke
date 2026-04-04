#!/usr/bin/env python3
"""
GitHubの全期間Contribution数だけUUID v4を発行し、README.mdに表示する。
Contributionが増えたら不足分だけuuids.txtに追記する。
"""

import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

PAGE_SIZE = 50
REPO_ROOT = Path(__file__).parent.parent.parent
UUIDS_FILE = REPO_ROOT / "uuids.txt"
README_FILE = REPO_ROOT / "README.md"

ACCOUNT_CREATED_YEAR = 2025


def get_total_contributions(token: str) -> int:
    """GraphQL APIで全期間のContribution数を取得する。"""
    current_year = datetime.now(timezone.utc).year
    total = 0

    for year in range(ACCOUNT_CREATED_YEAR, current_year + 1):
        query = """
        query($from: DateTime!, $to: DateTime!) {
          viewer {
            contributionsCollection(from: $from, to: $to) {
              contributionCalendar {
                totalContributions
              }
            }
          }
        }
        """
        variables = {
            "from": f"{year}-01-01T00:00:00Z",
            "to": f"{year}-12-31T23:59:59Z",
        }
        payload = json.dumps({"query": query, "variables": variables})

        result = subprocess.run(
            ["gh", "api", "graphql", "--input", "-"],
            input=payload,
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        count = (
            data["data"]["viewer"]["contributionsCollection"]
            ["contributionCalendar"]["totalContributions"]
        )
        total += count

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


def generate_readme(uuids: list[str], total_contributions: int, duplicates: list[str]) -> str:
    """README.mdの内容を生成する。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_uuids = len(uuids)

    # 新しく発行された順（末尾が最新）を逆順にしてPage1に最新を表示する
    display_uuids = list(reversed(uuids))
    total_pages = (total_uuids + PAGE_SIZE - 1) // PAGE_SIZE

    lines = [
        "## Hi there 👋",
        "",
        "これは私のGitHub Contributionの数（全期間累計）と同じ数だけUUID v4を発行したものです。",
        "世界中で1つでも同じUUIDが存在したら、このアカウントを削除します。",
        "",
        f"> Contribution数: {total_contributions}  ",
        f"> 発行UUID数: {total_uuids}  ",
        f"> 最終更新: {now}",
        "",
    ]

    if duplicates:
        lines += [
            "---",
            "",
            "## ⚠️ 重複しました。アカウントを削除してください。",
            "",
            "以下のUUIDが重複しています：",
            "",
        ]
        for dup in duplicates:
            lines.append(f"- `{dup}`")
        lines.append("")
        lines.append("---")
        lines.append("")

    for page in range(total_pages):
        start = page * PAGE_SIZE
        end = min(start + PAGE_SIZE, total_uuids)
        lines.append("<details>")
        lines.append(
            f"<summary>📄 Page {page + 1}（最新#{total_uuids - start}〜#{total_uuids - end + 1}）</summary>"
        )
        lines.append("")
        for u in display_uuids[start:end]:
            lines.append(f"`{u}`  ")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        # ローカル実行時はghコマンドの認証情報を使う
        pass

    print("Contribution数を取得中...")
    total = get_total_contributions(token)
    print(f"  -> {total} contributions")

    uuids = load_uuids()
    print(f"既存UUID数: {len(uuids)}")

    uuids = append_uuids(uuids, total)
    print(f"UUID数（追記後）: {len(uuids)}")

    duplicates = check_duplicates(uuids)
    if duplicates:
        print(f"⚠️  重複UUID検知: {duplicates}")
    else:
        print("重複なし ✅")

    readme = generate_readme(uuids, total, duplicates)
    README_FILE.write_text(readme)
    print("README.md を更新しました")


if __name__ == "__main__":
    main()
