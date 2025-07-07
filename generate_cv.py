import requests
from datetime import date

# USER CONFIG: Update these with your actual info
NAME = "Sheng-Kai Hsu"
EMAIL = "sh2246@cornell.edu"
AFFILIATION = "Postdoc, Institute for Genomic Diversity, Cornell University"
ORCID_ID = "0000-0002-6942-7163"  # replace with yours

# Fetch ORCID works
def fetch_publications(orcid_id):
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/works"
    headers = {"Accept": "application/json"}
    response = requests.get(url, headers=headers)
    works = response.json()["group"]
    publications = []
    for work in works:
        summary = work["work-summary"][0]
        title = summary["title"]["title"]["value"]
        year = summary.get("publication-date", {}).get("year", {}).get("value", "n.d.")
        doi = None
        external_ids = summary.get("external-ids", {}).get("external-id", [])
        for eid in external_ids:
            if isinstance(eid, dict):
                if eid.get("external-id-type") == "doi":
                    doi = eid.get("external-id-value")
                    break
        if doi:
            line = f"- **{title}** ({year}), [DOI](https://doi.org/{doi})"
        else:
            line = f"- **{title}** ({year})"
        publications.append(line)
    return "\n".join(sorted(publications, reverse=True))

# Fill template
with open("cv_template.md") as f:
    template = f.read()

cv_text = template.replace("{{NAME}}", NAME)\
                  .replace("{{EMAIL}}", EMAIL)\
                  .replace("{{AFFILIATION}}", AFFILIATION)\
                  .replace("{{ORCID}}", ORCID_ID)\
                  .replace("{{PUBLICATIONS}}", fetch_publications(ORCID_ID))\
                  .replace("{{DATE}}", str(date.today()))

with open("cv.md", "w") as f:
    f.write(cv_text)
