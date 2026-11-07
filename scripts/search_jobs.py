#!/usr/bin/env python3
"""
Multi-platform Ireland job search pipeline.

Sources:
  1. LinkedIn   — worldunboxer/rapid-linkedin-scraper ($0.00035/job incl. details;
                  jobs already in jobs.json are skipped free)
  2. Indeed IE  — valig/indeed-jobs-scraper (99.8% success, $0.0001/result)
  3. Glassdoor  — valig/glassdoor-jobs-scraper ($0.0004/result; SWE searches only)
  4. Company career pages — 16 companies via RAG browser (off unless
     SCRAPE_COMPANY_PAGES=1)

  (IrishJobs and Jobs.ie scrapers still exist below but are disabled in main();
  see the note there.)

All sources return structured data. Deduplicates against existing jobs.json.
"""
import os, re, json, hashlib, time, inspect, collections, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from apify_client import ApifyClient

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_FILE   = os.path.join(ROOT, "web", "data", "jobs.json")

# ── Role categories — MUST EXACTLY MATCH the chip values in web/index.html
# (Java / Backend, Python, Data Analyst, Data Scientist, Data Engineer, AI / ML,
# IT Support, Full Stack, Production Support, Trust & Safety). If you add a new bucket here, also add a
# matching chip in the dashboard, otherwise those jobs won't appear under
# any filter.
#
# Order = priority: software-engineering buckets run first so a mid-run Apify
# credit exhaustion can't starve them.
SEARCHES = [
    ("Java / Backend", [
        "junior java developer",
        "graduate java engineer",
        "graduate java software engineer ireland",
        "associate software engineer java",
        "entry level backend developer",
        "graduate spring boot developer",
        "junior backend engineer",
        "software engineer java",
        "junior kotlin developer",
        "graduate backend engineer dublin",
    ]),
    ("Python", [
        "junior python developer",
        "graduate python engineer",
        "graduate python developer ireland",
        "entry level python developer",
        "junior data engineer",
        "graduate data engineer",
        "software engineer python",
        "graduate backend python ireland",
    ]),
    ("Full Stack", [
        "junior full stack developer",
        "graduate software engineer",
        "graduate software engineer ireland",
        "entry level software engineer",
        "associate software engineer",
        "junior react developer",
        "junior node.js developer",
        "software engineer new grad",
        "junior web developer",
        "graduate fullstack developer dublin",
        "graduate programme software engineer",
    ]),
    ("Production Support", [
        "junior production support engineer",
        "graduate application support engineer",
        "junior devops engineer",
        "graduate site reliability engineer",
        "associate DevOps engineer",
        "junior cloud engineer",
        "graduate cloud engineer",
        "junior platform engineer",
        "graduate AWS engineer",
        "junior Azure engineer",
        "junior kubernetes engineer",
        "cloud support engineer",
        "graduate SRE ireland",
    ]),
    # Experience cap for this bucket is enforced separately (≤3 years) —
    # see exceeds_max_experience().
    ("Trust & Safety", [
        "trust and safety",
        "trust and safety analyst",
        "trust and safety specialist",
        "content moderator",
        "content reviewer",
        "policy enforcement specialist",
        "online safety analyst",
        "integrity analyst",
        "community operations specialist",
    ]),
    ("AI / ML", [
        "junior machine learning engineer",
        "graduate AI engineer",
        "graduate machine learning engineer",
        "entry level ML engineer",
        "associate machine learning engineer",
        "junior NLP engineer",
        "AI software engineer entry level",
        "graduate deep learning engineer",
        "graduate AI engineer ireland",
    ]),
    ("Data Scientist", [
        "graduate data scientist",
        "junior data scientist",
        "associate data scientist",
        "graduate data scientist ireland",
        "entry level data scientist",
        "data science graduate programme",
    ]),
    ("Data Analyst", [
        "junior data analyst",
        "graduate data analyst",
        "graduate data analyst ireland",
        "entry level data analyst",
        "associate business analyst",
        "graduate business intelligence analyst",
        "junior SQL analyst",
        "data analyst graduate dublin",
        "graduate business analyst data",
    ]),
    ("IT Support", [
        "junior IT support engineer",
        "graduate IT support",
        "entry level desktop support",
        "associate service desk analyst",
        "junior helpdesk engineer",
        "IT support analyst",
        "junior systems administrator",
        "graduate IT support ireland",
    ]),
]

# Broad Java / backend / support searches with no seniority word: Hari's core
# profile (Java + production support at HCL). They run first, so neither the
# time budget nor the Apify credit guard can cut them short.
BROAD_JAVA_QUERIES = [
    "java developer",
    "java software engineer",
    "java backend developer",
    "java full stack developer",
    "spring boot developer",
    "java engineer",
    "backend developer",
    "software development engineer",
    "microservices developer",
    "application support engineer",
    "production support engineer",
]

# Broad software-engineering searches with no seniority word. Most Irish SWE
# postings aren't titled "junior"/"graduate", so the bucket queries above miss
# them. These run right after the Java ones; senior titles and roles asking
# for more than MAX_YEARS_EXPERIENCE are still dropped, and strict_category()
# files each result under its real domain (Java, Python, DevOps → Production
# Support, ...).
BROAD_SWE_QUERIES = [
    "software engineer",
    "software developer",
    "software engineer II",
    "backend engineer",
    "python developer",
    "full stack developer",
    "frontend developer",
    ".net developer",
    "devops engineer",
    "site reliability engineer",
    "platform engineer",
    "cloud engineer",
    "data engineer",
]

# Buckets that get the software-engineering treatment: more results per query
# and Glassdoor coverage. Glassdoor costs 4x Indeed per result and mostly
# repeats LinkedIn/Indeed for the other buckets, so they skip it.
SWE_BUCKETS = {"Java / Backend", "Python", "Full Stack", "Production Support"}

# Maximum results per query per source.
RESULTS_PER_QUERY      = 15
SWE_RESULTS_PER_QUERY  = 30
JAVA_RESULTS_PER_QUERY = 50    # the Java / Backend bucket
BROAD_SWE_RESULTS      = 100

# How many days back each source looks. Daily runs only need a few days (dedup
# skips known jobs); after a gap, run the workflow by hand with a larger
# lookback_days to catch up. Indeed can't go past 14 days.
LOOKBACK_DAYS = max(1, int(os.environ.get("LOOKBACK_DAYS") or 3))

# The 16 career pages below go through the RAG browser — the costliest calls in
# a run — and yielded 1 job in total in a full run (Oct 2026). Off unless asked.
SCRAPE_COMPANY_PAGES = os.environ.get("SCRAPE_COMPANY_PAGES") == "1"

# Which job boards to query (comma-separated). A retry after one board failed
# can re-run just that board instead of paying again for the others.
SOURCES = {s.strip().lower() for s in
           (os.environ.get("SOURCES") or "linkedin,indeed,glassdoor").split(",") if s.strip()}

# A healthy Glassdoor run takes ~50 s; anything past this is a hung retry loop.
GLASSDOOR_TIMEOUT_SECS = 90

# The LinkedIn actor's own limit is 12 hours, so one search that keeps paging
# (e.g. digging past hundreds of known jobs for new ones) could stall a whole
# run. A timed-out run still returns what it collected.
LINKEDIN_TIMEOUT_SECS = 180

# Stop starting new searches after this long and move on to saving + resumes,
# so a slow run can never hit GitHub's 6-hour limit and lose everything.
# Searches run in priority order, so only the lowest-priority ones get cut.
SEARCH_BUDGET_MINUTES = int(os.environ.get("SEARCH_BUDGET_MINUTES") or 150)

# Stop starting new searches when the Apify account has less than this left
# for the month. Without it, the monthly hard limit hit mid-run and every
# later search silently returned nothing (Oct 2026). One query's three boards
# can charge at most ~$0.16, so this always leaves room for the last one.
CREDIT_RESERVE_USD = float(os.environ.get("APIFY_CREDIT_RESERVE_USD") or 0.30)

# ── Company career pages (RAG browser fallback) ───────────────────────────────
COMPANY_CAREER_PAGES = [
    ("Microsoft",   "https://careers.microsoft.com/v2/global/en/locations/dublin.html",               "Full Stack"),
    ("Google",      "https://www.google.com/about/careers/applications/jobs/results?location=Dublin,+Ireland", "Full Stack"),
    ("Stripe",      "https://stripe.com/jobs/search?location=Dublin&teams=engineering",               "Java / Backend"),
    ("Amazon",      "https://www.amazon.jobs/en/search?base_query=software+engineer&loc_query=Dublin%2C+Ireland", "Full Stack"),
    ("Workday",     "https://www.workday.com/en-us/company/careers/overview.html?q=software+engineer&location=Dublin", "Full Stack"),
    ("HubSpot",     "https://www.hubspot.com/careers/jobs?q=software+engineer&country=Ireland",       "Full Stack"),
    ("Salesforce",  "https://salesforce.wd12.myworkdayjobs.com/en-US/External_Career_Site?q=software+engineer&locationCountry=IE", "Full Stack"),
    ("MongoDB",     "https://www.mongodb.com/careers/search?department=Engineering&location=Dublin%2C+Ireland", "Full Stack"),
    ("Zendesk",     "https://jobs.zendesk.com/us/en/search-results?keywords=software+engineer&location=Dublin", "Full Stack"),
    ("Intercom",    "https://www.intercom.com/careers/jobs?search=engineer&location=Dublin",          "Full Stack"),
    ("Gong",        "https://www.gong.io/careers/#open-positions",                                    "Full Stack"),
    ("Arista",      "https://www.arista.com/en/careers",                                              "Full Stack"),
    ("Bentley",     "https://www.bentley.com/company/careers/?search=software+engineer&location=Dublin", "Full Stack"),
    ("Canonical",   "https://canonical.com/careers/all?location=Ireland",                             "Python"),
    ("Etsy",        "https://careers.etsy.com/?country=IE",                                           "Java / Backend"),
    ("Fidelity",    "https://www.fidelityinternational.com/careers/",                                 "Java / Backend"),
]

# ── Experience filter ──────────────────────────────────────────────────────────
# Hari has about 3.5 years of experience, so roles asking for more are dropped,
# both by title (Senior, Lead, ...) and by the years the JD asks for.
MAX_YEARS_EXPERIENCE = float(os.environ.get("MAX_YEARS_EXPERIENCE") or 3.5)

# Senior whatever else the title says ("Associate Director", "Senior
# Associate", "Lead Graduate Engineer").
SENIOR_TITLE_KEYWORDS = re.compile(
    r"\b(senior|snr|sr\.?|lead|principal|staff|head\s+of|director|vp\b|vice\s+president"
    r"|chief|cto|cio|architect|leader|expert|experienced|level\s+[4-9]"
    r"|(?:engineer|developer|analyst)\s+(?:iv|v|vi|[4-9])"
    r"|[4-9]\+?\s*years?|[1-9][0-9]\+?\s*years?)\b",
    re.IGNORECASE
)
# Senior-sounding words that a junior keyword outweighs ("Graduate Consultant").
SOFT_SENIOR_TITLE_KEYWORDS = re.compile(r"\b(manager|consultant)\b", re.IGNORECASE)
JUNIOR_TITLE_KEYWORDS = re.compile(
    r"\b(junior|jr\.?|graduate|grad\b|intern|trainee|associate|entry.?level"
    r"|new\s+grad|early\s+career|apprentice|software\s+engineer\s+i{1,2}$"
    r"|engineer\s+i{1,2}$|swe\s+i{1,2}$)\b",
    re.IGNORECASE
)

def is_experience_appropriate(title: str) -> bool:
    if SENIOR_TITLE_KEYWORDS.search(title):
        return False
    if JUNIOR_TITLE_KEYWORDS.search(title):
        return True
    return not SOFT_SENIOR_TITLE_KEYWORDS.search(title)   # neutral titles → include

# Years of experience a JD asks for: "4+ years of experience", "3-5 years'
# experience", "minimum of five (5) years in a similar role", "5 yrs building
# APIs". For a range the lower bound counts ("3-5 years" passes a 3.5 cap),
# also when HTML stripping glued it to the previous word ("Requirements3-5").
_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
              "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_NUM = r"(?:\d{1,2}(?:\.\d)?|one|two|three|four|five|six|seven|eight|nine|ten)"
_YEARS_REQ = re.compile(
    rf"(?i)(?<!\d)(?<!\d\.)({_NUM})\)?\s*(?:\+|plus|or more|or above)?\s*"
    rf"(?:(?:-|–|—|to)\s*{_NUM}\s*\+?\s*)?"
    r"(?:years?|yrs?)\b"
    r"(?=[^.;\n]{0,70}?\b(?:experience|exp\b|expertise|background|track record|hands[- ]on"
    r"|commercial|professional|industry|in (?:a |an |the )?(?:similar|relevant|software|engineering"
    r"|development|backend|java|python|devops|cloud|data|it\b|tech|technical|production|support"
    r"|trust|content|moderation|policy|operations|role|position|field)"
    r"|building|developing|working|writing|designing|delivering|programming|coding|using))"
)

def required_years(description: str) -> float:
    """Largest number of years of experience the JD asks for (0 if none).
    Numbers above 10 are ignored: "over 25 years of experience" is the company
    describing itself, not a requirement."""
    most = 0.0
    for m in _YEARS_REQ.finditer(description or ""):
        tok = m.group(1).lower()
        n = float(_NUM_WORDS.get(tok) or tok)
        if 1 <= n <= 10:
            most = max(most, n)
    return most

def exceeds_max_experience(description: str, max_years: float = MAX_YEARS_EXPERIENCE) -> bool:
    """True if the JD asks for more than max_years of experience (all domains)."""
    return required_years(description) > max_years

# Companies whose listings should never enter the tracker (gig-work / AI-trainer
# spam that floods every search query with hundreds of near-duplicate roles).
COMPANY_BLOCKLIST = {"dataannotation", "data annotation", "joblet", "crewlia", "data robotics"}
# Matched as whole names only (too short to match safely as a substring).
COMPANY_BLOCKLIST_EXACT = {"hired"}

def is_company_allowed(company: str) -> bool:
    c = (company or "").lower().strip()
    return c not in COMPANY_BLOCKLIST_EXACT and not any(b in c for b in COMPANY_BLOCKLIST)

# Titles that aren't software-engineering roles. Scrapers ingest these because
# generic queries like "graduate engineer" or "junior analyst" match civil/lab/
# admin postings. Drop them at ingestion so the tracker stays SWE-focused.
NON_SWE_TITLE = re.compile(
    r"\b("
    # Construction / civil / mechanical / electrical engineering
    r"civil (engineer|technician)|graduate civil|civil engineering|"
    r"mechanical engineer|graduate mechanical|hvac|"
    r"(graduate )?electrical engineer|power engineer|"
    r"wastewater|geospatial|surveyor|site engineer|construction|landscape (architect|engineer)|"
    r"roads and streets|elec\. engineer|"
    r"chemical engineer|process engineer|quantity surveyor|building services|"
    r"ehs |environmental consultant|heritage consultant|continuous improvement|"
    # Lab / Medical / Biotech / Pharma
    r"medical scientist|laboratory support|lab analyst|biopharma|biomedical|microbiology|"
    r"pharmacology|haematology|qc analyst|complaint investigation|"
    r"(associate|principal) research scientist|pharmaceutical|"
    # Sales / Marketing / Finance / Admin (non-technical)
    r"sales path|sales (graduate|associate)|marketing analyst|"
    r"accounts payable|accounts receivable|patient administrator|"
    r"junior administrator|landscape architect|change analyst|"
    r"project manager- change|graduate sales|business unit coordinator|"
    r"document controller|junior business analyst - revenue|financial analyst(?! .*tech)|"
    r"graduate health (and|&) safety|health (and|&) safety consultant"
    r")\b",
    re.I,
)

def is_swe_title(title: str) -> bool:
    return not NON_SWE_TITLE.search(title or "")

# ── Relevance allow-list ──────────────────────────────────────────────────────
# The boards pad thin searches with whatever they have: on 2026-11-07 the
# "software engineer" searches brought in accountants, supply planners, sales
# and manufacturing roles, and ~80% of the day's 502 new jobs were off-target.
# So a title now has to name a tech role to get in, and role-defining non-tech
# words win even over a tech word ("PLC Programmer", "Manufacturing Automation
# Engineer", "Analog IC Design Engineer").
def _words(*alternatives):
    return re.compile(r"(?i)\b(?:" + "|".join(alternatives) + r")\b")

_HARD_NON_TECH = _words(
    # manufacturing, supply chain, logistics, engineering trades
    r"manufactur\w*", r"supply", r"planner", r"procurement", r"purchasing", r"buyers?",
    r"logistics", r"warehouse", r"inventory", r"freight", r"forklift", r"rigger", r"crane",
    r"production (?:operator|technician|supervisor|engineer|planning|planner|co-?ordinator)",
    r"process (?:engineer|development|science|technician)", r"mould\w*", r"mold\w*", r"lean",
    r"npi", r"npd", r"maintenance", r"mechanical", r"electrical", r"civil", r"structural",
    r"chemical", r"drainage", r"rail", r"commissioning", r"cost engineer", r"project engineer",
    r"controls engineer", r"plc", r"scada", r"dcs", r"delta ?v", r"mes", r"cnc", r"cad programmer",
    r"(?<!software )(?<!test )(?<!qa )(?<!cloud )(?<!devops )(?<!network )(?<!it )"
    r"automation (?:engineer|graduate|equipment|technician)",
    r"(?<!software )(?<!data )quality (?:engineer|graduate|technician|specialist|officer|control|validation"
    r"|& compliance|and compliance|& governance|and governance)",
    r"qc", r"pqa", r"csv", r"gmp", r"validation (?:engineer|specialist|analyst)", r"qualified person",
    r"(?<!ai )lab", r"laborator\w*", r"chemist", r"microbiolog\w*", r"technologist", r"clinical",
    r"regulatory affairs", r"health (?:and|&) safety", r"ehs", r"shesq", r"lims",
    r"data integrity",
    # hardware, electronics, field service
    r"analog", r"asic", r"fpga", r"mixed[- ]signal", r"ic design\w*", r"verification engineer",
    r"semiconductor", r"silicon", r"gpu design", r"rf engineer", r"camera tuning",
    r"characteri[sz]ation", r"optic\w*", r"photonic\w*", r"security systems",
    r"field (?:service|services|technical|engineer|network|customer|safety)",
    # finance and accounting roles
    r"accountants?", r"accounting", r"bookkeep\w*", r"book keeper", r"auditor", r"payroll",
    r"fp&a", r"underwrit\w*", r"credit control\w*", r"transfer agency",
    r"fund (?:accountant|accounting|administrator|administration)",
    # sales, recruitment, customer service
    r"sales", r"account executive", r"business develop\w*", r"merchandis\w*", r"recruit\w*",
    r"talent acquisition", r"customer (?:service|care)", r"receptionist", r"front of house",
    r"showroom", r"aftersales",
    # gig AI-training work and other non-tech roles
    r"company secretar\w*", r"information developer", r"ai (?:trainer|training|tutor)",
    r"data (?:entry|verification|accuracy|assessment|review|reviewer)",
    r"teacher", r"tutor", r"lecturer", r"nurs(?:e|es|ing)", r"care (?:assistant|worker)",
    r"social care", r"youth", r"housing", r"veterinary", r"dental", r"dentistry",
    r"farm\w*", r"ecolog\w*", r"ombudsman",
)

# Roles that need a language other than English.
_LANGUAGE_ROLE = _words(
    r"speaking", r"speakers?", r"bilingual", r"multilingual", r"fluent",
    r"german", r"french", r"italian", r"spanish", r"portuguese", r"dutch", r"flemish", r"polish",
    r"russian", r"turkish", r"chinese", r"mandarin", r"cantonese", r"japanese", r"korean",
    r"arabic", r"hebrew", r"greek", r"czech", r"slovak", r"hungarian", r"romanian", r"bulgarian",
    r"croatian", r"serbian", r"ukrainian", r"swedish", r"danish", r"norwegian", r"finnish",
    r"nordics?", r"icelandic", r"estonian", r"latvian", r"lithuanian", r"thai", r"vietnamese",
    r"indonesian", r"malay", r"hindi", r"urdu", r"farsi", r"persian", r"benelux", r"dach",
)

# A title with one of these is a tech role.
_STRONG_TECH = _words(
    r"software", r"developers?", r"programmers?", r"dev ?ops", r"devsecops", r"sre",
    r"site reliability", r"sde", r"swe", r"sdet", r"full[- ]?stack", r"back[- ]?end",
    r"front[- ]?end", r"web (?:engineer|developer)", r"mobile (?:engineer|developer|app\w*)",
    r"ios", r"android", r"flutter", r"react", r"angular", r"vue(?:\.?js)?", r"node(?:\.?js)?",
    r"java", r"j2ee", r"spring boot", r"python", r"golang", r"kotlin", r"scala", r"typescript",
    r"javascript", r"rust", r"ruby", r"rails", r"php", r"perl",
    r"cloud (?:engineer|developer|architect|support|operations|platform|consultant|administrator)",
    r"cloud native",
    r"aws", r"azure", r"gcp", r"kubernetes", r"k8s", r"terraform", r"ansible",
    r"platform engineer", r"infrastructure (?:engineer|analyst|support)",
    r"data (?:engineer|engineering|scientist|science|modell?er|architect|platform|warehouse)",
    r"data quality engineer",
    r"machine learning", r"ml", r"deep learning", r"nlp", r"llm", r"computer vision", r"mlops",
    r"ai (?:engineer|developer|scientist|researcher|enablement|software|platform|solutions?)",
    r"generative ai", r"gen ?ai", r"database", r"dba", r"etl", r"elt", r"snowflake",
    r"databricks", r"sql", r"power ?bi", r"tableau", r"looker",
    r"information technology", r"help ?desk", r"service desk", r"desktop support",
    r"end[- ]user (?:support|computing|services)", r"deskside", r"tech(?:nical)? support",
    r"systems? (?:administrator|admin|engineer|developer|development engineer)", r"sysadmin", r"linux", r"unix",
    r"windows (?:engineer|administrator|support|server)", r"wintel", r"vmware", r"citrix",
    r"active directory", r"m365", r"office 365", r"intune", r"data ?cent(?:er|re)",
    r"network (?:engineer|administrator|technician|support|analyst)",
    r"applications? (?:support|developer|engineer|analyst)", r"production support",
    r"qa (?:engineer|analyst|tester|automation|test\w*)",
    r"quality assurance (?:engineer|analyst|tester|automation|test\w*)",
    r"testers?", r"test(?:ing)? (?:engineer|analyst|automation)", r"automation test\w*",
    r"security (?:engineer|analyst|operations|test\w*|enablement)", r"cyber\w*",
    r"soc analyst", r"penetration", r"vulnerability", r"infosec", r"incident response",
    r"integration (?:engineer|developer)", r"microservices", r"forward deployed",
    r"salesforce", r"service ?now", r"kdb", r"applied ai", r"copilot",
    r"(?:ai|data|technology|analytics)(?:,| &| and)+ (?:ai|data|technology|analytics)",
    r"sap (?:developer|abap|basis|consultant|analyst)", r"abap",
    r"mainframe", r"cobol", r"dynamics (?:365|crm|developer)",
)
_STRONG_TECH_SYMBOLS = re.compile(r"(?i)(?:\.net\b|\bc#|\bc\+\+)")
_IT_WORD = re.compile(r"\b(?:IT|ICT)\b")     # case-sensitive: not the word "it"

# Non-tech domains: drop the title unless a strong tech word is also there
# ("Java Developer - Financial Services" stays, "Finance Analyst" goes).
_SOFT_NON_TECH = _words(
    r"financ\w*", r"investments?", r"investor", r"insurance", r"claims", r"payments?",
    r"pricing", r"trad(?:er|ing)", r"treasury", r"credit", r"lending", r"banking", r"funds?",
    r"custody", r"derivatives", r"restructuring", r"private (?:credit|markets|equity)",
    r"real (?:estate|assets)", r"compliance", r"regulatory", r"legal", r"solicitor",
    r"paralegal", r"risk", r"aml", r"kyc", r"tax", r"audit\w*", r"actuar\w*",
    r"marketing", r"commercial", r"customer", r"clients?", r"retail", r"brand", r"campaigns?",
    r"call cent(?:er|re)", r"contact cent(?:er|re)",
    r"paid (?:social|media)", r"social media", r"seo", r"copywriter", r"public relations",
    r"communications", r"hr", r"human resources", r"talent", r"resourcing", r"reward", r"people",
    r"admin\w*", r"office", r"operations", r"co-?ordinator", r"executive", r"assistant",
    r"officer", r"secretary", r"project (?:manager|co-?ordinator|executive)", r"programme manager",
    r"product (?:owner|manager|designer|specialist|marketing)", r"proposal", r"bid",
    r"designer", r"ux", r"graphic", r"creative", r"research(?:er)?", r"market", r"strateg\w*",
    r"energy", r"sustainab\w*", r"environmental", r"health", r"safety", r"medical",
    r"healthcare", r"pharma\w*", r"care", r"facilities", r"construction", r"transport", r"cad",
    r"technician",
)

# Tech-leaning titles that are only trusted without a non-tech domain word.
_WEAK_TECH = _words(
    r"business analyst", r"systems? analyst", r"product analyst", r"technical analyst",
    r"engineering analyst",
    r"technology (?:analyst|graduate|programme|program|associate|consultant)",
    r"support (?:engineer|analyst)", r"technical services", r"escalations? engineer",
    r"deployment engineer", r"disaster recovery", r"solutions? engineer",
)

def is_relevant_title(title: str) -> bool:
    """True if the title names a role in one of Hari's domains."""
    t = title or ""
    if _HARD_NON_TECH.search(t) or _LANGUAGE_ROLE.search(t):
        return False
    if _STRONG_TECH.search(t) or _STRONG_TECH_SYMBOLS.search(t) or _IT_WORD.search(t):
        return True
    if _TS_TITLE.search(t) or strict_category(t, None):
        return True
    if _SOFT_NON_TECH.search(t):
        return False
    return bool(_WEAK_TECH.search(t))

def slug(text):
    text = re.sub(r"[^a-z0-9\s]", "", text.lower().strip())
    return re.sub(r"\s+", "_", text)[:40]

def job_id(company, title):
    return hashlib.md5(f"{slug(company)}_{slug(title)}".encode()).hexdigest()[:10]

# ── Safe string extractor (guards against scrapers returning dicts) ────────────
def _s(val):
    """Return val if it's a non-empty string, otherwise ''."""
    return val if isinstance(val, str) else ""

# ── Apify RAG browser (fallback for sites without dedicated actors) ────────────

# ── Cross-version helper: apify-client 1.x returns a dict from .call(),
# 2.x returns a Run object. Both expose the dataset ID; this helper grabs it.
def _dataset_id(run):
    if run is None:
        return None
    if hasattr(run, "default_dataset_id"):
        return run.default_dataset_id
    if isinstance(run, dict):
        return run.get("defaultDatasetId")
    return getattr(run, "defaultDatasetId", None)

# apify-client 1.x takes timeout_secs=int; 3.x takes run_timeout=timedelta.
# Passing the wrong name raises TypeError, which callers swallow — so pick
# whichever the installed version actually supports.
def _run_timeout_kwargs(actor_client, secs):
    params = inspect.signature(actor_client.call).parameters
    if "run_timeout" in params:
        return {"run_timeout": timedelta(seconds=secs)}
    if "timeout_secs" in params:
        return {"timeout_secs": secs}
    return {}

# Cap what one actor run may return and charge. Without a cap, a pay-per-event
# actor needs credit for its default maximum (e.g. 1000 LinkedIn jobs) before
# it will start, so runs near the end of the monthly credit were refused.
# Apify rejects caps under $0.05 ("Maximum cost per run is less than the
# allowed minimum"), which killed 83 of 97 LinkedIn searches on 2026-11-05.
MIN_CHARGE_CAP_USD = 0.05

def _charge_cap_kwargs(actor_client, max_items, max_usd):
    params = inspect.signature(actor_client.call).parameters
    kw = {}
    if "max_items" in params:
        kw["max_items"] = max_items
    if "max_total_charge_usd" in params:
        kw["max_total_charge_usd"] = Decimal(str(round(max(max_usd, MIN_CHARGE_CAP_USD), 4)))
    return kw

# Errors a retry can't fix: out of credit, bad token, actor gone.
_NO_RETRY = ("hard limit", "usage limit", "monthly usage", "credit", "insufficient",
             "not enough", "unauthorized", "authentication", "token", "not found")

def _run_actor(client, actor_id, run_input, timeout_secs=None, max_items=None, max_usd=None):
    """Run an actor and return its dataset items. A transient failure (network
    blip, Apify 5xx) gets one retry instead of losing that search."""
    actor = client.actor(actor_id)
    kw = {}
    if timeout_secs:
        kw.update(_run_timeout_kwargs(actor, timeout_secs))
    if max_items is not None:
        kw.update(_charge_cap_kwargs(actor, max_items, max_usd))
    run = None
    for attempt in (1, 2):
        try:
            run = actor.call(run_input=run_input, **kw)
            break
        except Exception as e:
            if attempt == 2 or any(s in str(e).lower() for s in _NO_RETRY):
                raise
            print(f"        ↻  {actor_id.split('/')[-1]}: {str(e)[:120]} (retrying in 15 s)")
            time.sleep(15)
    if run is None:
        return []
    for attempt in (1, 2, 3):
        try:
            return list(client.dataset(_dataset_id(run)).iterate_items())
        except Exception:
            if attempt == 3:
                raise
            time.sleep(5)

_CREDIT_WARNED = False

class ApifyTokenError(RuntimeError):
    """APIFY_TOKEN is missing or rejected: no search can work this run."""

def apify_credit_left():
    """USD left under this Apify account's monthly usage limit, or None if the
    API can't say (the run then carries on without the credit guard)."""
    if not APIFY_TOKEN:
        raise ApifyTokenError("APIFY_TOKEN is not set")
    try:
        req = urllib.request.Request("https://api.apify.com/v2/users/me/limits",
                                     headers={"Authorization": f"Bearer {APIFY_TOKEN}"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)["data"]
        return float(data["limits"]["maxMonthlyUsageUsd"]) - float(data["current"]["monthlyUsageUsd"])
    except urllib.error.HTTPError as e:
        if e.code == 401:
            # On 2026-11-07 a mistyped token made all 130 searches fail and
            # the run still "succeeded" with 0 jobs.
            raise ApifyTokenError("Apify rejected APIFY_TOKEN (401 Unauthorized): update the "
                                  "repo secret with the full token from Apify Console > Settings > "
                                  "API & Integrations")
        return _credit_unknown(e)
    except Exception as e:
        return _credit_unknown(e)

def _credit_unknown(e):
    global _CREDIT_WARNED
    if not _CREDIT_WARNED:      # once per run, not before every search
        print(f"    ⚠  Couldn't read the Apify credit ({str(e)[:100]}); carrying on without the credit check")
        _CREDIT_WARNED = True
    return None

# LinkedIn job IDs already in jobs.json or seen earlier in this run. Sent as
# exclude_job_ids: the actor skips those jobs without charging for them, so
# overlapping searches and wide catch-up windows only pay for new postings.
SEEN_LINKEDIN_IDS = set()
_LINKEDIN_JOB_ID = re.compile(r"linkedin\.com/jobs/view/(?:[^/?#]*-)?(\d{6,})")

def linkedin_job_id(url):
    m = _LINKEDIN_JOB_ID.search(url or "")
    return m.group(1) if m else None

def _indeed_date_posted(days):
    """Indeed only accepts 1, 3, 7 or 14 days: round up, capped at 14."""
    for opt in (1, 3, 7, 14):
        if days <= opt:
            return str(opt)
    return "14"

def rag_fetch(client, url, query="software engineer ireland", timeout=120):
    try:
        run   = client.actor("apify/rag-web-browser").call(
            run_input={"startUrls": [{"url": url}], "maxResults": 1, "query": query},
        )
        items = list(client.dataset(_dataset_id(run)).iterate_items())
        if not items:
            return ""
        return items[0].get("text", "") or items[0].get("markdown", "")
    except Exception as e:
        print(f"    ⚠  RAG fetch failed: {e}")
        return ""

# ── 1. LinkedIn — worldunboxer/rapid-linkedin-scraper (FREE) ─────────────────
def search_linkedin(client, query, max_results=RESULTS_PER_QUERY):
    """
    Dedicated LinkedIn scraper. Returns structured job objects.
    The actor's inputs changed in 2026: titles go in a jobs_titles list and the
    posting window is in seconds; the old experience_level / job_type /
    "r2592000" fields are no longer read, so seniority is filtered by title.
    """
    try:
        items = _run_actor(
            client, "worldunboxer/rapid-linkedin-scraper",
            {
                "jobs_titles":         [query],
                "location":            "Ireland",
                "jobs_entries":        max_results,
                "include_job_details": True,   # full description, used for tailoring
                "job_post_time":       str(LOOKBACK_DAYS * 86400),
                "exclude_job_ids":     sorted(SEEN_LINKEDIN_IDS),
            },
            timeout_secs=LINKEDIN_TIMEOUT_SECS,
            # $0.0001/job + $0.00025 detail enrichment, plus start fees
            max_items=max_results, max_usd=max_results * 0.0005 + 0.01,
        )
        jobs  = []
        for item in items:
            title   = (_s(item.get("job_title")) or _s(item.get("title")) or "").strip()
            company = (_s(item.get("company_name")) or _s(item.get("company")) or "").strip()
            loc     = (_s(item.get("job_location")) or _s(item.get("location")) or "Ireland").strip()
            url     = item.get("job_url") or item.get("url") or ""
            lid     = linkedin_job_id(url) or (str(item["job_id"]) if item.get("job_id") else None)
            if lid:
                SEEN_LINKEDIN_IDS.add(lid)
            desc    = (_s(item.get("description")) or _s(item.get("job_description")) or
                       _s(item.get("jobDescription")) or _s(item.get("snippet")) or "").strip()
            if title and company and len(title) > 3:
                jobs.append({"title": title, "company": company,
                             "location": loc, "source": "LinkedIn", "url": url,
                             "description": desc[:6000] if desc else ""})
        print(f"        LinkedIn   → {len(jobs)} results")
        return jobs
    except Exception as e:
        import traceback
        print(f"        ⚠  LinkedIn scraper failed ('{query}'): {e}")
        traceback.print_exc()
        return []

# ── 2. Indeed IE — valig/indeed-jobs-scraper (99.8% success) ─────────────────
def search_indeed(client, query, max_results=RESULTS_PER_QUERY):
    """
    Dedicated Indeed scraper — country=ie for Ireland, last LOOKBACK_DAYS
    (Indeed caps the window at 14 days).
    """
    try:
        items = _run_actor(
            client, "valig/indeed-jobs-scraper",
            {
                "country":    "ie",
                "title":      query,
                "location":   "Ireland",
                "limit":      max_results,
                "datePosted": _indeed_date_posted(LOOKBACK_DAYS),
            },
            # $0.0001/result plus start fees
            max_items=max_results, max_usd=max_results * 0.00015 + 0.01,
        )
        jobs  = []
        # Since the actor's Sep 2026 update, company/location/description are
        # nested objects (employer.name, location.city, description.text);
        # older runs returned flat strings. Accept both.
        def sub(obj, key):
            return _s(obj.get(key)) if isinstance(obj, dict) else ""
        for item in items:
            title   = (_s(item.get("title")) or _s(item.get("positionName")) or "").strip()
            company = (_s(item.get("company")) or _s(item.get("companyName")) or
                       sub(item.get("employer"), "name") or "").strip()
            loc     = (_s(item.get("location")) or sub(item.get("location"), "city") or "Ireland").strip()
            url     = item.get("url") or item.get("jobUrl") or ""
            desc    = (_s(item.get("description")) or sub(item.get("description"), "text") or
                       _s(item.get("jobDescription")) or _s(item.get("snippet")) or
                       _s(item.get("summary")) or "").strip()
            if title and company and len(title) > 3:
                jobs.append({"title": title, "company": company,
                             "location": loc, "source": "Indeed", "url": url,
                             "description": desc[:6000] if desc else ""})
        print(f"        Indeed     → {len(jobs)} results")
        return jobs
    except Exception as e:
        import traceback
        print(f"        ⚠  Indeed scraper failed ('{query}'): {e}")
        traceback.print_exc()
        return []

# ── 3. Glassdoor — valig/glassdoor-jobs-scraper (99.9% success) ──────────────
def search_glassdoor(client, query, max_results=RESULTS_PER_QUERY):
    """
    Dedicated Glassdoor scraper — Ireland location, last LOOKBACK_DAYS.
    """
    try:
        # Glassdoor's crawler sometimes hangs ~2 min retrying; a timed-out
        # run still returns whatever it collected.
        items = _run_actor(
            client, "valig/glassdoor-jobs-scraper",
            {
                "keywords": query,
                "location": "Ireland",
                "daysOld":  LOOKBACK_DAYS,
                "limit":    max_results,
            },
            timeout_secs=GLASSDOOR_TIMEOUT_SECS,
            # $0.0004/result plus start fees
            max_items=max_results, max_usd=max_results * 0.0006 + 0.01,
        )
        jobs  = []
        for item in items:
            title   = (_s(item.get("jobTitle")) or _s(item.get("title")) or "").strip()
            _emp = item.get("employer") or item.get("company") or item.get("companyName") or ""
            _name = _emp.get("name", "") if isinstance(_emp, dict) else _emp
            company = (_s(_name) or "").strip()
            loc     = (_s(item.get("location")) or "Ireland").strip()
            url     = item.get("jobUrl") or item.get("url") or ""
            desc    = (_s(item.get("description")) or _s(item.get("jobDescription")) or
                       _s(item.get("jobDescriptionText")) or _s(item.get("snippet")) or "").strip()
            if title and company and len(title) > 3:
                jobs.append({"title": title, "company": company,
                             "location": loc, "source": "Glassdoor", "url": url,
                             "description": desc[:6000] if desc else ""})
        print(f"        Glassdoor  → {len(jobs)} results")
        return jobs
    except Exception as e:
        import traceback
        print(f"        ⚠  Glassdoor scraper failed ('{query}'): {e}")
        traceback.print_exc()
        return []

# ── 4. IrishJobs.ie — dedicated scraper ───────────────────────────────────────
def search_irishjobs(client, query, max_results=RESULTS_PER_QUERY):
    """
    Dedicated IrishJobs.ie scraper — Ireland's #1 local job board.
    Falls back to RAG browser if actor fails.
    """
    try:
        run = client.actor("unfenced-group/irishjobs-ie-scraper").call(
            run_input={
                "keywords":   query,
                "location":   "Dublin",
                "maxResults": max_results,
            },
        )
        items = list(client.dataset(_dataset_id(run)).iterate_items())
        jobs  = []
        for item in items:
            title   = (_s(item.get("title")) or _s(item.get("jobTitle")) or "").strip()
            company = (_s(item.get("company")) or _s(item.get("companyName")) or "").strip()
            loc     = (_s(item.get("location")) or "Ireland").strip()
            url     = item.get("url") or item.get("jobUrl") or ""
            desc    = (_s(item.get("description")) or _s(item.get("jobDescription")) or
                       _s(item.get("fullDescription")) or _s(item.get("summary")) or "").strip()
            if title and company and len(title) > 3:
                jobs.append({"title": title, "company": company,
                             "location": loc, "source": "IrishJobs", "url": url,
                             "description": desc[:6000] if desc else ""})
        print(f"        IrishJobs  → {len(jobs)} results")
        return jobs
    except Exception as e:
        import traceback
        print(f"        ⚠  IrishJobs scraper failed ('{query}'): {e} — trying RAG fallback")
        traceback.print_exc()
        return _irishjobs_rag_fallback(client, query, max_results)

def _irishjobs_rag_fallback(client, query, max_results):
    url  = f"https://www.irishjobs.ie/Jobs/{query.replace(' ', '-')}?JobCategoryId=2,3,5,11"
    # Use site: prefix so Google returns irishjobs.ie results, not indeed.com
    text = rag_fetch(client, url, query=f"site:irishjobs.ie {query}")
    return _parse_generic(text, "IrishJobs", max_results)

# ── 5. Jobs.ie — RAG browser (no dedicated actor) ────────────────────────────
def search_jobsie(client, query, max_results=RESULTS_PER_QUERY):
    terms = query.replace(" ireland", "").replace(" ", "-")
    url   = f"https://www.jobs.ie/jobs/{terms}/ireland/"
    # Use site: prefix so Google returns jobs.ie results, not indeed.com (which 403s)
    text  = rag_fetch(client, url, query=f"site:jobs.ie {query}")
    jobs  = _parse_generic(text, "Jobs.ie", max_results)
    print(f"        Jobs.ie    → {len(jobs)} results")
    return jobs

def _parse_generic(text, source_name, max_results):
    jobs, seen = [], set()
    patterns = [
        r"^([A-Z][^\n]{4,79})\n([A-Z][^\n]{2,60})\n([^\n]*(?:Ireland|Dublin|Cork|Galway|Remote)[^\n]*)",
        r"([A-Z][^\n]{4,79}?)\s+at\s+([A-Z][^\n]{2,60}?)\s*[\n·]\s*([^\n]*(?:Ireland|Dublin|Cork)[^\n]*)",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.MULTILINE):
            title   = m.group(1).strip()
            company = m.group(2).strip() if len(m.groups()) > 1 else "Unknown"
            loc     = m.group(3).strip()[:80] if len(m.groups()) > 2 else "Ireland"
            key     = f"{title.lower()[:60]}_{company.lower()[:40]}"
            if key not in seen and 5 < len(title) < 90 and len(company) > 1:
                seen.add(key)
                jobs.append({"title": title, "company": company, "location": loc,
                             "source": source_name, "url": ""})
            if len(jobs) >= max_results:
                return jobs
    return jobs

# ── 6. Company career pages — RAG browser ─────────────────────────────────────
def parse_company_page(text, company, max_results=10):
    jobs, seen = [], set()
    title_re = re.compile(
        r"(?:^|\n)([A-Z][A-Za-z0-9 ,./\-&'()]{5,79})"
        r"(?:\n|\s*[-–·|]\s*)"
        r"(?:[^\n]*(?:Dublin|Ireland|Remote)[^\n]*)",
        re.MULTILINE
    )
    skip = re.compile(
        r"^(Apply|View|Learn|Read|See|Sign|Join|Home|About|Contact|Benefits|Culture"
        r"|Login|Life at|Jobs in|Search|Filter|Careers|Explore|Skip|Showing|Sort|Page)\b",
        re.I
    )
    for m in title_re.finditer(text):
        title = m.group(1).strip().rstrip("-–·|•").strip()
        if not (5 < len(title) < 90) or skip.match(title):
            continue
        key = f"{title.lower()[:60]}_{company.lower()[:30]}"
        if key not in seen and is_experience_appropriate(title):
            seen.add(key)
            jobs.append({"title": title, "company": company,
                         "location": "Dublin, Ireland", "source": f"{company} Careers", "url": ""})
        if len(jobs) >= max_results:
            break
    return jobs

def search_company_careers(client, company, url, category):
    print(f"    🏢  {company} careers page...")
    text = rag_fetch(client, url, query=f"software engineer {company} ireland", timeout=90)
    jobs = parse_company_page(text, company, max_results=10)
    print(f"        {company}  → {len(jobs)} results")
    return jobs, category

# ── Helpers ───────────────────────────────────────────────────────────────────
def load_existing_jobs():
    if os.path.exists(JOBS_FILE):
        with open(JOBS_FILE) as f:
            return json.load(f)
    return []

def save_jobs(jobs):
    os.makedirs(os.path.dirname(JOBS_FILE), exist_ok=True)
    with open(JOBS_FILE, "w") as f:
        json.dump(jobs, f, indent=2)

# ── Strict title-driven category classifier ─────────────────────────────────
# The search-query bucket that surfaced a job is a WEAK signal — a
# "junior python developer" search returns plenty of generic "Software
# Engineer" titles that aren't actually Python. So before we trust the
# search-bucket category, run the title through a strict title-based
# classifier and let it override when it has a strong signal.
#
# Order matters: most specific rules first; first match wins.
_STRICT_CATEGORY_RULES = [
    (re.compile(r"(?i)\b(machine learning|\bml\b engineer|\bai\b engineer|deep learning|\bnlp\b|computer vision|\bllm\b|gen[- ]?ai|generative ai|ai agents|mlops|ai/ml|ai engineer|ml ops|ai software)\b"), "AI / ML"),
    (re.compile(r"(?i)\bdata scientists?\b|\b(bio)?statistician\b|statistical programmer|\bdata science\b"), "Data Scientist"),
    (re.compile(r"(?i)\b(data analyst|bi analyst|business intelligence|reporting analyst|analytics analyst|data analytics|business analyst|product analyst)\b"), "Data Analyst"),
    (re.compile(r"(?i)\b(data engineer(ing)?|etl (developer|engineer)|analytics engineer|big data (engineer|developer)|data platform engineer|data warehouse (engineer|developer)|databricks (engineer|developer)|(pl/?)?sql developer|database developer|data modell?er|snowflake (developer|engineer))\b"), "Data Engineer"),
    (re.compile(r"(?i)\b(helpdesk|help desk|service desk|desktop support|ict support|technical support|it support|l1 support|l2 support|level 1 support|level 2 support|systems? admin|system administrator|data ?cent(er|re)|information technology|it technician|desktop (technician|engineer|analyst)|end[- ]user|deskside|network (engineer|administrator|technician|support)|deployment engineer)\b"), "IT Support"),
    (re.compile(r"(?i)\b(devops|\bsre\b|site reliability|cloud engineer|platform engineer|aws engineer|azure engineer|kubernetes|infrastructure engineer|terraform|application support|production support|reliability engineer|cloud operations|cloud platform|cloud architect|cloud developer|cloud security|cybersecurity|cyber security|security engineer|qa engineer|test automation|support engineer|support analyst|escalations? engineer|technical services engineer|disaster recovery|testers?|test (analyst|engineer)|qa (analyst|tester)|quality assurance|sdet)\b"), "Production Support"),
    # Language before stack: "Full Stack Java Developer" is a Java role and
    # "Python Backend Engineer" a Python one; a plain "Backend Engineer" stays
    # under Java / Backend.
    (re.compile(r"(?i)\b(java\b|spring boot|jvm|scala (engineer|developer)|kotlin (engineer|developer))\b"), "Java / Backend"),
    (re.compile(r"(?i)\b(python|django|flask|fastapi|pyspark|airflow developer)\b"), "Python"),
    (re.compile(r"(?i)\b(backend (engineer|developer|software)|back[- ]end (engineer|developer))\b"), "Java / Backend"),
    (re.compile(r"(?i)\b(react|vue|angular|frontend|front[- ]end|\bui\b engineer|\bui\b developer|full[- ]?stack|fullstack|mobile (engineer|developer)|\bios\b engineer|android (engineer|developer)|flutter|web developer|wordpress)\b"), "Full Stack"),
    (re.compile(r"(?i)\b(software engineer|software engineering|software developer|software development|sr software|associate software|junior software|graduate software|software internship|sde|forward deployed|salesforce|servicenow)\b"), "Full Stack"),
]

_TS_TITLE = re.compile(
    r"(?i)\b(trust\s*(&|and)\s*(safety|risk)|content (moderat\w*|review\w*|polic\w*|safety|integrity)"
    r"|moderator|policy enforcement|community (operations|standards|integrity|safety)"
    r"|online safety|user safety|integrity (analyst|specialist|operations|associate)"
    r"|abuse (analyst|investigat\w*|specialist)|safety (analyst|specialist|associate|agent)"
    r"|(video|child|platform|ads?|brand|marketplace) safety|fraud (investigat\w*|analyst|specialist|agent|associate))\b"
)
# SWE roles on T&S teams ("Trust & Safety Software Engineer") stay in their
# engineering domain.
_ENGINEERING_TITLE = re.compile(r"(?i)\b(engineer|developer|scientist|programmer|architect)\b")

def is_ts_search_noise(title: str, bucket: str) -> bool:
    """T&S searches also surface unrelated engineering roles. If no title rule
    claims one, it would inherit the T&S bucket — and get the T&S resume
    format. Drop it; the engineering searches find genuine ones."""
    return (bucket == "Trust & Safety"
            and strict_category(title, fallback=None) is None
            and bool(_ENGINEERING_TITLE.search(title or "")))

def strict_category(title: str, fallback: str) -> str:
    """Return the strict title-driven category, or fallback if no rule matches."""
    if _TS_TITLE.search(title or "") and not _ENGINEERING_TITLE.search(title or ""):
        return "Trust & Safety"
    for pat, cat in _STRICT_CATEGORY_RULES:
        if pat.search(title or ""):
            return cat
    # Java/Python searches also return plenty of generic titles ("Graduate
    # Programme", "Analyst"); without a language signal they're general
    # software roles, not Java or Python ones.
    if fallback in ("Java / Backend", "Python"):
        return "Full Stack"
    return fallback

def make_entry(r, category, next_num):
    title   = r["title"]
    company = r["company"]
    # Override the search-bucket category with strict title classification.
    # Falls back to the search-bucket category only when no rule matches.
    category = strict_category(title, fallback=category)
    source  = r.get("source", "LinkedIn")
    loc     = r.get("location", "Ireland")
    url     = r.get("url", "")
    if not url:
        if "Indeed" in source:
            url = f"https://ie.indeed.com/jobs?q={title.replace(' ', '+')}&l=Ireland"
        elif "Glassdoor" in source:
            url = f"https://www.glassdoor.com/Jobs/Ireland-{title.replace(' ', '-')}-SRCH_IL.0,7_IN97_KO8,{8+len(title)}.htm"
        elif "IrishJobs" in source:
            url = f"https://www.irishjobs.ie/Jobs/{title.replace(' ', '-')}"
        elif "Jobs.ie" in source:
            url = f"https://www.jobs.ie/jobs/{title.replace(' ', '-')}/ireland/"
        else:
            url = f"https://www.linkedin.com/jobs/search/?keywords={title.replace(' ', '%20')}&location=Ireland"
    entry = {
        "id":        job_id(company, title),
        "num":       next_num,
        "category":  category,
        "company":   company,
        "title":     title,
        "location":  loc,
        "source":    source,
        "posted":    datetime.now().strftime("%b %Y"),
        "apply_url": url,
        "resume":    f"hari_{slug(company)}_{slug(title)}.pdf",
        "status":    "Not Applied",
        "added":     datetime.now().strftime("%Y-%m-%d"),
    }
    # Capture job description if the scraper returned one
    desc = _s(r.get("description", "")).strip()
    if desc:
        entry["description"] = desc
    return entry

def rejection_reason(r, category):
    """Why a scraped job stays out of the tracker, or None to keep it."""
    title = r.get("title", "")
    if not is_company_allowed(r.get("company", "")):
        return "blocked company"
    if not is_experience_appropriate(title):
        return "senior title"
    if not is_swe_title(title) or not is_relevant_title(title):
        return "off-target role"
    if is_ts_search_noise(title, category):
        return "T&S search noise"
    if exceeds_max_experience(_s(r.get("description", ""))):
        return f"JD asks for >{MAX_YEARS_EXPERIENCE:g} yrs"
    return None

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print(f"🔍  Multi-platform job search — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"    Sources: {', '.join(sorted(SOURCES))} (Glassdoor: SWE searches only)"
          f"{' | 16 company sites' if SCRAPE_COMPANY_PAGES else ''}")
    client       = ApifyClient(APIFY_TOKEN)
    # One client per board: each board's searches run one at a time in its own
    # worker thread, so no client is shared between threads.
    board_client = {b: ApifyClient(APIFY_TOKEN) for b in ("linkedin", "indeed", "glassdoor")}
    pool         = ThreadPoolExecutor(max_workers=3)
    started      = time.time()
    existing     = load_existing_jobs()
    existing_ids = {j["id"] for j in existing}
    SEEN_LINKEDIN_IDS.update(filter(None, (linkedin_job_id(j.get("apply_url")) for j in existing)))
    print(f"    Lookback: {LOOKBACK_DAYS} days  |  known LinkedIn jobs skipped: {len(SEEN_LINKEDIN_IDS)}")
    print(f"    Keeping tech roles that ask for at most {MAX_YEARS_EXPERIENCE:g} years of experience")
    credit = apify_credit_left()    # raises ApifyTokenError for a bad token
    if credit is not None:
        print(f"    Apify credit left this month: ${credit:.2f}")
    new_jobs     = []
    next_num     = max((j.get("num", 0) for j in existing), default=0) + 1
    dropped      = collections.Counter()

    # (label, fallback category, queries, results per source, use Glassdoor)
    plan = [("Java / backend / support (broad)", "Java / Backend", BROAD_JAVA_QUERIES, BROAD_SWE_RESULTS, True),
            ("Software engineering (broad)", "Full Stack", BROAD_SWE_QUERIES, BROAD_SWE_RESULTS, True)]
    plan += [(cat, cat, qs,
              JAVA_RESULTS_PER_QUERY if cat == "Java / Backend"
              else SWE_RESULTS_PER_QUERY if cat in SWE_BUCKETS else RESULTS_PER_QUERY,
              cat in SWE_BUCKETS)
             for cat, qs in SEARCHES]

    stop_reason = None
    for (label, category, queries, limit, use_glassdoor) in plan:
        print(f"\n  📂  {label}")
        for query in queries:
            if time.time() - started > SEARCH_BUDGET_MINUTES * 60:
                stop_reason = f"Search time budget ({SEARCH_BUDGET_MINUTES} min) used up"
                break
            # Stop cleanly before the monthly limit is hit, instead of every
            # remaining search failing. Searches run in priority order.
            try:
                credit = apify_credit_left()
            except ApifyTokenError as e:      # token revoked mid-run
                stop_reason = str(e)
                break
            if credit is not None and credit < CREDIT_RESERVE_USD:
                stop_reason = f"Apify credit nearly used up (${credit:.2f} left)"
                break
            print(f"    🔎  {query}")

            # The boards are searched at the same time (≈3.2 GB of Apify memory
            # together, well inside the plan's limit), so a query takes as long
            # as its slowest board instead of all three added up.
            futures = []
            if "linkedin" in SOURCES:
                futures.append(pool.submit(search_linkedin, board_client["linkedin"], query, limit))
            # Indeed IE ($0.0001/result)
            if "indeed" in SOURCES:
                futures.append(pool.submit(search_indeed, board_client["indeed"], query, limit))
            # Glassdoor ($0.0004/result) — software-engineering searches only
            if use_glassdoor and "glassdoor" in SOURCES:
                futures.append(pool.submit(search_glassdoor, board_client["glassdoor"], query, min(limit, 50)))
            all_results = []
            for f in futures:          # LinkedIn, Indeed, Glassdoor order — as before
                all_results += f.result()

            # IrishJobs and Jobs.ie are disabled: the IrishJobs actor ignores
            # the "keywords" input (returns the same 15 generic Dublin jobs
            # for every query) and is now 403-blocked, burning residential-
            # proxy credit on retries; Jobs.ie 403s every request. Together
            # they cost ~1.5 min per query for zero usable results.

            for r in all_results:
                reason = rejection_reason(r, category)
                if reason:
                    dropped[reason] += 1
                    continue
                jid = job_id(r["company"], r["title"])
                if jid in existing_ids:
                    dropped["already in tracker"] += 1
                    continue
                entry = make_entry(r, category, next_num)
                new_jobs.append(entry)
                existing_ids.add(jid)
                next_num += 1
                print(f"        ✓  [{r.get('source','?')}] {r['title']} @ {r['company']}")
        # Save after every bucket, so a crash later on keeps what was found.
        save_jobs(existing + new_jobs)
        if stop_reason:
            print(f"\n  ⏹  {stop_reason}: skipping the remaining searches (jobs found so far are kept)")
            break
    pool.shutdown(wait=True)

    # ── Company career pages ────────────────────────────────────────────────
    if SCRAPE_COMPANY_PAGES:
        print("\n\n🏢  Scraping company career pages...")
    else:
        print("\n\n🏢  Company career pages skipped (set SCRAPE_COMPANY_PAGES=1 to enable)")
    for (company, url, cat) in (COMPANY_CAREER_PAGES if SCRAPE_COMPANY_PAGES else []):
        try:
            results, category = search_company_careers(client, company, url, cat)
            time.sleep(3)
            for r in results:
                if rejection_reason(r, category):
                    continue
                jid = job_id(r["company"], r["title"])
                if jid not in existing_ids:
                    entry = make_entry(r, category, next_num)
                    new_jobs.append(entry)
                    existing_ids.add(jid)
                    next_num += 1
                    print(f"        ✓  {r['title']} @ {r['company']}")
        except Exception as e:
            print(f"    ⚠  {company} failed: {e}")

    all_jobs = existing + new_jobs
    save_jobs(all_jobs)
    print(f"\n✅  Total jobs: {len(all_jobs)}  |  New today: {len(new_jobs)}")
    if dropped:
        print("    Filtered out: " + ", ".join(f"{n} {why}" for why, n in dropped.most_common()))
    credit = apify_credit_left()
    if credit is not None:
        print(f"    Apify credit left: ${credit:.2f}")
    return new_jobs

if __name__ == "__main__":
    main()
