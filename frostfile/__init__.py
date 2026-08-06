"""FrostFile — a local-only identity-control tracker.

Nothing in this package sends data on its own. Outbound network calls happen
only when the user presses a button: breach lookups to Have I Been Pwned
(services/hibp.py) and the Sources page's agency-link checker
(services/linkcheck.py). There is no telemetry, analytics, or update check.
"""

__version__ = "0.3.0"
