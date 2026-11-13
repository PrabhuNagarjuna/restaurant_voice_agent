-- SQLite schema for the voice restaurant assistant
PRAGMA foreign_keys = ON;

-- Customer-facing restaurant info (what the voice agent is allowed to read)
CREATE TABLE IF NOT EXISTS restaurants (
    restaurant_id      TEXT PRIMARY KEY,               -- e.g. PUN-0003
    name               TEXT NOT NULL,
    city               TEXT NOT NULL,
    area               TEXT,                           -- may be NULL (missing in source)
    cuisine            TEXT NOT NULL,
    price_range        TEXT NOT NULL CHECK (price_range IN ('Budget','Mid-range','Premium','Luxury')),
    rating             REAL CHECK (rating IS NULL OR (rating >= 0 AND rating <= 5)),
    review_count       INTEGER CHECK (review_count IS NULL OR review_count >= 0),
    avg_meal_price     INTEGER,                        -- INR per person
    seating_capacity   INTEGER CHECK (seating_capacity IS NULL OR seating_capacity > 0),
    delivery_available INTEGER NOT NULL CHECK (delivery_available IN (0,1)),
    opening_year       INTEGER
);

-- Internal analytics only. Kept separate so the agent never exposes revenue/costs.
CREATE TABLE IF NOT EXISTS restaurant_financials (
    restaurant_id    TEXT PRIMARY KEY REFERENCES restaurants(restaurant_id) ON DELETE CASCADE,
    monthly_revenue  INTEGER,                          -- INR
    operating_costs  INTEGER                           -- INR
);

CREATE TABLE IF NOT EXISTS reservations (
    reservation_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    confirmation_code TEXT NOT NULL UNIQUE,
    restaurant_id     TEXT NOT NULL REFERENCES restaurants(restaurant_id),
    customer_name     TEXT NOT NULL,
    phone             TEXT NOT NULL,                   -- digits only
    party_size        INTEGER NOT NULL CHECK (party_size BETWEEN 1 AND 20),
    reservation_date  TEXT NOT NULL,                   -- YYYY-MM-DD
    reservation_time  TEXT NOT NULL,                   -- HH:MM (24h)
    status            TEXT NOT NULL DEFAULT 'confirmed' CHECK (status IN ('confirmed','cancelled')),
    special_requests  TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_rest_city_cuisine ON restaurants(city, cuisine);
CREATE INDEX IF NOT EXISTS idx_rest_rating       ON restaurants(rating);
CREATE INDEX IF NOT EXISTS idx_res_slot          ON reservations(restaurant_id, reservation_date, status);
