#!/usr/bin/env python3
"""
Fetch CALGETC (IGETC) transferability data from ASSIST and write JSON.

Endpoint pattern:
https://www.assist.org/api/transferability/courses?institutionId=133&academicYearId=76&listType=CALGETC

Includes:
- course name
- transfer areas
- approved date / term
- removed date / term
- isCurrentlyApproved flag (Python 3.9 compatible)
"""

import json
import requests
import argparse
import os
from datetime import datetime
from typing import Optional


# ---------------------------
# Helpers
# ---------------------------

def fetch_api_data(url: str) -> dict:
    headers = {
        "User-Agent": "assist-transfer-scraper/1.0",
        "Accept": "application/json",
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def is_currently_approved(end_date_str: Optional[str]) -> bool:
    """
    Consider currently approved if:
    - endDate is missing/null OR
    - endDate is in the future

    ASSIST timestamps are typically timezone-naive.
    """
    if not end_date_str:
        return True

    try:
        end_dt = datetime.fromisoformat(end_date_str)
        return end_dt > datetime.utcnow()
    except ValueError:
        return False


# ---------------------------
# Core logic
# ---------------------------

def get_transfer_courses(institution_id: int, academic_year_id: int, list_type: str) -> dict:
    url = (
        "https://www.assist.org/api/transferability/courses"
        f"?institutionId={institution_id}"
        f"&academicYearId={academic_year_id}"
        f"&listType={list_type}"
    )

    data = fetch_api_data(url)

    courses_out = []
    for c in data.get("courseInformationList", []) or []:
        identifier = (c.get("identifier") or "").strip()
        title = (c.get("courseTitle") or "").strip()
        course_name = f"{identifier} - {title}".strip(" -")

        transfer_areas = [
            a.get("code")
            for a in (c.get("transferAreas") or [])
            if a.get("code")
        ]

        end_date = c.get("endDate")

        courses_out.append({
            "course": course_name,
            "transferAreas": transfer_areas,
            "approvedDate": c.get("beginDate"),
            "approvedTerm": c.get("beginTermCode"),
            "removedDate": end_date,
            "removedTerm": c.get("endTermCode"),
            "isCurrentlyApproved": is_currently_approved(end_date),
        })

    return {
        "institutionName": data.get("institutionName"),
        "academicYear": (data.get("academicYear") or {}).get("code"),
        "listType": data.get("listType"),
        "listTypeRequested": list_type,
        "courses": courses_out,
    }


# ---------------------------
# CLI entry point
# ---------------------------

def main(institution_id: int, academic_year_id: int, list_type: str, out_file: str):
    result = get_transfer_courses(institution_id, academic_year_id, list_type)

    # Write output next to this script unless absolute path is provided
    if os.path.isabs(out_file):
        out_path = out_file
    else:
        out_path = os.path.join(os.path.dirname(__file__), out_file)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Saved {len(result['courses'])} courses to {out_path}")
    if result.get("institutionName") and result.get("academicYear"):
        print(f"{result['institutionName']} ({result['academicYear']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build CALGETC (IGETC) transfer list from ASSIST API")
    parser.add_argument("--institutionId", type=int, default=133)
    parser.add_argument("--academicYearId", type=int, default=76)
    parser.add_argument("--listType", default="CALGETC")  # <-- default switched
    parser.add_argument("--out", default="calgetc_transfers.json")  # <-- default output name
    args = parser.parse_args()

    main(args.institutionId, args.academicYearId, args.listType, args.out)
