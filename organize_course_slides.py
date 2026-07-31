#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Reorganize files downloaded by the course crawler by course code.

Default behavior:
1. Read Master_Slides/download_manifest.csv.
2. Detect UCL course codes, such as COMP0249 and COMP0123, from filenames,
   source-page titles, source URLs, and original saved paths.
3. Create one folder for each course.
4. Copy files by default without deleting the original downloads.
5. Exclude coursework, assignment, submission, and quiz pages by default.
6. Keep PPT, PPTX, PPS, PPSX, and PDF files by default.
"""

import argparse
import csv
import hashlib
import re
import shutil
from pathlib import Path
from urllib.parse import unquote


SLIDE_EXTENSIONS = {".ppt", ".pptx", ".pps", ".ppsx", ".pdf"}
PPT_ONLY_EXTENSIONS = {".ppt", ".pptx", ".pps", ".ppsx"}

# Common UCL module-code format, for example COMP0249.
DEFAULT_COURSE_PATTERN = re.compile(r"\b[A-Z]{4}\d{4}\b", re.IGNORECASE)

# Exclude student assignments, submissions, quizzes, and related pages by default.
DEFAULT_EXCLUDE_WORDS = (
    "coursework",
    "assignment",
    "assessment",
    "submission",
    "submitted",
    "turnitin",
    "quiz",
    "exam",
    "marking",
    "rubric",
    "feedback",
    "survey",
)

INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
SPACE_RE = re.compile(r"\s+")

WEEK_PATTERNS = (
    re.compile(r"\bweek[\s_-]*0?(\d{1,2})\b", re.IGNORECASE),
    re.compile(r"\blecture[\s_-]*0?(\d{1,2})\b", re.IGNORECASE),
)


def clean_name(text: str, fallback: str = "Unnamed", limit: int = 180) -> str:
    text = unquote(text or "")
    text = SPACE_RE.sub(" ", text).strip(" .")
    text = INVALID_FILENAME_CHARS.sub("_", text)
    return text[:limit].rstrip(" .") or fallback


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_week(text: str) -> str | None:
    for pattern in WEEK_PATTERNS:
        match = pattern.search(text or "")
        if match:
            number = int(match.group(1))
            if 1 <= number <= 99:
                return f"Week_{number:02d}"
    return None


def extract_course_codes(text: str, pattern: re.Pattern[str]) -> list[str]:
    found = []
    seen = set()

    for match in pattern.findall(text or ""):
        if isinstance(match, tuple):
            value = "".join(match)
        else:
            value = match

        value = value.upper()
        if value not in seen:
            seen.add(value)
            found.append(value)

    return found


def should_exclude(text: str, exclude_words: tuple[str, ...]) -> bool:
    lower = (text or "").lower()
    return any(word.lower() in lower for word in exclude_words)


def unique_destination(
    destination_dir: Path,
    filename: str,
    digest: str,
) -> Path:
    destination = destination_dir / filename

    if not destination.exists():
        return destination

    # Treat an existing file with identical content as a duplicate.
    try:
        if sha256_file(destination) == digest:
            return destination
    except OSError:
        pass

    return destination_dir / f"{destination.stem}_{digest[:8]}{destination.suffix}"


def load_manifest(input_root: Path) -> list[dict[str, str]]:
    manifest_path = input_root / "download_manifest.csv"

    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Manifest not found: {manifest_path}\n"
            "Confirm that --input points to the crawler output directory, Master_Slides."
        )

    with manifest_path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def build_search_text(row: dict[str, str]) -> str:
    fields = (
        row.get("filename", ""),
        row.get("saved_path", ""),
        row.get("source_title", ""),
        row.get("source_page", ""),
        row.get("download_url", ""),
        row.get("final_url", ""),
    )
    return " ".join(fields)


def organize(args: argparse.Namespace) -> None:
    input_root = Path(args.input).expanduser().resolve()
    output_root = Path(args.output).expanduser().resolve()

    rows = load_manifest(input_root)
    output_root.mkdir(parents=True, exist_ok=True)

    course_pattern = re.compile(args.course_pattern, re.IGNORECASE)
    selected_courses = {
        course.strip().upper()
        for course in args.course
        if course.strip()
    }

    extensions = PPT_ONLY_EXTENSIONS if args.ppt_only else SLIDE_EXTENSIONS

    exclude_words = tuple(DEFAULT_EXCLUDE_WORDS)
    if args.extra_exclude:
        exclude_words += tuple(word.lower() for word in args.extra_exclude)

    copied_hashes: dict[str, Path] = {}
    report_rows: list[dict[str, str]] = []

    copied = 0
    duplicates = 0
    skipped_missing = 0
    skipped_extension = 0
    skipped_assessment = 0
    skipped_no_course = 0

    for row in rows:
        relative_path = row.get("saved_path", "").strip()
        if not relative_path:
            continue

        source = input_root / relative_path
        if not source.exists() or not source.is_file():
            skipped_missing += 1
            print(f"[Missing] {source}")
            continue

        extension = source.suffix.lower()
        if extension not in extensions:
            skipped_extension += 1
            continue

        search_text = build_search_text(row)

        if not args.include_assessment and should_exclude(search_text, exclude_words):
            skipped_assessment += 1
            print(f"[Assessment excluded] {source.name}")
            continue

        course_codes = extract_course_codes(search_text, course_pattern)

        if selected_courses:
            course_codes = [
                code for code in course_codes
                if code in selected_courses
            ]

        if not course_codes:
            if args.include_unsorted:
                course_codes = ["UNSORTED"]
            else:
                skipped_no_course += 1
                print(f"[Course not identified] {source.name}")
                continue

        # A file normally belongs to one course. Use the first code if several are found.
        course_code = course_codes[0]

        destination_dir = output_root / course_code

        if args.by_week:
            week_source = " ".join(
                (
                    row.get("source_title", ""),
                    row.get("filename", ""),
                    row.get("saved_path", ""),
                )
            )
            week = parse_week(week_source)
            destination_dir = destination_dir / (week or "Other")

        destination_dir.mkdir(parents=True, exist_ok=True)

        digest = row.get("sha256", "").strip().lower()
        if not digest:
            digest = sha256_file(source)

        if digest in copied_hashes:
            duplicates += 1
            print(f"[Duplicate skipped] {source.name}")
            continue

        filename = clean_name(source.name, f"slides_{digest[:10]}{extension}", 220)

        # Optionally prefix the source-page title to reduce filename collisions.
        if args.prefix_source:
            source_title = clean_name(
                row.get("source_title", ""),
                "Source",
                70,
            )
            filename = clean_name(
                f"{source_title} - {filename}",
                filename,
                220,
            )

        destination = unique_destination(destination_dir, filename, digest)

        # Skip copying if unique_destination returns an existing identical file.
        if destination.exists():
            try:
                if sha256_file(destination) == digest:
                    copied_hashes[digest] = destination
                    duplicates += 1
                    print(f"[Already exists] {destination.relative_to(output_root)}")
                    continue
            except OSError:
                pass

        if args.move:
            shutil.move(str(source), str(destination))
            action = "moved"
        else:
            shutil.copy2(source, destination)
            action = "copied"

        copied_hashes[digest] = destination
        copied += 1

        relative_destination = destination.relative_to(output_root)
        print(f"[Organized] {relative_destination}")

        report_rows.append(
            {
                "course_code": course_code,
                "filename": destination.name,
                "destination": str(relative_destination),
                "source": str(source),
                "source_title": row.get("source_title", ""),
                "source_page": row.get("source_page", ""),
                "sha256": digest,
                "action": action,
            }
        )

    report_path = output_root / "organize_manifest.csv"
    fieldnames = [
        "course_code",
        "filename",
        "destination",
        "source",
        "source_title",
        "source_page",
        "sha256",
        "action",
    ]

    with report_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report_rows)

    print("\n" + "=" * 68)
    print("Organization completed")
    print(f"Input directory: {input_root}")
    print(f"Output directory: {output_root}")
    print(f"Files organized: {copied}")
    print(f"Duplicates skipped: {duplicates}")
    print(f"Assessments excluded: {skipped_assessment}")
    print(f"Non-target formats: {skipped_extension}")
    print(f"Courses not identified: {skipped_no_course}")
    print(f"Missing source files: {skipped_missing}")
    print(f"Organization manifest: {report_path}")
    print("=" * 68)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reorganize course-crawler downloads by course code.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Crawler output directory, for example C:\\Users\\Lja18\\Desktop\\Master_Slides",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Destination for organized courses, for example C:\\Users\\Lja18\\Desktop\\Organized_Courses",
    )
    parser.add_argument(
        "--course",
        action="append",
        default=[],
        help=(
            "Organize only selected course codes. Repeat this option, for example "
            "--course COMP0249 --course COMP0123. "
            "If omitted, all detected courses are organized automatically."
        ),
    )
    parser.add_argument(
        "--course-pattern",
        default=r"\b[A-Z]{4}\d{4}\b",
        help="Regular expression used to identify course codes.",
    )
    parser.add_argument(
        "--by-week",
        action="store_true",
        help="Create Week_01, Week_02, and similar subfolders inside each course folder.",
    )
    parser.add_argument(
        "--ppt-only",
        action="store_true",
        help="Organize only PPT/PPTX/PPS/PPSX files and exclude PDFs.",
    )
    parser.add_argument(
        "--include-assessment",
        action="store_true",
        help="Also keep coursework, assignment, submission, quiz, and other assessment files.",
    )
    parser.add_argument(
        "--extra-exclude",
        action="append",
        default=[],
        help="Additional exclusion keyword. Repeat this option for multiple keywords.",
    )
    parser.add_argument(
        "--include-unsorted",
        action="store_true",
        help="Place files without an identified course code in an UNSORTED folder.",
    )
    parser.add_argument(
        "--prefix-source",
        action="store_true",
        help="Prefix filenames with the source-page title to reduce name collisions.",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="Move files instead of copying them. Copying is the default, so original downloads are preserved.",
    )

    args = parser.parse_args()
    organize(args)


if __name__ == "__main__":
    main()