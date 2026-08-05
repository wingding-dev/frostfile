"""Extract entities from a credit report and compare consecutive pulls.

An honest description of what this does
---------------------------------------
The three bureaus format their reports differently, change those formats
without notice, and none of them publish a parseable export. So this does not
"parse credit reports" in any strong sense. It pulls out patterns that are
reliable across formats — masked account numbers, street addresses, creditor-
looking headings, dates near an inquiries heading — and tells you which ones
are new since your last pull.

That means two things you should know before trusting it:

* It will miss things. A creditor name in an unusual layout may not be
  recognized, so the entity summary is a lead generator, not an audit.
* It flags noise. Reformatting between pulls can produce "new" items that are
  not new at all.

Because of both, every comparison also offers a plain line-by-line diff of the
underlying text. When the summary and the raw diff disagree, the raw diff is
the one that is right.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any

# A masked account number: XXXX1234, ****5678, ####9012, and similar.
ACCOUNT_RE = re.compile(r"(?:[Xx*#•]{3,}[\s-]?\d{2,6})")

STREET_SUFFIX = (
    r"ST|STREET|AVE|AVENUE|RD|ROAD|DR|DRIVE|LN|LANE|BLVD|BOULEVARD|CT|COURT|"
    r"WAY|PL|PLACE|TER|TERRACE|CIR|CIRCLE|PKWY|PARKWAY|HWY|HIGHWAY|TRL|TRAIL|"
    r"APT|UNIT|SUITE|STE"
)
ADDRESS_RE = re.compile(
    rf"\b\d{{1,6}}\s+(?:[A-Za-z0-9.'#-]+\s+){{0,4}}(?:{STREET_SUFFIX})\b\.?",
    re.IGNORECASE,
)

PHONE_RE = re.compile(r"\b(?:\(\d{3}\)\s?|\d{3}[.-])\d{3}[.-]\d{4}\b")

DATE_RE = re.compile(
    r"\b(?:\d{1,2}/\d{1,2}/\d{2,4}|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b"
)

# Headings that introduce the sections we care about most.
INQUIRY_HEADING = re.compile(
    r"\b(?:inquir(?:y|ies)|requests?\s+for\s+your\s+credit\s+history|"
    r"regular\s+inquir(?:y|ies)|hard\s+inquir(?:y|ies))\b",
    re.IGNORECASE,
)
EMPLOYER_HEADING = re.compile(r"\b(?:employ(?:er|ment)s?)\b", re.IGNORECASE)
ADDRESS_HEADING = re.compile(r"\b(?:address(?:es)?|addresses\s+identified)\b", re.IGNORECASE)

# Lines that look like an organization name rather than prose or a label.
CREDITOR_RE = re.compile(r"^[A-Z0-9][A-Z0-9 &.,'/\-]{3,48}$")

# Words that show up in ALL-CAPS headings and would otherwise be mistaken for
# creditor names. Not exhaustive; false positives are expected and harmless.
HEADING_NOISE = {
    "ACCOUNT", "ACCOUNTS", "ACCOUNT HISTORY", "ADDRESS", "ADDRESSES",
    "BALANCE", "CREDIT REPORT", "CREDIT SCORE", "CONSUMER STATEMENT",
    "DATE", "DATE OPENED", "EMPLOYER", "EMPLOYERS", "EMPLOYMENT",
    "INQUIRIES", "INQUIRY", "NAME", "PAYMENT HISTORY", "PERSONAL INFORMATION",
    "PUBLIC RECORDS", "REPORT DATE", "SUMMARY", "TOTAL", "STATUS",
    "OPEN ACCOUNTS", "CLOSED ACCOUNTS", "COLLECTIONS", "PAGE",
}

# How many lines after a section heading to treat as belonging to it.
SECTION_WINDOW = 40


@dataclass
class Extraction:
    accounts: list[str] = field(default_factory=list)
    addresses: list[str] = field(default_factory=list)
    inquiries: list[str] = field(default_factory=list)
    employers: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "accounts": self.accounts,
            "addresses": self.addresses,
            "inquiries": self.inquiries,
            "employers": self.employers,
            "phones": self.phones,
        }

    @property
    def total(self) -> int:
        return sum(len(v) for v in self.as_dict().values())


def extract_text(data: bytes, filename: str) -> str:
    """Get text out of a PDF or a text/HTML file."""
    if filename.lower().endswith(".pdf") or data[:5] == b"%PDF-":
        return _extract_pdf(data)
    text = data.decode("utf-8", errors="replace")
    if "<html" in text[:2000].lower():
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", "\n", text)
        text = re.sub(r"&nbsp;?", " ", text)
    return text


def _extract_pdf(data: bytes) -> str:
    from io import BytesIO

    from pypdf import PdfReader

    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted:
        # Bureau PDFs are sometimes password-protected with the user's own
        # details; an empty password unlocks many of them.
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001 - surfaced to the user as-is
            raise ValueError(
                "That PDF is password-protected. Save an unprotected copy and retry."
            ) from exc
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def normalize(text: str) -> list[str]:
    """Collapse whitespace and drop blank lines, preserving line structure."""
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"[ \t ]+", " ", raw).strip()
        if line:
            lines.append(line)
    return lines


def _dedupe(values: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for value in values:
        key = re.sub(r"\s+", " ", value).strip().upper()
        if key and key not in seen:
            seen[key] = value.strip()
    return sorted(seen.values())


def _section_indices(lines: list[str], heading: re.Pattern[str]) -> set[int]:
    """Line numbers falling within a window after any matching heading."""
    inside: set[int] = set()
    for index, line in enumerate(lines):
        if heading.search(line) and len(line) < 80:
            for offset in range(1, SECTION_WINDOW + 1):
                if index + offset < len(lines):
                    inside.add(index + offset)
    return inside


def _looks_like_creditor(line: str) -> bool:
    candidate = line.strip().rstrip(".")
    if not CREDITOR_RE.match(candidate):
        return False
    if candidate.upper() in HEADING_NOISE:
        return False
    if candidate.isdigit():
        return False
    # Needs at least one run of letters; "1234 5678" is not a creditor.
    return bool(re.search(r"[A-Z]{3,}", candidate))


def extract_entities(text: str) -> Extraction:
    lines = normalize(text)
    result = Extraction()

    inquiry_zone = _section_indices(lines, INQUIRY_HEADING)
    employer_zone = _section_indices(lines, EMPLOYER_HEADING)
    address_zone = _section_indices(lines, ADDRESS_HEADING)

    accounts: list[str] = []
    addresses: list[str] = []
    inquiries: list[str] = []
    employers: list[str] = []
    phones: list[str] = []

    for index, line in enumerate(lines):
        accounts.extend(ACCOUNT_RE.findall(line))
        phones.extend(PHONE_RE.findall(line))

        found_addresses = ADDRESS_RE.findall(line)
        if found_addresses or index in address_zone:
            addresses.extend(found_addresses)

        if _looks_like_creditor(line):
            if index in inquiry_zone:
                inquiries.append(line)
            elif index in employer_zone:
                employers.append(line)

    result.accounts = _dedupe(accounts)
    result.addresses = _dedupe(addresses)
    result.inquiries = _dedupe(inquiries)
    result.employers = _dedupe(employers)
    result.phones = _dedupe(phones)
    return result


@dataclass
class CategoryDelta:
    name: str
    added: list[str]
    removed: list[str]

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed)


@dataclass
class Comparison:
    deltas: list[CategoryDelta]
    line_diff: list[tuple[str, str]]
    only_one_pull: bool = False

    @property
    def added_count(self) -> int:
        return sum(len(d.added) for d in self.deltas)

    @property
    def removed_count(self) -> int:
        return sum(len(d.removed) for d in self.deltas)

    @property
    def has_changes(self) -> bool:
        return any(d.has_changes for d in self.deltas)


LABELS = {
    "accounts": "Account numbers",
    "addresses": "Addresses",
    "inquiries": "Inquiries",
    "employers": "Employers",
    "phones": "Phone numbers",
}


def compare(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
    previous_text: str = "",
    current_text: str = "",
) -> Comparison:
    """Diff two extractions, plus a line diff of the underlying text."""
    if previous is None:
        return Comparison(deltas=[], line_diff=[], only_one_pull=True)

    deltas = []
    for key, label in LABELS.items():
        before = set(previous.get(key, []))
        after = set(current.get(key, []))
        deltas.append(
            CategoryDelta(
                name=label,
                added=sorted(after - before),
                removed=sorted(before - after),
            )
        )

    line_diff: list[tuple[str, str]] = []
    if previous_text or current_text:
        diff = difflib.unified_diff(
            normalize(previous_text),
            normalize(current_text),
            lineterm="",
            n=2,
        )
        for line in diff:
            if line.startswith("+++") or line.startswith("---"):
                continue
            if line.startswith("+"):
                line_diff.append(("add", line[1:]))
            elif line.startswith("-"):
                line_diff.append(("del", line[1:]))
            elif line.startswith("@@"):
                line_diff.append(("ctx", line))
            else:
                line_diff.append(("ctx", line[1:] if line.startswith(" ") else line))

    return Comparison(deltas=deltas, line_diff=line_diff)
