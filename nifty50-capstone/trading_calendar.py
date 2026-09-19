"""Which sessions the Nifty 50 prediction job should chart.

Shared by load_prediction_data.py (what to generate) and Predict_Future_N50_Opening.py
(what to predict) so the two can never disagree about the window.
"""

from datetime import date, timedelta

# NSE trading holidays for the Capital Market segment that fall on a weekday - these are
# dropped from the week, so a holiday is never charted as a session.
#
# Source: NSE "Market Timings & Holidays"
#         https://www.nseindia.com/resources/exchange-communication-holidays
#
# The list starts at October 2026 because that is when this package was submitted; the
# earlier 2026 holidays are already in the past and would never be reached. NSE publishes
# each year's circular the preceding December, so the 2027 dates did not exist when this
# was written - append them below when the circular is released.
#
# Running past the end of the list is safe, not a failure: the week window simply stops
# filtering and charts all five weekdays. Nothing raises.
MARKET_HOLIDAYS = set([
    date(2026, 10, 2),    # Fri - Mahatma Gandhi Jayanti
    date(2026, 10, 20),   # Tue - Dussehra
    date(2026, 11, 10),   # Tue - Diwali Balipratipada
    date(2026, 11, 24),   # Tue - Prakash Gurpurb Sri Guru Nanak Dev
    date(2026, 12, 25),   # Fri - Christmas
    # --- 2027: add here once NSE publishes the circular (expected Dec 2026) ---
])

# Deliberately NOT modelled: the Muhurat trading session on Sunday 8 Nov 2026 (Diwali
# Laxmi Pujan). The market opens for roughly an hour on a day this job treats as a
# weekend. Charting a Mon-Fri week is the stated design, so that one special session is
# out of scope rather than overlooked.


def is_weekend(today=None):
    """True when the market is shut for the whole day (Saturday or Sunday)."""
    return (today or date.today()).weekday() >= 5


def week_window(today=None):
    """The week to chart, as a list of (day, is_forecast) pairs.

    Weekday run - Monday to Friday of the current week. Days up to and including
    today have already traded and are shown as past; the days after today are the
    live forecast. Running Wednesday that is Mon/Tue/Wed past, Thu/Fri forecast.

    Weekend run - the market is shut, so the window jumps to the whole of next
    week and every day is a forecast.

    Dates in MARKET_HOLIDAYS are dropped entirely.
    """
    today = today or date.today()

    if is_weekend(today):
        monday = today + timedelta(days=7 - today.weekday())
    else:
        monday = today - timedelta(days=today.weekday())

    days = [monday + timedelta(days=i) for i in range(5)]
    return [(d, d > today) for d in days if d not in MARKET_HOLIDAYS]
