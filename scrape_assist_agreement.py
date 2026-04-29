import argparse
import json
import re
import time
from collections import deque
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests

BASE_URL = "https://assist.org"
CATEGORY_BY_FILE_PREFIX = {
    "AD": "dept",     # All Departments
    "AM": "major",    # All Majors
    "AP": "prefix",   # All Prefixes
}
ALL_KEY_SUFFIX_BY_FILE_PREFIX = {
    "AD": "AllDepartments",
    "AM": "AllMajors",
    "AP": "AllPrefixes",
}


class AssistClient:
    def __init__(self, max_requests: int = 50, window_seconds: int = 300) -> None:
        self.session = requests.Session()
        self.session.get(f"{BASE_URL}/", timeout=30)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.request_times: deque[float] = deque()

        token = self.session.cookies.get("X-XSRF-TOKEN")
        self.headers = {
            "X-XSRF-TOKEN": token or "",
            "Referer": f"{BASE_URL}/",
            "Origin": BASE_URL,
            "Accept": "application/json, text/plain, */*",
        }

    def _throttle(self) -> None:
        now = time.monotonic()
        while self.request_times and now - self.request_times[0] >= self.window_seconds:
            self.request_times.popleft()

        if len(self.request_times) >= self.max_requests:
            sleep_for = self.window_seconds - (now - self.request_times[0]) + 0.05
            time.sleep(max(0.05, sleep_for))

        now = time.monotonic()
        while self.request_times and now - self.request_times[0] >= self.window_seconds:
            self.request_times.popleft()
        self.request_times.append(now)

    def _get_json(self, url: str, params: Dict, retries: int = 5, allow_400: bool = False) -> Optional[Dict]:
        backoff = 1.0
        last_exc: Optional[Exception] = None
        for _ in range(retries):
            try:
                self._throttle()
                resp = self.session.get(
                    url,
                    params=params,
                    headers=self.headers,
                    timeout=120,
                )
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    sleep_for = float(retry_after) if retry_after else backoff
                    time.sleep(max(1.0, sleep_for))
                    backoff = min(backoff * 2, 30.0)
                    continue

                if allow_400 and resp.status_code == 400:
                    return None

                resp.raise_for_status()
                return resp.json()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

        raise RuntimeError(f"Request failed after retries: {url} {params} | {last_exc}")

    def get_all_key(self, year: int, to_id: int, from_id: int, file_prefix: str) -> Optional[str]:
        category_code = CATEGORY_BY_FILE_PREFIX[file_prefix]
        data = self._get_json(
            f"{BASE_URL}/api/agreements",
            {
                "receivingInstitutionId": to_id,
                "sendingInstitutionId": from_id,
                "academicYearId": year,
                "categoryCode": category_code,
            },
        )

        all_reports = data.get("allReports") or []
        if all_reports:
            return all_reports[0]["key"]

        reports = data.get("reports") or []
        if not reports:
            return None

        suffix = ALL_KEY_SUFFIX_BY_FILE_PREFIX[file_prefix]
        return f"{year}/{from_id}/to/{to_id}/{suffix}"

    def fetch_agreement(self, key: str) -> Optional[Dict]:
        return self._get_json(
            f"{BASE_URL}/api/articulation/Agreements",
            {"Key": key},
            allow_400=True,
        )

    def fetch_all_agreement(self, year: int, to_id: int, from_id: int, file_prefix: str) -> Optional[Dict]:
        suffix = ALL_KEY_SUFFIX_BY_FILE_PREFIX[file_prefix]
        key = f"{year}/{from_id}/to/{to_id}/{suffix}"
        return self.fetch_agreement(key)


def write_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=4, ensure_ascii=False), encoding="utf-8")


def has_valid_payload(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False
    return bool(data.get("isSuccessful"))


def scrape_pair(
    client: AssistClient,
    year: int,
    to_id: int,
    from_id: int,
    out_dir: Path,
    skip_existing: bool,
) -> Dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    statuses: Dict[str, str] = {}

    for file_prefix in ["AD", "AM", "AP"]:
        out_path = out_dir / f"{file_prefix}{to_id}_{from_id}.json"
        if skip_existing and has_valid_payload(out_path):
            statuses[file_prefix] = "cached"
            continue
        try:
            payload = client.fetch_all_agreement(year=year, to_id=to_id, from_id=from_id, file_prefix=file_prefix)
            if not payload:
                statuses[file_prefix] = "no-data"
                continue
            write_json(out_path, payload)
            statuses[file_prefix] = "ok"
        except Exception as exc:  # noqa: BLE001
            statuses[file_prefix] = f"error: {exc}"

    return statuses


def parse_folder_ids(folder_name: str) -> Tuple[int, int]:
    m = re.fullmatch(r"(\d+)_(\d+)", folder_name)
    if not m:
        raise ValueError(f"Invalid folder format: {folder_name}")
    return int(m.group(1)), int(m.group(2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch ASSIST agreement JSON files (AD/AM/AP).")
    parser.add_argument("--year", type=int, required=True, help="Academic year id (e.g. 76)")
    parser.add_argument("--to-id", type=int, help="Receiving institution id")
    parser.add_argument("--from-id", type=int, help="Sending institution id")
    parser.add_argument("--root", default="mappings", help="Root folder containing mapping folders")
    parser.add_argument("--all", action="store_true", help="Scrape every {to}_{from} folder under --root")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between folder requests (seconds)")
    parser.add_argument("--skip-existing", action="store_true", help="Skip files that already contain successful JSON")
    parser.add_argument("--start-from", help="Start from this folder name (e.g. 12_131) when using --all")
    parser.add_argument("--max-requests", type=int, default=50, help="Max requests per window")
    parser.add_argument("--window-seconds", type=int, default=300, help="Rate-limit window in seconds")
    args = parser.parse_args()

    client = AssistClient(max_requests=args.max_requests, window_seconds=args.window_seconds)
    root = Path(args.root)

    if args.all:
        folders = sorted([p for p in root.iterdir() if p.is_dir() and re.fullmatch(r"\d+_\d+", p.name)])
        if args.start_from:
            folders = [p for p in folders if p.name >= args.start_from]
        print(f"Found {len(folders)} mapping folders")
        for idx, folder in enumerate(folders, start=1):
            to_id, from_id = parse_folder_ids(folder.name)
            statuses = scrape_pair(client, args.year, to_id, from_id, folder, skip_existing=args.skip_existing)
            print(f"[{idx}/{len(folders)}] {folder.name} -> AD:{statuses['AD']} AM:{statuses['AM']} AP:{statuses['AP']}")
            time.sleep(args.delay)
        return

    if args.to_id is None or args.from_id is None:
        raise SystemExit("Provide --to-id and --from-id, or use --all")

    out_dir = root / f"{args.to_id}_{args.from_id}"
    statuses = scrape_pair(client, args.year, args.to_id, args.from_id, out_dir, skip_existing=args.skip_existing)
    print(f"Completed {out_dir.name} -> AD:{statuses['AD']} AM:{statuses['AM']} AP:{statuses['AP']}")


if __name__ == "__main__":
    main()
