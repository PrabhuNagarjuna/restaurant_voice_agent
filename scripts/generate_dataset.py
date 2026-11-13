"""
Generate a realistic synthetic restaurant dataset (1,000 rows) -> data/restaurants.csv

Design notes
- Price tier depends on cuisine and city tier; avg meal price (INR, per person) depends on tier.
- Seating depends on venue type; revenue is built from seats x occupancy x turns x price.
- Review count grows with restaurant age and popularity (heavy-tailed).
- ~2-6% missing values in selected columns; a handful of deliberate outliers.
- Fixed seed => reproducible.

Run:  python scripts/generate_dataset.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
N = 1000
rng = np.random.default_rng(SEED)

# city -> (city tier multiplier, areas)
CITIES = {
    "Mumbai": (1.30, ["Bandra", "Andheri", "Powai", "Colaba", "Lower Parel", "Dadar", "Borivali"]),
    "Pune": (1.05, ["Koregaon Park", "Kothrud", "Viman Nagar", "Baner", "Hinjewadi", "Pimpri", "Camp"]),
    "Delhi": (1.25, ["Connaught Place", "Hauz Khas", "Saket", "Karol Bagh", "Dwarka", "Lajpat Nagar"]),
    "Bengaluru": (1.20, ["Indiranagar", "Koramangala", "Whitefield", "HSR Layout", "Jayanagar", "MG Road"]),
    "Hyderabad": (1.00, ["Banjara Hills", "Jubilee Hills", "Gachibowli", "Madhapur", "Secunderabad"]),
    "Chennai": (0.95, ["T. Nagar", "Adyar", "Anna Nagar", "Velachery", "Mylapore"]),
    "Kolkata": (0.90, ["Park Street", "Salt Lake", "Ballygunge", "New Town", "Howrah"]),
    "Ahmedabad": (0.90, ["Navrangpura", "SG Highway", "Satellite", "Maninagar"]),
    "Jaipur": (0.85, ["C-Scheme", "Malviya Nagar", "Vaishali Nagar", "Mansarovar"]),
    "Nagpur": (0.80, ["Dharampeth", "Sitabuldi", "Manish Nagar"]),
}
CITY_WEIGHTS = np.array([14, 14, 13, 13, 10, 9, 8, 7, 6, 6], dtype=float)
CITY_WEIGHTS /= CITY_WEIGHTS.sum()

# cuisine -> (weight, base price tier probs [Budget, Mid, Premium, Luxury], base price INR/person, venue type)
CUISINES = {
    "North Indian": (14, [0.20, 0.50, 0.27, 0.03], 380, "restaurant"),
    "South Indian": (9, [0.55, 0.38, 0.06, 0.01], 220, "casual"),
    "Chinese": (8, [0.30, 0.50, 0.18, 0.02], 320, "restaurant"),
    "Italian": (7, [0.05, 0.45, 0.42, 0.08], 650, "restaurant"),
    "Continental": (5, [0.04, 0.40, 0.46, 0.10], 700, "restaurant"),
    "Fast Food": (9, [0.75, 0.23, 0.02, 0.00], 190, "quick"),
    "Cafe": (9, [0.20, 0.60, 0.19, 0.01], 350, "cafe"),
    "Biryani": (6, [0.40, 0.48, 0.11, 0.01], 300, "casual"),
    "Street Food": (5, [0.92, 0.08, 0.00, 0.00], 120, "quick"),
    "Mughlai": (5, [0.10, 0.50, 0.35, 0.05], 520, "restaurant"),
    "Seafood": (4, [0.08, 0.45, 0.40, 0.07], 650, "restaurant"),
    "Japanese": (3, [0.02, 0.28, 0.50, 0.20], 1100, "restaurant"),
    "Thai": (3, [0.05, 0.50, 0.40, 0.05], 600, "restaurant"),
    "Mexican": (3, [0.10, 0.55, 0.32, 0.03], 550, "restaurant"),
    "Bakery & Desserts": (4, [0.35, 0.50, 0.14, 0.01], 250, "cafe"),
    "Multi-cuisine": (6, [0.10, 0.45, 0.38, 0.07], 600, "banquet"),
}
TIERS = ["Budget", "Mid-range", "Premium", "Luxury"]
TIER_MULT = {"Budget": 0.75, "Mid-range": 1.0, "Premium": 1.55, "Luxury": 2.8}

NAME_PARTS = {
    "North Indian": (["Punjabi", "Tadka", "Dhaba", "Rasoi", "Zaika", "Swad", "Desi", "Handi"], ["Junction", "House", "Express", "Kitchen", "Darbar", "Corner"]),
    "South Indian": (["Udupi", "Madras", "Dosa", "Saravana", "Idli", "Kerala", "Mysore", "Filter"], ["Cafe", "Bhavan", "Tiffins", "Mess", "Kitchen", "Point"]),
    "Chinese": (["Wok", "Dragon", "Golden", "Lucky", "Noodle", "Chopstick", "Panda", "Jade"], ["Express", "House", "Garden", "Bowl", "Hub", "Palace"]),
    "Italian": (["Bella", "Trattoria", "Pasta", "Napoli", "Roma", "Olive", "La Piazza", "Basilico"], ["Kitchen", "Cucina", "Bistro", "House", "Table", "Co."]),
    "Continental": (["The Grill", "Oak", "Maple", "Brasserie", "Cedar", "Hearth", "Provence", "Atlas"], ["Room", "Bistro", "House", "Table", "Kitchen", "& Co."]),
    "Fast Food": (["Burger", "Crispy", "Fry", "Wrap", "Sizzle", "Quick", "Bite", "Munch"], ["Hub", "Shack", "Point", "Box", "Stop", "Corner"]),
    "Cafe": (["Brew", "Bean", "Roast", "Daily Grind", "Latte", "Cuppa", "Mocha", "Chai"], ["Cafe", "Lab", "Co.", "Social", "Roasters", "Studio"]),
    "Biryani": (["Hyderabadi", "Dum", "Nawabi", "Biryani", "Lucknowi", "Awadhi", "Paradise", "Royal"], ["House", "Darbar", "Kitchen", "Point", "Centre", "Handi"]),
    "Street Food": (["Chaat", "Vada Pav", "Pani Puri", "Gully", "Thela", "Nukkad", "Bhel", "Sev"], ["Wala", "Corner", "Stall", "Junction", "Adda", "Point"]),
    "Mughlai": (["Shahi", "Mughal", "Kebab", "Nizam", "Dilli", "Sultan", "Tandoor", "Badshah"], ["Darbar", "Mahal", "Kitchen", "House", "Khana", "Tales"]),
    "Seafood": (["Coastal", "Konkan", "Catch", "Mangalore", "Goan", "Tide", "Anchor", "Fisherman's"], ["Kitchen", "Shack", "House", "Table", "Grill", "Wharf"]),
    "Japanese": (["Sakura", "Sushi", "Kyoto", "Ramen", "Izakaya", "Tokyo", "Matsu", "Umami"], ["Bar", "House", "Kitchen", "Room", "Table", "Den"]),
    "Thai": (["Siam", "Bangkok", "Lemongrass", "Thai", "Basil", "Orchid", "Chilli", "Lotus"], ["Kitchen", "House", "Garden", "Table", "Orchid", "Express"]),
    "Mexican": (["Taco", "Casa", "El", "Burrito", "Fiesta", "Salsa", "Nacho", "Cantina"], ["Loco", "House", "Kitchen", "Grill", "Bar", "Co."]),
    "Bakery & Desserts": (["Sweet", "Crumbs", "Frosted", "Dough", "Cake", "Sugar", "Cocoa", "Butter"], ["Bakery", "Studio", "Patisserie", "House", "Box", "Co."]),
    "Multi-cuisine": (["Grand", "Royal", "Spice", "Heritage", "Sapphire", "Ambrosia", "Urban", "Monsoon"], ["Banquet", "Dine", "Garden", "Terrace", "Plaza", "Kitchen"]),
}
CHAIN_NAMES = ["Burger Hub", "Chai Point", "Dosa Express", "Wok Express", "Pizza Corner"]

VENUE = {
    # seats lognormal (median, sigma), occupancy mean, turns/day mean, delivery prob, opex ratio mean
    "quick": dict(seats=(28, 0.35), occ=0.55, turns=4.5, deliv=0.88, opex=0.74),
    "cafe": dict(seats=(36, 0.35), occ=0.48, turns=3.0, deliv=0.65, opex=0.80),
    "casual": dict(seats=(50, 0.35), occ=0.55, turns=2.8, deliv=0.75, opex=0.76),
    "restaurant": dict(seats=(70, 0.40), occ=0.50, turns=1.8, deliv=0.58, opex=0.82),
    "banquet": dict(seats=(140, 0.45), occ=0.35, turns=1.4, deliv=0.40, opex=0.85),
}

PREFIX_BY_CITY = {
    "Mumbai": "MUM", "Pune": "PUN", "Delhi": "DEL", "Bengaluru": "BLR", "Hyderabad": "HYD",
    "Chennai": "CHE", "Kolkata": "KOL", "Ahmedabad": "AMD", "Jaipur": "JAI", "Nagpur": "NAG",
}


def make_name(cuisine: str) -> str:
    if rng.random() < 0.06:
        return str(rng.choice(CHAIN_NAMES))
    a, b = NAME_PARTS[cuisine]
    return f"{rng.choice(a)} {rng.choice(b)}"


def build() -> pd.DataFrame:
    cuis_names = list(CUISINES)
    cuis_w = np.array([CUISINES[c][0] for c in cuis_names], dtype=float)
    cuis_w /= cuis_w.sum()
    city_names = list(CITIES)

    rows = []
    for i in range(1, N + 1):
        city = str(rng.choice(city_names, p=CITY_WEIGHTS))
        city_mult, areas = CITIES[city]
        area = str(rng.choice(areas))
        cuisine = str(rng.choice(cuis_names, p=cuis_w))
        _, tier_p, base_price, venue = CUISINES[cuisine]
        tier = str(rng.choice(TIERS, p=tier_p))

        # Average meal price per person (INR)
        price = base_price * TIER_MULT[tier] * city_mult * rng.lognormal(0, 0.18)
        price = int(round(price / 10) * 10)
        price = max(price, 60)

        # Seating
        med, sig = VENUE[venue]["seats"]
        seat_adj = {"Budget": 0.9, "Mid-range": 1.0, "Premium": 1.1, "Luxury": 0.9}[tier]
        seats = int(max(8, round(med * seat_adj * rng.lognormal(0, sig))))

        # Age / opening year
        year = int(np.clip(2026 - rng.gamma(2.2, 3.4), 1985, 2026))
        age = max(2026 - year, 0.5)

        # Rating (slightly better for premium, slightly noisier for very new places)
        rating = rng.normal(3.95 + {"Budget": -0.05, "Mid-range": 0.05, "Premium": 0.15, "Luxury": 0.25}[tier], 0.42)
        rating = float(np.clip(round(rating, 1), 2.0, 5.0))

        # Popularity & reviews (heavy-tailed, grows with age)
        popularity = rng.lognormal(0, 0.8)
        reviews = int(max(0, round(35 * popularity * (age ** 0.65) * (seats / 60) ** 0.5 * (1.15 if rating >= 4.2 else 1.0))))

        # Delivery
        deliv_p = VENUE[venue]["deliv"] - (0.25 if tier == "Luxury" else 0) + (0.08 if year >= 2018 else 0)
        delivery = "Yes" if rng.random() < np.clip(deliv_p, 0.05, 0.97) else "No"

        # Monthly revenue (INR) = seats x occupancy x turns x 30 days x price x demand factor
        occ = np.clip(rng.normal(VENUE[venue]["occ"], 0.10), 0.15, 0.95)
        turns = max(0.8, rng.normal(VENUE[venue]["turns"], 0.4))
        demand = 0.75 + 0.1 * (rating - 3.5) + 0.05 * np.log1p(reviews) / 3
        revenue = seats * occ * turns * 30 * price * demand
        if delivery == "Yes":
            revenue *= rng.uniform(1.05, 1.30)
        revenue = float(revenue * rng.lognormal(0, 0.10))

        # Operating costs (rent + staff + ingredients + utilities) as share of revenue
        opex_ratio = np.clip(rng.normal(VENUE[venue]["opex"], 0.10) + (0.04 if age < 2 else 0), 0.50, 1.25)
        costs = revenue * opex_ratio

        rows.append(
            dict(
                restaurant_id=f"{PREFIX_BY_CITY[city]}-{i:04d}",
                restaurant_name=make_name(cuisine),
                city=city,
                area=area,
                cuisine=cuisine,
                price_range=tier,
                rating=rating,
                review_count=reviews,
                avg_meal_price=price,
                seating_capacity=seats,
                delivery_available=delivery,
                opening_year=year,
                monthly_revenue=int(round(revenue, -2)),
                operating_costs=int(round(costs, -2)),
            )
        )
    return pd.DataFrame(rows)


def add_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """A few deliberate but believable outliers."""
    def pick(mask):
        return rng.choice(df.index[mask])

    # 1) Ultra-luxury fine dining
    i = pick((df.cuisine == "Japanese") & (df.price_range == "Luxury"))
    df.loc[i, ["avg_meal_price", "seating_capacity"]] = [9500, 34]
    df.loc[i, "monthly_revenue"] = 4_800_000
    df.loc[i, "operating_costs"] = 3_700_000

    # 2) Huge banquet hall
    i = pick(df.cuisine == "Multi-cuisine")
    df.loc[i, "seating_capacity"] = 950
    df.loc[i, "monthly_revenue"] = 11_500_000
    df.loc[i, "operating_costs"] = 9_400_000

    # 3) Viral restaurant with a massive review count
    i = pick((df.cuisine.isin(["Street Food", "Cafe"])) & (df.opening_year >= 2018))
    df.loc[i, "review_count"] = 62_000
    df.loc[i, "rating"] = 4.8

    # 4) Heavily loss-making new restaurant
    i = pick(df.opening_year >= 2025)
    df.loc[i, "operating_costs"] = int(df.loc[i, "monthly_revenue"] * 2.4)

    # 5) Legacy restaurant with a huge review base
    i = pick(df.opening_year <= 1992)
    df.loc[i, "review_count"] = 38_500

    # 6) Tiny kiosk
    i = pick(df.cuisine.isin(["Street Food", "Bakery & Desserts"]))
    df.loc[i, "seating_capacity"] = 4
    df.loc[i, "monthly_revenue"] = 85_000
    df.loc[i, "operating_costs"] = 61_000
    return df


def add_missing(df: pd.DataFrame) -> pd.DataFrame:
    rates = {
        "rating": 0.04, "review_count": 0.03, "avg_meal_price": 0.03,
        "seating_capacity": 0.02, "opening_year": 0.03,
        "monthly_revenue": 0.06, "operating_costs": 0.06, "area": 0.02,
    }
    for col, rate in rates.items():
        mask = rng.random(len(df)) < rate
        df[col] = df[col].astype("object")
        df.loc[mask, col] = np.nan
    # Very new / low-traffic places are more likely to have no rating yet
    low = (df["review_count"].fillna(0).astype(float) < 15) & (rng.random(len(df)) < 0.25)
    df.loc[low, "rating"] = np.nan
    return df


if __name__ == "__main__":
    df = add_missing(add_outliers(build()))
    out = Path(__file__).resolve().parent.parent / "data" / "restaurants.csv"
    out.parent.mkdir(exist_ok=True)

    # Nullable ints so CSV shows "412" not "412.0"
    for c in ["review_count", "avg_meal_price", "seating_capacity", "opening_year", "monthly_revenue", "operating_costs"]:
        df[c] = pd.to_numeric(df[c]).astype("Int64")
    df["rating"] = pd.to_numeric(df["rating"])
    df.to_csv(out, index=False)
    print(f"Wrote {len(df)} rows -> {out}")
