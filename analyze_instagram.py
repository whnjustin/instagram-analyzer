from __future__ import annotations

import json
import zipfile
from datetime import datetime, date
from pathlib import Path
from typing import Iterable, Set

DATA_DIR = Path(__file__).parent / "data"


class SnapshotNotFound(Exception):
    """Raised when a requested snapshot cannot be located."""


def list_accounts() -> list[str]:
    accounts: set[str] = set()
    for path in DATA_DIR.glob("instagram-*"):
        if not path.is_dir():
            continue
        parts = path.name.split("-")
        if len(parts) < 6 or parts[0] != "instagram":
            continue
        account_parts = parts[1 : len(parts) - 4]
        if not account_parts:
            continue
        accounts.add("-".join(account_parts))
    return sorted(accounts)


def unpack_archives() -> None:
    for archive in DATA_DIR.glob("*.zip"):
        try:
            should_delete = False
            with zipfile.ZipFile(archive) as zf:
                if not zf.namelist():
                    continue
                dest = DATA_DIR / archive.stem
                if dest.exists():
                    continue
                zf.extractall(dest)
                should_delete = True
                print(f"Extracted {archive.name} -> {dest.name}")
            if should_delete:
                archive.unlink(missing_ok=True)
        except zipfile.BadZipFile:
            print(f"Skipping invalid zip: {archive.name}")


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def list_snapshots(account: str) -> list[tuple[date, Path]]:
    snapshots: list[tuple[date, Path]] = []
    pattern = f"instagram-{account}-*"
    for path in DATA_DIR.glob(pattern):
        if not path.is_dir():
            continue
        parts = path.name.split("-")
        if len(parts) < 6:
            continue
        date_str = "-".join(parts[2:5])
        try:
            snapshot_date = parse_date(date_str)
        except ValueError:
            continue
        snapshots.append((snapshot_date, path))
    return sorted(snapshots, key=lambda item: item[0])


def find_snapshot(account: str, target_date: date) -> Path:
    for snapshot_date, path in list_snapshots(account):
        if snapshot_date == target_date:
            return path
    raise SnapshotNotFound(f"No snapshot found for {account} on {target_date}")


def load_followers(path: Path) -> Set[str]:
    followers_path = path / "connections" / "followers_and_following" / "followers_1.json"
    if not followers_path.exists():
        raise FileNotFoundError(f"Missing followers file: {followers_path}")
    with followers_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    usernames: Set[str] = set()
    for item in data:
        string_list: Iterable[dict] = item.get("string_list_data", [])
        for entry in string_list:
            value = entry.get("value")
            if value:
                usernames.add(value)
    return usernames


def load_following(path: Path) -> Set[str]:
    following_path = path / "connections" / "followers_and_following" / "following.json"
    if not following_path.exists():
        raise FileNotFoundError(f"Missing following file: {following_path}")
    with following_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    relationships = data.get("relationships_following", [])
    usernames: Set[str] = set()
    for item in relationships:
        title = item.get("title")
        if title:
            usernames.add(title)
    return usernames


def summarize_changes(account: str, date_a: date, date_b: date) -> tuple[list[str], date, date] | None:
    earlier, later = sorted([date_a, date_b])
    snapshots = list_snapshots(account)
    if not snapshots:
        print(f"No snapshots found for account '{account}'.")
        return None

    available_dates = [snap_date.isoformat() for snap_date, _ in snapshots]
    try:
        earlier_path = find_snapshot(account, earlier)
    except SnapshotNotFound:
        print(f"Could not find snapshot for {earlier}. Available: {', '.join(available_dates)}")
        return None
    try:
        later_path = find_snapshot(account, later)
    except SnapshotNotFound:
        print(f"Could not find snapshot for {later}. Available: {', '.join(available_dates)}")
        return None

    followers_earlier = load_followers(earlier_path)
    followers_later = load_followers(later_path)
    following_later = load_following(later_path)

    gained = sorted(followers_later - followers_earlier)
    lost = sorted(followers_earlier - followers_later)
    not_followed_back = sorted(following_later - followers_later)
    # followers_not_followed = sorted(followers_later - following_later)

    lines: list[str] = []
    lines.append(f"Account: {account}")
    lines.append(f"Comparing {earlier.isoformat()} -> {later.isoformat()}")
    lines.append(
        f"Followers then: {len(followers_earlier)} | Followers now: {len(followers_later)} | Net change: {len(followers_later) - len(followers_earlier)}"
    )

    lines.append("\nFollowers gained:")
    if gained:
        lines.extend([f"  + {name}" for name in gained])
    else:
        lines.append("  None")

    lines.append("\nFollowers lost:")
    if lost:
        lines.extend([f"  - {name}" for name in lost])
    else:
        lines.append("  None")

    lines.append("\nFollowing but not followed back (latest snapshot):")
    if not_followed_back:
        lines.extend([f"  * {name}" for name in not_followed_back])
    else:
        lines.append("  None")

    # lines.append("\nFollowers you do not follow back (latest snapshot):")
    # if followers_not_followed:
    #     lines.extend([f"  * {name}" for name in followers_not_followed])
    # else:
    #     lines.append("  None")

    print("\n".join(lines))
    return lines, earlier, later


def main() -> None:
    unpack_archives()

    accounts = list_accounts()
    if not accounts:
        print("No accounts found under the data directory.")
        return

    print("Select an account:")
    for idx, acct in enumerate(accounts, start=1):
        print(f"  {idx}) {acct}")

    try:
        account_choice = int(input("Enter account number: ").strip())
        account = accounts[account_choice - 1]
    except (ValueError, IndexError):
        print("Invalid account selection.")
        return

    snapshots = list_snapshots(account)
    if not snapshots:
        print(f"No snapshots found for account '{account}'.")
        return

    print("\nAvailable snapshot dates:")
    for idx, (snap_date, _) in enumerate(snapshots, start=1):
        print(f"  {idx}) {snap_date.isoformat()}")

    try:
        first_choice = int(input("Enter first date number: ").strip())
        second_choice = int(input("Enter second date number: ").strip())
        first_date = snapshots[first_choice - 1][0]
        second_date = snapshots[second_choice - 1][0]
    except (ValueError, IndexError):
        print("Invalid date selection.")
        return

    summary = summarize_changes(account, first_date, second_date)
    if not summary:
        return

    lines, earlier, later = summary

    export_choice = input("\nExport to data/export as txt? (y/n): ").strip().lower()
    if export_choice not in {"y", "yes"}:
        return

    export_dir = DATA_DIR / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{account}_{earlier.isoformat()}_to_{later.isoformat()}.txt"
    export_path = export_dir / filename
    export_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved to {export_path}")


if __name__ == "__main__":
    main()
