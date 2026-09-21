"""Build cv.md from cv_template.md, pulling the publication list from ORCID.

Journal articles and preprints are fetched from ORCID, enriched with Crossref
metadata, and a preprint is dropped from the preprint section once its
peer-reviewed version shows up among the journal articles.
"""

import html
import re
import sys
import time
from datetime import date

import requests

# USER CONFIG: Update these with your actual info
NAME = "Sheng-Kai Hsu"
EMAIL = "sh2246@cornell.edu"
TITLE = "Postdoc"
AFFILIATION = "Institute for Genomic Diversity, Cornell University"
ORCID_ID = "0000-0002-6942-7163"
# The `user=` value in your Google Scholar profile URL. Leave empty to omit the link.
SCHOLAR_ID = "u_wofDgAAAAJ"

# For bolding your name
YOUR_FAMILY_NAME = "Hsu"
YOUR_INITIALS = "S.-K."

# List every author up to this many; beyond it, truncate with "et al."
MAX_AUTHORS = 20
AUTHORS_WHEN_TRUNCATED = 10

REQUEST_TIMEOUT = 30
# Crossref asks API users to identify themselves; this gets us the polite pool.
USER_AGENT = f"cv-builder (https://orcid.org/{ORCID_ID}; mailto:{EMAIL})"
ORCID_HEADERS = {"Accept": "application/json", "User-Agent": USER_AGENT}

PREPRINT_DOI_PREFIXES = ("10.1101/", "10.64898/")


def get_json(url, headers=None, attempts=3):
    """GET a JSON document, retrying transient failures. None on failure."""
    for attempt in range(attempts):
        try:
            response = requests.get(
                url, headers=headers or {"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            if attempt == attempts - 1:
                print(f"⚠️ Giving up on {url}: {exc}")
                return None
            time.sleep(2**attempt)
    return None


# === TEXT CLEANUP ===

TAG_RE = re.compile(r"<[^>]+>")
ITALIC_RE = re.compile(r"<(i|em)\b[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL)


def clean_text(text):
    """Turn Crossref's JATS-flavoured markup into single-line markdown."""
    if not text:
        return ""
    text = ITALIC_RE.sub(
        # Crossref sometimes italicises bare punctuation ("<i>-</i>"); markdown
        # emphasis around it renders as literal asterisks, so drop it.
        lambda m: f"*{m.group(2).strip()}*" if re.search(r"\w", m.group(2)) else m.group(2),
        text,
    )
    text = TAG_RE.sub("", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    # Removing tags can leave " :" or " ," behind.
    return re.sub(r"\s+([,.;:!?)\]])", r"\1", text).strip()


def normalize_title(title):
    """Comparison key: lowercase alphanumerics only."""
    return re.sub(r"[^a-z0-9]+", "", clean_text(title).lower())


def doi_base(doi):
    """Strip a trailing version suffix (10.7554/eLife.102321.2 -> ...102321)."""
    return re.sub(r"\.\d{1,2}$", "", (doi or "").lower())


def doi_version(doi):
    match = re.search(r"\.(\d{1,2})$", doi or "")
    return int(match.group(1)) if match else 0


# === AUTHOR FORMATTING ===


def extract_initials(given):
    if not given or not isinstance(given, str):
        return ""

    given = re.sub(r"[‐‑‒–—―]", "-", given)
    initials = []
    for part in given.strip().split():
        if "-" in part:
            initials.append("-".join(f"{p[0]}." for p in part.split("-") if p))
        else:
            initials.append(f"{part[0]}.")
    return "".join(initials)


def is_you(family, initials):
    target = YOUR_INITIALS.replace(".", "").replace(" ", "").lower()
    actual = initials.replace(".", "").replace(" ", "").lower()
    return family.lower() == YOUR_FAMILY_NAME.lower() and target in actual


def format_author(family, given):
    if not family:
        return "Unknown Author"
    initials = extract_initials(given)
    name = f"{family}, {initials}" if initials else family
    return f"**{name}**" if is_you(family, initials) else name


def join_authors(authors):
    """Join formatted author names, eliding the middle of very long lists.

    Truncation follows APA: the first few authors, an ellipsis, then the final
    author — never "et al.", which would wrongly imply further authors after
    the last one. Your own name is spliced back in (between ellipses) when it
    falls in the elided middle, so senior/first authorship stays visible.
    """
    if not authors:
        return "Unknown Author"
    if len(authors) == 1:
        return authors[0]
    if len(authors) <= MAX_AUTHORS:
        return ", ".join(authors[:-1]) + ", & " + authors[-1]

    shown = authors[:AUTHORS_WHEN_TRUNCATED]
    middle = ""
    you = next((i for i, a in enumerate(authors) if a.startswith("**")), None)
    if you is not None and AUTHORS_WHEN_TRUNCATED <= you < len(authors) - 1:
        middle = f", …, {authors[you]}"
    return ", ".join(shown) + middle + ", …, & " + authors[-1]


# === ORCID / CROSSREF ===


def orcid_works(orcid_id):
    """Yield one record per distinct DOI in the ORCID profile."""
    data = get_json(f"https://pub.orcid.org/v3.0/{orcid_id}/works", headers=ORCID_HEADERS)
    if not data:
        sys.exit("❌ Could not read the ORCID works list; refusing to rewrite cv.md.")

    seen = set()
    for group_index, group in enumerate(data.get("group", [])):
        for summary in group.get("work-summary", []):
            work_type = summary.get("type", "").lower()
            if work_type not in ("journal-article", "preprint"):
                continue

            doi = None
            for eid in summary.get("external-ids", {}).get("external-id", []):
                if eid.get("external-id-type") == "doi":
                    doi = (eid.get("external-id-value") or "").strip()
                    break
            if not doi or doi.lower() in seen:
                continue
            seen.add(doi.lower())

            yield {
                "doi": doi,
                "key": doi.lower(),
                "type": work_type,
                "group": group_index,
                "put_code": summary.get("put-code"),
                "title": summary.get("title", {}).get("title", {}).get("value", "Untitled"),
                "year": summary.get("publication-date", {}).get("year", {}).get("value"),
            }


def orcid_authors(orcid_id, put_code):
    data = get_json(
        f"https://pub.orcid.org/v3.0/{orcid_id}/work/{put_code}", headers=ORCID_HEADERS
    )
    if not data:
        return []

    authors = []
    for contributor in data.get("contributors", {}).get("contributor", []):
        name = (contributor.get("credit-name", {}) or {}).get("value", "").strip()
        if not name:
            continue
        parts = name.split()
        family, given = (parts[-1], " ".join(parts[:-1])) if len(parts) >= 2 else (name, "")
        authors.append(format_author(family, given))
    return authors


def first(values):
    """First element of a Crossref list field, tolerating missing/empty lists."""
    return values[0] if isinstance(values, list) and values else ""


def default_preprint_server(doi):
    return "bioRxiv" if doi.startswith(PREPRINT_DOI_PREFIXES) else "Preprint"


def crossref_metadata(doi):
    data = get_json(f"https://api.crossref.org/works/{doi}")
    return (data or {}).get("message")


def biorxiv_published_doi(doi):
    """Ask the bioRxiv/medRxiv API whether a preprint has been published."""
    if not doi.startswith(PREPRINT_DOI_PREFIXES):
        return None
    for server in ("biorxiv", "medrxiv"):
        data = get_json(f"https://api.biorxiv.org/details/{server}/{doi}")
        for record in (data or {}).get("collection", []):
            published = (record.get("published") or "").strip().lower()
            if published and published != "na":
                return published
    return None


def crossref_related_dois(metadata, relations):
    dois = set()
    for relation in relations:
        for item in (metadata or {}).get("relation", {}).get(relation, []):
            if (item.get("id-type") or "").lower() == "doi" and item.get("id"):
                dois.add(item["id"].strip().lower())
    return dois


# === ENTRY BUILDING ===


def build_entry(work, metadata, orcid_id):
    """Return (sort_key, citation) for one publication."""
    title = clean_text(work["title"])
    year = work["year"] or "n.d."
    sort_date = (int(year) if str(year).isdigit() else 0, 0, 0)
    doi_url = f"https://doi.org/{work['doi']}"

    if metadata:
        authors = [
            format_author(a.get("family", ""), a.get("given", ""))
            for a in metadata.get("author", [])
        ]
        date_parts = first(metadata.get("issued", {}).get("date-parts")) or []
        if date_parts and date_parts[0]:
            year = date_parts[0]
            sort_date = tuple((list(date_parts) + [0, 0])[:3])
        title = clean_text(first(metadata.get("title"))) or title
        container = clean_text(first(metadata.get("container-title")))
        if not container:
            # Crossref preprints ("posted-content") carry the server here instead.
            institutions = [i.get("name", "") for i in metadata.get("institution") or []]
            container = clean_text(first(institutions) or metadata.get("group-title", ""))
        if not container and work["type"] == "preprint":
            container = default_preprint_server(work["doi"])
        volume = metadata.get("volume", "")
        issue = metadata.get("issue", "")
        pages = metadata.get("page", "")
    else:
        authors = orcid_authors(orcid_id, work["put_code"])
        container = default_preprint_server(work["doi"]) if work["type"] == "preprint" else ""
        volume = issue = pages = ""

    if not authors:
        authors = orcid_authors(orcid_id, work["put_code"])
    if not authors:
        print(f"⚠️ No author information for {work['doi']} ({title})")

    citation = f"{join_authors(authors)} ({year}). **{title}**."
    if container:
        citation += f" *{container}*"
        if volume:
            citation += f", *{volume}*"
            if issue:
                citation += f"({issue})"
        if pages:
            citation += f", {pages}"
        citation += "."
    citation += f" {doi_url}"
    return sort_date, citation


# === PREPRINT / PUBLISHED RECONCILIATION ===


def drop_published_preprints(journals, preprints):
    """Remove preprints whose peer-reviewed version is already in the CV.

    A preprint counts as published when any of these point at a journal article
    we already list: the Crossref preprint/article relation, the bioRxiv API's
    `published` field, ORCID's own grouping, a shared versioned-DOI stem, or an
    identical title. Older versions of the same preprint are collapsed too.
    """
    journal_dois = {j["key"] for j in journals}
    journal_bases = {doi_base(j["key"]) for j in journals}
    journal_titles = {normalize_title(j["title"]): j["doi"] for j in journals}
    journal_groups = {j["group"] for j in journals}
    journal_preprint_links = set()
    for journal in journals:
        journal_preprint_links |= crossref_related_dois(
            journal["metadata"], ("has-preprint", "has-version", "is-version-of")
        )

    # Collapse multiple deposited versions of the same preprint (eLife .1/.2/...).
    newest_by_base = {}
    for preprint in preprints:
        base = doi_base(preprint["key"])
        current = newest_by_base.get(base)
        if current is None or doi_version(preprint["key"]) > doi_version(current["key"]):
            newest_by_base[base] = preprint

    kept = []
    for preprint in preprints:
        doi = preprint["key"]
        title = clean_text(preprint["title"])

        if newest_by_base[doi_base(doi)]["key"] != doi:
            print(f"↩️  Superseded by a newer version of the same preprint: {title}")
            continue

        reason = None
        if doi_base(doi) in journal_bases and doi not in journal_dois:
            reason = "same versioned DOI as a listed article"
        elif doi in journal_preprint_links:
            reason = "Crossref links it to a listed article"
        elif preprint["group"] in journal_groups:
            reason = "ORCID groups it with a listed article"
        elif normalize_title(title) in journal_titles:
            reason = f"same title as {journal_titles[normalize_title(title)]}"
        else:
            published = crossref_related_dois(
                preprint["metadata"], ("is-preprint-of", "is-manuscript-of", "is-version-of")
            )
            published |= {biorxiv_published_doi(doi)} - {None}
            match = published & journal_dois
            if match:
                reason = f"published as {sorted(match)[0]}"
            elif published:
                print(
                    f"ℹ️  {title} looks published as {sorted(published)[0]}, "
                    "but that article is not in your ORCID record yet — keeping the preprint."
                )

        if reason:
            print(f"✅ Dropping published preprint ({reason}): {title}")
            continue
        kept.append(preprint)
    return kept


# === OUTPUT ===


def format_section(heading, entries):
    if not entries:
        return ""
    ordered = sorted(entries, key=lambda e: e["sort_date"], reverse=True)
    body = "\n\n".join(f"{i + 1}. {e['citation']}" for i, e in enumerate(ordered))
    return f"## {heading}\n\n{body}\n"


def fetch_publications(orcid_id):
    works = list(orcid_works(orcid_id))
    for work in works:
        work["metadata"] = crossref_metadata(work["doi"])

    journals = [w for w in works if w["type"] == "journal-article"]
    preprints = [w for w in works if w["type"] == "preprint"]
    preprints = drop_published_preprints(journals, preprints)

    for work in journals + preprints:
        work["sort_date"], work["citation"] = build_entry(work, work["metadata"], orcid_id)

    sections = [
        format_section("Peer-reviewed Publications", journals),
        format_section("Preprints", preprints),
    ]
    return "\n".join(s for s in sections if s), len(journals) + len(preprints)


def check_not_truncated(new_count, path="cv.md"):
    """Guard against a half-answered API silently gutting the publication list."""
    try:
        with open(path) as f:
            previous = len(re.findall(r"https://doi\.org/", f.read()))
    except FileNotFoundError:
        return
    if new_count < previous * 0.8:
        sys.exit(
            f"❌ Only {new_count} publications resolved but {path} has {previous}; "
            "refusing to overwrite. Re-run once ORCID/Crossref are healthy."
        )


def main():
    publications, count = fetch_publications(ORCID_ID)
    if count == 0:
        sys.exit("❌ No publications resolved; refusing to rewrite cv.md.")
    check_not_truncated(count)

    with open("cv_template.md") as f:
        template = f.read()

    scholar = (
        f"  \n**Google Scholar:** "
        f"[{NAME}](https://scholar.google.com/citations?user={SCHOLAR_ID})"
        if SCHOLAR_ID
        else ""
    )
    cv_filled = (
        template.replace("{{NAME}}", NAME)
        .replace("{{EMAIL}}", EMAIL)
        .replace("{{TITLE}}", TITLE)
        .replace("{{AFFILIATION}}", AFFILIATION)
        .replace("{{ORCID}}", ORCID_ID)
        .replace("{{SCHOLAR}}", scholar)
        .replace("{{PUBLICATIONS}}", publications)
        .replace("{{DATE}}", str(date.today()))
    )

    with open("cv.md", "w") as f:
        f.write(cv_filled)
    print(f"Wrote cv.md with {count} publications.")


if __name__ == "__main__":
    main()
