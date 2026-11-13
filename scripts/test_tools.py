"""
Test the tool layer with no AI, against a throwaway copy of the database.
Run:  python scripts/test_tools.py
"""
import os
import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
tmp = Path(tempfile.mkdtemp()) / "test.db"
shutil.copy(ROOT / "restaurants.db", tmp)
os.environ["DB_PATH"] = str(tmp)

from app import tools  # noqa: E402

tomorrow = (date.today() + timedelta(days=1)).isoformat()
passed = 0


def check(label, cond):
    global passed
    assert cond, f"FAILED: {label}"
    passed += 1
    print(f"  ok  {label}")


print("search")
r = tools.search_restaurants(city="Pune", cuisine="Italian", price_range="cheap")
check("alias 'cheap' -> Budget works (call succeeds)", r["success"])
r = tools.search_restaurants(city="Pune", cuisine="Italian", limit=3)
check("returns <= 3 results", 0 < r["returned"] <= 3)
check("results sorted by rating desc", [x["rating"] for x in r["restaurants"]] == sorted([x["rating"] for x in r["restaurants"]], reverse=True))
check("financials never exposed", all("monthly_revenue" not in x and "operating_costs" not in x for x in r["restaurants"]))
r = tools.search_restaurants(min_rating=4.5, limit=10)
check("min_rating excludes unrated", all(x["rating"] is not None and x["rating"] >= 4.5 for x in r["restaurants"]))
r = tools.search_restaurants(city="Atlantis")
check("no matches handled", r["success"] and r["returned"] == 0)

print("details")
rid = tools.search_restaurants(city="Pune", limit=1)["restaurants"][0]["restaurant_id"]
check("lookup by id", tools.get_restaurant_details(restaurant_id=rid)["success"])
check("ambiguous chain name flagged", tools.get_restaurant_details(name="Burger Hub").get("ambiguous") is True)
check("unknown -> not_found", tools.get_restaurant_details(name="zzzz")["error_code"] == "not_found")
unrated = [x for x in tools.search_restaurants(limit=10)["restaurants"]]
with tools.connection() as c:
    nr = c.execute("SELECT restaurant_id FROM restaurants WHERE rating IS NULL LIMIT 1").fetchone()[0]
check("unrated restaurant reads 'not rated yet'", tools.get_restaurant_details(restaurant_id=nr)["restaurant"]["rating_text"] == "not rated yet")

print("availability + booking")
a = tools.check_availability(rid, tomorrow, "20:00", 2)
check("table free for 2", a["success"] and a["available"])
b = tools.create_reservation(rid, "Asha Patil", "+91 98765 43210", 2, tomorrow, "20:00", "window seat")
check("booking succeeds with 6-char code", b["success"] and len(b["confirmation_code"]) == 6)
code = b["confirmation_code"]
check("past date rejected", tools.check_availability(rid, "2020-01-01", "20:00", 2)["error_code"] == "invalid_request")
check("after-hours time rejected", tools.check_availability(rid, tomorrow, "03:00", 2)["error_code"] == "invalid_request")
check("bad phone rejected", tools.create_reservation(rid, "Asha", "123", 2, tomorrow, "20:00")["error_code"] == "invalid_phone")
check("party of 50 rejected", tools.check_availability(rid, tomorrow, "20:00", 50)["error_code"] == "bad_party_size")

# Fill a tiny restaurant, then verify overbooking is blocked and alternatives are offered
with tools.connection() as c:
    c.execute("UPDATE restaurants SET seating_capacity = 10 WHERE restaurant_id = ?", (rid,))  # 6 bookable seats
full = tools.create_reservation(rid, "Ravi Kumar", "9123456789", 4, tomorrow, "20:00")
check("second booking fits (2+4 = 6)", full["success"])
over = tools.create_reservation(rid, "Meena Rao", "9000011111", 2, tomorrow, "20:30")
check("overlapping slot now full -> no_availability", over["error_code"] == "no_availability")
alt = tools.check_availability(rid, tomorrow, "20:30", 2)
check("alternatives offered", alt["available"] is False and len(alt["alternative_times"]) > 0)
check("every suggested alternative is genuinely bookable", all(tools.check_availability(rid, tomorrow, t, 2)["available"] for t in alt["alternative_times"]))
check("later slot still bookable", tools.create_reservation(rid, "Meena Rao", "9000011111", 2, tomorrow, "22:30")["success"])

print("lookup + cancel (security)")
check("wrong phone digits -> not_found", tools.get_reservation(code, "0000")["error_code"] == "not_found")
check("lookup with right last4", tools.get_reservation(code.lower(), "3210")["status"] == "confirmed")
check("cancel with wrong phone fails", tools.cancel_reservation(code, "1111")["success"] is False)
check("cancel works", tools.cancel_reservation(code, "3210")["cancelled"])
check("cancel twice is idempotent", tools.cancel_reservation(code, "3210")["already_cancelled"])
check("cancelled seats are freed", tools.create_reservation(rid, "Neha", "9555512345", 2, tomorrow, "20:15")["success"])

print("dispatch")
check("unknown tool handled", tools.execute_tool("nope", {})["error_code"] == "unknown_tool")
check("bad args handled", tools.execute_tool("check_availability", {"foo": 1})["error_code"] == "bad_arguments")
check("schemas match functions", {t["name"] for t in tools.TOOL_SCHEMAS} == set(tools.TOOL_FUNCTIONS))

print(f"\nAll {passed} checks passed.")
