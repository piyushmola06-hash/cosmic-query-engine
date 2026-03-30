"""Constants for the collection app (S-01, S-02, S-03)."""

# ── Collection steps ──────────────────────────────────────────────────────────

STEP_QUERY = "query"
STEP_ICHING_OPTIN = "iching_optin"
STEP_DOB = "dob"
STEP_DOB_CONFIRM = "dob_confirm"
STEP_BIRTH_TIME = "birth_time"
STEP_BIRTH_TIME_CONFIRM = "birth_time_confirm"
STEP_BIRTH_LOCATION = "birth_location"
STEP_BIRTH_LOCATION_COUNTRY = "birth_location_country"
STEP_FULL_BIRTH_NAME = "full_birth_name"
STEP_CURRENT_NAME = "current_name"
STEP_GENDER = "gender"
STEP_COMPLETE = "complete"

ORDERED_STEPS = [
    STEP_QUERY,
    STEP_ICHING_OPTIN,
    STEP_DOB,
    STEP_BIRTH_TIME,
    STEP_BIRTH_LOCATION,
    STEP_FULL_BIRTH_NAME,
    STEP_CURRENT_NAME,
    STEP_GENDER,
]

# ── Birth time tier values ─────────────────────────────────────────────────────

TIER_EXACT = "exact"
TIER_APPROXIMATE = "approximate"
TIER_NONE = "none"

# ── Approximate time window mapping (from S-02 contract) ──────────────────────
# Each entry: (frozenset of trigger phrases, window_start HH:MM, window_end HH:MM)

APPROXIMATE_TIME_WINDOWS: list[tuple[frozenset[str], str, str]] = [
    (frozenset({"dawn", "early morning", "before sunrise"}), "04:00", "06:00"),
    (frozenset({"morning", "in the morning"}), "06:00", "09:00"),
    (frozenset({"late morning", "before noon"}), "09:00", "12:00"),
    (frozenset({"noon", "around noon", "midday"}), "11:00", "13:00"),
    (frozenset({"afternoon", "in the afternoon"}), "12:00", "15:00"),
    (frozenset({"late afternoon", "evening started"}), "15:00", "18:00"),
    (frozenset({"evening", "in the evening", "after sunset"}), "18:00", "21:00"),
    (frozenset({"night", "at night"}), "21:00", "00:00"),
    (frozenset({"late night", "past midnight", "early hours"}), "00:00", "04:00"),
]

# ── Active heads ──────────────────────────────────────────────────────────────

MANDATORY_HEADS = ["vedic", "western", "numerology", "chinese", "philosophy"]
OPTIONAL_HEAD_ICHING = "iching"

# ── Rephrase attempt limit ────────────────────────────────────────────────────

MAX_REPHRASE_ATTEMPTS = 1
