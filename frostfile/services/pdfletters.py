"""Server-generated PDF mailing packets.

The browser's print dialog can only produce one PDF per print job, so bulk
printing yields one combined file. This module builds the packets directly —
one self-named PDF per child-agency pair, zipped — so nobody sits renaming
"document (3).pdf" twelve times.

Layout mirrors templates/_letter_body.html; a change to one should be made to
the other.
"""

from __future__ import annotations

import re
import zipfile
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter as LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_BODY = ParagraphStyle("body", fontName="Times-Roman", fontSize=11, leading=15)
_BOLD = ParagraphStyle("bold", parent=_BODY, fontName="Times-Bold")
_HEAD = ParagraphStyle(
    "head", fontName="Times-Bold", fontSize=14, leading=18, spaceAfter=10
)
_SMALL = ParagraphStyle("small", parent=_BODY, fontSize=9, leading=12)

_BLANK = "__________________"
_SSN_BLANK = "_______ - _____ - __________"


def _p(text: str, style: ParagraphStyle = _BODY) -> Paragraph:
    return Paragraph(escape(text).replace("\n", "<br/>"), style)


def _info_table(person, guardian) -> Table:
    minor_address = person.address or (guardian.address if guardian else None)
    rows = [
        ("Minor's full name", person.display_name),
        ("Minor's date of birth", person.birth_date or _BLANK),
        ("Minor's Social Security number", person.ssn or _SSN_BLANK),
        ("Minor's address", minor_address or _BLANK),
        ("Parent or guardian", guardian.display_name if guardian else _BLANK),
        (
            "Guardian's date of birth",
            guardian.birth_date if guardian and guardian.birth_date else _BLANK,
        ),
        (
            "Guardian's Social Security number",
            guardian.ssn if guardian and guardian.ssn else _SSN_BLANK,
        ),
    ]
    table = Table(
        [[_p(label, _BOLD), _p(value)] for label, value in rows],
        colWidths=[2.4 * inch, 4.0 * inch],
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.Color(0.8, 0.8, 0.8)),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _checklist(items: list[str]) -> Table:
    table = Table(
        [[_p("[   ]"), _p(item)] for item in items],
        colWidths=[0.5 * inch, 5.9 * inch],
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _teen_packet_story(person, agency, guardian, today: str) -> list:
    """A 16-17-year-old requests their OWN standard freeze (phone or mail;
    online requires 18) — the parent-placed protected-consumer letter would be
    the wrong instrument, so teens get a letter in their own name."""
    address = person.address or (guardian.address if guardian else None)
    sender_lines = [person.display_name] + ([address] if address else [])
    head = Table(
        [[_p("\n".join(sender_lines)), _p(today)]],
        colWidths=[4.4 * inch, 2.0 * inch],
    )
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    rows = [
        ("Full name", person.display_name),
        ("Date of birth", person.birth_date or _BLANK),
        ("Social Security number", person.ssn or _SSN_BLANK),
        ("Current address", address or _BLANK),
    ]
    info = Table(
        [[_p(label, _BOLD), _p(value)] for label, value in rows],
        colWidths=[2.4 * inch, 4.0 * inch],
    )
    info.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.Color(0.8, 0.8, 0.8)),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story = [
        head, Spacer(1, 24), _p(agency.mail_address), Spacer(1, 22),
        _p("Re: Request for a security freeze on my credit file", _BOLD),
        Spacer(1, 12), _p("To whom it may concern,"), Spacer(1, 10),
        _p("I am requesting that you place a security freeze on my credit "
           "file, and that you create a file for the sole purpose of placing "
           "the freeze if none currently exists. Security freezes are free "
           "under federal law."),
        Spacer(1, 14), info, Spacer(1, 14),
        _p("Copies of documents confirming my identity and address are "
           "enclosed. Please confirm in writing once the freeze is in place."),
        Spacer(1, 30), _p("Sincerely,"), Spacer(1, 40),
        _p("_________________________________________"),
        _p(person.display_name),
        PageBreak(),
        _p("Teen Freeze — Read This First", _HEAD),
        _p(f"{person.display_name} is 16 or 17, so the parent-placed child "
           "freeze no longer applies — the teen requests their own freeze, by "
           "phone or by mail (online accounts require being 18).", _SMALL),
        Spacer(1, 10), _p("Fastest Route: One Phone Call", _BOLD), Spacer(1, 4),
        _p((f"Have {person.display_name} call {agency.phone} and ask to place "
            "a security freeze. Mailing this letter is the backup.")
           if agency.phone else
           "Check the agency's official page for its phone number — calling "
           "is usually faster than mail.", _SMALL),
        Spacer(1, 10), _p("If Mailing, Enclose Copies Of", _BOLD), Spacer(1, 4),
        _p("The bureaus do not publish one consistent document list for 16- "
           "and 17-year-olds — call first to confirm. Commonly requested:", _SMALL),
        Spacer(1, 4),
        _checklist([
            "A photo ID (school ID, learner's permit, state ID, or passport)",
            "Copy of the Social Security card",
            "Proof of address (bank statement, or a parent's bill listing the teen)",
        ]),
        Spacer(1, 10), _p("Before Mailing", _BOLD), Spacer(1, 4),
        _checklist([
            f"Mailing address compared, line by line, against {agency.name}'s "
            "own website — today, by you",
            "Every enclosure is a copy, not an original",
            f"The letter is signed by {person.display_name} (not the parent)",
            "Sent with tracking or certified mail",
            "Date mailed recorded in the app",
        ]),
        Spacer(1, 14), _p("Mail to:", _BOLD), Spacer(1, 4), _p(agency.mail_address),
    ]
    return story


def build_packet_pdf(person, agency, guardian, today: str) -> bytes:
    """Cover letter (page 1) and enclosure checklist (page 2)."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=1 * inch,
        rightMargin=1 * inch,
        topMargin=1 * inch,
        bottomMargin=1 * inch,
        title=f"{agency.name} freeze packet - {person.display_name}",
    )

    if getattr(person, "is_teen", False):
        doc.build(_teen_packet_story(person, agency, guardian, today))
        return buffer.getvalue()

    if guardian:
        sender_lines = [guardian.display_name]
        if guardian.address:
            sender_lines.append(guardian.address)
        if guardian.phone:
            sender_lines.append(guardian.phone)
        sender = "\n".join(sender_lines)
    else:
        sender = "\n".join([_BLANK] * 3)

    head = Table(
        [[_p(sender), _p(today)]],
        colWidths=[4.4 * inch, 2.0 * inch],
    )
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    story = [
        head,
        Spacer(1, 24),
        _p(agency.mail_address),
        Spacer(1, 22),
        _p("Re: Request for a protected consumer security freeze for a minor", _BOLD),
        Spacer(1, 12),
        _p("To whom it may concern,"),
        Spacer(1, 10),
        _p(
            f"I am the parent or legal guardian of {person.display_name}, a "
            "minor. I am writing to request that you place a security freeze "
            "on any consumer report you maintain for this child, and that you "
            "create one for the sole purpose of placing a freeze if none "
            "currently exists."
        ),
        Spacer(1, 14),
        _info_table(person, guardian),
        Spacer(1, 14),
        _p(
            "Copies of the documents establishing my identity, the minor's "
            "identity, and my authority to act on the minor's behalf are "
            "enclosed, as listed on the attached checklist page. Please "
            "confirm in writing once the "
            "freeze is in place."
        ),
        Spacer(1, 30),
        _p("Sincerely,"),
        Spacer(1, 40),
        _p("_________________________________________"),
        _p(guardian.display_name if guardian else ""),
        PageBreak(),
        _p("Enclosure Checklist", _HEAD),
        _p(
            f"{agency.name} — freeze for {person.display_name}. "
            "Send photocopies only.",
            _SMALL,
        ),
        Spacer(1, 10),
    ]

    requirements = agency.minor_requirements or {}
    if requirements.get("guardian"):
        story += [_p("From the Parent or Guardian", _BOLD), Spacer(1, 4),
                  _checklist(requirements["guardian"]), Spacer(1, 10)]
    if requirements.get("minor"):
        story += [_p("For the Minor", _BOLD), Spacer(1, 4),
                  _checklist(requirements["minor"]), Spacer(1, 10)]

    story += [
        _p("Before Mailing", _BOLD),
        Spacer(1, 4),
        _checklist(
            [
                f"Mailing address compared, line by line, against "
                f"{agency.name}'s own website — today, by you",
                "Every enclosure is a copy, not an original",
                "The cover letter is signed",
                "Sent with tracking or certified mail",
                "Date mailed recorded in the app",
            ]
        ),
        Spacer(1, 14),
    ]
    if agency.notes:
        story += [_p("Agency Notes", _BOLD), Spacer(1, 4), _p(agency.notes, _SMALL),
                  Spacer(1, 14)]
    story += [_p("Mail to:", _BOLD), Spacer(1, 4), _p(agency.mail_address)]

    # Carry the app's citation honesty onto the mailed page: name the sources
    # behind the address and document list, and flag anything not confirmed at
    # a primary source (the same "?" signal the on-screen packet shows).
    story += [Spacer(1, 18), _p("Where these details came from", _BOLD), Spacer(1, 4)]
    for label, field in (("Mailing address", "mail_address"),
                         ("Required documents", "minor_requirements")):
        sources = agency.cite(field)
        if sources:
            for src in sources:
                mark = f"read {src.retrieved}" if src.is_primary else "listing only — not captured"
                story.append(_p(f"{label}: {src.publisher} — {src.title} ({mark})", _SMALL))
        else:
            story.append(
                _p(
                    f"⚠ {label}: not confirmed at a primary source — verify it "
                    f"on {agency.name}'s own website before relying on it.",
                    _SMALL,
                )
            )

    story += [
        Spacer(1, 8),
        _p(
            "FrostFile is a record-keeping tool, not legal advice. If this "
            f"page and {agency.name}'s own website ever disagree, the "
            "website wins.",
            _SMALL,
        ),
    ]

    doc.build(story)
    return buffer.getvalue()


def _safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "-", name).strip()


def build_zip(packets, guardian, today: str) -> bytes:
    """One PDF per (person, agency) pair, each self-named, in one zip."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for person, agency in packets:
            pdf = build_packet_pdf(person, agency, guardian, today)
            filename = _safe_filename(
                f"{agency.name} freeze packet - {person.display_name}.pdf"
            )
            archive.writestr(filename, pdf)
    return buffer.getvalue()
