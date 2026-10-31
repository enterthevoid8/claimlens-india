"""Synthetic world: procedures, hospitals, cities, item prices.

Everything here is invented. Prices are plausible-looking but are *not* real tariffs; the reference
price book derived from this catalog is a stand-in for one built from an insurer's historical bills.
"""

from __future__ import annotations

from dataclasses import dataclass, field

CITY_MULTIPLIER: dict[str, float] = {
    "Mumbai": 1.25,
    "Delhi": 1.2,
    "Bengaluru": 1.15,
    "Hyderabad": 1.05,
    "Chennai": 1.05,
    "Pune": 1.0,
    "Ahmedabad": 0.95,
    "Jaipur": 0.85,
    "Lucknow": 0.8,
    "Indore": 0.8,
    "Nagpur": 0.75,
    "Patna": 0.7,
}
CITY_TIER: dict[str, int] = {
    c: (1 if m >= 1.15 else 2 if m >= 0.85 else 3) for c, m in CITY_MULTIPLIER.items()
}

ROOMS: dict[str, tuple[str, float]] = {
    "room_general": ("Room rent - General ward", 1500),
    "room_semi": ("Room rent - Semi private", 3000),
    "room_private": ("Room rent - Private", 5000),
    "room_deluxe": ("Room rent - Deluxe suite", 8500),
}
ROOM_LABEL = {
    "room_general": "General ward",
    "room_semi": "Semi private",
    "room_private": "Private",
    "room_deluxe": "Deluxe suite",
}

# generic per-unit items: key -> (display names, base price, category)
GENERIC_ITEMS: dict[str, tuple[list[str], float, str]] = {
    "icu": (["ICU charges", "Intensive care unit charges"], 9000, "icu"),
    "nursing": (["Nursing charges", "Nursing care charges"], 700, "nursing"),
    "doctor_visit": (["Doctor visit charges", "Consultant visit charges"], 900, "doctor_fee"),
    "registration": (["Registration and admission fee"], 500, "admin"),
    "documentation": (["Documentation charges"], 300, "admin"),
    "inj_ceftriaxone": (["Injection Ceftriaxone 1g"], 85, "medicine"),
    "inj_pantoprazole": (["Injection Pantoprazole 40mg"], 70, "medicine"),
    "iv_fluid": (["IV fluids NS 500ml", "IV fluid - Normal saline 500ml"], 60, "medicine"),
    "tab_paracetamol": (["Tablet Paracetamol 650mg"], 3, "medicine"),
    "pharmacy": (["Pharmacy - medicines", "Medicines and drugs"], 1800, "medicine"),
    "cbc": (["CBC (complete blood count)"], 350, "diagnostic"),
    "crp": (["CRP test"], 600, "diagnostic"),
    "xray_chest": (["X-ray chest"], 500, "diagnostic"),
    "usg_abdomen": (["USG abdomen"], 1100, "diagnostic"),
    "ct_scan": (["CT scan"], 5500, "diagnostic"),
    "mri": (["MRI scan"], 9000, "diagnostic"),
    "ecg": (["ECG"], 400, "diagnostic"),
    "echo": (["2D Echo"], 2200, "diagnostic"),
    "creatinine": (["Serum creatinine"], 300, "diagnostic"),
    "hba1c": (["HbA1c test"], 650, "diagnostic"),
    "dengue_ns1": (["Dengue NS1 antigen"], 900, "diagnostic"),
}

# procedure-linked items: key suffix -> (label, share of procedure base cost, category)
PROC_ITEMS: dict[str, tuple[str, float, str]] = {
    "surgeon": ("Surgeon fee", 0.24, "surgeon"),
    "anaesthesia": ("Anaesthesia charges", 0.09, "anaesthesia"),
    "ot": ("Operation theatre charges", 0.12, "ot"),
    "consumables": ("Surgical consumables kit", 0.08, "consumable"),
    "implant": ("Implant charges", 0.30, "procedure"),
}
PACKAGE_LABEL = "Surgical package (all inclusive)"


@dataclass(frozen=True)
class Procedure:
    key: str
    diagnosis: str
    procedure: str
    kind: str  # surgical | medical | daycare
    los: tuple[int, int]
    base: float
    emergency_prob: float = 0.0
    accident: bool = False
    chronic_years: tuple[int, int] | None = None  # history range if chronic
    chronic_note: str = ""
    implant: bool = False
    icu_prob: float = 0.0
    diagnostics: tuple[str, ...] = ("cbc",)
    medicines: tuple[str, ...] = ("pharmacy",)


PROCEDURES: list[Procedure] = [
    Procedure(
        "appendectomy",
        "Acute appendicitis",
        "Laparoscopic appendectomy",
        "surgical",
        (2, 4),
        60000,
        0.9,
        diagnostics=("cbc", "usg_abdomen", "crp"),
        medicines=("inj_ceftriaxone", "inj_pantoprazole", "iv_fluid"),
    ),
    Procedure(
        "cataract",
        "Senile cataract",
        "Phacoemulsification with IOL",
        "daycare",
        (0, 1),
        28000,
        implant=True,
        diagnostics=("cbc",),
        medicines=("pharmacy",),
    ),
    Procedure(
        "hernia",
        "Inguinal hernia",
        "Hernioplasty (mesh repair)",
        "surgical",
        (1, 3),
        55000,
        implant=True,
        diagnostics=("cbc", "usg_abdomen"),
        medicines=("inj_ceftriaxone", "iv_fluid"),
    ),
    Procedure(
        "lithotripsy",
        "Renal calculus",
        "Ureteroscopic lithotripsy",
        "surgical",
        (1, 3),
        70000,
        0.3,
        diagnostics=("cbc", "usg_abdomen", "creatinine"),
        medicines=("inj_ceftriaxone", "iv_fluid"),
    ),
    Procedure(
        "tkr",
        "Knee osteoarthritis",
        "Total knee replacement",
        "surgical",
        (4, 7),
        230000,
        0.0,
        chronic_years=(3, 12),
        chronic_note="Osteoarthritis knee",
        implant=True,
        diagnostics=("cbc", "xray_chest", "ecg", "mri"),
        medicines=("inj_ceftriaxone", "inj_pantoprazole", "iv_fluid"),
    ),
    Procedure(
        "dengue",
        "Dengue fever",
        "Medical management",
        "medical",
        (3, 6),
        45000,
        0.7,
        diagnostics=("cbc", "dengue_ns1", "crp"),
        medicines=("inj_pantoprazole", "iv_fluid", "tab_paracetamol"),
    ),
    Procedure(
        "pneumonia",
        "Viral pneumonia",
        "Medical management",
        "medical",
        (4, 8),
        58000,
        0.8,
        icu_prob=0.15,
        diagnostics=("cbc", "xray_chest", "crp", "ct_scan"),
        medicines=("inj_ceftriaxone", "iv_fluid", "pharmacy"),
    ),
    Procedure(
        "gastro",
        "Acute gastroenteritis",
        "Medical management",
        "medical",
        (2, 4),
        26000,
        0.8,
        diagnostics=("cbc", "creatinine"),
        medicines=("iv_fluid", "inj_pantoprazole"),
    ),
    Procedure(
        "angioplasty",
        "Coronary artery disease",
        "Angioplasty with stent",
        "surgical",
        (3, 5),
        290000,
        0.5,
        chronic_years=(1, 10),
        chronic_note="Coronary artery disease",
        implant=True,
        icu_prob=0.6,
        diagnostics=("cbc", "ecg", "echo", "creatinine"),
        medicines=("pharmacy", "iv_fluid"),
    ),
    Procedure(
        "dka",
        "Type 2 diabetes mellitus with ketoacidosis",
        "Medical management",
        "medical",
        (4, 7),
        62000,
        0.9,
        chronic_years=(1, 15),
        chronic_note="Type 2 diabetes mellitus",
        icu_prob=0.4,
        diagnostics=("cbc", "hba1c", "creatinine", "ecg"),
        medicines=("iv_fluid", "pharmacy", "inj_pantoprazole"),
    ),
    Procedure(
        "orif_femur",
        "Fracture shaft of femur",
        "ORIF with intramedullary nail",
        "surgical",
        (5, 9),
        190000,
        1.0,
        accident=True,
        implant=True,
        diagnostics=("cbc", "xray_chest", "ct_scan"),
        medicines=("inj_ceftriaxone", "inj_pantoprazole", "iv_fluid"),
    ),
    Procedure(
        "hysterectomy",
        "Uterine fibroid",
        "Total laparoscopic hysterectomy",
        "surgical",
        (3, 5),
        115000,
        0.05,
        diagnostics=("cbc", "usg_abdomen", "hba1c"),
        medicines=("inj_ceftriaxone", "iv_fluid"),
    ),
    Procedure(
        "rhinoplasty",
        "Nasal deformity",
        "Cosmetic rhinoplasty",
        "surgical",
        (1, 2),
        150000,
        diagnostics=("cbc",),
        medicines=("pharmacy",),
    ),
    Procedure(
        "rootcanal",
        "Dental caries",
        "Root canal treatment (dental)",
        "daycare",
        (0, 0),
        16000,
        diagnostics=("cbc",),
        medicines=("pharmacy",),
    ),
    Procedure(
        "normal_delivery",
        "Pregnancy at term",
        "Normal delivery",
        "medical",
        (2, 3),
        42000,
        0.6,
        diagnostics=("cbc", "usg_abdomen"),
        medicines=("pharmacy", "iv_fluid"),
    ),
    Procedure(
        "tonsillectomy",
        "Chronic tonsillitis",
        "Tonsillectomy",
        "surgical",
        (1, 2),
        42000,
        diagnostics=("cbc",),
        medicines=("inj_ceftriaxone", "iv_fluid"),
    ),
    Procedure(
        "htn_crisis",
        "Hypertensive crisis",
        "Medical management",
        "medical",
        (2, 4),
        36000,
        0.9,
        chronic_years=(2, 18),
        chronic_note="Hypertension",
        diagnostics=("cbc", "ecg", "creatinine", "echo"),
        medicines=("pharmacy", "iv_fluid"),
    ),
    Procedure(
        "typhoid",
        "Typhoid fever",
        "Medical management",
        "medical",
        (3, 5),
        30000,
        0.6,
        diagnostics=("cbc", "crp"),
        medicines=("inj_ceftriaxone", "iv_fluid", "tab_paracetamol"),
    ),
    Procedure(
        "head_injury",
        "Head injury following road traffic accident",
        "Observation and conservative management",
        "medical",
        (3, 5),
        95000,
        1.0,
        accident=True,
        icu_prob=0.4,
        diagnostics=("cbc", "ct_scan", "xray_chest"),
        medicines=("inj_pantoprazole", "iv_fluid", "pharmacy"),
    ),
]

HOSPITAL_WORDS_A = [
    "Sunrise",
    "Lotus",
    "Metro",
    "Greenfield",
    "Riverside",
    "Crescent",
    "Evergreen",
    "Harmony",
    "Pinnacle",
    "Orchid",
    "Silverline",
    "Banyan",
    "Cedar",
    "Maple",
    "Zenith",
    "Aster",
    "Coral",
    "Summit",
]
HOSPITAL_WORDS_B = [
    "Care Hospital",
    "Multispeciality Hospital",
    "Medical Centre",
    "Institute of Medical Sciences",
    "Healthcare",
    "General Hospital",
    "Heart and Surgical Centre",
    "Super Speciality Hospital",
]
FIRST_NAMES = [
    "Aarav",
    "Vivaan",
    "Aditya",
    "Rohan",
    "Karan",
    "Neha",
    "Priya",
    "Anjali",
    "Sneha",
    "Pooja",
    "Rahul",
    "Amit",
    "Sunita",
    "Meera",
    "Vikram",
    "Deepa",
    "Arjun",
    "Kavita",
    "Manoj",
    "Ritu",
]
LAST_NAMES = [
    "Sharma",
    "Verma",
    "Iyer",
    "Nair",
    "Patel",
    "Reddy",
    "Singh",
    "Gupta",
    "Mehta",
    "Joshi",
    "Kulkarni",
    "Das",
    "Bose",
    "Khan",
    "Rao",
    "Chopra",
    "Saini",
    "Menon",
]
DOCTORS = [
    "Dr. R. Menon",
    "Dr. S. Kapoor",
    "Dr. A. Banerjee",
    "Dr. P. Deshmukh",
    "Dr. N. Hegde",
    "Dr. K. Fernandes",
]


@dataclass
class Hospital:
    hospital_id: str
    name: str
    city: str
    layout: str  # pipe | columns | narrative
    date_fmt: str
    keys: dict[str, str]
    total_label: str
    propensity: (
        float  # latent: how often this hospital's claims get queried (not directly observable)
    )
    price_level: float = 1.0  # latent: pricing tendency vs peers
    extra: dict[str, str] = field(default_factory=dict)
