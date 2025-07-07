import requests
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

def fetch_publications(orcid_id):
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/works"
    headers = {"Accept": "application/json"}
    response = requests.get(url, headers=headers)
    works = response.json()["group"]
    publications = []

    for work in works:
        summary = work["work-summary"][0]
        year = summary.get("publication-date", {}).get("year", {}).get("value", "n.d.")
        doi = None
        external_ids = summary.get("external-ids", {}).get("external-id", [])
        for eid in external_ids:
            if isinstance(eid, dict) and eid.get("external-id-type") == "doi":
                doi = eid.get("external-id-value")
                break

        if not doi:
            continue  # Skip entries without DOI

        # Query Crossref
        crossref_url = f"https://api.crossref.org/works/{doi}"
        try:
            r = requests.get(crossref_url)
            if r.status_code != 200:
                continue
            metadata = r.json()["message"]

            authors = metadata.get("author", [])
            author_strs = []
            for a in authors:
                given = a.get("given", "")
                family = a.get("family", "")
                initials = "".join([g[0] + "." for g in given.split()]) if given else ""
                name_str = f"{family}, {initials}"

                # Bold your name
                if family == YOUR_FAMILY_NAME and YOUR_INITIALS in initials:
                    name_str = f"**{name_str}**"
                author_strs.append(name_str)

            # Format author list
            if len(author_strs) > 1:
                author_text = ", ".join(author_strs[:-1]) + ", & " + author_strs[-1]
            elif author_strs:
                author_text = author_strs[0]
            else:
                author_text = "Unknown Author"

            pub_year = metadata.get("issued", {}).get("date-parts", [[year]])[0][0]
            title = metadata.get("title", [""])[0]
            journal = metadata.get("container-title", [""])[0]
            volume = metadata.get("volume", "")
            issue = metadata.get("issue", "")
            pages = metadata.get("page", "")
            doi_url = f"https://doi.org/{doi}"

            # Build APA-style citation
            citation = f"{author_text} ({pub_year}). *{title}*. *{journal}*"
            if volume:
                citation += f", *{volume}*"
                if issue:
                    citation += f"({issue})"
            if pages:
                citation += f", {pages}"
            citation += f". {doi_url}"

            publications.append((pub_year, citation))

        except Exception as e:
            print(f"Error processing DOI {doi}: {e}")
            continue

    # Sort and format
    sorted_entries = sorted(publications, key=lambda x: str(x[0]), reverse=True)
    return "\n\n".join(f"{i+1}. {entry}" for i, (_, entry) in enumerate(sorted_entries))

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
