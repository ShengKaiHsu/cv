import requests
from datetime import date

# USER CONFIG: Update these with your actual info
NAME = "Sheng-Kai Hsu"
EMAIL = "sh2246@cornell.edu"
AFFILIATION = "Postdoc, Institute for Genomic Diversity, Cornell University"
ORCID_ID = "0000-0002-6942-7163"  # replace with yours

# For bolding your name
YOUR_FAMILY_NAME = "Hsu"
YOUR_INITIALS = "S."  # Set to "W" or "W.-Y" depending on how it's recorded

# === MAIN FUNCTIONS ===

def fetch_publications(orcid_id):
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/works"
    headers = {"Accept": "application/json"}
    response = requests.get(url, headers=headers)
    works = response.json()["group"]

    apa_entries = []
    non_doi_entries = []

    for work in works:
        summary = work["work-summary"][0]
        title = summary["title"]["title"]["value"]
        year = summary.get("publication-date", {}).get("year", {}).get("value", "n.d.")
        external_ids = summary.get("external-ids", {}).get("external-id", [])

        doi = None
        for eid in external_ids:
            if isinstance(eid, dict) and eid.get("external-id-type") == "doi":
                doi = eid.get("external-id-value")
                break

        if doi:
            # Try Crossref lookup
            crossref_url = f"https://api.crossref.org/works/{doi}"
            try:
                r = requests.get(crossref_url)
                if r.status_code != 200:
                    raise ValueError("DOI not found in Crossref")
                metadata = r.json()["message"]

                authors = metadata.get("author", [])
                author_strs = []
                for a in authors:
                    given = a.get("given", "")
                    family = a.get("family", "")
                    initials = "".join([g[0] + "." for g in given.split()]) if given else ""
                    name_str = f"{family}, {initials}"
                    if family == YOUR_FAMILY_NAME and YOUR_INITIALS in initials:
                        name_str = f"**{name_str}**"
                    author_strs.append(name_str)

                if len(author_strs) > 1:
                    author_text = ", ".join(author_strs[:-1]) + ", & " + author_strs[-1]
                else:
                    author_text = author_strs[0] if author_strs else "Unknown Author"

                pub_year = metadata.get("issued", {}).get("date-parts", [[year]])[0][0]
                title = metadata.get("title", [""])[0]
                journal = metadata.get("container-title", [""])[0]
                volume = metadata.get("volume", "")
                issue = metadata.get("issue", "")
                pages = metadata.get("page", "")
                doi_url = f"https://doi.org/{doi}"

                citation = f"{author_text} ({pub_year}). **{title}**. *{journal}*"
                if volume:
                    citation += f", *{volume}*"
                    if issue:
                        citation += f"({issue})"
                if pages:
                    citation += f", {pages}"
                citation += f". {doi_url}"

                apa_entries.append((pub_year, citation))
            except Exception as e:
                print(f"Error fetching DOI {doi}: {e}")
                continue
        else:
            # Format fallback entry
            authors = summary.get("contributors", {}).get("contributor", [])
            author_text = "Unknown Author"
            if authors:
                author_strs = []
                for a in authors:
                    credit = a.get("credit-name", {}).get("value", "")
                    if YOUR_FAMILY_NAME in credit and YOUR_INITIALS in credit:
                        credit = f"**{credit}**"
                    author_strs.append(credit)
                if len(author_strs) > 1:
                    author_text = ", ".join(author_strs[:-1]) + ", & " + author_strs[-1]
                else:
                    author_text = author_strs[0]

            source = summary.get("journal-title", {}).get("value", "Preprint")
            fallback_entry = f"{author_text} ({year}). **{title}**. *{source}*."
            non_doi_entries.append((year, fallback_entry))

    # Sort both lists
    apa_sorted = sorted(apa_entries, key=lambda x: str(x[0]), reverse=True)
    non_doi_sorted = sorted(non_doi_entries, key=lambda x: str(x[0]), reverse=True)

    # Combine and number
    all_entries = apa_sorted + non_doi_sorted
    return "\n\n".join(f"{i+1}. {entry}" for i, (_, entry) in enumerate(all_entries))

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
