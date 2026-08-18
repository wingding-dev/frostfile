"""FrostFile — a local-only identity-control tracker.

Nothing in this package touches the network. Ever. This is a project
requirement, not an accident: the app makes ZERO outbound connections — no
breach lookups, no link checks, no telemetry, no update checks. Anything that
needs the internet is a plain <a> link that opens in the user's own browser
(agency sites, haveibeenpwned.com, frostfile.org). Source links are verified
outside the app; each carries the date it was last verified, and the app
never checks them itself.

Do not add an outbound call, however benign. It erodes the core promise.
"""

__version__ = "2.1.0"
