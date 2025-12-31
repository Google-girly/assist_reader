import requests
import json

URL = "https://www.assist.org/api/institutions"

def main():
    response = requests.get(URL)
    response.raise_for_status()
    institutions = response.json()

    parsed = [
        {
            "schoolName": inst["names"][0]["name"] if inst.get("names") else None,
            "code": inst["id"]
        }
        for inst in institutions
    ]

    with open("school_codes.txt", "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2)

    print(f"Wrote {len(parsed)} schools to school_codes.txt")

if __name__ == "__main__":
    main()
