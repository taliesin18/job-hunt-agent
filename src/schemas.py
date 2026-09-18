"""
Pydantic models mirroring job-hunt-rag-agent-spec.md.
These validate every JSON file on load so bad data is caught at
ingestion time, not silently embedded.
"""
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class WorkPreferences(BaseModel):
    remote: Optional[bool] = None
    relocation: Optional[bool] = None
    salary_range: Optional[str] = None


class Profile(BaseModel):
    name: str
    headline: Optional[str] = None
    location: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    links: Dict[str, str] = Field(default_factory=dict)
    summary: Optional[str] = None
    target_roles: List[str] = Field(default_factory=list)
    target_industries: List[str] = Field(default_factory=list)
    work_preferences: Optional[WorkPreferences] = None


class Skill(BaseModel):
    id: str
    name: str
    category: str  # technical | soft | tool | language | domain
    subcategory: Optional[str] = None
    proficiency: Optional[str] = None  # beginner | intermediate | advanced | expert
    years_experience: Optional[float] = None
    last_used: Optional[str] = None
    related_experience_ids: List[str] = Field(default_factory=list)
    related_project_ids: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class Achievement(BaseModel):
    description: str
    metric: Optional[str] = None
    skills_used: List[str] = Field(default_factory=list)


class Experience(BaseModel):
    id: str
    company: str
    title: str
    location: Optional[str] = None
    employment_type: Optional[str] = None
    start_date: str
    end_date: str  # "present" allowed
    summary: Optional[str] = None
    responsibilities: List[str] = Field(default_factory=list)
    achievements: List[Achievement] = Field(default_factory=list)
    skills_used: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class Education(BaseModel):
    id: str
    institution: str
    degree: str
    field_of_study: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    gpa: Optional[str] = None
    honors: List[str] = Field(default_factory=list)
    relevant_coursework: List[str] = Field(default_factory=list)


class Project(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    role: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    tech_stack: List[str] = Field(default_factory=list)
    outcomes: List[str] = Field(default_factory=list)
    links: Dict[str, str] = Field(default_factory=dict)
    related_skills: List[str] = Field(default_factory=list)


class Certification(BaseModel):
    id: str
    name: str
    issuer: Optional[str] = None
    date_earned: Optional[str] = None
    expiry_date: Optional[str] = None
    credential_id: Optional[str] = None
    credential_url: Optional[str] = None
    related_skills: List[str] = Field(default_factory=list)


class JobPosting(BaseModel):
    id: str
    company: str
    title: str
    url: Optional[str] = None
    date_saved: Optional[str] = None
    raw_description: str
    required_skills: List[str] = Field(default_factory=list)
    # Optional source facts captured by the companion browser extension.
    # The raw description remains the source of truth for matching, but keeping
    # these fields makes a saved posting easier to inspect and reuse later.
    location: Optional[str] = None
    employment_type: Optional[str] = None
    seniority: Optional[str] = None
    compensation: Optional[str] = None
    application_deadline: Optional[str] = None
    responsibilities: List[str] = Field(default_factory=list)
    qualifications: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    benefits: List[str] = Field(default_factory=list)
    application_instructions: List[str] = Field(default_factory=list)
    captured_at: Optional[str] = None
    # Kanban board status. Free string (not a strict enum) so the UI's
    # column set can change without a schema migration; the board's
    # current columns are: saved, application_sent, initial_interview,
    # rejected, failed. Anything else falls back to the "saved" column.
    status: Optional[str] = "saved"
    # Set once a match is run against this posting — shown on the Kanban
    # card and used to decide whether a posting was worth saving at all.
    last_match_confidence: Optional[int] = None
    # Populated when you generate a resume/cover letter for this posting
    # from the UI, so re-opening the job later (the Kanban card's detail
    # view) shows what was actually sent, not just the job description.
    resume_text: Optional[str] = None
    cover_letter_text: Optional[str] = None


# Maps entity_type name -> pydantic model, used generically by ingest.py
ENTITY_MODELS = {
    "skill": Skill,
    "experience": Experience,
    "education": Education,
    "project": Project,
    "certification": Certification,
    "job_posting": JobPosting,
}
