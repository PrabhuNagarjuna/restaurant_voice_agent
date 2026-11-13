"""
Business-logic tools the LLM agent can call. Plain Python + SQLite, no AI inside,
so they can be unit-tested and reused by REST endpoints.

Every tool returns a JSON-serialisable dict. Failures return
{"success": False, "error_code": ..., "error": "human-readable message"} instead of
raising, so the LLM can read the problem and explain it to the customer.
"""
import re
import secrets
from datetime import date, datetime, timedelta

from . import config
from .db import connection

# ----------------------------------------------------------------------------- helpers

PRICE_ALIASES = {
    "cheap": "Budget", "budget": "Budget", "inexpensive": "Budget", "affordable": "Budget",
    "mid": "Mid-range", "mid-range": "Mid-range", "midrange": "Mid-range", "moderate": "Mid-range",
    "premium": "Premium", "expensive": "Premium", "upscale": "Premium",
    "luxury": "Luxury", "fine dining": "Luxury",
}
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/L: easy to say aloud


def _err(code: str, msg: str, **extra) -> dict:
    return {"success": False, "error_code": code, "error": msg, **extra}


def _rating_text(rating, reviews) -> str:
    if rating is None:
        return "not rated yet"
    if reviews:
        return f"{rating:.1f} out of 5 from about {reviews} reviews"
    return f"{rating:.1f} out of 5"


def _public(row) -> dict:
    """Customer-facing view of a restaurant row (never includes financials)."""
    return {
        "restaurant_id": row["restaurant_id"],
        "name": row["name"],
        "city": row["city"],
        "area": row["area"],
        "cuisine": row["cuisine"],
        "price_range": row["price_range"],
        "avg_meal_price_inr": row["avg_meal_price"],
        "rating": row["rating"],
        "review_count": row["review_count"],
        "rating_text": _rating_text(row["rating"], row["review_count"]),
        "delivery_available": bool(row["delivery_available"]),
        "opening_year": row["opening_year"],
    }


def _hhmm_to_min(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _min_to_hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def _parse_when(date_str: str, time_str: str):
    """Validate a requested slot. Returns (date, minutes) or raises ValueError(message)."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise ValueError("Date must be in YYYY-MM-DD format.")
    if not re.fullmatch(r"\d{1,2}:\d{2}", str(time_str or "")):
        raise ValueError("Time must be in 24-hour HH:MM format.")
    mins = _hhmm_to_min(time_str)
    if mins >= 24 * 60 or mins % 60 > 59:
        raise ValueError("That is not a valid time.")
    now = datetime.now()
    if d < now.date() or (d == now.date() and mins <= now.hour * 60 + now.minute):
        raise ValueError("That date and time is in the past.")
    if d > now.date() + timedelta(days=config.MAX_ADVANCE_DAYS):
        raise ValueError(f"Bookings can only be made up to {config.MAX_ADVANCE_DAYS} days ahead.")
    if not (config.OPEN_MINUTE <= mins <= config.LAST_BOOKING_MINUTE):
        raise ValueError(
            f"Reservations are available between {_min_to_hhmm(config.OPEN_MINUTE)} "
            f"and {_min_to_hhmm(config.LAST_BOOKING_MINUTE)}."
        )
    return d, mins


def _bookable_seats(seating_capacity) -> int:
    cap = seating_capacity or config.DEFAULT_SEATING
    return max(2, int(cap * config.ONLINE_SHARE))


def _seats_taken(conn, restaurant_id: str, d: date, mins: int) -> int:
    rows = conn.execute(
        """SELECT reservation_time, party_size FROM reservations
           WHERE restaurant_id = ? AND reservation_date = ? AND status = 'confirmed'""",
        (restaurant_id, d.isoformat()),
    ).fetchall()
    return sum(r["party_size"] for r in rows if abs(_hhmm_to_min(r["reservation_time"]) - mins) < config.SLOT_MINUTES)


def _get_restaurant(conn, restaurant_id: str):
    return conn.execute("SELECT * FROM restaurants WHERE restaurant_id = ?", (restaurant_id,)).fetchone()


def _digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


# ----------------------------------------------------------------------------- tools

def search_restaurants(city=None, area=None, cuisine=None, price_range=None, delivery_only=None,
                       min_rating=None, max_avg_price=None, limit=5) -> dict:
    """Find restaurants matching the filters, best rated first."""
    where, params = [], []
    if city:
        where.append("LOWER(city) = LOWER(?)"); params.append(city.strip())
    if area:
        where.append("LOWER(area) LIKE LOWER(?)"); params.append(f"%{area.strip()}%")
    if cuisine:
        where.append("LOWER(cuisine) LIKE LOWER(?)"); params.append(f"%{cuisine.strip()}%")
    if price_range:
        tier = PRICE_ALIASES.get(price_range.strip().lower(), price_range.strip())
        where.append("LOWER(price_range) = LOWER(?)"); params.append(tier)
    if delivery_only:
        where.append("delivery_available = 1")
    if min_rating is not None:
        where.append("rating >= ?"); params.append(float(min_rating))     # unrated places excluded
    if max_avg_price is not None:
        where.append("avg_meal_price <= ?"); params.append(int(max_avg_price))

    limit = max(1, min(int(limit or 5), 10))
    sql = "SELECT * FROM restaurants"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY rating IS NULL, rating DESC, COALESCE(review_count, 0) DESC LIMIT ?"
    with connection() as conn:
        rows = conn.execute(sql, params + [limit]).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM restaurants" + (" WHERE " + " AND ".join(where) if where else ""), params
        ).fetchone()[0]
    return {"success": True, "total_matches": total, "returned": len(rows), "restaurants": [_public(r) for r in rows]}


def get_restaurant_details(restaurant_id=None, name=None, city=None) -> dict:
    """Look up one restaurant by ID, or by name (optionally narrowed by city)."""
    with connection() as conn:
        if restaurant_id:
            rows = [r for r in [_get_restaurant(conn, restaurant_id)] if r]
        elif name:
            sql, params = "SELECT * FROM restaurants WHERE LOWER(name) LIKE LOWER(?)", [f"%{name.strip()}%"]
            if city:
                sql += " AND LOWER(city) = LOWER(?)"; params.append(city.strip())
            rows = conn.execute(sql + " ORDER BY COALESCE(review_count,0) DESC LIMIT 5", params).fetchall()
        else:
            return _err("missing_argument", "Provide restaurant_id or name.")
    if not rows:
        return _err("not_found", "No restaurant found with that name or ID.")
    if len(rows) > 1:
        return {"success": True, "ambiguous": True,
                "message": "Several restaurants match; ask the customer which one (city/area).",
                "restaurants": [_public(r) for r in rows]}
    out = _public(rows[0])
    cap = rows[0]["seating_capacity"]
    out["seating_capacity"] = cap  # may be None -> do not claim a number
    return {"success": True, "restaurant": out}


def check_availability(restaurant_id: str, date: str, time: str, party_size: int) -> dict:
    """Check if a table for `party_size` is free; suggest nearby times if not."""
    try:
        party_size = int(party_size)
        if not 1 <= party_size <= config.MAX_PARTY_SIZE:
            return _err("bad_party_size", f"Party size must be between 1 and {config.MAX_PARTY_SIZE}. "
                                           "For larger groups the customer should call the restaurant.")
        d, mins = _parse_when(date, time)
    except ValueError as e:
        return _err("invalid_request", str(e))

    with connection() as conn:
        r = _get_restaurant(conn, restaurant_id)
        if not r:
            return _err("not_found", "Unknown restaurant_id.")
        limit = _bookable_seats(r["seating_capacity"])
        left = limit - _seats_taken(conn, restaurant_id, d, mins)
        if party_size <= left:
            return {"success": True, "available": True, "restaurant": r["name"],
                    "date": date, "time": time, "party_size": party_size}
        # suggest nearby free times (30-min steps, up to +/- 3h)
        alternatives = []
        for delta in (30, -30, 60, -60, 90, -90, 120, -120, 150, -150, 180, -180):
            m = mins + delta
            if not config.OPEN_MINUTE <= m <= config.LAST_BOOKING_MINUTE:
                continue
            if d == datetime.now().date() and m <= datetime.now().hour * 60 + datetime.now().minute:
                continue
            if party_size <= limit - _seats_taken(conn, restaurant_id, d, m):
                alternatives.append(_min_to_hhmm(m))
            if len(alternatives) == 3:
                break
        return {"success": True, "available": False, "restaurant": r["name"], "date": date, "time": time,
                "party_size": party_size, "alternative_times": sorted(alternatives)}


def create_reservation(restaurant_id: str, customer_name: str, phone: str, party_size: int,
                       date: str, time: str, special_requests=None) -> dict:
    """Book a table. Re-checks availability inside a write transaction to avoid double-booking."""
    name = (customer_name or "").strip()
    phone_digits = _digits(phone)
    if len(name) < 2:
        return _err("missing_argument", "Customer name is required.")
    if not 10 <= len(phone_digits) <= 13:
        return _err("invalid_phone", "A valid phone number (10 digits) is required.")
    try:
        party_size = int(party_size)
        if not 1 <= party_size <= config.MAX_PARTY_SIZE:
            return _err("bad_party_size", f"Party size must be between 1 and {config.MAX_PARTY_SIZE}.")
        d, mins = _parse_when(date, time)
    except ValueError as e:
        return _err("invalid_request", str(e))
    time = _min_to_hhmm(mins)

    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")  # take the write lock before checking seats
        r = _get_restaurant(conn, restaurant_id)
        if not r:
            return _err("not_found", "Unknown restaurant_id.")
        left = _bookable_seats(r["seating_capacity"]) - _seats_taken(conn, restaurant_id, d, mins)
        if party_size > left:
            return _err("no_availability", "That slot is full. Call check_availability for alternatives.")
        for _ in range(10):
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
            try:
                conn.execute(
                    """INSERT INTO reservations
                       (confirmation_code, restaurant_id, customer_name, phone, party_size,
                        reservation_date, reservation_time, special_requests)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (code, restaurant_id, name, phone_digits, party_size, d.isoformat(), time,
                     (special_requests or None)),
                )
                break
            except Exception as e:  # unique collision on code -> retry
                if "UNIQUE" not in str(e):
                    raise
        else:
            return _err("internal", "Could not generate a confirmation code. Please try again.")
    return {"success": True, "confirmation_code": code, "restaurant": r["name"], "area": r["area"],
            "city": r["city"], "date": d.isoformat(), "time": time, "party_size": party_size,
            "customer_name": name}


def _find_reservation(conn, code: str, phone_last4: str):
    row = conn.execute(
        """SELECT res.*, r.name AS restaurant_name FROM reservations res
           JOIN restaurants r USING (restaurant_id) WHERE res.confirmation_code = ?""",
        ((code or "").strip().upper(),),
    ).fetchone()
    if not row or not row["phone"].endswith(_digits(phone_last4)[-4:] or "!"):
        return None  # same answer for "not found" and "wrong phone": do not leak existence
    return row


def get_reservation(confirmation_code: str, phone_last4: str) -> dict:
    """Look up a booking. Needs the code AND last 4 digits of the phone used."""
    with connection() as conn:
        row = _find_reservation(conn, confirmation_code, phone_last4)
    if not row:
        return _err("not_found", "No booking found with that code and phone number.")
    return {"success": True, "confirmation_code": row["confirmation_code"], "restaurant": row["restaurant_name"],
            "date": row["reservation_date"], "time": row["reservation_time"], "party_size": row["party_size"],
            "status": row["status"], "customer_name": row["customer_name"]}


def cancel_reservation(confirmation_code: str, phone_last4: str) -> dict:
    with connection() as conn:
        row = _find_reservation(conn, confirmation_code, phone_last4)
        if not row:
            return _err("not_found", "No booking found with that code and phone number.")
        if row["status"] == "cancelled":
            return {"success": True, "already_cancelled": True, "restaurant": row["restaurant_name"]}
        conn.execute("UPDATE reservations SET status='cancelled' WHERE reservation_id = ?", (row["reservation_id"],))
    return {"success": True, "cancelled": True, "restaurant": row["restaurant_name"],
            "date": row["reservation_date"], "time": row["reservation_time"]}


# ----------------------------------------------------------------------------- LLM tool schemas

TOOL_SCHEMAS = [
    {
        "name": "search_restaurants",
        "description": "Find restaurants by city, area, cuisine, price range, delivery, minimum rating or "
                       "maximum price per person. Returns the best-rated matches first. Use this for "
                       "recommendations like 'cheap Italian place in Pune'.",
        "input_schema": {"type": "object", "properties": {
            "city": {"type": "string", "description": "e.g. Pune, Mumbai"},
            "area": {"type": "string", "description": "Neighbourhood, e.g. Baner"},
            "cuisine": {"type": "string", "description": "e.g. Italian, North Indian, Cafe, Biryani"},
            "price_range": {"type": "string", "enum": ["Budget", "Mid-range", "Premium", "Luxury"]},
            "delivery_only": {"type": "boolean"},
            "min_rating": {"type": "number", "description": "0-5"},
            "max_avg_price": {"type": "integer", "description": "Max average meal price per person, in INR"},
            "limit": {"type": "integer", "description": "Default 5, max 10"},
        }},
    },
    {
        "name": "get_restaurant_details",
        "description": "Get details of one restaurant by restaurant_id or by name (optionally with city).",
        "input_schema": {"type": "object", "properties": {
            "restaurant_id": {"type": "string"}, "name": {"type": "string"}, "city": {"type": "string"}}},
    },
    {
        "name": "check_availability",
        "description": "Check whether a table for N people is free at a date and time. If not, returns "
                       "alternative times. Always call this before create_reservation.",
        "input_schema": {"type": "object", "required": ["restaurant_id", "date", "time", "party_size"],
                         "properties": {
                             "restaurant_id": {"type": "string"},
                             "date": {"type": "string", "description": "YYYY-MM-DD"},
                             "time": {"type": "string", "description": "24-hour HH:MM"},
                             "party_size": {"type": "integer"}}},
    },
    {
        "name": "create_reservation",
        "description": "Book a table. Only call after the customer has confirmed restaurant, date, time, "
                       "party size, their name and phone number.",
        "input_schema": {"type": "object",
                         "required": ["restaurant_id", "customer_name", "phone", "party_size", "date", "time"],
                         "properties": {
                             "restaurant_id": {"type": "string"}, "customer_name": {"type": "string"},
                             "phone": {"type": "string"}, "party_size": {"type": "integer"},
                             "date": {"type": "string", "description": "YYYY-MM-DD"},
                             "time": {"type": "string", "description": "24-hour HH:MM"},
                             "special_requests": {"type": "string"}}},
    },
    {
        "name": "get_reservation",
        "description": "Look up an existing booking. Needs the confirmation code and last 4 digits of the phone.",
        "input_schema": {"type": "object", "required": ["confirmation_code", "phone_last4"], "properties": {
            "confirmation_code": {"type": "string"}, "phone_last4": {"type": "string"}}},
    },
    {
        "name": "cancel_reservation",
        "description": "Cancel a booking. Needs the confirmation code and last 4 digits of the phone. "
                       "Confirm with the customer before calling.",
        "input_schema": {"type": "object", "required": ["confirmation_code", "phone_last4"], "properties": {
            "confirmation_code": {"type": "string"}, "phone_last4": {"type": "string"}}},
    },
]

TOOL_FUNCTIONS = {
    "search_restaurants": search_restaurants,
    "get_restaurant_details": get_restaurant_details,
    "check_availability": check_availability,
    "create_reservation": create_reservation,
    "get_reservation": get_reservation,
    "cancel_reservation": cancel_reservation,
}


def execute_tool(name: str, arguments: dict) -> dict:
    """Dispatch a tool call from the LLM. Never raises."""
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return _err("unknown_tool", f"No tool named {name}.")
    try:
        return fn(**(arguments or {}))
    except TypeError as e:
        return _err("bad_arguments", f"Invalid arguments for {name}: {e}")
    except Exception as e:  # keep the voice call alive; log in real deployments
        return _err("internal", f"Unexpected error in {name}: {type(e).__name__}")
