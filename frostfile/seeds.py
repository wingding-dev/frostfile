"""The bundled directory of consumer reporting agencies and identity controls.

Every factual field can carry citations — see ``frostfile/sources.py``. The
rule applied throughout: a field is cited only if the claim was taken from a
page that was actually retrieved and read, or from the organization's own page
for that topic. Anything uncited renders in the UI with an "unverified" marker
rather than quietly passing itself off as checked.

``address_verified`` is the stricter gate. It gates letter generation, because
a minor-freeze packet contains a child's birth certificate and Social Security
card, and mailing one to a stale address is worse than not mailing it at all.

Compiled 2026-08-03. Agencies reorganize; re-check before a large mailing.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

# Status vocabulary shared by freezes and enrollments.
STATUS_NOT_STARTED = "not_started"
STATUS_IN_PROGRESS = "in_progress"
STATUS_ACTIVE = "active"
STATUS_THAWED = "thawed"
STATUS_NO_FILE = "no_file"
STATUS_NOT_APPLICABLE = "not_applicable"

STATUS_ORDER = [
    STATUS_NOT_STARTED,
    STATUS_IN_PROGRESS,
    STATUS_ACTIVE,
    STATUS_THAWED,
    STATUS_NO_FILE,
    STATUS_NOT_APPLICABLE,
]

CATEGORY_LABELS = {
    "credit_bureau": "Nationwide Credit Bureaus",
    "specialty_cra": "Specialty Reporting Agencies",
    "banking": "Banking and Check Acceptance",
    "telecom_utility": "Telecom and Utilities",
    "subprime": "Subprime and Payday Lending",
    "rental": "Rental and Housing Screening",
    "employment": "Employment and Income",
    "gov_control": "Government Controls",
    "other_control": "Other Controls",
}

# What a row asks of the user. "act" rows are the household's to-do list;
# "covered" rows are handled by an action recorded on another row and only need
# confirming; "fyi" rows have no step a person can take and exist so the user
# knows the file exists. FYI rows are excluded from progress counts and from
# the freeze grid — a to-do list with un-doable items on it teaches people to
# ignore it.
ACTION_KIND_LABELS = {
    "act": "Something to do",
    # Claiming an account is a race, not a chore: whoever registers first owns
    # it, and the questions asked to prove identity draw on the same records a
    # breach exposes. These sort above the freezes for that reason.
    "claim_first": "Claim this first",
    "covered": "Covered elsewhere",
    "fyi": "FYI only",
}

# Categories where "active" means a freeze; elsewhere it means an enrollment.
FREEZE_CATEGORIES = {
    "credit_bureau",
    "specialty_cra",
    "banking",
    "telecom_utility",
    "subprime",
    "rental",
    "employment",
}


def status_label(status: str, category: str) -> str:
    if status == STATUS_ACTIVE:
        return "Frozen" if category in FREEZE_CATEGORIES else "Enrolled"
    return {
        STATUS_NOT_STARTED: "Not started",
        STATUS_IN_PROGRESS: "In progress",
        STATUS_THAWED: "Temporarily lifted",
        STATUS_NO_FILE: "No file exists",
        STATUS_NOT_APPLICABLE: "Not applicable",
    }.get(status, status)


AGENCIES: list[dict[str, Any]] = [
    # ---------------------------------------------------------------- bureaus
    {
        "slug": "equifax",
        "name": "Equifax",
        "category": "credit_bureau",
        "description": "One of the three nationwide credit bureaus.",
        "why_it_matters": (
            "Freezing here blocks most new credit accounts opened in your name. "
            "Equifax also operates NCTUE and The Work Number, which are frozen "
            "separately."
        ),
        "freeze_url": "https://www.equifax.com/personal/credit-report-services/credit-freeze/",
        "phone": "1-888-298-0045",
        "mail_address": "Equifax Information Services LLC\nP.O. Box 105788\nAtlanta, GA 30348",
        "address_verified": True,
        "source_url": "https://assets.equifax.com/assets/personal/Minor_Freeze_Request_Form.pdf",
        "supports_online": True,
        "supports_minor": True,
        "minor_mail_only": True,
        "thaw_procedure": (
            "Placing, temporarily lifting, and permanently removing a freeze are "
            "all free. Lift online or via the myEquifax app."
        ),
        "notes": (
            "The minor freeze form covers children under 16. 16- and "
            "17-year-olds request their own standard freeze by phone or mail "
            "(online accounts require 18) — FrostFile's Letters page prints a "
            "teen letter for this."
        ),
        "minor_requirements": {
            "guardian": [
                "Proof of your identity — one of: driver's license or other "
                "government-issued ID, Social Security card, or birth certificate",
                "Proof you are the minor's parent or authorized representative — "
                "one of: the minor's birth certificate, a court order, a valid "
                "power of attorney, or foster care certification",
            ],
            "minor": [
                "Copy of the minor's Social Security card",
                "Copy of the minor's birth certificate",
            ],
        },
        "citations": {
            "mail_address": ["equifax-minor-form", "ca-ag-child-freeze"],
            "minor_requirements": ["equifax-minor-form", "ca-ag-child-freeze"],
            "thaw_procedure": ["equifax-minor-form"],
            "notes": ["equifax-minor-form", "equifax-child-faq", "ftc-minors-under-16"],
            "freeze_url": ["equifax-freeze"],
            "phone": ["equifax-freeze"],
        },
        "sort_order": 10,
    },
    {
        "slug": "experian",
        "name": "Experian",
        "category": "credit_bureau",
        "description": "One of the three nationwide credit bureaus.",
        "why_it_matters": (
            "Freezing here blocks most new credit accounts. Experian also owns "
            "Clarity Services, which covers payday and subprime lending and is "
            "frozen separately."
        ),
        "freeze_url": "https://www.experian.com/freeze/center.html",
        "phone": "1-888-397-3742",
        "mail_address": "Experian\nP.O. Box 9554\nAllen, TX 75013",
        "address_verified": True,
        "source_url": "https://www.experian.com/blogs/ask-experian/requesting-a-security-freeze-for-a-minor-childs-credit-report/",
        "supports_online": True,
        "supports_minor": True,
        "minor_mail_only": True,
        "thaw_procedure": "Lift online or by phone, at no charge.",
        "notes": (
            "Overnight deliveries go to 701 Experian Parkway, Allen, TX 75013. "
            "Include a list of your home addresses for the past two years."
        ),
        "minor_requirements": {
            "guardian": [
                "Copy of your government-issued ID card (such as a driver's license)",
                "Copy of recent mail showing your current address — a utility bill, "
                "bank statement, or insurance statement",
                "Court document naming you as guardian, if you are not the parent",
            ],
            "minor": [
                "Copy of the child's birth certificate",
                "Copy of the child's Social Security card",
            ],
        },
        "citations": {
            "mail_address": ["experian-minor-freeze", "ca-ag-child-freeze"],
            "minor_requirements": ["experian-minor-freeze", "ca-ag-child-freeze"],
            "notes": ["experian-minor-freeze"],
            "freeze_url": ["experian-freeze"],
            "phone": ["experian-contact"],
        },
        "sort_order": 11,
    },
    {
        "slug": "transunion",
        "name": "TransUnion",
        "category": "credit_bureau",
        "description": "One of the three nationwide credit bureaus.",
        "why_it_matters": "Freezing here blocks most new credit accounts.",
        "freeze_url": "https://www.transunion.com/credit-freeze",
        "phone": "1-800-916-8800",
        "mail_address": "TransUnion\nP.O. Box 380\nWoodlyn, PA 19094",
        "address_verified": True,
        "source_url": "https://oag.ca.gov/idtheft/facts/freeze-child-credit",
        "supports_online": True,
        "supports_minor": True,
        "minor_mail_only": True,
        "thaw_procedure": "Lift online or by phone, at no charge.",
        "notes": (
            "Protected consumer (minor) freezes cannot be placed online or by "
            "phone — the documentation requirement makes it mail-only. Send "
            "copies, never original documents."
        ),
        "minor_requirements": {
            "guardian": [
                "One document proving your authority — a court order, power of "
                "attorney, the child's birth certificate, or foster care certification",
                "Your identification — Social Security card or number, plus a "
                "driver's license, state ID, or other government-issued ID",
            ],
            "minor": [
                "Certified or official copy of the child's birth certificate",
                "The child's Social Security card or number",
            ],
        },
        "citations": {
            "mail_address": ["ca-ag-child-freeze"],
            "minor_requirements": ["ca-ag-child-freeze"],
            "notes": ["ca-ag-child-freeze"],
            "freeze_url": ["transunion-freeze"],
            "phone": ["transunion-freeze"],
        },
        "sort_order": 12,
    },
    {
        "slug": "innovis",
        "name": "Innovis",
        "category": "credit_bureau",
        "description": "The fourth credit bureau, used largely for identity verification.",
        "why_it_matters": (
            "Lenders and telecoms use Innovis for fraud checks even when they do "
            "not pull one of the big three. Free to freeze, and widely skipped."
        ),
        "freeze_url": "https://www.innovis.com/personal/securityFreeze",
        "phone": "1-866-712-4546",
        "mail_address": "Innovis Consumer Assistance\nP.O. Box 530088\nAtlanta, GA 30353-0088",
        "address_verified": True,
        "source_url": "https://www.innovis.com/personal/securityFreeze",
        "supports_online": True,
        "supports_minor": False,
        "minor_mail_only": True,
        "thaw_procedure": "Lift online or by phone at no charge.",
        "notes": (
            "General consumer assistance is 1-800-540-2505. Minor freeze handling "
            "was not documented on the freeze page — call before mailing anything."
        ),
        "citations": {
            "mail_address": ["innovis-freeze"],
            "phone": ["innovis-freeze"],
            "freeze_url": ["innovis-freeze"],
            "notes": ["innovis-freeze"],
        },
        "sort_order": 13,
    },
    # ------------------------------------------------------------- speciality
    {
        "slug": "lexisnexis",
        "name": "LexisNexis Risk Solutions",
        "category": "specialty_cra",
        "description": "Public records, identity, and fraud analytics. Includes SageStream.",
        "why_it_matters": (
            "Feeds identity verification behind many lenders and insurers. A "
            "LexisNexis freeze also covers SageStream reports, so one request "
            "handles both."
        ),
        "freeze_url": "https://consumer.risk.lexisnexis.com/freeze",
        "phone": "1-800-456-1244",
        "mail_address": "LexisNexis Risk Solutions Consumer Center\nAttn: Security Freeze\nP.O. Box 105108\nAtlanta, GA 30348-5108",
        "address_verified": True,
        "source_url": "https://consumer.risk.lexisnexis.com/freeze",
        "supports_online": True,
        "supports_minor": True,
        "minor_mail_only": False,
        "thaw_procedure": "Lift online or by phone.",
        "notes": (
            "Freezes for a minor under 16 or a protected consumer can be "
            "requested online, by mail, or by phone. Also worth requesting your "
            "full consumer disclosure — it is often the most revealing single "
            "file about you."
        ),
        "minor_requirements": {
            "guardian": [
                "Proof of your identity — government-issued ID",
                "Proof of authority — birth certificate, court order, or power of attorney",
            ],
            "minor": [
                "The minor's Social Security number",
                "The minor's birth certificate",
            ],
        },
        "citations": {
            "mail_address": ["lexisnexis-freeze"],
            "phone": ["lexisnexis-freeze"],
            "freeze_url": ["lexisnexis-freeze"],
            "why_it_matters": ["lexisnexis-freeze"],
            "notes": ["lexisnexis-freeze"],
        },
        "sort_order": 20,
    },
    {
        "slug": "sagestream",
        "name": "SageStream",
        "category": "specialty_cra",
        "description": "Alternative credit data. Now part of LexisNexis Risk Solutions.",
        "why_it_matters": (
            "Used by auto lenders, card issuers, retailers, utilities, and mobile "
            "carriers."
        ),
        "freeze_url": "https://consumer.risk.lexisnexis.com/freeze",
        "phone": "",
        "mail_address": "",
        "address_verified": False,
        "source_url": "https://consumer.risk.lexisnexis.com/freeze",
        "supports_online": True,
        "supports_minor": False,
        "minor_mail_only": True,
        "thaw_procedure": "Handled through LexisNexis.",
        "notes": (
            "A LexisNexis freeze covers SageStream reports. Tracked separately so "
            "you can confirm that rather than assume it."
        ),
        "action_kind": "covered",
        "action_note": (
            "Nothing separate to do here: freezing LexisNexis covers SageStream "
            "too. This row exists so you can mark it confirmed instead of "
            "assuming it."
        ),
        "citations": {
            "freeze_url": ["lexisnexis-freeze"],
            "notes": ["lexisnexis-freeze"],
        },
        "sort_order": 21,
    },
    {
        "slug": "clue",
        "name": "LexisNexis C.L.U.E.",
        "category": "specialty_cra",
        "description": "Auto and property insurance claim history.",
        "why_it_matters": (
            "Affects insurance pricing and eligibility. Request the report and "
            "dispute errors; there is nothing to freeze here."
        ),
        "freeze_url": "https://consumer.risk.lexisnexis.com/request",
        "phone": "",
        "mail_address": "",
        "address_verified": False,
        "source_url": "https://consumer.risk.lexisnexis.com/request",
        "supports_online": True,
        "supports_minor": False,
        "minor_mail_only": True,
        "thaw_procedure": "Not applicable — disclosure only.",
        "notes": "Request annually alongside your LexisNexis consumer disclosure.",
        "action_kind": "fyi",
        "action_note": (
            "There is nothing to freeze here — it is a record of insurance "
            "claims, not credit. Good to know it exists; once a year you can ask "
            "for a free copy and dispute anything wrong in it."
        ),
        "citations": {"freeze_url": ["lexisnexis-request"]},
        "sort_order": 22,
    },
    # ---------------------------------------------------------------- banking
    {
        "slug": "chexsystems",
        "name": "ChexSystems",
        "category": "banking",
        "description": "Deposit account history used when opening checking and savings accounts.",
        "why_it_matters": (
            "A freeze here stops someone opening a bank account in your name — a "
            "common step in moving money through a stolen identity."
        ),
        "freeze_url": "https://www.chexsystems.com/security-freeze/place-freeze",
        "phone": "1-800-887-7652",
        "mail_address": "Chex Systems, Inc.\nAttn: Security Freeze Department\nP.O. Box 583399\nMinneapolis, MN 55458",
        "address_verified": True,
        "source_url": "https://www.chexsystems.com/security-freeze/place-freeze",
        "supports_online": True,
        "supports_minor": True,
        "minor_mail_only": True,
        "thaw_procedure": "Lift online or by phone at no charge.",
        "notes": (
            "Parents and legal guardians can freeze a minor's file by written "
            "request. Also request your free ChexSystems consumer disclosure."
        ),
        "minor_requirements": {
            "guardian": [
                "Proof of your identity and current address",
            ],
            "minor": [
                "Copy of the child's birth certificate",
                "Copy of the child's Social Security card",
            ],
        },
        "citations": {
            "mail_address": ["chexsystems-freeze"],
            "phone": ["chexsystems-freeze"],
            "freeze_url": ["chexsystems-freeze"],
            "minor_requirements": ["chexsystems-freeze"],
            "notes": ["chexsystems-freeze"],
        },
        "sort_order": 30,
    },
    {
        "slug": "early_warning",
        "name": "Early Warning Services",
        "category": "banking",
        "description": "Bank-owned network behind Zelle and deposit account screening.",
        "why_it_matters": "Used by large banks for account opening and fraud decisions.",
        "freeze_url": "https://www.earlywarning.com/consumer-information",
        "phone": "",
        "mail_address": "",
        "address_verified": False,
        "source_url": "https://www.earlywarning.com/consumer-information",
        "supports_online": True,
        "supports_minor": False,
        "minor_mail_only": True,
        "thaw_procedure": "Confirm the current process on their consumer page.",
        "notes": "",
        "action_kind": "fyi",
        "action_note": (
            "Their public pages do not offer a do-it-yourself freeze, so there "
            "is nothing for you to do unless a bank points you here. This entry "
            "exists so you know the database is out there."
        ),
        "citations": {"freeze_url": ["earlywarning-consumer"]},
        "sort_order": 31,
    },
    {
        "slug": "telecheck",
        "name": "TeleCheck (Fiserv)",
        "category": "banking",
        "description": "Check acceptance and verification at retailers.",
        "why_it_matters": "Stops fraudulent check writing against your identity.",
        "freeze_url": "https://getassistance.telecheck.com/",
        "phone": "800-366-2425",
        "mail_address": "",
        "address_verified": False,
        "source_url": "https://getassistance.telecheck.com/",
        "supports_online": False,
        "supports_minor": False,
        "minor_mail_only": True,
        "thaw_procedure": "Contact directly.",
        "notes": "",
        "citations": {
            "freeze_url": ["telecheck-consumer"],
            "phone": ["cfpb-telecheck"],
        },
        "sort_order": 32,
    },
    {
        "slug": "certegy",
        "name": "Certegy",
        "category": "banking",
        "description": "Check acceptance and verification.",
        "why_it_matters": "Same exposure as TeleCheck, different retailer network.",
        "freeze_url": "https://www.certegy.com/consumers",
        "phone": "",
        "mail_address": "",
        "address_verified": False,
        "source_url": "https://www.certegy.com/consumers",
        "supports_online": False,
        "supports_minor": False,
        "minor_mail_only": True,
        "thaw_procedure": "Contact directly.",
        "notes": "",
        "citations": {"freeze_url": ["certegy-consumers"]},
        "sort_order": 33,
    },
    # -------------------------------------------------------- telecom/utility
    {
        "slug": "nctue",
        "name": "NCTUE",
        "category": "telecom_utility",
        "description": "National Consumer Telecom and Utilities Exchange, operated by Equifax.",
        "why_it_matters": (
            "Phone, cable, and utility accounts are opened against this file, not "
            "your regular credit report. Freezing the big three does not cover it."
        ),
        "freeze_url": "https://www.nctue.com/Consumers",
        "phone": "1-866-349-5355",
        "mail_address": "Security Freeze\nExchange Service Center - NCTUE\nP.O. Box 105561\nAtlanta, GA 30348",
        "address_verified": True,
        "source_url": "https://www.nctue.com/Consumers",
        "supports_online": True,
        "supports_minor": False,
        "minor_mail_only": True,
        "thaw_procedure": (
            "Place, temporarily lift, or remove a freeze online, by phone, or by "
            "mail at no cost."
        ),
        "notes": "The online portal is at nctueconsumerportal.com.",
        "citations": {
            "mail_address": ["nctue-consumers"],
            "phone": ["nctue-consumers"],
            "freeze_url": ["nctue-consumers"],
            "thaw_procedure": ["nctue-consumers"],
            "notes": ["nctue-consumers"],
        },
        "sort_order": 40,
    },
    # --------------------------------------------------------------- subprime
    {
        "slug": "clarity",
        "name": "Clarity Services",
        "category": "subprime",
        "description": "Subprime and payday lending bureau, owned by Experian.",
        "why_it_matters": (
            "Payday lenders often skip the big three entirely. This is where a "
            "stolen SSN gets turned into a small, fast loan."
        ),
        "freeze_url": "https://www.clarityservices.com/support/security-freeze/",
        "phone": "866-390-3118",
        "mail_address": "",
        "address_verified": False,
        "source_url": "https://www.clarityservices.com/support/security-freeze/",
        "supports_online": True,
        "supports_minor": False,
        "minor_mail_only": True,
        "thaw_procedure": "Contact directly.",
        "notes": "Separate from the main Experian freeze.",
        "citations": {
            "freeze_url": ["clarity-consumers"],
            "phone": ["clarity-consumers"],
        },
        "sort_order": 50,
    },
    {
        "slug": "teletrack",
        "name": "Teletrack",
        "category": "subprime",
        "description": "Subprime lending bureau — now part of DataX (Equifax).",
        "why_it_matters": "Same exposure as Clarity, different lender network.",
        "freeze_url": "https://consumers.teletrack.com/",
        "phone": "877-309-5226",
        "mail_address": "",
        "address_verified": False,
        "source_url": "https://consumers.teletrack.com/",
        "supports_online": True,
        "supports_minor": False,
        "minor_mail_only": True,
        "thaw_procedure": "Handled at DataX.",
        "notes": (
            "Teletrack's consumer portal now announces it is part of DataX and "
            "directs consumers there — the DataX freeze is the one that counts."
        ),
        "action_kind": "covered",
        "action_note": (
            "Nothing separate to do here: Teletrack was folded into DataX, so "
            "the DataX freeze covers it. This row exists so you can confirm "
            "that rather than assume it."
        ),
        "citations": {
            "freeze_url": ["teletrack-consumers"],
            "phone": ["cfpb-teletrack"],
            "notes": ["teletrack-consumers"],
        },
        "sort_order": 51,
    },
    {
        "slug": "datax",
        "name": "DataX",
        "category": "subprime",
        "description": "Payday and installment lending bureau, owned by Equifax.",
        "why_it_matters": (
            "Payday and installment lenders that never touch the big three "
            "report here. Teletrack now lives inside it too, so this one "
            "freeze covers both networks."
        ),
        "freeze_url": "https://consumers.dataxltd.com/consumerCreditFreeze",
        "phone": "800-295-4790",
        "mail_address": "DataX, an Equifax Company\nConsumer Reporting Division\nP.O. Box 740124\nAtlanta, GA 30374",
        "address_verified": True,
        "source_url": "https://consumers.dataxltd.com/consumerCreditFreeze",
        "supports_online": True,
        "supports_minor": False,
        "minor_mail_only": True,
        "thaw_procedure": "Lift or remove free of charge, online or by mail.",
        "notes": (
            "Freezing is free, online or by mail. Phone hours are limited "
            "(Mon-Thu 7am-4pm, Fri 7am-noon, Pacific). The CFPB lists a "
            "neighboring P.O. Box (740125) for this company — the freeze "
            "request form itself says 740124, so that is the one to use."
        ),
        "citations": {
            "freeze_url": ["datax-freeze"],
            "phone": ["datax-freeze", "cfpb-datax"],
            "mail_address": ["datax-freeze"],
            "why_it_matters": ["cfpb-datax", "teletrack-consumers"],
            "notes": ["datax-freeze", "cfpb-datax"],
        },
        "sort_order": 52,
    },
    # ----------------------------------------------------------------- rental
    {
        "slug": "corelogic",
        "name": "SafeRent Solutions",
        "category": "rental",
        "description": "Tenant screening and rental history (formerly CoreLogic Rental Property Solutions).",
        "why_it_matters": "Used by landlords; errors here can cost you a lease.",
        "freeze_url": "https://saferentsolutions.com/consumer-support/",
        "phone": "888-333-2413",
        "mail_address": "",
        "address_verified": False,
        "source_url": "https://saferentsolutions.com/consumer-support/",
        "supports_online": True,
        "supports_minor": False,
        "minor_mail_only": True,
        "thaw_procedure": "Contact directly.",
        "notes": "Older guides call this company CoreLogic or SafeRent — same outfit, new name.",
        "citations": {
            "freeze_url": ["corelogic-consumers", "cfpb-saferent"],
            "phone": ["corelogic-consumers", "cfpb-saferent"],
            "notes": ["cfpb-saferent"],
        },
        "sort_order": 60,
    },
    {
        "slug": "realpage",
        "name": "RealPage LeasingDesk",
        "category": "rental",
        "description": "Tenant screening.",
        "why_it_matters": "Second major landlord screening network.",
        "freeze_url": "https://www.realpage.com/support/consumer/",
        "phone": "866-934-1124",
        "mail_address": "",
        "address_verified": False,
        "source_url": "https://www.realpage.com/support/consumer/",
        "supports_online": True,
        "supports_minor": False,
        "minor_mail_only": True,
        "thaw_procedure": "Contact directly.",
        "notes": "",
        "citations": {
            "freeze_url": ["realpage-consumer"],
            "phone": ["realpage-consumer"],
        },
        "sort_order": 61,
    },
    # ------------------------------------------------------------- employment
    {
        "slug": "work_number",
        "name": "The Work Number (Equifax)",
        "category": "employment",
        "description": "Employment and income verification database.",
        "why_it_matters": (
            "Holds detailed salary history. Freezing it limits who can pull your "
            "income record and makes employment fraud harder to sustain."
        ),
        "freeze_url": "https://theworknumber.com/employees/",
        "phone": "",
        "mail_address": "",
        "address_verified": False,
        "source_url": "https://theworknumber.com/employees/",
        "supports_online": True,
        "supports_minor": False,
        "minor_mail_only": True,
        "thaw_procedure": "Managed through the Equifax freeze portal.",
        "notes": "Request your free Employment Data Report while you are there.",
        "citations": {"freeze_url": ["theworknumber-employees"]},
        "sort_order": 70,
    },
    # ---------------------------------------------------------- gov. controls
    {
        "slug": "irs_ip_pin",
        "name": "IRS Identity Protection PIN",
        "category": "gov_control",
        "description": "A six-digit PIN required to file a federal tax return in your name.",
        "why_it_matters": (
            "Refund fraud is the fastest way to monetize a stolen SSN. An IP PIN "
            "blocks it outright and is free. Parents and legal guardians can "
            "request one for dependents."
        ),
        "freeze_url": "https://www.irs.gov/identity-theft-fraud-scams/get-an-identity-protection-pin",
        "phone": "",
        "mail_address": "",
        "address_verified": False,
        "source_url": "https://www.irs.gov/identity-theft-fraud-scams/get-an-identity-protection-pin",
        "supports_online": True,
        "supports_minor": True,
        "minor_mail_only": True,
        "expires_after_days": 365,
        "thaw_procedure": "You may opt out, but there is rarely a reason to.",
        "notes": (
            "A new IP PIN is generated each year and must be retrieved before "
            "filing; it is available from mid-January through mid-November. The "
            "fastest route is an IRS online account — identity checks there run "
            "through ID.me. Dependents under 18 cannot "
            "use the online method — file Form 15227 (available below an income "
            "threshold) or book an in-person appointment at a Taxpayer Assistance "
            "Center."
        ),
        "citations": {
            "why_it_matters": ["irs-ip-pin"],
            "notes": ["irs-ip-pin", "irs-ip-pin-faq"],
            "freeze_url": ["irs-ip-pin"],
        },
        "action_kind": "claim_first",
        "action_note": (
            "Claiming comes before freezing — sign-up has to verify your "
            "identity, which is simplest before the locks go on. Once the PIN "
            "is yours, a return filed without it is refused; whoever registers "
            "first owns the account."
        ),
        "sort_order": 1,
    },
    {
        "slug": "ssa_account",
        "name": "Social Security online account",
        "category": "gov_control",
        "description": "Your my Social Security account at ssa.gov.",
        "why_it_matters": (
            "Claiming the account stops someone else creating one against your "
            "SSN. Reviewing the earnings record annually reveals phantom "
            "employment, often the first visible sign of SSN misuse."
        ),
        "freeze_url": "https://www.ssa.gov/myaccount/",
        "phone": "",
        "mail_address": "",
        "address_verified": False,
        "source_url": "https://www.ssa.gov/myaccount/",
        "supports_online": True,
        "supports_minor": False,
        "minor_mail_only": True,
        "expires_after_days": 365,
        "thaw_procedure": "Not applicable.",
        "notes": "Check the earnings record once a year for employers you do not recognize.",
        "citations": {"freeze_url": ["ssa-myaccount"]},
        "action_kind": "claim_first",
        "action_note": (
            "Claiming comes before freezing — sign-up has to verify your "
            "identity, which is simplest before the locks go on. An account "
            "that already exists can't be opened again by someone pretending "
            "to be you."
        ),
        "sort_order": 2,
    },
    {
        "slug": "everify_self_lock",
        "name": "E-Verify Self Lock",
        "category": "gov_control",
        "description": "Locks your SSN against use in E-Verify employment checks.",
        "why_it_matters": (
            "Stops someone using your SSN to get hired at employers that run "
            "E-Verify — not every employer does, but a locked SSN fails the "
            "check at the ones that do. Employment fraud otherwise produces "
            "wage records the IRS attributes to you."
        ),
        "freeze_url": "https://www.e-verify.gov/employees/employee-self-services/mye-verify/self-lock",
        "phone": "",
        "mail_address": "",
        "address_verified": False,
        "source_url": "https://www.e-verify.gov/employees/employee-self-services/mye-verify/self-lock",
        "supports_online": True,
        "supports_minor": False,
        "minor_mail_only": True,
        "thaw_procedure": "Unlock yourself before starting a new job.",
        "notes": "Remember to unlock before a legitimate employer runs E-Verify on you.",
        "citations": {"freeze_url": ["everify-self-lock"]},
        "action_kind": "claim_first",
        "action_note": (
            "Claiming comes before freezing — enrolling runs an identity "
            "quiz, and a credit freeze can make it fail. If that happens, "
            "temporarily lifting the freeze and retrying is the usual fix."
        ),
        "sort_order": 3,
    },
    {
        "slug": "usps_informed_delivery",
        "name": "USPS Informed Delivery",
        "category": "gov_control",
        "description": "Daily scan of mail arriving at your address.",
        "why_it_matters": (
            "Claiming the account for your address prevents someone else "
            "enrolling and watching your mail. It also lets you notice a card or "
            "statement you did not expect."
        ),
        "freeze_url": "https://informeddelivery.usps.com/",
        "phone": "",
        "mail_address": "",
        "address_verified": False,
        "source_url": "https://informeddelivery.usps.com/",
        "supports_online": True,
        "supports_minor": False,
        "minor_mail_only": True,
        "thaw_procedure": "Not applicable.",
        "notes": "One account per address, so claim it before someone else does.",
        "citations": {"freeze_url": ["usps-informed-delivery"]},
        "action_kind": "claim_first",
        "action_note": (
            "Claiming comes before freezing — sign-up has to verify your "
            "identity, which is simplest before the locks go on. An address "
            "that's already claimed can't be enrolled by a stranger watching "
            "for your mail."
        ),
        "sort_order": 4,
    },
    # -------------------------------------------------------- other controls
    {
        "slug": "optoutprescreen",
        "name": "Prescreened offer opt-out",
        "category": "other_control",
        "description": "Removes you from prescreened credit and insurance offer lists.",
        "why_it_matters": (
            "Preapproved offers arriving by mail are raw material for identity "
            "theft. Opting out removes the supply."
        ),
        "freeze_url": "https://www.optoutprescreen.com/",
        "phone": "",
        "mail_address": "",
        "address_verified": False,
        "source_url": "https://www.optoutprescreen.com/",
        "supports_online": True,
        "supports_minor": False,
        "minor_mail_only": True,
        "thaw_procedure": "Opt back in at the same site.",
        "notes": "Five-year opt-out online; the permanent opt-out requires a mailed form.",
        "citations": {"freeze_url": ["optoutprescreen"]},
        "sort_order": 90,
    },
    {
        "slug": "carrier_port_lock",
        "name": "Mobile carrier port-out lock",
        "category": "other_control",
        "description": "Number lock and transfer PIN with your mobile carrier.",
        "why_it_matters": (
            "SIM swapping defeats SMS two-factor on banking and email. This is "
            "the single highest-value phone call on the list."
        ),
        "freeze_url": "",
        "phone": "",
        "mail_address": "",
        "address_verified": False,
        "source_url": "",
        "supports_online": True,
        "supports_minor": False,
        "minor_mail_only": True,
        "thaw_procedure": "Disable the lock when legitimately switching carriers.",
        "notes": (
            "Ask your carrier for both a port-out PIN and a number lock — they "
            "are separate settings. Do this for every line on the family plan."
        ),
        "citations": {},
        "sort_order": 91,
    },
    {
        "slug": "data_broker_optout",
        "name": "Data broker opt-outs",
        "category": "other_control",
        "description": "Removal from people-search sites.",
        "why_it_matters": (
            "People-search listings supply the answers to security questions and "
            "make social engineering easy. Listings regenerate, so this needs "
            "re-running a few times a year."
        ),
        "freeze_url": "https://www.privacyrights.org/data-brokers",
        "phone": "",
        "mail_address": "",
        "address_verified": False,
        "source_url": "https://www.privacyrights.org/data-brokers",
        "supports_online": True,
        "supports_minor": False,
        "minor_mail_only": True,
        "thaw_procedure": "Not applicable.",
        "notes": (
            "Doing this by hand takes hours and doesn't stay done — paid "
            "opt-out services exist for exactly this gap. FrostFile has no "
            "relationship with any of them; compare before paying."
        ),
        "citations": {"freeze_url": ["privacyrights-databrokers"]},
        "sort_order": 92,
    },
]


# Reminders created for each person when they are added. Offsets are in days
# from the date the person is created.
REMINDER_TEMPLATES: list[dict[str, Any]] = [
    {
        "kind": "ip_pin",
        "title": "Retrieve this year's IRS IP PIN",
        "detail": (
            "A new IP PIN is generated each year and is available mid-January "
            "through mid-November. Get it before filing."
        ),
        "recurrence": "yearly",
        "offset_days": 30,
    },
    {
        "kind": "ssa_earnings",
        "title": "Review Social Security earnings record",
        "detail": "Look for employers you do not recognize — a sign of SSN misuse.",
        "recurrence": "yearly",
        "offset_days": 60,
        "adults_only": True,
    },
    {
        "kind": "credit_report",
        "title": "Get free credit reports from all three bureaus",
        "detail": (
            "Free at annualcreditreport.com. Save each report in FrostFile so "
            "it can compare it against the last one."
        ),
        "recurrence": "quarterly",
        "offset_days": 7,
        "adults_only": True,
    },
    {
        "kind": "minor_file_check",
        "title": "Check whether a credit file exists for this child",
        "detail": (
            "A child should have no credit file. 'No file found' is the answer "
            "you want. A file that exists is worth chasing — sometimes it's "
            "fraud, sometimes a benign mix-up like an authorized-user account "
            "or a bureau error. The bureau's response will say what's in it."
        ),
        "recurrence": "yearly",
        "offset_days": 14,
        "minors_only": True,
    },
    {
        "kind": "broker_optout",
        "title": "Re-run data broker opt-outs",
        "detail": "People-search listings regenerate. Re-check the major sites.",
        "recurrence": "quarterly",
        "offset_days": 90,
        "adults_only": True,
    },
    {
        "kind": "freeze_audit",
        "title": "Verify all freezes are still in place",
        "detail": "Confirm each freeze rather than assuming. Update statuses here.",
        "recurrence": "yearly",
        "offset_days": 180,
    },
]


# One plain phrase per entry answering "what does doing this actually get me?"
# Shown under agency names in the grid and to-do lists, because a wall of
# company names means nothing to someone who has never heard of NCTUE.
PROTECTS: dict[str, str] = {
    "equifax": "Blocks new loans & credit cards",
    "experian": "Blocks new loans & credit cards",
    "transunion": "Blocks new loans & credit cards",
    "innovis": "Blocks new loans & credit cards",
    "lexisnexis": "Blocks identity checks by lenders & insurers",
    "sagestream": "Blocks alternative credit checks",
    "clue": "Insurance claim history (read-only)",
    "chexsystems": "Blocks new bank accounts",
    "early_warning": "Bank account screening (no action offered)",
    "telecheck": "Blocks check fraud at stores",
    "certegy": "Blocks check fraud at stores",
    "nctue": "Blocks new phone, cable & utility accounts",
    "clarity": "Blocks payday & quick-cash loans",
    "teletrack": "Blocks payday & quick-cash loans",
    "datax": "Blocks payday & quick-cash loans",
    "corelogic": "Blocks apartment applications in your name",
    "realpage": "Blocks apartment applications in your name",
    "work_number": "Limits who sees your salary & job history",
    "irs_ip_pin": "Blocks fake tax refunds in your name",
    "ssa_account": "Guards your Social Security record",
    "everify_self_lock": "Blocks E-Verify hiring checks as you",
    "usps_informed_delivery": "Guards your incoming mail",
    "optoutprescreen": "Stops pre-approved card offers in your mailbox",
    "carrier_port_lock": "Stops phone-number theft (SIM swap)",
    "data_broker_optout": "Gets your info off people-search sites",
}


# Editorial ranking of how much protection each step buys, used to help people
# order the work — the same judgment already baked into sort_order, made
# visible. 3 = blocks the main ways a stolen SSN gets monetized, 2 = closes a
# real side door, 1 = worthwhile hygiene. 0 = not ranked (FYI/covered rows).
IMPACT: dict[str, int] = {
    "equifax": 3,
    "experian": 3,
    "transunion": 3,
    "innovis": 2,
    "lexisnexis": 2,
    "chexsystems": 2,
    "telecheck": 1,
    "certegy": 1,
    "nctue": 2,
    "clarity": 2,
    "teletrack": 2,
    "datax": 2,
    "corelogic": 1,
    "realpage": 1,
    "work_number": 2,
    "irs_ip_pin": 3,
    "ssa_account": 2,
    "everify_self_lock": 2,
    "usps_informed_delivery": 1,
    "optoutprescreen": 1,
    "carrier_port_lock": 3,
    "data_broker_optout": 1,
}

IMPACT_LABELS = {3: "High impact", 2: "Worth doing", 1: "Nice to have"}


def seed_agencies(conn: sqlite3.Connection) -> int:
    """Insert or refresh the built-in directory.

    Built-in rows are updated in place on upgrade so corrected addresses reach
    existing installs. User-added agencies (is_builtin = 0) are never touched,
    and neither is is_active, so an agency you hid stays hidden.
    """
    inserted = 0
    for entry in AGENCIES:
        row = conn.execute(
            "SELECT id, is_builtin FROM agencies WHERE slug = ?", (entry["slug"],)
        ).fetchone()

        citations = dict(entry.get("citations", {}))
        if entry.get("minor_requirements"):
            citations.setdefault("minor_requirements", [])
        payload = {
            "requirements": entry.get("minor_requirements", {}),
            "citations": citations,
        }

        values = {
            "name": entry["name"],
            "category": entry["category"],
            "description": entry.get("description", ""),
            "why_it_matters": entry.get("why_it_matters", ""),
            "freeze_url": entry.get("freeze_url", ""),
            "phone": entry.get("phone", ""),
            "mail_address": entry.get("mail_address", ""),
            "address_verified": int(entry.get("address_verified", False)),
            "source_url": entry.get("source_url", ""),
            "citations_json": json.dumps(payload),
            "supports_online": int(entry.get("supports_online", True)),
            "supports_minor": int(entry.get("supports_minor", False)),
            "minor_mail_only": int(entry.get("minor_mail_only", True)),
            "expires_after_days": entry.get("expires_after_days"),
            "thaw_procedure": entry.get("thaw_procedure", ""),
            "notes": entry.get("notes", ""),
            "action_kind": entry.get("action_kind", "act"),
            "action_note": entry.get("action_note", ""),
            "protects": PROTECTS.get(entry["slug"], ""),
            "impact": IMPACT.get(entry["slug"], 0),
            "sort_order": entry.get("sort_order", 0),
        }
        if row is None:
            columns = ", ".join(["slug", *values, "is_builtin"])
            placeholders = ", ".join(["?"] * (len(values) + 2))
            conn.execute(
                f"INSERT INTO agencies ({columns}) VALUES ({placeholders})",
                (entry["slug"], *values.values(), 1),
            )
            inserted += 1
        elif row["is_builtin"]:
            assignments = ", ".join(f"{c} = ?" for c in values)
            conn.execute(
                f"UPDATE agencies SET {assignments} WHERE id = ?",
                (*values.values(), row["id"]),
            )
    conn.commit()
    return inserted
