"""
SPARK — tracked institutions.

The single, maintainer-editable list of departments SPARK ranks. Adding an
institution is one entry here plus a pipeline run (`bash pipeline/refresh.sh`);
no other code changes. Read by resolve_pids.py (`--all` walks every entry,
`--institution SHORT` picks one).

Schema — key is the SHORT code (also the pid-cache filename, lowercased, e.g.
"IITB" → data/iitb_pid_cache.json), so treat it as stable once added:

    name                  display name used in the roster/site
    affiliation           EXACT CSRankings affiliation string — rows are matched
                          verbatim, so a typo silently yields zero faculty
    country/state/city    location metadata carried into the roster
    website               department/institute homepage
    affiliation_keywords  lowercase phrases that, if any appears in a DBLP
                          affiliation note, confirm the resolved identity.
                          Matching is substring-based on punctuation-stripped
                          text, so keep them unambiguous: "iit hyderabad" is a
                          substring of "iiit hyderabad" and would confirm the
                          wrong person, hence the long form only for IITH.
"""

INSTITUTIONS = {
    "IITD": {
        "name": "IIT Delhi", "affiliation": "IIT Delhi",
        "country": "India", "website": "https://www.iitd.ac.in",
        "state": "Delhi", "city": "New Delhi",
        "affiliation_keywords": ["indian institute of technology delhi", "iit delhi"],
    },
    "IIITD": {
        "name": "IIIT Delhi", "affiliation": "IIIT Delhi",
        "country": "India", "website": "https://www.iiitd.ac.in",
        "state": "Delhi", "city": "New Delhi",
        "affiliation_keywords": [
            "indraprastha institute of information technology", "iiit delhi", "iiit d",
        ],
    },
    "IITB": {
        "name": "IIT Bombay", "affiliation": "IIT Bombay",
        "country": "India", "website": "https://www.iitb.ac.in",
        "state": "Maharashtra", "city": "Mumbai",
        "affiliation_keywords": ["indian institute of technology bombay", "iit bombay"],
    },
    "IITM": {
        "name": "IIT Madras", "affiliation": "IIT Madras",
        "country": "India", "website": "https://www.iitm.ac.in",
        "state": "Tamil Nadu", "city": "Chennai",
        "affiliation_keywords": ["indian institute of technology madras", "iit madras"],
    },
    "IISC": {
        "name": "IISc Bangalore", "affiliation": "IISc Bangalore",
        "country": "India", "website": "https://iisc.ac.in/",
        "state": "Karnataka", "city": "Bangalore",
        "affiliation_keywords": ["indian institute of science", "iisc"],
    },
    "IITK": {
        "name": "IIT Kanpur", "affiliation": "IIT Kanpur",
        "country": "India", "website": "https://www.iitk.ac.in",
        "state": "Uttar Pradesh", "city": "Kanpur",
        "affiliation_keywords": ["indian institute of technology kanpur", "iit kanpur"],
    },
    "IITKGP": {
        "name": "IIT Kharagpur", "affiliation": "IIT Kharagpur",
        "country": "India", "website": "https://www.iitkgp.ac.in",
        "state": "West Bengal", "city": "Kharagpur",
        "affiliation_keywords": ["indian institute of technology kharagpur", "iit kharagpur"],
    },
    "IIITH": {
        "name": "IIIT Hyderabad", "affiliation": "IIIT Hyderabad",
        "country": "India", "website": "https://www.iiit.ac.in",
        "state": "Telangana", "city": "Hyderabad",
        "affiliation_keywords": [
            "international institute of information technology hyderabad", "iiit hyderabad",
        ],
    },
    "IITBBS": {
        "name": "IIT Bhubaneswar", "affiliation": "IIT Bhubaneswar",
        "country": "India", "website": "https://www.iitbbs.ac.in",
        "state": "Odisha", "city": "Bhubaneswar",
        "affiliation_keywords": ["indian institute of technology bhubaneswar", "iit bhubaneswar"],
    },
    "IITBHILAI": {
        "name": "IIT Bhilai", "affiliation": "IIT Bhilai",
        "country": "India", "website": "https://www.iitbhilai.ac.in",
        "state": "Chhattisgarh", "city": "Bhilai",
        "affiliation_keywords": ["indian institute of technology bhilai", "iit bhilai"],
    },
    # CSRankings spells this one with the parenthetical; DBLP notes use either
    # "IIT (BHU)", "IIT BHU" or the full Banaras Hindu University name.
    "IITBHU": {
        "name": "IIT (BHU) Varanasi", "affiliation": "IIT (BHU) Varanasi",
        "country": "India", "website": "https://www.iitbhu.ac.in",
        "state": "Uttar Pradesh", "city": "Varanasi",
        "affiliation_keywords": [
            "indian institute of technology bhu", "indian institute of technology varanasi",
            "iit bhu", "banaras hindu university",
        ],
    },
    "IITDH": {
        "name": "IIT Dharwad", "affiliation": "IIT Dharwad",
        "country": "India", "website": "https://www.iitdh.ac.in",
        "state": "Karnataka", "city": "Dharwad",
        "affiliation_keywords": ["indian institute of technology dharwad", "iit dharwad"],
    },
    "IITG": {
        "name": "IIT Guwahati", "affiliation": "IIT Guwahati",
        "country": "India", "website": "https://www.iitg.ac.in",
        "state": "Assam", "city": "Guwahati",
        "affiliation_keywords": ["indian institute of technology guwahati", "iit guwahati"],
    },
    "IITGN": {
        "name": "IIT Gandhinagar", "affiliation": "IIT Gandhinagar",
        "country": "India", "website": "https://www.iitgn.ac.in",
        "state": "Gujarat", "city": "Gandhinagar",
        "affiliation_keywords": ["indian institute of technology gandhinagar", "iit gandhinagar"],
    },
    "IITGOA": {
        "name": "IIT Goa", "affiliation": "IIT Goa",
        "country": "India", "website": "https://www.iitgoa.ac.in",
        "state": "Goa", "city": "Ponda",
        "affiliation_keywords": ["indian institute of technology goa", "iit goa"],
    },
    # No short "iit hyderabad" key — it is a substring of "iiit hyderabad" and
    # would confirm an IIIT Hyderabad homonym as this department's faculty.
    "IITH": {
        "name": "IIT Hyderabad", "affiliation": "IIT Hyderabad",
        "country": "India", "website": "https://www.iith.ac.in",
        "state": "Telangana", "city": "Hyderabad",
        "affiliation_keywords": ["indian institute of technology hyderabad"],
    },
    "IITI": {
        "name": "IIT Indore", "affiliation": "IIT Indore",
        "country": "India", "website": "https://www.iiti.ac.in",
        "state": "Madhya Pradesh", "city": "Indore",
        "affiliation_keywords": ["indian institute of technology indore", "iit indore"],
    },
    "IITJ": {
        "name": "IIT Jodhpur", "affiliation": "IIT Jodhpur",
        "country": "India", "website": "https://www.iitj.ac.in",
        "state": "Rajasthan", "city": "Jodhpur",
        "affiliation_keywords": ["indian institute of technology jodhpur", "iit jodhpur"],
    },
    "IITJMU": {
        "name": "IIT Jammu", "affiliation": "IIT Jammu",
        "country": "India", "website": "https://www.iitjammu.ac.in",
        "state": "Jammu and Kashmir", "city": "Jammu",
        "affiliation_keywords": ["indian institute of technology jammu", "iit jammu"],
    },
    "IITMANDI": {
        "name": "IIT Mandi", "affiliation": "IIT Mandi",
        "country": "India", "website": "https://www.iitmandi.ac.in",
        "state": "Himachal Pradesh", "city": "Mandi",
        "affiliation_keywords": ["indian institute of technology mandi", "iit mandi"],
    },
    "IITP": {
        "name": "IIT Patna", "affiliation": "IIT Patna",
        "country": "India", "website": "https://www.iitp.ac.in",
        "state": "Bihar", "city": "Patna",
        "affiliation_keywords": ["indian institute of technology patna", "iit patna"],
    },
    "IITPKD": {
        "name": "IIT Palakkad", "affiliation": "IIT Palakkad",
        "country": "India", "website": "https://www.iitpkd.ac.in",
        "state": "Kerala", "city": "Palakkad",
        "affiliation_keywords": ["indian institute of technology palakkad", "iit palakkad"],
    },
    "IITR": {
        "name": "IIT Roorkee", "affiliation": "IIT Roorkee",
        "country": "India", "website": "https://www.iitr.ac.in",
        "state": "Uttarakhand", "city": "Roorkee",
        "affiliation_keywords": ["indian institute of technology roorkee", "iit roorkee"],
    },
    "IITRPR": {
        "name": "IIT Ropar", "affiliation": "IIT Ropar",
        "country": "India", "website": "https://www.iitrpr.ac.in",
        "state": "Punjab", "city": "Rupnagar",
        "affiliation_keywords": ["indian institute of technology ropar", "iit ropar"],
    },
    "IITTP": {
        "name": "IIT Tirupati", "affiliation": "IIT Tirupati",
        "country": "India", "website": "https://www.iittp.ac.in",
        "state": "Andhra Pradesh", "city": "Tirupati",
        "affiliation_keywords": ["indian institute of technology tirupati", "iit tirupati"],
    },

    # ── Research institutes ──────────────────────────────────────────────
    # Narrower and more theory-concentrated than the IITs. Worth remembering
    # when reading their rank: geo_mean_score is a geometric mean over the
    # areas a department publishes in, so an institute active in one or two
    # areas is scored on those alone while a broad department is pulled toward
    # its weaker ones.
    "TIFR": {
        "name": "TIFR Mumbai", "affiliation": "Tata Inst. of Fundamental Research",
        "country": "India", "website": "https://www.tifr.res.in",
        "state": "Maharashtra", "city": "Mumbai",
        "affiliation_keywords": ["tata institute of fundamental research", "tifr"],
    },
    # CSRankings spells this one as the bare acronym "CMI". That is safe as an
    # affiliation (rows are matched exactly, not by substring) but far too
    # short to use as a keyword, so only the expanded name confirms identity.
    "CMI": {
        "name": "CMI Chennai", "affiliation": "CMI",
        "country": "India", "website": "https://www.cmi.ac.in",
        "state": "Tamil Nadu", "city": "Chennai",
        "affiliation_keywords": ["chennai mathematical institute"],
    },
    # Only ISI's Kolkata centre appears in CSRankings; the keyword is left
    # centre-agnostic because DBLP notes rarely name one.
    "ISI": {
        "name": "ISI Kolkata", "affiliation": "ISI Kolkata",
        "country": "India", "website": "https://www.isical.ac.in",
        "state": "West Bengal", "city": "Kolkata",
        "affiliation_keywords": ["indian statistical institute"],
    },

    # ── BITS Pilani: two campuses, one name ──────────────────────────────
    # These two deliberately share broad keywords, which the substring rule at
    # the top of this file would normally forbid ("bits pilani" nests inside a
    # Goa-campus note). The rule is relaxed here because the cost is inverted:
    # tiering sends anyone WITH a DBLP affiliation note that fails the keyword
    # check to REVIEW rather than MEDIUM, so a campus-specific keyword would
    # push most of both rosters out of the roster and into manual triage. The
    # residual risk — confirming a homonym from the sibling campus — is small,
    # since rosters are selected by exact CSRankings affiliation (cleanly split:
    # Pilani homepages sit under /pilani, Goa under /goa) and the keyword only
    # verifies a selection that is already correct.
    # Only Pilani and Goa are in CSRankings; the Hyderabad and Dubai campuses
    # have no rows at all, under any spelling.
    "BITSP": {
        "name": "BITS Pilani", "affiliation": "BITS Pilani",
        "country": "India", "website": "https://www.bits-pilani.ac.in",
        "state": "Rajasthan", "city": "Pilani",
        "affiliation_keywords": ["bits pilani", "birla institute of technology and science"],
    },
    # NOTE the hyphen: the CSRankings string is "BITS Pilani-Goa", not a space.
    "BITSG": {
        "name": "BITS Pilani Goa", "affiliation": "BITS Pilani-Goa",
        "country": "India", "website": "https://www.bits-pilani.ac.in/goa",
        "state": "Goa", "city": "Zuarinagar",
        "affiliation_keywords": [
            "bits pilani", "birla institute of technology and science",
            "goa campus", "bits goa",
        ],
    },
}
