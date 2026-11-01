import pytest
import pandas as pd
from datetime import date
from travel_monitor import TravelPriceMonitor


def test_travel_monitor_cyprus_scope():
    """Проверяет, что офферы Кипра проходят проверку scope, а офферы Испании/Албании отсеиваются."""
    config = {
        "url": "https://fly.pl/szukaj-wycieczek/?filter[type]=1&filter[dest]=6:&filter[duration]=7:10&filter[whenFrom]=19-12-2026&filter[whenTo]=05-01-2027",
        "filter_mode": "fixed_trip",
        "dynamic_search_dates": False,
        "required_offer_url_contains": ["/wycieczka/cypr", "transport=accommodation_flight"],
        "excluded_offer_url_contains": ["/wycieczka/polska", "/wycieczka/czechy", "transport=accommodation&"],
    }
    monitor = TravelPriceMonitor(config)

    # Легитимный тур на Кипр от туроператора (ссылка формата /ofertasv/ без transport=accommodation_flight)
    cyprus_offer = {
        "hotel_name": "Navarria",
        "price": 2500,
        "offer_url": "https://fly.pl/wycieczka/cypr,limassol/navarria/abc123xyz/ofertasv/?filter[tourOperator]=EXIM&filter[person]=1&departureDate=2026-12-20",
        "duration": "8 dni",
        "dates": "20.12.2026 - 27.12.2026",
    }
    assert monitor._is_offer_in_expected_scope(cyprus_offer) is True

    # Оффер Испании (ошибка/сброс поиска fly.pl)
    spain_offer = {
        "hotel_name": "Marbella Inn",
        "price": 3029,
        "offer_url": "https://fly.pl/wycieczka/hiszpania,costa-del-sol,marbella/marbella-inn/abc123xyz/?operator=XTOP&adults=1&departureDate=2026-12-20",
        "duration": "8 dni",
        "dates": "20.12.2026 - 27.12.2026",
    }
    assert monitor._is_offer_in_expected_scope(spain_offer) is False

    # Оффер Албании
    albania_offer = {
        "hotel_name": "Bonita Albania",
        "price": 3019,
        "offer_url": "https://fly.pl/wycieczka/albania,riwiera-albanska,durres/bonita/abc123xyz/?operator=XTOP&departureDate=2026-12-20",
        "duration": "8 dni",
        "dates": "20.12.2026 - 27.12.2026",
    }
    assert monitor._is_offer_in_expected_scope(albania_offer) is False

    # Оффер "только проживание" без перелета
    hotel_only_offer = {
        "hotel_name": "Navarria Hotel Only",
        "price": 1200,
        "offer_url": "https://fly.pl/wycieczka/cypr,limassol/navarria/abc123xyz/?transport=accommodation&adults=1",
        "duration": "8 dni",
        "dates": "20.12.2026 - 27.12.2026",
    }
    assert monitor._is_offer_in_expected_scope(hotel_only_offer) is False


def test_extract_duration_range_from_url():
    """Проверяет корректное извлечение диапазона длительности из различных вариантов query params."""
    # Вариант filter[duration]=7:10
    m1 = TravelPriceMonitor({"url": "https://fly.pl/szukaj-wycieczek/?filter[type]=1&filter[duration]=7:10", "filter_mode": "fixed_trip", "dynamic_search_dates": False})
    assert m1._extract_duration_range_from_url() == (7, 10)

    # Вариант filter%5Bduration%5D=7%3A10
    m2 = TravelPriceMonitor({"url": "https://fly.pl/szukaj-wycieczek/?filter%5Bduration%5D=7%3A10", "filter_mode": "fixed_trip", "dynamic_search_dates": False})
    assert m2._extract_duration_range_from_url() == (7, 10)

    # Вариант durationFrom=7&durationTo=10
    m3 = TravelPriceMonitor({"url": "https://fly.pl/szukaj-wycieczek/?durationFrom=7&durationTo=10", "filter_mode": "fixed_trip", "dynamic_search_dates": False})
    assert m3._extract_duration_range_from_url() == (7, 10)


def test_dashboard_scope_filtering_logic():
    """Проверяет логику отсева мусорных офферов других стран при загрузке данных дашборда."""
    df = pd.DataFrame([
        {
            "hotel_name": "Bonita Albania",
            "price": 3019.0,
            "offer_url": "https://fly.pl/wycieczka/albania,riwiera/bonita/",
            "dates": "20.12.2026 - 27.12.2026"
        },
        {
            "hotel_name": "Marbella Inn",
            "price": 3029.0,
            "offer_url": "https://fly.pl/wycieczka/hiszpania,costa-del-sol/marbella-inn/",
            "dates": "20.12.2026 - 27.12.2026"
        },
        {
            "hotel_name": "Navarria",
            "price": 2500.0,
            "offer_url": "https://fly.pl/wycieczka/cypr,limassol/navarria/ofertasv/",
            "dates": "20.12.2026 - 27.12.2026"
        },
    ])

    cfg_for_scope = {
        "required_offer_url_contains": ["/wycieczka/cypr"],
        "excluded_offer_url_contains": ["/wycieczka/polska", "transport=accommodation&"]
    }

    req_contains = [str(x).strip().lower() for x in cfg_for_scope["required_offer_url_contains"]]
    country_tokens = [t for t in req_contains if t.startswith('/wycieczka/')]
    other_tokens = [t for t in req_contains if not t.startswith('/wycieczka/')]
    excl_contains = [str(x).strip().lower() for x in cfg_for_scope["excluded_offer_url_contains"]]

    def _is_valid_scope(row):
        u = str(row.get('offer_url') or '').strip().lower()
        if not u:
            return True
        if country_tokens and not any(ct in u for ct in country_tokens):
            return False
        if other_tokens:
            for ot in other_tokens:
                if ot == 'transport=accommodation_flight':
                    if 'transport=accommodation&' in u and 'transport=accommodation_flight' not in u:
                        return False
                elif ot not in u:
                    return False
        if excl_contains and any(et in u for et in excl_contains):
            return False
        return True

    filtered_df = df[df.apply(_is_valid_scope, axis=1)]
    assert len(filtered_df) == 1
    assert filtered_df.iloc[0]["hotel_name"] == "Navarria"


def test_early_booking_skip_reason_uses_csv_scraped_at(tmp_path):
    """Verifies check_early_booking_skip_reason reads real scraped_at from CSV rather than git checkout mtime."""
    from datetime import datetime, date, timedelta
    from filter_trip import check_early_booking_skip_reason, extract_last_scraped_at_from_csv

    csv_file = tmp_path / "travel_prices.csv"
    # Scraped 2 days ago
    past_iso = (datetime.now() - timedelta(hours=48)).isoformat()
    csv_file.write_text(
        f'"hotel_name","price","dates","duration","duration_bucket","rating","ta_rating","ta_review_count","ta_source","departure_airport","scraped_at"\n'
        f'"Grand Santana","7642.0","03.07.2027 - 10.07.2027","8 dni","","","","","","Warszawa - Okęcie","{past_iso}"\n',
        encoding="utf-8",
    )

    extracted_dt = extract_last_scraped_at_from_csv(str(csv_file))
    assert extracted_dt is not None

    cfg = {
        "early_booking_tracking": True,
        "trip_anchor_date": "2027-07-15",
        "data_dir": str(tmp_path),
        "output_data_file": "travel_prices.csv",
        "scrape_interval_rules": [
            {"d_min": 60, "d_max": 9999, "every_hours": 12},
        ],
    }

    # 48 hours passed > 12 hours required -> should NOT skip (return empty reason)
    reason = check_early_booking_skip_reason(cfg, today=date(2026, 10, 31), now=datetime.now())
    assert reason == ""

    # Now write a row scraped 2 hours ago
    recent_iso = (datetime.now() - timedelta(hours=2)).isoformat()
    csv_file.write_text(
        f'"hotel_name","price","dates","duration","duration_bucket","rating","ta_rating","ta_review_count","ta_source","departure_airport","scraped_at"\n'
        f'"Grand Santana","7642.0","03.07.2027 - 10.07.2027","8 dni","","","","","","Warszawa - Okęcie","{recent_iso}"\n',
        encoding="utf-8",
    )
    # 2 hours passed < 12 hours required -> SHOULD skip
    reason_recent = check_early_booking_skip_reason(cfg, today=date(2026, 10, 31), now=datetime.now())
    assert "EB расписание" in reason_recent

