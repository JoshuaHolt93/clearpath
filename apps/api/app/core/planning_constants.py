from __future__ import annotations

from datetime import date  # noqa: F401  (kept for parity with extracted tables that may reference it)

# Extracted verbatim from the Flask app's services.py (commit 9b5dff0) so the
# category groups and 2026 tax tables stay byte-identical to the source of
# truth. Do not hand-edit values here; re-extract when the Flask tables change.

STARTER_CATEGORY_GROUPS = [
    {
        "key": "home_expenses",
        "label": "Home Expenses",
        "description": "Mortgage, rent, insurance, utilities, communication, and upkeep for the home.",
        "categories": [
            ("Mortgage/Rent", "expense", 1800),
            ("Home/Rental Insurance", "expense", 150),
            ("Electricity", "expense", 150),
            ("Gas", "expense", 100),
            ("Water/Sewage/Trash", "expense", 100),
            ("Phone", "expense", 120),
            ("Internet", "expense", 80),
            ("Maintenance", "expense", 100),
        ],
        "aliases": {"housing", "mortgage", "rent", "utilities"},
        "keywords": ("home", "housing", "mortgage", "rent", "electric", "utility", "water", "sewage", "trash", "phone", "internet", "maintenance"),
    },
    {
        "key": "transportation",
        "label": "Transportation",
        "description": "Vehicle payments, insurance, fuel, public transit, rides, repairs, and registration.",
        "categories": [
            ("Vehicle Payments", "expense", 0),
            ("Auto Insurance", "expense", 150),
            ("Fuel/Gasoline", "expense", 220),
            ("Bus/Taxi", "expense", 0),
            ("Repairs", "expense", 75),
            ("Registration/License", "expense", 25),
        ],
        "aliases": {"transportation", "gas", "fuel", "auto", "car"},
        "keywords": ("vehicle", "auto", "fuel", "gas", "bus", "taxi", "transit", "repair", "registration", "license", "uber", "lyft"),
    },
    {
        "key": "charity_gifts",
        "label": "Charity/Donations/Gifts",
        "description": "Tithing, charitable donations, and gifts given.",
        "categories": [
            ("Tithing", "expense", 0),
            ("Charitable Donations", "expense", 0),
            ("Gifts Given", "expense", 0),
        ],
        "aliases": {"charity", "donations", "gifts"},
        "keywords": ("tith", "charit", "donation", "gift"),
    },
    {
        "key": "health_wellness",
        "label": "Health/Wellness",
        "description": "Insurance, medical care, prescriptions, life insurance, and fitness.",
        "categories": [
            ("Health Insurance", "expense", 250),
            ("Doctor/Dentist", "expense", 100),
            ("Medicine/Prescriptions", "expense", 75),
            ("Life Insurance", "expense", 75),
            ("Gym/Fitness", "expense", 50),
            ("Health Club Dues", "expense", 0),
        ],
        "aliases": {"healthcare", "health", "wellness", "fitness"},
        "keywords": ("health", "doctor", "dentist", "medicine", "prescription", "life insurance", "gym", "fitness", "wellness"),
    },
    {
        "key": "consumer_subscriptions",
        "label": "Consumer Subscriptions",
        "description": "Recurring consumer memberships, apps, services, and subscription tools.",
        "categories": [
            ("Consumer Subscriptions", "expense", 0),
        ],
        "aliases": {"subscriptions", "consumer subscriptions"},
        "keywords": ("subscription", "membership", "recurring"),
    },
    {
        "key": "daily_living",
        "label": "Daily Living",
        "description": "Groceries, supplies, clothing, cleaning, lessons, dining, grooming, pets, and laundry.",
        "categories": [
            ("Groceries", "expense", 600),
            ("Personal Supplies", "expense", 75),
            ("Clothing", "expense", 100),
            ("Cleaning", "expense", 40),
            ("Education/Lessons", "expense", 100),
            ("Dining/Eating Out", "expense", 300),
            ("Salon/Barber", "expense", 50),
            ("Pet Food", "expense", 75),
            ("Laundry", "expense", 25),
        ],
        "aliases": {"daily living", "groceries", "dining", "shopping"},
        "keywords": ("grocery", "groceries", "personal", "clothing", "cleaning", "lesson", "education", "dining", "restaurant", "salon", "barber", "pet", "laundry"),
    },
    {
        "key": "entertainment",
        "label": "Entertainment",
        "description": "Media, events, hobbies, sports, outdoor recreation, and vacation or travel.",
        "categories": [
            ("Rentals", "expense", 0),
            ("Music", "expense", 25),
            ("Books", "expense", 25),
            ("Streaming Services", "expense", 50),
            ("Movies/Theater/Concerts/Plays", "expense", 75),
            ("Hobbies", "expense", 75),
            ("Sports/Outdoor Recreation", "expense", 75),
            ("Vacation/Travel", "expense", 150),
        ],
        "aliases": {"entertainment", "travel"},
        "keywords": ("rental", "music", "book", "streaming", "movie", "theater", "concert", "play", "hobby", "sports", "outdoor", "vacation", "travel"),
    },
    {
        "key": "savings",
        "label": "Savings",
        "description": "Emergency savings, transfers to savings, retirement, investments, and education savings.",
        "categories": [
            ("Emergency Fund", "expense", 0),
            ("Transfer to Savings", "transfer", 0),
            ("Retirement (401k, IRA)", "expense", 0),
            ("Investments", "expense", 0),
            ("Education Savings", "expense", 0),
        ],
        "aliases": {"savings", "retirement", "investing", "investments"},
        "keywords": ("emergency", "savings", "retirement", "401k", "ira", "investment", "education savings"),
    },
    {
        "key": "debt_obligations",
        "label": "Debt/Obligations",
        "description": "Loans, credit cards, child care obligations, and federal, state, or local taxes.",
        "categories": [
            ("Student Loans", "expense", 0),
            ("Other Loan", "expense", 0),
            ("Credit Cards", "expense", 0),
            ("Credit Card Payments", "transfer", 0),
            ("Alimony/Child Care", "expense", 0),
            ("Federal Taxes", "expense", 0),
            ("State/Local Taxes", "expense", 0),
        ],
        "aliases": {"loan", "loans", "debt", "credit card", "taxes"},
        "keywords": ("student loan", "loan", "debt", "credit", "alimony", "child care", "federal tax", "state tax", "local tax"),
    },
    {
        "key": "miscellaneous",
        "label": "Miscellaneous",
        "description": "Bank fees and anything that does not fit cleanly elsewhere.",
        "categories": [
            ("Bank Fees", "expense", 0),
            ("Other", "expense", 200),
            ("Income", "income", 0),
            ("Transfers", "transfer", 0),
        ],
        "aliases": {"miscellaneous", "other", "bank fees"},
        "keywords": ("bank fee", "fee", "other", "misc"),
    },
]

STARTER_CATEGORIES = [
    {"name": name, "kind": kind, "monthly_target": monthly_target, "group_key": group["key"]}
    for group in STARTER_CATEGORY_GROUPS
    for name, kind, monthly_target in group["categories"]
]

LEGACY_DEFAULT_CATEGORIES = [
    ("Housing", "expense", 1800),
    ("Utilities", "expense", 280),
    ("Dining", "expense", 300),
    ("Gas", "expense", 220),
    ("Shopping", "expense", 200),
    ("Entertainment", "expense", 150),
    ("Healthcare", "expense", 200),
    ("Travel", "expense", 150),
    ("Income", "income", 0),
    ("Transfers", "transfer", 0),
]

DEFAULT_CATEGORY_TARGETS = {category["name"]: category["monthly_target"] for category in STARTER_CATEGORIES}
DEFAULT_CATEGORY_TARGETS.update({name: target for name, _kind, target in LEGACY_DEFAULT_CATEGORIES})

DEFAULT_APP_TIMEZONE = "America/New_York"
FIXED_EXPENSE_CATEGORY_NAMES = {"Housing", "Utilities", "Mortgage", "Loan", "Consumer Subscriptions"}
LOAN_CATEGORY_NAMES = {"Mortgage", "Mortgage/Rent", "Loan", "Vehicle Payments", "Student Loans", "Other Loan", "Credit Cards"}

INCOME_TYPE_OPTIONS = {
    "salary": "Salary",
    "hourly": "Hourly",
    "bonus": "Bonus/Other",
}

INCOME_BASIS_OPTIONS = {
    "take_home": "Take-Home Income",
    "gross": "Gross Income",
}

PAYCHECK_CADENCE_OPTIONS = {
    "annual": "Annually",
    "monthly": "Monthly",
    "semimonthly": "Twice Per Month",
    "biweekly": "Bi-Weekly",
    "weekly": "Weekly",
    "irregular": "Irregular",
}

TAX_FILING_STATUS_OPTIONS = {
    "single": "Single",
    "married_joint": "Married Filing Jointly",
    "married_separate": "Married Filing Separately",
    "head_of_household": "Head Of Household",
}

STANDARD_DEDUCTIONS_2026 = {
    "single": 16100,
    "married_joint": 32200,
    "married_separate": 16100,
    "head_of_household": 24150,
}

FEDERAL_TAX_BRACKETS_2026 = {
    "single": [
        (0, 12400, 0, 0.10),
        (12400, 50400, 1240, 0.12),
        (50400, 105700, 5800, 0.22),
        (105700, 201775, 17966, 0.24),
        (201775, 256225, 41024, 0.32),
        (256225, 640600, 58448, 0.35),
        (640600, None, 192979.25, 0.37),
    ],
    "head_of_household": [
        (0, 17700, 0, 0.10),
        (17700, 67450, 1770, 0.12),
        (67450, 105700, 7740, 0.22),
        (105700, 201750, 16155, 0.24),
        (201750, 256200, 39207, 0.32),
        (256200, 640600, 56631, 0.35),
        (640600, None, 191171, 0.37),
    ],
    "married_joint": [
        (0, 24800, 0, 0.10),
        (24800, 100800, 2480, 0.12),
        (100800, 211400, 11600, 0.22),
        (211400, 403550, 35932, 0.24),
        (403550, 512450, 82048, 0.32),
        (512450, 768700, 116896, 0.35),
        (768700, None, 206583.50, 0.37),
    ],
    "married_separate": [
        (0, 12400, 0, 0.10),
        (12400, 50400, 1240, 0.12),
        (50400, 105700, 5800, 0.22),
        (105700, 201775, 17966, 0.24),
        (201775, 256225, 41024, 0.32),
        (256225, 384350, 58448, 0.35),
        (384350, None, 103291.75, 0.37),
    ],
}

NO_WAGE_INCOME_TAX_STATES = {"AK", "FL", "NV", "NH", "SD", "TN", "TX", "WA", "WY"}
SOCIAL_SECURITY_RATE_2026 = 0.062
SOCIAL_SECURITY_WAGE_BASE_2026 = 184500
MEDICARE_RATE_2026 = 0.0145
ADDITIONAL_MEDICARE_RATE = 0.009
ADDITIONAL_MEDICARE_THRESHOLDS = {
    "single": 200000,
    "head_of_household": 200000,
    "married_joint": 250000,
    "married_separate": 125000,
}

STATE_TAX_SOURCE_URL = "https://taxfoundation.org/data/all/state/state-income-tax-rates-2026/"


def _state_rule(
    brackets: list[tuple[float, float]],
    single_deduction: float = 0,
    joint_deduction: float = 0,
    single_exemption: float = 0,
    joint_exemption: float = 0,
    single_credit: float = 0,
    joint_credit: float = 0,
    note: str = "2026 state wage income tax estimate; local taxes, custom allowances, credits, and employer-specific withholding elections are not included.",
    joint_brackets: list[tuple[float, float]] | None = None,
) -> dict:
    return {
        "type": "bracket",
        "brackets": brackets,
        "joint_brackets": joint_brackets or brackets,
        "single_deduction": single_deduction,
        "joint_deduction": joint_deduction,
        "single_exemption": single_exemption,
        "joint_exemption": joint_exemption,
        "single_credit": single_credit,
        "joint_credit": joint_credit,
        "note": note,
        "source_url": STATE_TAX_SOURCE_URL,
    }


def _no_wage_tax_rule(note: str = "No broad state wage income tax is applied to paycheck income.") -> dict:
    return {
        "type": "none",
        "brackets": [],
        "single_deduction": 0,
        "joint_deduction": 0,
        "single_exemption": 0,
        "joint_exemption": 0,
        "single_credit": 0,
        "joint_credit": 0,
        "note": note,
        "source_url": STATE_TAX_SOURCE_URL,
    }


STATE_TAX_RULES_2026 = {
    "AL": _state_rule([(0, 0.02), (500, 0.04), (3000, 0.05)], 3000, 8500, 1500, 3000, joint_brackets=[(0, 0.02), (1000, 0.04), (6000, 0.05)]),
    "AK": _no_wage_tax_rule(),
    "AZ": _state_rule([(0, 0.025)], 8350, 16700),
    "AR": _state_rule([(0, 0.02), (4600, 0.039)], 2470, 4940, single_credit=29, joint_credit=58),
    "CA": _state_rule(
        [(0, 0.01), (11079, 0.02), (26264, 0.04), (41452, 0.06), (57542, 0.08), (72724, 0.093), (371479, 0.103), (445771, 0.113), (742953, 0.123), (1000000, 0.133)],
        5540,
        11080,
        single_credit=153,
        joint_credit=306,
        joint_brackets=[(0, 0.01), (22158, 0.02), (52528, 0.04), (82904, 0.06), (115084, 0.08), (145448, 0.093), (742958, 0.103), (891542, 0.113), (1000000, 0.123), (1485906, 0.133)],
    ),
    "CO": _state_rule([(0, 0.044)], 16100, 32200),
    "CT": _state_rule([(0, 0.02), (10000, 0.045), (50000, 0.055), (100000, 0.06), (200000, 0.065), (250000, 0.069), (500000, 0.0699)], 0, 0, 15000, 24000, joint_brackets=[(0, 0.02), (20000, 0.045), (100000, 0.055), (200000, 0.06), (400000, 0.065), (500000, 0.069), (1000000, 0.0699)]),
    "DE": _state_rule([(2000, 0.022), (5000, 0.039), (10000, 0.048), (20000, 0.052), (25000, 0.0555), (60000, 0.066)], 3250, 6500, single_credit=110, joint_credit=220),
    "FL": _no_wage_tax_rule(),
    "GA": _state_rule([(0, 0.0519)], 12000, 24000),
    "HI": _state_rule(
        [(0, 0.014), (9600, 0.032), (14400, 0.055), (19200, 0.064), (24000, 0.068), (36000, 0.072), (48000, 0.076), (125000, 0.079), (175000, 0.0825), (225000, 0.09), (275000, 0.10), (325000, 0.11)],
        4400,
        8800,
        1144,
        2288,
        joint_brackets=[(0, 0.014), (19200, 0.032), (28800, 0.055), (38400, 0.064), (48000, 0.068), (72000, 0.072), (96000, 0.076), (250000, 0.079), (350000, 0.0825), (450000, 0.09), (550000, 0.10), (650000, 0.11)],
    ),
    "ID": _state_rule([(4811, 0.053)], 16100, 32200, joint_brackets=[(9622, 0.053)]),
    "IL": _state_rule([(0, 0.0495)], 0, 0, 2925, 5850),
    "IN": _state_rule([(0, 0.0295)], 0, 0, 1000, 2000),
    "IA": _state_rule([(0, 0.038)], 16100, 32200, single_credit=40, joint_credit=80),
    "KS": _state_rule([(0, 0.052), (23000, 0.0558)], 3605, 8240, 9160, 18320, joint_brackets=[(0, 0.052), (46000, 0.0558)]),
    "KY": _state_rule([(0, 0.035)], 3360, 3360),
    "LA": _state_rule([(0, 0.03)], 12875, 25750),
    "ME": _state_rule([(0, 0.058), (27399, 0.0675), (64849, 0.0715)], 8350, 16700, 5300, 10600, joint_brackets=[(0, 0.058), (54849, 0.0675), (129749, 0.0715)]),
    "MD": _state_rule([(0, 0.02), (1000, 0.03), (2000, 0.04), (3000, 0.0475), (100000, 0.05), (125000, 0.0525), (150000, 0.055), (250000, 0.0575), (500000, 0.0625), (1000000, 0.065)], 3350, 6700, 3200, 6400, joint_brackets=[(0, 0.02), (1000, 0.03), (2000, 0.04), (3000, 0.0475), (150000, 0.05), (175000, 0.0525), (225000, 0.055), (300000, 0.0575), (600000, 0.0625), (1200000, 0.065)]),
    "MA": _state_rule([(0, 0.05), (1083150, 0.09)], 0, 0, 4400, 8800),
    "MI": _state_rule([(0, 0.0425)], 0, 0, 5900, 11800),
    "MN": _state_rule([(0, 0.0535), (33310, 0.068), (109430, 0.0785), (203150, 0.0985)], 15300, 30600, joint_brackets=[(0, 0.0535), (48700, 0.068), (193480, 0.0785), (337930, 0.0985)]),
    "MS": _state_rule([(10000, 0.04)], 2300, 4600, 6000, 12000),
    "MO": _state_rule([(1348, 0.02), (2696, 0.025), (4044, 0.03), (5392, 0.035), (6740, 0.04), (8088, 0.045), (9436, 0.047)], 16100, 32200),
    "MT": _state_rule([(0, 0.047), (47500, 0.0565)], 16100, 32200, joint_brackets=[(0, 0.047), (95000, 0.0565)]),
    "NE": _state_rule([(0, 0.0246), (4130, 0.0351), (24760, 0.0455)], 8850, 17700, single_credit=176, joint_credit=352, joint_brackets=[(0, 0.0246), (8250, 0.0351), (49530, 0.0455)]),
    "NV": _no_wage_tax_rule(),
    "NH": _no_wage_tax_rule(),
    "NJ": _state_rule(
        [(0, 0.014), (20000, 0.0175), (35000, 0.035), (40000, 0.0553), (75000, 0.0637), (500000, 0.0897), (1000000, 0.1075)],
        0,
        0,
        1000,
        2000,
        joint_brackets=[(0, 0.014), (20000, 0.0175), (50000, 0.0245), (70000, 0.035), (80000, 0.0553), (150000, 0.0637), (500000, 0.0897), (1000000, 0.1075)],
    ),
    "NM": _state_rule([(0, 0.015), (5500, 0.032), (16500, 0.043), (33500, 0.047), (66500, 0.049), (210000, 0.059)], 16100, 32200, joint_brackets=[(0, 0.015), (8000, 0.032), (25000, 0.043), (50000, 0.047), (100000, 0.049), (315000, 0.059)]),
    "NY": _state_rule([(0, 0.039), (8500, 0.044), (11700, 0.0515), (13900, 0.054), (80650, 0.059), (215400, 0.0685), (1077550, 0.0965), (5000000, 0.103), (25000000, 0.109)], 8000, 16050, joint_brackets=[(0, 0.039), (17150, 0.044), (23600, 0.0515), (27900, 0.054), (161550, 0.059), (323200, 0.0685), (2155350, 0.0965), (5000000, 0.103), (25000000, 0.109)]),
    "NC": _state_rule([(0, 0.0399)], 12750, 25500),
    "ND": _state_rule([(48475, 0.0195), (244825, 0.025)], 16100, 32200, joint_brackets=[(80975, 0.0195), (298075, 0.025)]),
    "OH": _state_rule([(26050, 0.0275)], 0, 0, 2400, 4800),
    "OK": _state_rule([(3750, 0.025), (4900, 0.035), (7200, 0.045)], 6350, 12700, 1000, 2000, joint_brackets=[(7500, 0.025), (9800, 0.035), (14400, 0.045)]),
    "OR": _state_rule([(0, 0.0475), (4550, 0.0675), (11400, 0.0875), (125000, 0.099)], 2910, 5820, single_credit=256, joint_credit=512, joint_brackets=[(0, 0.0475), (9100, 0.0675), (22800, 0.0875), (250000, 0.099)]),
    "PA": _state_rule([(0, 0.0307)]),
    "RI": _state_rule([(0, 0.0375), (82050, 0.0475), (186450, 0.0599)], 11200, 22400, 5250, 10500),
    "SC": _state_rule([(0, 0), (3640, 0.03), (18230, 0.06)], 8350, 16700),
    "SD": _no_wage_tax_rule(),
    "TN": _no_wage_tax_rule(),
    "TX": _no_wage_tax_rule(),
    "UT": _state_rule([(0, 0.045)], single_credit=966, joint_credit=1932),
    "VT": _state_rule([(0, 0.0335), (49400, 0.066), (119700, 0.076), (249700, 0.0875)], 7650, 15300, 5300, 10600, joint_brackets=[(0, 0.0335), (82500, 0.066), (199450, 0.076), (304000, 0.0875)]),
    "VA": _state_rule([(0, 0.02), (3000, 0.03), (5000, 0.05), (17000, 0.0575)], 8750, 17500, 930, 1860),
    "WA": _no_wage_tax_rule("Washington taxes certain high capital gains, but no broad state wage income tax is applied to paycheck income."),
    "WV": _state_rule([(0, 0.0222), (10000, 0.0296), (25000, 0.0333), (40000, 0.0444), (60000, 0.0482)], 0, 0, 2000, 4000),
    "WI": _state_rule([(0, 0.035), (15110, 0.044), (51950, 0.053), (332720, 0.0765)], 13960, 25840, 700, 1400, joint_brackets=[(0, 0.035), (20150, 0.044), (69260, 0.053), (443630, 0.0765)]),
    "WY": _no_wage_tax_rule(),
    "DC": _state_rule([(0, 0.04), (10000, 0.06), (40000, 0.065), (60000, 0.085), (250000, 0.0925), (500000, 0.0975), (1000000, 0.1075)], 16100, 32200),
}

STATE_OPTIONS = {
    "": "Select State",
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District Of Columbia",
}

CASH_ACCOUNT_TYPES = {
    "cash",
    "cash management",
    "cash_management",
    "checking",
    "savings",
    "money market",
    "money_market",
    "prepaid",
    "depository",
}

LIABILITY_ACCOUNT_TYPES = {
    "auto",
    "business",
    "commercial",
    "construction",
    "consumer",
    "credit",
    "credit card",
    "credit_card",
    "debt",
    "heloc",
    "home equity",
    "home_equity",
    "line of credit",
    "line_of_credit",
    "loan",
    "loans",
    "mortgage",
    "overdraft",
    "student",
    "student loan",
    "student_loan",
    "personal loan",
    "personal_loan",
    "liability",
    "liabilities",
}

LIABILITY_ACCOUNT_LABEL_KEYWORDS = {
    "auto loan",
    "car loan",
    "card account",
    "charge card",
    "credit card",
    "citi double cash",
    "custom cash card",
    "double cash card",
    "home equity",
    "home equity line",
    "heloc",
    "line of credit",
    "loan account",
    "mortgage",
    "personal loan",
    "student loan",
    "vehicle loan",
}

RECURRING_FREQUENCY_OPTIONS = {
    "weekly": "Weekly",
    "biweekly": "Bi-Weekly",
    "monthly": "Monthly",
    "semimonthly": "Twice Per Month",
    "quarterly": "Quarterly",
    "annual": "Annual",
}

WEEKDAY_OPTIONS = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}

MONTHLY_WEEK_OPTIONS = {
    1: "1st",
    2: "2nd",
    3: "3rd",
    4: "4th",
    5: "Last",
}

ANALYTICS_RANGE_OPTIONS = {
    "month": "Month",
    "quarter": "Quarter",
    "six_months": "6 Months",
    "year": "1 Year",
}



# Added by Flask cf17a56 ("Refine transaction budget link and credit tracking").
ACCOUNT_CLASSIFICATION_OPTIONS = (
    ("checking", "Checking / Cash"),
    ("savings", "Savings"),
    ("depository", "Depository / Bank Account"),
    ("money market", "Money Market"),
    ("credit", "Credit Account"),
    ("credit card", "Credit Card"),
    ("line of credit", "Line of Credit"),
    ("loan", "Loan"),
    ("mortgage", "Mortgage"),
    ("investment", "Investment"),
    ("other", "Other Asset"),
)

REVOLVING_DEBT_ACCOUNT_TYPES = {
    "credit",
    "credit card",
    "credit_card",
    "heloc",
    "home equity",
    "home_equity",
    "line of credit",
    "line_of_credit",
    "overdraft",
}
