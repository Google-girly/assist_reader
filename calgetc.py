#!/usr/bin/env python3
"""
Fetch published ASSIST agreements and write JSON.

Endpoint pattern:
https://prod.assistng.org/articulation/api/Agreements/Published/for/12/to/110/in/76?types=Major

Includes:
- selected endpoint parameters
- agreement count
- raw agreements payload
"""

import json
import requests
import argparse
import os


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


def get_agreements(from_institution_id: int, to_institution_id: int, academic_year_id: int, agreement_type: str) -> dict:
    url = (
        "https://prod.assistng.org/articulation/api/Agreements/Published"
        f"/for/{from_institution_id}"
        f"/to/{to_institution_id}"
        f"/in/{academic_year_id}"
        f"?types={agreement_type}"
    )

    data = fetch_api_data(url)

    if isinstance(data, dict) and "result" in data:
        agreements_payload = data.get("result")
    else:
        agreements_payload = data

    if isinstance(agreements_payload, list):
        agreement_count = len(agreements_payload)
    elif agreements_payload is None:
        agreement_count = 0
    else:
        agreement_count = 1

    return {
        "endpoint": url,
        "fromInstitutionId": from_institution_id,
        "toInstitutionId": to_institution_id,
        "academicYearId": academic_year_id,
        "typeRequested": agreement_type,
        "agreementCount": agreement_count,
        "agreements": agreements_payload,
    }


# ---------------------------
# CLI entry point
# ---------------------------

def main(from_institution_id: int, to_institution_id: int, academic_year_id: int, agreement_type: str, out_file: str):
    result = get_agreements(from_institution_id, to_institution_id, academic_year_id, agreement_type)

    # Write output next to this script unless absolute path is provided
    if os.path.isabs(out_file):
        out_path = out_file
    else:
        out_path = os.path.join(os.path.dirname(__file__), out_file)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Saved {result['agreementCount']} agreement record(s) to {out_path}")
    print(result["endpoint"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch published ASSIST agreements")
    parser.add_argument("--fromInstitutionId", type=int, default=None)
    parser.add_argument("--toInstitutionId", type=int, default=110)
    parser.add_argument("--academicYearId", type=int, default=76)
    parser.add_argument("--types", default="Major")
    parser.add_argument("--out", default="calgetc_transfers.json")

    # Backward compatibility with previous CLI args
    parser.add_argument("--institutionId", type=int, default=None)
    parser.add_argument("--listType", default=None)

    args = parser.parse_args()

    from_institution_id = args.fromInstitutionId if args.fromInstitutionId is not None else args.institutionId
    if from_institution_id is None:
        from_institution_id = 12

    agreement_type = args.types if args.types is not None else args.listType
    if agreement_type is None:
        agreement_type = "Major"

    main(from_institution_id, args.toInstitutionId, args.academicYearId, agreement_type, args.out)
