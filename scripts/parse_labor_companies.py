"""
parse_labor_companies.py
========================
Standalone script to extract company entries from USA_Labor_Companies.pdf
and write to runtime/company_directory_raw.json.

Usage:
    python3 scripts/parse_labor_companies.py

Output:
    runtime/company_directory_raw.json  — array of parsed company objects

Strategy:
  The PDF is a multi-column spreadsheet that pdfplumber partially mangles.
  Legible entries pack all fields on one line, e.g.:
      InCrowdProductions505-270-0594http://www.incrowdstudio.comWILLNOTPROVIDE
  Section headers are standalone "City,ST" or "city" lines.
  We walk the lines, track current city/state from headers, and extract
  fields from each clean data line.
"""

import json
import re
import time
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    raise SystemExit("pdfplumber is required. Install with: pip install pdfplumber")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PDF_PATH = PROJECT_ROOT / "uploads" / "USA_Labor_Companies.pdf"
OUTPUT_PATH = PROJECT_ROOT / "runtime" / "company_directory_raw.json"

# ---------------------------------------------------------------------------
# Status keyword mapping
# ---------------------------------------------------------------------------
STATUS_KEYWORDS = [
    "WILLNOTPROVIDE", "NATIONALPROVIDER", "STAFFINGAGENCY", "NOANSWER",
    "NORESPONSE", "NORESPSONSE", "RECEIVED", "EMAILED", "PARTIALLYRECEIVED",
    "UNION",
]
STATUS_DISPLAY = {
    "WILLNOTPROVIDE":    "Will Not Provide",
    "NATIONALPROVIDER":  "National Provider",
    "STAFFINGAGENCY":    "Staffing Agency",
    "NOANSWER":          "No Answer",
    "NORESPONSE":        "No Response",
    "NORESPSONSE":       "No Response",
    "RECEIVED":          "Received",
    "EMAILED":           "Emailed",
    "PARTIALLYRECEIVED": "Partially Received",
    "UNION":             "Union",
}

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------
PHONE_RE = re.compile(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}')
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,6}')
URL_RE   = re.compile(r'https?://[^\s]+|www\.[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,6}[/\w\-\.]*')
PAY_RE   = re.compile(r'\$(\d+\.\d{2})')
HRS_RE   = re.compile(r'(\d+)\s*[Hh]rs?')

US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN",
    "IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV",
    "NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN",
    "TX","UT","VT","VA","WA","WV","WI","WY","DC",
}

# Standalone "City,ST" header (no extra text)
CITY_HDR_EXACT = re.compile(r'^([A-Za-z][A-Za-z\s\.\-]+),([A-Z]{2})$')
# "City,ST " embedded at start of a line (followed by data)
CITY_HDR_PREFIX = re.compile(r'^([A-Za-z][A-Za-z\s\.\-]+),([A-Z]{2})\s+\d')


def is_garbled(line: str) -> bool:
    """Return True if line has too many isolated single-letter tokens (scrambled columns)."""
    tokens = line.split()
    if len(tokens) < 6:
        return False
    single_alpha = sum(1 for t in tokens if len(t) == 1 and t.isalpha())
    return single_alpha / len(tokens) > 0.22


def detect_status(text: str) -> str:
    """Return human-readable status label or empty string."""
    upper_nospace = re.sub(r'\s+', '', text.upper())
    for kw in STATUS_KEYWORDS:
        if kw in upper_nospace:
            return STATUS_DISPLAY[kw]
    return ""


def is_garbled_name(name: str) -> bool:
    """
    Heuristic to detect garbled company names (interlaced chars from multiple columns).
    Garbled names have high digit-letter transition rates or many short CamelCase runs.
    """
    if not name:
        return False
    # Count digit<->letter transitions
    transitions = sum(
        1 for i in range(len(name) - 1)
        if (name[i].isalpha() and name[i+1].isdigit()) or
           (name[i].isdigit() and name[i+1].isalpha())
    )
    if len(name) > 0 and transitions / len(name) > 0.10:
        return True
    # Many short CamelCase bursts: UpperLowerUpper within 4 chars (interlaced columns)
    weird_case = len(re.findall(r'[A-Z][a-z]{1,3}[A-Z]', name))
    # A real long name may have 1-2 such patterns (e.g. "AboveTheMark"), but garbled
    # text from two interleaved columns will have many more
    if len(name) > 30 and weird_case >= 2:
        return True
    if len(name) > 20 and weird_case >= 3:
        return True
    if weird_case > 4:
        return True
    # Slash followed immediately by uppercase then digits (garble artifact e.g. "/A5V")
    if re.search(r'/[A-Z]\d', name):
        return True
    # Doubled uppercase letters that appear as interlacing artifacts (e.g. "PPelr", "MMia", "AAzv")
    doubled_caps = len(re.findall(r'[A-Z]{2}[a-z]', name))
    if doubled_caps >= 2:
        return True
    return False


def clean_company_name(raw: str) -> str:
    """Normalise a raw company name extracted from the packed line."""
    # Strip leading date prefix e.g. "12/6/21"
    raw = re.sub(r'^\d{1,2}/\d{1,2}/\d{2,4}\s*', '', raw).strip()
    # Strip trailing slash or contact name separator
    raw = raw.rstrip('/ ').strip()
    return raw


def fix_city_name(raw: str) -> str:
    """Add spaces at camelCase boundaries (e.g. 'SanDiego' -> 'San Diego')."""
    # Insert space before an uppercase letter that follows a lowercase letter
    spaced = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', raw)
    return spaced.strip().title()


def parse_data_line(
    line: str,
    city: str,
    state: str,
    parsed_at: int,
) -> dict | None:
    """
    Extract a company entry from a single densely-packed line.
    Returns None if extraction fails or line appears garbled.
    """
    if is_garbled(line):
        return None

    # Check for city header at start of line (e.g. "Albuquerque,NM 12/6/21...")
    m_prefix = CITY_HDR_PREFIX.match(line)
    if m_prefix and m_prefix.group(2) in US_STATES:
        # Strip the city header prefix, update city/state for this entry
        city  = fix_city_name(m_prefix.group(1))
        state = m_prefix.group(2)
        line  = line[m_prefix.end():].strip()

    # Find earliest anchor: phone or email
    phone_m = PHONE_RE.search(line)
    email_m = EMAIL_RE.search(line)

    anchors = []
    if phone_m:
        anchors.append(phone_m.start())
    if email_m:
        anchors.append(email_m.start())

    if not anchors:
        return None

    name_end = min(anchors)
    company_raw = line[:name_end]
    company_name = clean_company_name(company_raw)

    if len(company_name) < 3:
        return None

    if is_garbled_name(company_name):
        return None

    # Reject company names that are clearly payload data or too short
    if len(company_name) < 4:
        return None

    # Names that are suspiciously long are likely garble (real names < 70 chars)
    if len(company_name) > 65:
        return None

    # Names that start with data fields (e.g. "VIDER550%" "Min4HR" "askfor")
    if re.match(r'^(VIDER|Min\d|askfor|Sundays|Holidays|Fed\.|After\d)', company_name):
        return None
    # Names with embedded pay/data patterns
    if re.search(r'\d+%|\$\d+\.\d{2}|Hrs?\b|RECEIVED|WILLNOT', company_name):
        return None
    # Names with embedded date prefix after company start (e.g. "Rosemont12/16/21AboveTheMark")
    # A date fragment "/21" or "/22" or "/20" mid-name is a garble signal
    if re.search(r'/2[012][\w]', company_name):
        return None
    # Names that contain a city,state pattern inside (garble artifact)
    if re.search(r'[A-Z][a-z]+,MD|,TX|,FL|,NY|,IL', company_name):
        return None
    # Very short artifacts or known garble tokens
    if company_name in {'ctions', 'CAVL', '12/6', '12/7', '12/8', 'AB', 'In'}:
        return None
    # Names with double-hyphen sequences (garble from phone number interlacing)
    if '--' in company_name:
        return None
    # Names ending with a trailing hyphen then digits (phone leaked into name)
    if re.search(r'\d{3,}-?$', company_name):
        return None

    # Extract remaining contact fields from the part after the company name
    rest = line[name_end:]

    phone = (PHONE_RE.search(rest) or type('', (), {'group': lambda self, n: ''})()).group(0)
    if hasattr(phone, 'group'):
        phone = ""
    phone_match = PHONE_RE.search(rest)
    phone = phone_match.group(0).strip() if phone_match else ""

    email_match = EMAIL_RE.search(rest)
    email = email_match.group(0).strip() if email_match else ""

    url_match = URL_RE.search(rest)
    website = url_match.group(0).strip() if url_match else ""
    if website and not website.startswith("http"):
        website = "https://" + website

    status = detect_status(rest)

    pay_matches = PAY_RE.findall(rest)
    st_pay = f"${pay_matches[0]}" if pay_matches else ""

    hrs_matches = HRS_RE.findall(rest)
    load_in_min  = int(hrs_matches[0]) * 60 if len(hrs_matches) > 0 else 0
    load_out_min = int(hrs_matches[1]) * 60 if len(hrs_matches) > 1 else 0

    return {
        "company_name":   company_name,
        "city":           city,
        "state":          state,
        "phone":          phone,
        "email":          email,
        "website":        website,
        "status":         status,
        "st_pay":         st_pay,
        "load_in_min":    load_in_min,
        "load_out_min":   load_out_min,
        "do_not_contact": False,
        "do_not_use":     False,
        "internal_notes": "",
        "source_file":    "USA_Labor_Companies.pdf",
        "parsed_at":      parsed_at,
    }


def parse_pdf(pdf_path: Path) -> list[dict]:
    """Walk all pages, track city/state headers, parse clean company lines."""
    with pdfplumber.open(str(pdf_path)) as pdf:
        all_lines: list[str] = []
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                stripped = line.strip()
                if stripped:
                    all_lines.append(stripped)

    # City names that are PDF artifacts (garbled/truncated) — skip their entries
    INVALID_CITIES: set[str] = {"Unknown", "Ion", "Ab"}

    parsed_at = int(time.time())
    entries: list[dict] = []
    seen_keys: set[tuple] = set()

    current_city  = "Unknown"
    current_state = ""

    for line in all_lines:
        # --- City header detection -----------------------------------------
        # Standalone exact match: "Cleveland,OH"
        m_exact = CITY_HDR_EXACT.match(line)
        if m_exact and m_exact.group(2) in US_STATES:
            current_city  = fix_city_name(m_exact.group(1))
            current_state = m_exact.group(2)
            continue

        # Single lowercase city word — skip, ambiguous (could be a PDF artifact)
        # The section label "miami" on the cover page causes false attribution.
        # All real section headers appear as "City,ST" (already handled above).
        if re.match(r'^[a-z]{3,20}$', line):
            continue

        # --- Skip obviously useless lines -----------------------------------
        if len(line) < 15:
            continue
        if re.match(r'^[A-Z\s\d:/\-\.]+$', line) and not EMAIL_RE.search(line):
            # All-caps header rows (table header, instructions, etc.)
            continue

        # --- Must have contact info to parse --------------------------------
        has_phone = bool(PHONE_RE.search(line))
        has_email = bool(EMAIL_RE.search(line))
        if not has_phone and not has_email:
            continue

        entry = parse_data_line(line, current_city, current_state, parsed_at)
        if entry is None:
            continue

        # Skip entries with artifact city names
        if entry["city"] in INVALID_CITIES:
            continue

        # Dedup
        key = (entry["company_name"].lower(), entry["city"].lower())
        if key in seen_keys:
            continue
        seen_keys.add(key)

        entries.append(entry)

    return entries


def main():
    if not PDF_PATH.exists():
        raise SystemExit(f"PDF not found at {PDF_PATH}")

    print(f"Parsing: {PDF_PATH}")
    entries = parse_pdf(PDF_PATH)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    print(f"\nParsed {len(entries)} entries -> {OUTPUT_PATH}\n")

    print("--- 10 Sample Rows ---")
    for i, e in enumerate(entries[:10], 1):
        print(
            f"{i:>3}. {e['company_name'][:36]:<36} | "
            f"{e['city'][:18]}, {e['state']:<2} | "
            f"{e['phone']:<16} | "
            f"{e['status']:<20} | "
            f"{e['st_pay']}"
        )


if __name__ == "__main__":
    main()
