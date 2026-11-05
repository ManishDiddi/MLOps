# Point-in-Time Joins and `pandas.merge_asof()`

**A worked guide based on the AWS SageMaker Feature Store notebook**  
Source: `v2_Class13_AWS_SageMaker_Feature_Store_1_Training_Copyable(2).ipynb`, particularly Section 8.

## Part I — Understanding point-in-time joins

### 1. What is a point-in-time join?

A **point-in-time join** attaches to each order the latest customer-feature record that existed **strictly before the order date**. It avoids accidentally using customer information from the future.

For an order placed on 20 January, the question is not *“What do we know about this customer now?”* It is *“What was the latest feature snapshot available before 20 January?”*

### 2. Two datasets for the same customer

We'll use **four orders and four feature snapshots** for the same customer, `C-01`, so the joins can be followed row by row. **This is a deliberately small, fictional example**, not four literal records copied from the notebook. The notebook's full data contains 12,000 orders and 15,598 historical feature rows; those totals do **not** have to be equal.

**Dataset A — Orders (four rows)**

| order_id | customer_id | order_date | price |
|---|---|---|---:|
| O1 | C-01 | 2026-01-10 | 500 |
| O2 | C-01 | 2026-01-24 | 800 |
| O3 | C-01 | 2026-02-07 | 600 |
| O4 | C-01 | 2026-02-21 | 900 |

**Dataset B — Historical customer features (four rows)**

| customer_id | event_time | orders_so_far | returns_so_far |
|---|---|---:|---:|
| C-01 | 2026-01-10 | 1 | 0 |
| C-01 | 2026-01-24 | 2 | 1 |
| C-01 | 2026-02-07 | 3 | 2 |
| C-01 | 2026-02-21 | 4 | 3 |

Each row in Dataset B is a **snapshot of customer information at that time**, not a row to automatically pair with the order on the same date. The matching row counts here are only to make the example easier to follow; in the real notebook, the number of feature snapshots and orders is different.

The actual notebook also has `return_rate` and `tenure_days`. We leave them out here so we can concentrate on **which row gets matched**, rather than on the number of columns.

### 3. Join each order to the correct historical snapshot

For each order in Dataset A, look through Dataset B and choose the **newest row for `C-01` with `event_time < order_date`**.

| Order being predicted | Eligible snapshot dates | Selected snapshot | Historical orders | Historical returns |
|---|---|---|---:|---:|
| **O1 — 10 Jan** | None | **No match** | — | — |
| **O2 — 24 Jan** | 10 Jan | **10 Jan** | 1 | 0 |
| **O3 — 7 Feb** | 10 Jan, 24 Jan | **24 Jan** | 2 | 1 |
| **O4 — 21 Feb** | 10 Jan, 24 Jan, 7 Feb | **7 Feb** | 3 | 2 |

Take **O3 (7 February)** as a detailed example:

1. The order belongs to customer `C-01`.
2. The snapshot dated **10 January** is eligible, but old.
3. The snapshot dated **24 January** is eligible and more recent.
4. The snapshot dated **7 February** is **not** eligible: it already includes the current day's order.
5. The **24 January** snapshot is chosen, giving `orders_so_far = 2` and `returns_so_far = 1`.

For **O1**, no earlier snapshot exists, so pandas returns missing values (`NaT` for the matched date and `NaN` for numerical features). The notebook fills such missing feature values later.

**Why exclude an exactly matching date?** The notebook records these events at day-level precision, and its same-date feature row already includes the order being predicted. Therefore it uses a **strictly earlier** comparison (`<`), not `<=`.

### 4. Honest join versus naive join

The difference is entirely about **which row from Dataset B gets attached to an order**.

**Honest join — latest snapshot strictly before each order**

| order_id | order_date | Matched event_time | orders_so_far | returns_so_far |
|---|---|---|---:|---:|
| O1 | 10 Jan | *No match* | — | — |
| O2 | 24 Jan | **10 Jan** | 1 | 0 |
| O3 | 7 Feb | **24 Jan** | 2 | 1 |
| O4 | 21 Feb | **7 Feb** | 3 | 2 |

**Naive join — customer's latest snapshot from the entire history**

| order_id | order_date | Matched event_time | orders_so_far | returns_so_far |
|---|---|---|---:|---:|
| O1 | 10 Jan | **21 Feb** | 4 | 3 |
| O2 | 24 Jan | **21 Feb** | 4 | 3 |
| O3 | 7 Feb | **21 Feb** | 4 | 3 |
| O4 | 21 Feb | **21 Feb** | 4 | 3 |

The naive join attaches the **same latest-ever** feature record to all four orders. Even O1 (10 January) gets a record from 21 February! This is **future-information leakage**. O4 also gets its own same-day record, which already counts O4 and is therefore invalid for the notebook's prediction timing.

The honest join instead reconstructs what was known **at each order date**.

### 5. How this maps to the actual SageMaker notebook

The notebook uses the following operations (shown here in shortened form):

```python
# Honest: each order gets its latest strictly earlier customer snapshot.
honest = pd.merge_asof(
    o,
    feats[["customer_id", "time"] + FEATS],
    by="customer_id",
    left_on="order_date",
    right_on="time",
    allow_exact_matches=False,
)

# Naive: each order gets the customer's last snapshot overall.
latest = feats.groupby("customer_id").tail(1)
naive = o.merge(latest[["customer_id", "time"] + FEATS], on="customer_id", how="left")
```

For its **real notebook example**, customer `C-00001` has an order `ORD-210337` on **10 August 2026**:

| Join | Selected customer snapshot | orders_so_far | returns_so_far |
|---|---|---:|---:|
| **Honest** | **27 June 2026** | **11** | **9** |
| **Naive** | **14 September 2026** | **14** | **11** |

The second result uses information dated *after* the order and therefore cannot represent a real checkout-time prediction. The first is the intended point-in-time match.

The exact pandas function behind the honest join is explained separately in Part II.

---

## Part II — `pd.merge_asof()` explained separately

### 6. The idea in one sentence

`pd.merge_asof()` is a pandas join that finds the **nearest eligible key value** in another table, rather than requiring an exact key match. It is especially useful for matching events to observations recorded at different times.

A normal `pd.merge()` often asks: **“Which row has exactly the same date?”**  
A backward `pd.merge_asof()` asks: **“Which row has the latest date *at or before* this date?”**

### 7. Example A — one customer, different dates

**Orders (left table):**

| order_id | customer_id | order_date |
|---|---|---|
| O1 | A | 2026-01-10 |
| O2 | A | 2026-01-20 |
| O3 | A | 2026-01-30 |

**Feature snapshots (right table):**

| customer_id | event_time | returns_so_far |
|---|---|---:|
| A | 2026-01-05 | 0 |
| A | 2026-01-15 | 1 |
| A | 2026-01-25 | 2 |

With `direction="backward"`, the result is:

| order_id | order_date | Matched event_time | returns_so_far |
|---|---|---|---:|
| O1 | 2026-01-10 | **2026-01-05** | 0 |
| O2 | 2026-01-20 | **2026-01-15** | 1 |
| O3 | 2026-01-30 | **2026-01-25** | 2 |

Notice that **none of the dates had to be equal**.

### 8. Example B — two customers, where `by=` matters

If order `A / 20 Jan` and feature `B / 19 Jan` are close in time, they still **must not** be paired. `by="customer_id"` restricts the search to records for the **same customer**.

| Order | Order date | Customer A's feature | Customer B's feature | Correct match |
|---|---|---|---|---|
| A | 20 Jan | 15 Jan | 19 Jan | **A / 15 Jan** |
| B | 20 Jan | 15 Jan | 19 Jan | **B / 19 Jan** |

The function first respects customer identity (`by`) and then selects the appropriate timestamp within that customer.

### 9. Example C — same-day snapshots

Suppose an order and a snapshot both have date `2026-01-20`, and an older snapshot exists on `2026-01-15`.

| Setting | Matched feature snapshot |
|---|---|
| `allow_exact_matches=True` | **20 Jan** (same timestamp allowed) |
| `allow_exact_matches=False` | **15 Jan** (strictly earlier) |

For the notebook, **`False` is required** because the 20 January snapshot already includes the order being scored.

### 10. Example D — no prior history

First order: **10 Jan**. First feature row: **10 Jan**. With `allow_exact_matches=False` and `direction="backward"`, **no row qualifies**. The feature columns in the result are `NaN`. The notebook later supplies defaults, rather than using an invalid same-day or future snapshot.

### 11. Example E — `direction` changes the matching rule

For a target time of **20 Jan**, with available snapshots on **18 Jan** and **25 Jan**:

| `direction` | What it finds | Match |
|---|---|---|
| `"backward"` | Latest record at/before target | **18 Jan** |
| `"forward"` | Earliest record at/after target | **25 Jan** |
| `"nearest"` | Closest in either direction | **18 Jan** |

`allow_exact_matches=False` makes backward/forward comparisons strict and excludes same-time values for nearest matching too. Backward is the **default direction**, and it is the direction used by this notebook.

### 12. The actual notebook code, annotated

```python
FEATS = ["orders_so_far", "returns_so_far", "return_rate", "tenure_days"]

# Athena returns historical feature rows from the offline Feature Store table.
feats = query(f"SELECT customer_id, event_time, {', '.join(FEATS)} FROM {TABLE}")

# Event timestamps look like 2025-10-13T00:00:00Z.
# Parse them, and drop the UTC timezone marker to match the naive order dates.
feats["time"] = pd.to_datetime(feats["event_time"]).dt.tz_localize(None)
feats = feats.sort_values("time")

# Make order dates proper datetime values, then sort by the merge key.
o = orders.assign(order_date=pd.to_datetime(orders["order_date"]))
o = o.sort_values("order_date")

# The latest snapshot strictly earlier than each order, for that customer.
honest = pd.merge_asof(
    o,
    feats[["customer_id", "time"] + FEATS],
    by="customer_id",
    left_on="order_date",
    right_on="time",
    direction="backward",
    allow_exact_matches=False,
)

# Comparison only: assign every order the latest snapshot of all time.
latest = feats.groupby("customer_id").tail(1)
naive = o.merge(
    latest[["customer_id", "time"] + FEATS],
    on="customer_id",
    how="left",
)
```

The explicit `direction="backward"` above merely makes the notebook's default direction visible; it does not change the join's behavior.

**Parameter-by-parameter:**

| Parameter | Meaning in this notebook |
|---|---|
| `o` | Left table: the original orders; every order remains represented. |
| `feats[...]` | Right table: historical feature snapshots. |
| `by="customer_id"` | Do not mix one customer's features with another's. |
| `left_on="order_date"` | Timestamp to predict at. |
| `right_on="time"` | Timestamp when the feature snapshot describes the customer's state. |
| `direction="backward"` | Search only earlier (or, if allowed, equal-time) feature snapshots. |
| `allow_exact_matches=False` | Require **feature time < order date**. |

### 13. Why the datetime and sorting lines exist

```python
feats["time"] = pd.to_datetime(feats["event_time"]).dt.tz_localize(None)
feats = feats.sort_values("time")
o = orders.assign(order_date=pd.to_datetime(orders["order_date"]))
o = o.sort_values("order_date")
```

- `pd.to_datetime(...)` converts date *strings* to actual pandas datetime values. The as-of merge needs compatible numeric/datetime merge keys.
- The `Z` in a value such as `2025-10-13T00:00:00Z` means **UTC**. Here, `.dt.tz_localize(None)` removes the timezone tag while preserving the displayed clock time. This is safe for the notebook's UTC-midnight feature timestamps paired with date-only order timestamps; it is **not** a general recipe for arbitrary timezones.
- `sort_values(...)` puts the **time key** in ascending order on both sides. `merge_asof()` requires both tables sorted by their as-of keys. Sorting only by customer, without globally ascending time, is not sufficient.
- `groupby("customer_id").tail(1)` works for the naive comparison because `feats` was sorted chronologically first: it picks each customer's latest row overall.

### 14. A fully runnable dummy example (no AWS required)

Copy this into any Python environment with pandas installed:

```python
import pandas as pd

orders = pd.DataFrame({
    "order_id": ["A1", "B1", "A2", "B2", "C1"],
    "customer_id": ["A", "B", "A", "B", "C"],
    "order_date": ["2026-01-10", "2026-01-12", "2026-01-20", "2026-01-25", "2026-01-10"],
})

features = pd.DataFrame({
    "customer_id": ["A", "B", "A", "B", "C"],
    "event_time": ["2026-01-05", "2026-01-08", "2026-01-20", "2026-01-22", "2026-01-10"],
    "returns_so_far": [0, 3, 2, 4, 0],
})

orders["order_date"] = pd.to_datetime(orders["order_date"])
features["event_time"] = pd.to_datetime(features["event_time"])

orders = orders.sort_values("order_date")
features = features.sort_values("event_time")

honest = pd.merge_asof(
    orders,
    features,
    by="customer_id",
    left_on="order_date",
    right_on="event_time",
    direction="backward",
    allow_exact_matches=False,
)

print(honest[["order_id", "customer_id", "order_date", "event_time", "returns_so_far"]].to_string(index=False))
```

**Expected behavior (sorted by order date):**

| Order | Order date | Matched feature date | Returns so far | Why |
|---|---|---|---:|---|
| A1 | 10 Jan | 5 Jan | 0 | Latest earlier record for A |
| C1 | 10 Jan | `NaT` | `NaN` | Only C's same-day snapshot exists; it is excluded |
| B1 | 12 Jan | 8 Jan | 3 | Latest earlier record for B |
| A2 | 20 Jan | 5 Jan | 0 | A's 20 Jan snapshot is excluded; no A snapshot in between |
| B2 | 25 Jan | 22 Jan | 4 | Latest earlier record for B |

`NaT` is the datetime equivalent of a missing value; `NaN` marks a missing numeric value.

### 15. Common mistakes and quick checks

1. **Joining on `customer_id` only:** `merge()` against the customer's latest-ever row ignores historical timing and can leak future outcomes.
2. **Allowing exact matches by accident:** the notebook's same-day feature row already counts the current order.
3. **Forgetting to sort by the as-of time keys:** this can raise a sorting error.
4. **Mixing timezone-aware and timezone-naive timestamps:** pandas needs compatible types; align timestamps to a consistent time convention first.
5. **Assuming an unmatched row is a bug:** first orders may legitimately have no earlier feature history.
6. **Confusing the label with a feature:** `returned` is allowed as the supervised target in historical training, but must not be used as a checkout-time input.
7. **Assuming point-in-time correctness checks every input:** direct order columns must also be available at the intended prediction time.

A simple sanity check after joining:

```python
matched = honest["time"].notna()  # Use "event_time" in the standalone dummy example.
assert (honest.loc[matched, "time"] < honest.loc[matched, "order_date"]).all()
```

This verifies the time condition. The `by="customer_id"` parameter separately enforces customer identity.

---

## Final takeaway

**Point-in-time correctness** is the *rule* that historical model inputs must reflect what was knowable at prediction time. **`pd.merge_asof()`** is the *pandas operation* used in this notebook to apply that rule: match the same customer, find the latest strictly earlier snapshot, and attach its features to the order.

The AWS Feature Store offline history makes those snapshots available; it is the **join** that chooses which historical snapshot belongs to each training example.
