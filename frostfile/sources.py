"""The citation registry.

Every factual claim the app makes — a mailing address, a phone number, a
procedural detail like "children under 18 cannot use the online tool" — points
at an entry here, and the UI renders it as a clickable superscript. You should
never have to take this app's word for anything.

Two levels of confidence, and the difference is deliberate:

``fetched``
    The page was retrieved and read when this directory was compiled, and the
    claim was taken directly from its text. This is the standard required
    before FrostFile will print a mailing packet.

``listed``
    The organization's own page for this topic, linked so you can confirm, but
    its contents were not captured at compile time. Treat these as pointers,
    not as verified values.

Nothing here is scraped at runtime. These agencies reorganize their sites
regularly, so if a link rots, the honest fix is to re-verify and update the
entry rather than to guess.
"""

from __future__ import annotations

from dataclasses import dataclass

COMPILED_ON = "2026-08-03"


@dataclass(frozen=True)
class Source:
    key: str
    title: str
    url: str
    publisher: str
    kind: str  # "official" | "government"
    checked: str  # "fetched" | "listed"
    retrieved: str = COMPILED_ON

    @property
    def is_primary(self) -> bool:
        return self.checked == "fetched"

    @property
    def confidence_note(self) -> str:
        if self.is_primary:
            return f"Retrieved and read on {self.retrieved}."
        return "Official page for this topic; contents not captured. Confirm before relying on it."


def _s(key: str, title: str, url: str, publisher: str, kind: str, checked: str) -> Source:
    return Source(
        key=key, title=title, url=url, publisher=publisher, kind=kind, checked=checked
    )


SOURCES: dict[str, Source] = {
    s.key: s
    for s in [
        # --- credit bureaus -------------------------------------------------
        _s(
            "equifax-minor-form",
            "Minor Freeze Request Form (PDF)",
            "https://assets.equifax.com/assets/personal/Minor_Freeze_Request_Form.pdf",
            "Equifax",
            "official",
            "fetched",
        ),
        _s(
            "equifax-freeze",
            "Security Freeze — freeze or unfreeze your credit",
            "https://www.equifax.com/personal/credit-report-services/credit-freeze/",
            "Equifax",
            "official",
            "listed",
        ),
        _s(
            "experian-minor-freeze",
            "Request a Security Freeze for a Minor Child's Credit Report",
            "https://www.experian.com/blogs/ask-experian/requesting-a-security-freeze-for-a-minor-childs-credit-report/",
            "Experian",
            "official",
            "fetched",
        ),
        _s(
            "experian-freeze",
            "Experian Freeze Center",
            "https://www.experian.com/freeze/center.html",
            "Experian",
            "official",
            "listed",
        ),
        _s(
            "experian-contact",
            "How to Contact the Credit Bureaus",
            "https://www.experian.com/blogs/ask-experian/how-to-contact-the-credit-bureaus/",
            "Experian",
            "official",
            "listed",
        ),
        _s(
            "transunion-freeze",
            "Credit Freeze",
            "https://www.transunion.com/credit-freeze",
            "TransUnion",
            "official",
            "listed",
        ),
        _s(
            "ca-ag-child-freeze",
            'How to "Freeze" Your Child\'s Credit Files',
            "https://oag.ca.gov/idtheft/facts/freeze-child-credit",
            "California Attorney General",
            "government",
            "fetched",
        ),
        _s(
            "innovis-freeze",
            "Security Freeze",
            "https://www.innovis.com/personal/securityFreeze",
            "Innovis",
            "official",
            "fetched",
        ),
        # --- specialty ------------------------------------------------------
        _s(
            "lexisnexis-freeze",
            "Security Freeze request",
            "https://consumer.risk.lexisnexis.com/freeze",
            "LexisNexis Risk Solutions",
            "official",
            "fetched",
        ),
        _s(
            "lexisnexis-request",
            "Request your consumer disclosure report",
            "https://consumer.risk.lexisnexis.com/request",
            "LexisNexis Risk Solutions",
            "official",
            "listed",
        ),
        # --- banking --------------------------------------------------------
        _s(
            "chexsystems-freeze",
            "Place a Security Freeze",
            "https://www.chexsystems.com/security-freeze/place-freeze",
            "ChexSystems",
            "official",
            "fetched",
        ),
        _s(
            "earlywarning-consumer",
            "Consumer Information",
            "https://www.earlywarning.com/consumer-information",
            "Early Warning Services",
            "official",
            "listed",
        ),
        _s(
            "telecheck-consumer",
            "TeleCheck Consumer Information",
            "https://www.firstdata.com/telecheck/consumer-information.html",
            "Fiserv / TeleCheck",
            "official",
            "listed",
        ),
        _s(
            "certegy-consumers",
            "Certegy for Consumers",
            "https://www.certegy.com/consumers",
            "Certegy",
            "official",
            "listed",
        ),
        # --- telecom / utility ----------------------------------------------
        _s(
            "nctue-consumers",
            "NCTUE Consumers",
            "https://www.nctue.com/Consumers",
            "NCTUE",
            "official",
            "fetched",
        ),
        # --- subprime -------------------------------------------------------
        _s(
            "clarity-consumers",
            "Clarity Services for Consumers",
            "https://www.clarityservices.com/consumers/",
            "Clarity Services (Experian)",
            "official",
            "listed",
        ),
        _s(
            "teletrack-consumers",
            "Teletrack for Consumers",
            "https://teletrack.com/consumers/",
            "Teletrack (TransUnion)",
            "official",
            "listed",
        ),
        # --- rental ---------------------------------------------------------
        _s(
            "corelogic-consumers",
            "CoreLogic Consumer Portal",
            "https://consumers.corelogic.com/",
            "CoreLogic",
            "official",
            "listed",
        ),
        _s(
            "realpage-consumer",
            "RealPage Consumer Relations",
            "https://www.realpage.com/consumer/",
            "RealPage",
            "official",
            "listed",
        ),
        # --- employment -----------------------------------------------------
        _s(
            "theworknumber-employees",
            "The Work Number for Employees",
            "https://theworknumber.com/employees/",
            "Equifax Workforce Solutions",
            "official",
            "listed",
        ),
        # --- government controls --------------------------------------------
        _s(
            "irs-ip-pin",
            "Get an Identity Protection PIN (IP PIN)",
            "https://www.irs.gov/identity-theft-fraud-scams/get-an-identity-protection-pin",
            "Internal Revenue Service",
            "government",
            "fetched",
        ),
        _s(
            "irs-ip-pin-faq",
            "Frequently asked questions about the IP PIN",
            "https://www.irs.gov/identity-theft-fraud-scams/frequently-asked-questions-about-the-identity-protection-personal-identification-number-ip-pin",
            "Internal Revenue Service",
            "government",
            "listed",
        ),
        _s(
            "ssa-myaccount",
            "my Social Security account",
            "https://www.ssa.gov/myaccount/",
            "Social Security Administration",
            "government",
            "listed",
        ),
        _s(
            "everify-self-lock",
            "Self Lock",
            "https://www.e-verify.gov/employees/employee-self-services/mye-verify/self-lock",
            "E-Verify (USCIS)",
            "government",
            "listed",
        ),
        _s(
            "usps-informed-delivery",
            "Informed Delivery",
            "https://informeddelivery.usps.com/",
            "United States Postal Service",
            "government",
            "listed",
        ),
        # --- other ----------------------------------------------------------
        _s(
            "optoutprescreen",
            "OptOutPrescreen.com",
            "https://www.optoutprescreen.com/",
            "Consumer Credit Reporting Industry",
            "official",
            "listed",
        ),
        _s(
            "privacyrights-databrokers",
            "Data Brokers directory",
            "https://www.privacyrights.org/data-brokers",
            "Privacy Rights Clearinghouse",
            "official",
            "listed",
        ),
        _s(
            "cfpb-crc-list",
            "List of Consumer Reporting Companies (PDF)",
            "https://files.consumerfinance.gov/f/documents/cfpb_consumer-reporting-companies-list.pdf",
            "Consumer Financial Protection Bureau",
            "government",
            "listed",
        ),
        _s(
            "annualcreditreport",
            "AnnualCreditReport.com",
            "https://www.annualcreditreport.com/",
            "Central Source LLC (federally mandated)",
            "official",
            "listed",
        ),
        _s(
            "ftc-fcra",
            "Fair Credit Reporting Act, 15 U.S.C. § 1681 (PDF)",
            "https://www.ftc.gov/system/files/documents/statutes/fair-credit-reporting-act/545a_fair-credit-reporting-act-0918.pdf",
            "Federal Trade Commission",
            "government",
            "listed",
        ),
        _s(
            "hibp-subscription",
            "Have I Been Pwned — subscription tiers",
            "https://haveibeenpwned.com/Subscription",
            "Have I Been Pwned",
            "official",
            "listed",
        ),
        _s(
            "hibp-api",
            "Have I Been Pwned — API v3 documentation",
            "https://haveibeenpwned.com/api/v3",
            "Have I Been Pwned",
            "official",
            "listed",
        ),
    ]
}


def get(key: str) -> Source | None:
    return SOURCES.get(key)


def resolve(keys: list[str] | None) -> list[Source]:
    """Turn citation keys into Source objects, silently dropping unknown keys."""
    if not keys:
        return []
    return [SOURCES[k] for k in keys if k in SOURCES]


def all_sources() -> list[Source]:
    return sorted(SOURCES.values(), key=lambda s: (s.publisher.lower(), s.title.lower()))
