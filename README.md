# Voice Restaurant Assistant

Customer speaks -> **STT** -> **LLM** understands intent -> **agent calls a tool** (search / book / cancel) -> **TTS** speaks the answer.

Stack: Python, FastAPI, SQLite, an LLM with tool use (Anthropic API), faster-whisper (STT), gTTS (TTS).

```
restaurant_voice_agent/
├── data/restaurants.csv        1,000 synthetic restaurants (generated)
├── schema.sql                  SQLite schema (restaurants, restaurant_financials, reservations)
├── restaurants.db              ready-to-use database built from the CSV
├── app/
│   ├── main.py                 FastAPI: /voice, /chat, REST endpoints, test page
│   ├── agent.py                LLM loop + system prompt + session memory
│   ├── tools.py                search / details / availability / reserve / lookup / cancel
│   ├── voice.py                speech_to_text(), text_to_speech()
│   ├── db.py, config.py
├── scripts/
│   ├── generate_dataset.py     regenerate the CSV (seeded, reproducible)
│   ├── init_db.py              CSV -> SQLite (safe to re-run)
│   ├── test_tools.py           30 no-AI tests of the booking logic
│   └── chat_cli.py             talk to the agent in the terminal
└── static/index.html           push-to-talk test page
```

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # then put your ANTHROPIC_API_KEY in it

python scripts/init_db.py          # (restaurants.db is already included; re-run to reload the CSV)
python scripts/test_tools.py       # step 1: verify tools with no AI
python scripts/chat_cli.py         # step 2: text conversation with the agent
uvicorn app.main:app --reload      # step 3: API + voice page at http://127.0.0.1:8000
```

Browsers only allow the microphone on `localhost` or HTTPS.

## Try the API

```bash
curl "localhost:8000/restaurants?city=Pune&cuisine=Italian&min_rating=4"

curl -X POST localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"message":"Find me a good Italian place in Pune and book a table for 2 tomorrow at 8 pm"}'
# reuse the returned session_id so the agent remembers the conversation
```

Interactive docs: http://127.0.0.1:8000/docs

## Dataset columns (`data/restaurants.csv`)

| Column | Notes |
|---|---|
| restaurant_id | Unique, e.g. `PUN-0003` (city prefix + row number) |
| restaurant_name | Chains like "Burger Hub" repeat across cities on purpose |
| city, area | 10 Indian cities, ~50 neighbourhoods |
| cuisine | 16 cuisines |
| price_range | Budget / Mid-range / Premium / Luxury |
| rating | 2.0-5.0 |
| review_count | Heavy-tailed; grows with restaurant age |
| avg_meal_price | INR per person; driven by tier x cuisine x city |
| seating_capacity | Driven by venue type (kiosk, cafe, restaurant, banquet) |
| delivery_available | Yes / No |
| opening_year | 1985-2025 |
| monthly_revenue, operating_costs | INR; revenue ~ seats x occupancy x turns x price |

Built in: ~2-7% missing values in rating, review_count, avg_meal_price, seating_capacity,
opening_year, revenue, costs and area; six deliberate outliers (a ₹9,500/person fine-dining place,
a 950-seat banquet hall, a 62,000-review viral spot, a deep loss-maker, a 4-seat kiosk, a legacy
place with 38,500 reviews). Change `SEED` or `N` in `generate_dataset.py` for a different sample.

## Design decisions worth knowing

- **Revenue and costs live in a separate table** (`restaurant_financials`) and are never returned by any tool,
  so the voice agent can't leak them. Use them for analytics.
- **Missing values** stay `NULL` in the database. Tools return `rating_text: "not rated yet"` and the
  system prompt tells the LLM not to read out nulls. Missing seating capacity falls back to 40 for booking only.
- **Availability model:** only 60% of seats are bookable in advance (rest = walk-ins); a party holds its seats
  for 90 minutes; bookings are 11:00-23:00, up to 60 days ahead, parties up to 20. Edit these in `app/config.py`.
- **No double-booking:** `create_reservation` re-checks seats inside a `BEGIN IMMEDIATE` write transaction.
- **Cancel/lookup need the confirmation code + last 4 phone digits**, and wrong answers look identical to "not found".
- **The LLM never touches the database directly**, only through the tools in `tools.py`.
- Sessions are kept in memory (lost on restart, single process). For production use Redis or a DB table.

## Known limitations / next steps

- gTTS needs internet and sounds robotic; swap `text_to_speech()` for Azure, ElevenLabs or Piper for quality.
- Whisper `base` is fast but imperfect on accents; try `small` or set `STT_LANGUAGE`.
- No auth, rate limiting or SMS confirmation yet.
- Latency is STT + LLM + TTS in sequence. Streaming each stage is the main optimisation.
