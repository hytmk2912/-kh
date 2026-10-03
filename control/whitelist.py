"""Industry / job-type whitelist (control layer 3)."""
from control._frozen import freeze

ALLOWED_JOB_TYPES = frozenset({"write", "translate", "proofread"})

ALLOWED_INDUSTRIES = frozenset({
    "education",
    "technology",
    "travel",
    "ecommerce",
    "food",
    "culture",
    "health_wellness",  # general information only, no medical advice
    "general",          # scouted gigs that passed agent/scout.py legality filter
})


class NotWhitelisted(PermissionError):
    pass


def check(job_type: str, industry: str) -> None:
    if job_type not in ALLOWED_JOB_TYPES:
        raise NotWhitelisted(f"job type '{job_type}' not allowed; allowed={sorted(ALLOWED_JOB_TYPES)}")
    if industry not in ALLOWED_INDUSTRIES:
        raise NotWhitelisted(f"industry '{industry}' not allowed; allowed={sorted(ALLOWED_INDUSTRIES)}")


freeze(__name__)
