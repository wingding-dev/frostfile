"""Export reminders as an .ics file.

The point is not to build a calendar inside Identilock — it is to get these
dates into whatever calendar you already look at, so an annual task does not
depend on remembering to open this app.

Reminder titles can carry a family member's name, so an exported file is
sensitive in the same way the database is. The UI says so at the download link.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from ..repo import Reminder

# Maps our recurrence vocabulary onto iCalendar RRULEs.
RRULES = {
    "yearly": "FREQ=YEARLY",
    "quarterly": "FREQ=MONTHLY;INTERVAL=3",
    "monthly": "FREQ=MONTHLY",
    "weekly": "FREQ=WEEKLY",
}


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """iCalendar limits lines to 75 octets; continuations start with a space."""
    if len(line) <= 73:
        return line
    chunks = [line[:73]]
    rest = line[73:]
    while rest:
        chunks.append(" " + rest[:72])
        rest = rest[72:]
    return "\r\n".join(chunks)


def build_calendar(reminders: list[Reminder], *, stamp: datetime | None = None) -> str:
    now = (stamp or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Identilock//Identity control reminders//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Identilock",
    ]

    for reminder in reminders:
        try:
            due = date.fromisoformat(reminder.due_date)
        except ValueError:
            continue

        summary = reminder.title
        if reminder.person_name:
            summary = f"{reminder.title} — {reminder.person_name}"

        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:identilock-{reminder.id}@localhost")
        lines.append(f"DTSTAMP:{now}")
        # All-day event: DTEND is exclusive, so it lands on the following day.
        lines.append(f"DTSTART;VALUE=DATE:{due.strftime('%Y%m%d')}")
        lines.append(f"DTEND;VALUE=DATE:{(due + timedelta(days=1)).strftime('%Y%m%d')}")
        lines.append(_fold(f"SUMMARY:{_escape(summary)}"))
        if reminder.detail:
            lines.append(_fold(f"DESCRIPTION:{_escape(reminder.detail)}"))
        rule = RRULES.get(reminder.recurrence)
        if rule:
            lines.append(f"RRULE:{rule}")
        lines.append("TRANSP:TRANSPARENT")
        lines.append("BEGIN:VALARM")
        lines.append("TRIGGER:-P1D")
        lines.append("ACTION:DISPLAY")
        lines.append(_fold(f"DESCRIPTION:{_escape(summary)}"))
        lines.append("END:VALARM")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
