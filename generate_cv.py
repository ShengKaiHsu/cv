import requests
import re
from datetime import date

# USER CONFIG: Update these with your actual info
NAME = "Sheng-Kai Hsu"
EMAIL = "sh2246@cornell.edu"
AFFILIATION = "Postdoc, Institute for Genomic Diversity, Cornell University"
ORCID_ID = "0000-0002-6942-7163"  # replace with yours

# For bolding your name
YOUR_FAMILY_NAME = "Hsu"
YOUR_INITIALS = "S.-K."  # Set to "W" or "W.-Y" depending on how it's recorded

# === MAIN FUNCTIONS ===

def extract_initials(given):
    if not given or not isinstance(given, str):
        return ""
    parts = re.split(r"[\s\-]+", given.strip())
    initials = ".".join(p[0] for p in parts if p and p[0].isalpha())
    return initials + "." if initials else ""

def format_author(family, given, bold_if_matches=False):
    initials = extract_initials(given)
    if not family:
        return "Unknown Author"
    name = f"{family}, {initials}"
    if bold_if_matches:
        target = YOUR_INITIALS.replace(".", "").lower()
        actual = initials.replace(".", "").lower()
        if family.lower() == YOUR_FAMILY_NAME.lower() and target in actual:
            return f"**{name}**"
    return name

def fetch_publications(orcid_id):
    headers = {"Accept": "application/json"}
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/works"
    response = requests.get(url, headers=headers)
    works = response.json()["group"]

    journal_entries = []
    preprint_entries = []
    seen_dois = set()

    for group in works:
        for summary in group.get("work-summary", []):
            work_type = summary.get("type", "").lower()
            if work_type not in ["journal-article", "preprint"]:
                continue

            title = summary.get("title", {}).get("title", {}).get("value", "Untitled")
            year = summary.get("publication-date", {}).get("year", {}).get("value", "n.d.")
            put_code = summary.get("put-code")

            doi = None
            for eid in summary.get("external-ids", {}).get("external-id", []):
                if eid.get("external-id-type") == "doi":
                    doi = eid.get("external-id-value")
                    break

            if not doi or doi in seen_dois:
                continue
            seen_dois.add(doi)

            entry_list = journal_entries if work_type == "journal-article" else preprint_entries

            # === Try Crossref ===
            try:
                r = requests.get(f"https://api.crossref.org/works/{doi}")
                if r.status_code != 200:
                    raise ValueError("Not in Crossref")
                metadata = r.json()["message"]

                authors = metadata.get("author", [])
                author_strs = []
                for a in authors:
                    given = a.get("given", "")
                    family = a.get("family", "")
                    if not given or not family:
                        print(f"⚠️ Missing author info in Crossref: {title}, DOI: {doi}")
                    name_str = format_author(family, given, bold_if_matches=True)
                    author_strs.append(name_str)

                display_authors = author_strs[:10] + ["*et al.*"] if len(author_strs) > 10 else author_strs
                author_text = ", ".join(display_authors[:-1]) + ", & " + display_authors[-1] if len(display_authors) > 1 else display_authors[0]

                pub_year = metadata.get("issued", {}).get("date-parts", [[year]])[0][0]
                title = metadata.get("title", [""])[0]
                journal = metadata.get("container-title", [""])[0]
                volume = metadata.get("volume", "")
                issue = metadata.get("issue", "")
                pages = metadata.get("page", "")
                doi_url = f"https://doi.org/{doi}"

                citation = f"{author_text} ({pub_year}). *{title}*. *{journal}*"
                if volume:
                    citation += f", *{volume}*"
                    if issue:
                        citation += f"({issue})"
                if pages:
                    citation += f", {pages}"
                citation += f". {doi_url}"

                entry_list.append((pub_year, citation))
                continue
            except Exception:
                pass

            # === Try DataCite ===
            try:
                r = requests.get(f"https://api.datacite.org/dois/{doi}")
                if r.status_code != 200:
                    raise ValueError("Not in DataCite")
                dc = r.json()["data"]["attributes"]

                title = dc.get("title", "Untitled")
                creators = dc.get("creators", [])
                pub_year = dc.get("publicationYear", year)
                journal = dc.get("container-title", "Preprint") or "Preprint"

                author_strs = []
                for c in creators:
                    given = c.get("givenName", "")
                    family = c.get("familyName", "")
                    if not given or not family:
                        print(f"⚠️ Missing author info in DataCite: {title}, DOI: {doi}")
                    name_str = format_author(family, given, bold_if_matches=True)
                    author_strs.append(name_str)

                display_authors = author_strs[:10] + ["*et al.*"] if len(author_strs) > 10 else author_strs
                author_text = ", ".join(display_authors[:-1]) + ", & " + display_authors[-1] if len(display_authors) > 1 else display_authors[0]

                citation = f"{author_text} ({pub_year}). *{title}*. *{journal}*. https://doi.org/{doi}"
                entry_list.append((pub_year, citation))
                continue
            except Exception:
                pass

            # === Fallback ORCID contributor list ===
            try:
                work_url = f"https://pub.orcid.org/v3.0/{orcid_id}/work/{put_code}"
                r = requests.get(work_url, headers=headers)
                if r.status_code != 200:
                    raise ValueError("put-code not found")

                work_data = r.json()
                contribs = work_data.get("contributors", {}).get("contributor", [])

                author_strs = []
                for c in contribs:
                    name = c.get("credit-name", {}).get("value", "")
                    parts = name.strip().split()
                    if len(parts) >= 2:
                        given = " ".join(parts[:-1])
                        family = parts[-1]
                    else:
                        given = ""
                        family = name
                    if not given or not family:
                        print(f"⚠️ Missing author info in ORCID fallback: {title}, DOI: {doi}")
                    name_str = format_author(family.strip(), given.strip(), bold_if_matches=True)
                    author_strs.append(name_str)

                if not author_strs:
                    author_strs = ["Unknown Author"]

                display_authors = author_strs[:10] + ["*et al.*"] if len(author_strs) > 10 else author_strs
                author_text = ", ".join(display_authors[:-1]) + ", & " + display_authors[-1] if len(display_authors) > 1 else author_strs[0]

                citation = f"{author_text} ({year}). *{title}*. bioRxiv. https://doi.org/{doi}"
                entry_list.append((year, citation))

            except Exception as e:
                print(f"Could not retrieve full ORCID work {put_code}: {e}")

    def format_section(title, entries):
        if not entries:
            return ""
        sorted_entries = sorted(entries, key=lambda x: str(x[0]), reverse=True)
        formatted = [f"{i+1}. {entry}" for i, (_, entry) in enumerate(sorted_entries)]
        return f"## {title}\n\n" + "\n\n".join(formatted) + "\n"

    output = []
    output.append(format_section("Peer-reviewed Publications", journal_entries))
    output.append(format_section("Preprints", preprint_entries))
    return "\n".join(output)

# === CV TEMPLATE MERGE ===

with open("cv_template.md") as f:
    template = f.read()

cv_filled = (
    template.replace("{{NAME}}", NAME)
            .replace("{{EMAIL}}", EMAIL)
            .replace("{{AFFILIATION}}", AFFILIATION)
            .replace("{{ORCID}}", ORCID_ID)
            .replace("{{PUBLICATIONS}}", fetch_publications(ORCID_ID))
            .replace("{{DATE}}", str(date.today()))
)

with open("cv.md", "w") as f:
    f.write(cv_filled)
