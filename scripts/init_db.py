"""
Create the SQLite database and load data/restaurants.csv into it.
Safe to re-run: restaurants are upserted, reservations are left untouched.

Run:  python scripts/init_db.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import BASE_DIR, DB_PATH  # noqa: E402
from app.db import get_conn  # noqa: E402

CSV_PATH = BASE_DIR / "data" / "restaurants.csv"


def num(v, cast=int):
    """Blank CSV cell -> None, else number."""
    v = (v or "").strip()
    if v == "":
        return None
    return cast(float(v)) if cast is int else float(v)


def main():
    conn = get_conn()
    conn.executescript((BASE_DIR / "schema.sql").read_text())

    restaurants, financials = [], []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            restaurants.append((
                r["restaurant_id"], r["restaurant_name"].strip(), r["city"],
                (r["area"] or "").strip() or None, r["cuisine"], r["price_range"],
                num(r["rating"], float), num(r["review_count"]), num(r["avg_meal_price"]),
                num(r["seating_capacity"]), 1 if r["delivery_available"] == "Yes" else 0,
                num(r["opening_year"]),
            ))
            financials.append((r["restaurant_id"], num(r["monthly_revenue"]), num(r["operating_costs"])))

    conn.executemany(
        """INSERT INTO restaurants VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(restaurant_id) DO UPDATE SET
             name=excluded.name, city=excluded.city, area=excluded.area, cuisine=excluded.cuisine,
             price_range=excluded.price_range, rating=excluded.rating, review_count=excluded.review_count,
             avg_meal_price=excluded.avg_meal_price, seating_capacity=excluded.seating_capacity,
             delivery_available=excluded.delivery_available, opening_year=excluded.opening_year""",
        restaurants,
    )
    conn.executemany(
        """INSERT INTO restaurant_financials VALUES (?,?,?)
           ON CONFLICT(restaurant_id) DO UPDATE SET
             monthly_revenue=excluded.monthly_revenue, operating_costs=excluded.operating_costs""",
        financials,
    )
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM restaurants").fetchone()[0]
    conn.close()
    print(f"Loaded {n} restaurants into {DB_PATH}")


if __name__ == "__main__":
    main()
