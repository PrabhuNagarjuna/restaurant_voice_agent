import os
from pathlib import Path

try:  # optional: load a local .env file
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "restaurants.db"))

# Booking rules
DEFAULT_SEATING = 40        # used when seating_capacity is missing in the data
ONLINE_SHARE = 0.60         # share of seats that can be reserved ahead (rest = walk-ins)
SLOT_MINUTES = 90           # how long a party occupies a table
OPEN_MINUTE = 11 * 60       # earliest booking 11:00
LAST_BOOKING_MINUTE = 23 * 60   # latest booking 23:00
MAX_ADVANCE_DAYS = 60
MAX_PARTY_SIZE = 20

# LLM / voice
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")       # tiny | base | small | medium
STT_LANGUAGE = os.getenv("STT_LANGUAGE") or None         # e.g. "en", "hi"; None = auto-detect
TTS_LANG = os.getenv("TTS_LANG", "en")
TTS_TLD = os.getenv("TTS_TLD", "co.in")                  # Indian English accent
