"""Column names of a therapy-session record, as read from the therapy_sessions view."""

SESSION_ID = "session_id"
USER_ID = "user_id"
STARTED_AT = "started_at"
ZONE = "zone"
TEMPERATURE = "temperature_c"
DURATION = "duration_min"
MODE = "therapy_mode"
PAIN_ZONE = "pain_zone"
PAIN_BEFORE = "pain_before"
PAIN_AFTER = "pain_after"
CYCLE_DAY = "cycle_day"
CYCLE_PHASE = "cycle_phase"
END_REASON = "end_reason"

# Derived
PAIN_REDUCTION = "pain_reduction"

REQUIRED_COLUMNS: tuple[str, ...] = (
    USER_ID,
    STARTED_AT,
    ZONE,
    TEMPERATURE,
    DURATION,
    MODE,
    PAIN_BEFORE,
    PAIN_AFTER,
)
OPTIONAL_COLUMNS: tuple[str, ...] = (SESSION_ID, PAIN_ZONE, CYCLE_DAY, CYCLE_PHASE, END_REASON)

CYCLE_PHASES: tuple[str, ...] = ("menstrual", "follicular", "ovulatory", "luteal", "unknown")

# Sessions cut short by a device fault or lost connection say little about how
# well the setting worked, so they are left out of training and history.
EXCLUDED_END_REASONS: frozenset[str] = frozenset({"fault", "connection_lost"})

PAIN_MIN, PAIN_MAX = 0, 10
