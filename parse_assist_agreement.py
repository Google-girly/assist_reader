import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def parse_embedded_json(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        if value and value[0] in "[{":
            return json.loads(value)
    return value


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        if "name" in value and isinstance(value["name"], str):
            return value["name"].strip()
        if "value" in value and isinstance(value["value"], str):
            return value["value"].strip()
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def course_label(course: Optional[Dict[str, Any]]) -> str:
    if not course:
        return ""
    prefix = as_text(course.get("prefix"))
    number = as_text(course.get("courseNumber"))
    title = as_text(course.get("courseTitle"))
    code = " ".join(p for p in [prefix, number] if p).strip()
    return f"{code} - {title}" if title and code else code or title


def series_label(series: Optional[Dict[str, Any]]) -> str:
    if not series:
        return ""
    if series.get("name"):
        return as_text(series["name"])
    courses = series.get("courses") or []
    return ", ".join(course_label(c) for c in courses if c)


def receiving_label(cell_or_articulation: Dict[str, Any]) -> str:
    t = cell_or_articulation.get("type")
    if t == "Course":
        return course_label(cell_or_articulation.get("course"))
    if t == "Series":
        return series_label(cell_or_articulation.get("series"))
    if t == "Requirement":
        req = cell_or_articulation.get("requirement") or {}
        return as_text(req.get("name"))
    return as_text(cell_or_articulation)


def render_group(group: Dict[str, Any]) -> str:
    items = group.get("items") or []
    parts = [course_label(item) for item in items if item.get("type") == "Course"]
    parts = [p for p in parts if p]
    if not parts:
        return ""
    conj = as_text(group.get("courseConjunction") or "And") or "And"
    joiner = f" {conj.upper()} "
    return joiner.join(parts)


def split_or_options(rendered_groups: List[str], group_map: Dict[Any, str]) -> List[str]:
    if not rendered_groups:
        return []

    options = [rendered_groups[0]]
    for i in range(1, len(rendered_groups)):
        conj = (group_map.get((i - 1, i), "And") or "And").strip().upper()
        current = rendered_groups[i]

        if conj == "OR":
            options.append(current)
        else:
            options = [f"({opt}) AND ({current})" for opt in options]

    return options


def render_sending_articulation(sending: Dict[str, Any]) -> str:
    reason = as_text(sending.get("noArticulationReason"))
    if reason:
        return f"No articulation ({reason})"

    groups = sorted(
        sending.get("items") or [],
        key=lambda g: g.get("position", 0),
    )
    if not groups:
        return ""

    group_map = {
        (c.get("sendingCourseGroupBeginPosition"), c.get("sendingCourseGroupEndPosition")): as_text(
            c.get("groupConjunction")
        )
        for c in (sending.get("courseGroupConjunctions") or [])
    }

    rendered = [render_group(g) for g in groups]
    rendered = [r for r in rendered if r]
    if not rendered:
        return ""

    output = rendered[0]
    for i in range(1, len(rendered)):
        conj = group_map.get((i - 1, i), "And") or "And"
        output = f"({output}) {conj.upper()} ({rendered[i]})"

    denied = [course_label(c) for c in (sending.get("deniedCourses") or []) if c]
    denied = [d for d in denied if d]
    if denied:
        output += " | Not accepted: " + ", ".join(denied)

    return output


def sending_articulation_details(sending: Dict[str, Any]) -> Dict[str, Any]:
    reason = as_text(sending.get("noArticulationReason"))
    denied = [course_label(c) for c in (sending.get("deniedCourses") or []) if c]
    denied = [d for d in denied if d]

    if reason:
        return {
            "sending_courses": f"No articulation ({reason})",
            "sending_course_options": [],
            "no_articulation_reason": reason,
            "denied_courses": denied,
        }

    groups = sorted(
        sending.get("items") or [],
        key=lambda g: g.get("position", 0),
    )

    group_map = {
        (c.get("sendingCourseGroupBeginPosition"), c.get("sendingCourseGroupEndPosition")): as_text(
            c.get("groupConjunction")
        )
        for c in (sending.get("courseGroupConjunctions") or [])
    }

    rendered_groups = [render_group(g) for g in groups]
    rendered_groups = [r for r in rendered_groups if r]
    options = split_or_options(rendered_groups, group_map)

    sending_text = render_sending_articulation(sending)
    return {
        "sending_courses": sending_text,
        "sending_course_options": options,
        "no_articulation_reason": "",
        "denied_courses": denied,
    }


def build_template_index(template_assets: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    index: Dict[str, Dict[str, str]] = {}

    def walk(node: Any, major: str = "", group: str = "", section: str = "") -> None:
        if isinstance(node, list):
            for item in node:
                walk(item, major, group, section)
            return

        if not isinstance(node, dict):
            return

        if "name" in node and "templateAssets" in node:
            major = as_text(node.get("name"))

        node_type = node.get("type")
        if node_type == "RequirementGroup":
            group = as_text(node.get("instruction"))
        elif node_type == "RequirementSection":
            section = as_text(node.get("name") or node.get("instruction"))

        cells = node.get("cells") or []
        for cell in cells:
            cell_id = cell.get("id")
            if not cell_id:
                continue
            index[cell_id] = {
                "major": major,
                "group": group,
                "section": section,
                "receiving_type": as_text(cell.get("type")),
                "receiving_label": receiving_label(cell),
            }

        for child in node.values():
            walk(child, major, group, section)

    walk(template_assets)
    return index


def parse_agreement(path: Path) -> List[Dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    result = raw["result"]

    receiving_inst = parse_embedded_json(result.get("receivingInstitution")) or {}
    sending_inst = parse_embedded_json(result.get("sendingInstitution")) or {}
    year_info = parse_embedded_json(result.get("academicYear")) or {}

    receiving_name = as_text(((receiving_inst.get("names") or [{}])[0]).get("name"))
    sending_name = as_text(((sending_inst.get("names") or [{}])[0]).get("name"))
    academic_year = as_text(year_info.get("code"))

    template_assets = parse_embedded_json(result.get("templateAssets")) or []
    articulations = parse_embedded_json(result.get("articulations")) or []

    template_index = build_template_index(template_assets)

    rows: List[Dict[str, Any]] = []
    seen = set()
    for entry in articulations:
        cell_id = entry.get("templateCellId")
        articulation = entry.get("articulation") or {}
        sending = articulation.get("sendingArticulation") or {}

        template = template_index.get(cell_id, {})
        receiving_desc = receiving_label(articulation) or template.get("receiving_label", "")

        sending_details = sending_articulation_details(sending)

        row = {
            "academic_year": academic_year,
            "sending_institution": sending_name,
            "receiving_institution": receiving_name,
            "major": template.get("major", ""),
            "group": template.get("group", ""),
            "section": template.get("section", ""),
            "receiving_type": template.get("receiving_type", as_text(articulation.get("type"))),
            "receiving_requirement": receiving_desc,
            "sending_courses": sending_details["sending_courses"],
            "sending_course_options": sending_details["sending_course_options"],
            "no_articulation_reason": sending_details["no_articulation_reason"],
            "denied_courses": sending_details["denied_courses"],
            "template_cell_id": as_text(cell_id),
        }

        dedupe_key = (
            row["academic_year"],
            row["sending_institution"],
            row["receiving_institution"],
            row["major"],
            row["receiving_requirement"],
            row["sending_courses"],
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        rows.append(row)

    return rows


def write_outputs(rows: List[Dict[str, Any]], json_path: Path, csv_path: Path) -> None:
    json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    if not rows:
        csv_path.write_text("", encoding="utf-8")
        return

    fieldnames = list(rows[0].keys())
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse ASSIST agreement JSON and extract receiving-to-sending course mappings."
    )
    parser.add_argument("input", nargs="?", default="AM12_133.json", help="Path to ASSIST agreement JSON")
    parser.add_argument("--json-out", default="transfer_mappings.json", help="Output JSON file")
    parser.add_argument("--csv-out", default="transfer_mappings.csv", help="Output CSV file")
    args = parser.parse_args()

    input_path = Path(args.input)
    rows = parse_agreement(input_path)
    write_outputs(rows, Path(args.json_out), Path(args.csv_out))

    print(f"Parsed {len(rows)} articulation rows")
    print(f"JSON: {args.json_out}")
    print(f"CSV:  {args.csv_out}")


if __name__ == "__main__":
    main()
