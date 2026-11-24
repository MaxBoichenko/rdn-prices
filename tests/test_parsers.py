import sys
from datetime import datetime, timezone, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_prices as fp  # noqa: E402

XML_15 = """<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
 <TimeSeries>
  <currency_Unit.name>EUR</currency_Unit.name>
  <curveType>A03</curveType>
  <Period>
   <timeInterval><start>2026-11-22T23:00Z</start><end>2026-11-23T01:00Z</end></timeInterval>
   <resolution>PT15M</resolution>
   <Point><position>1</position><price.amount>100</price.amount></Point>
   <Point><position>2</position><price.amount>80</price.amount></Point>
   <Point><position>4</position><price.amount>60</price.amount></Point>
   <Point><position>5</position><price.amount>50</price.amount></Point>
  </Period>
 </TimeSeries>
 <TimeSeries>
  <currency_Unit.name>EUR</currency_Unit.name>
  <curveType>A01</curveType>
  <Period>
   <timeInterval><start>2026-11-22T23:00Z</start><end>2026-11-23T02:00Z</end></timeInterval>
   <resolution>PT60M</resolution>
   <Point><position>1</position><price.amount>999</price.amount></Point>
   <Point><position>3</position><price.amount>42.5</price.amount></Point>
  </Period>
 </TimeSeries>
</Publication_MarketDocument>"""

ACK = """<Acknowledgement_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-1:acknowledgementdocument:7:0">
<Reason><code>999</code><text>No matching data found for Data item ...</text></Reason></Acknowledgement_MarketDocument>"""


def U(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)


def test_entsoe_15min_a03_and_hourly():
    series, cur = fp.parse_entsoe_a44(XML_15)
    assert cur == "EUR"
    q = series["PT15M"]
    # позиция 3 пропущена -> A03 повторяет 80
    assert q[U("2026-11-22T23:30Z")] == 80
    # позиции 6-8 пропущены -> повторяют 50
    assert q[U("2026-11-23T00:45Z")] == 50
    h = fp.to_hourly(series)
    assert h[U("2026-11-22T23:00Z")] == round((100 + 80 + 80 + 60) / 4, 2)  # 15-мин важнее часовой
    assert h[U("2026-11-23T00:00Z")] == 50
    assert h[U("2026-11-23T01:00Z")] == 42.5          # только часовая
    assert U("2026-11-23T02:00Z") not in h


def test_entsoe_ack():
    series, cur = fp.parse_entsoe_a44(ACK)
    assert series == {} and cur is None


def _dsap(n_prev, n_day, price0=1000.0):
    """Ответ ОРЕЕ DSAP: подряд часы предыдущих суток и суток d."""
    n = n_prev + n_day
    return {
        "price": [price0 + i for i in range(n)],
        "buy": [10.0] * n,
        "sell": [20.0] * n,
        "accepted_volume": [5.0] * n,
    }


def test_oree_dsap_normal_day():
    out = fp.parse_oree_dsap(_dsap(24, 24), date(2026, 11, 23))
    assert len(out) == 24
    # час 1 по Киеву (UTC+2 зимой) = 22:00 UTC предыдущих суток; берутся значения суток d
    assert out[U("2026-11-22T22:00Z")] == {"price": 1024.0, "buy": 10.0, "sell": 20.0, "accepted": 5.0}
    assert out[U("2026-11-23T21:00Z")]["price"] == 1047.0


def test_oree_dsap_spring_dst():
    # 29.03.2026 по Киеву 23 часа, ОРЕЕ всё равно даёт 24 значения; 4-е значение выбрасывается
    out = fp.parse_oree_dsap(_dsap(24, 24), date(2026, 3, 29))
    assert len(out) == 23
    assert out[U("2026-03-28T22:00Z")]["price"] == 1024.0
    assert out[U("2026-03-29T01:00Z")]["price"] == 1028.0
    assert out[U("2026-03-29T20:00Z")]["price"] == 1047.0


def test_oree_dsap_autumn_dst():
    out = fp.parse_oree_dsap(_dsap(24, 25), date(2026, 10, 25))
    assert len(out) == 25
    assert out[U("2026-10-24T21:00Z")]["price"] == 1024.0
    assert out[U("2026-10-25T21:00Z")]["price"] == 1048.0


def test_oree_dsap_empty_or_bad():
    assert fp.parse_oree_dsap({}, date(2026, 11, 23)) == {}
    assert fp.parse_oree_dsap(_dsap(24, 20), date(2026, 11, 23)) == {}      # неожиданная длина
    zeros = {k: [0] * 48 for k in ("price", "buy", "sell", "accepted_volume")}
    assert fp.parse_oree_dsap(zeros, date(2026, 11, 23)) == {}             # данных за день ещё нет


A11 = """<GL_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0">
 <TimeSeries><curveType>A01</curveType>
  <Period><timeInterval><start>2026-11-22T23:00Z</start><end>2026-11-23T01:00Z</end></timeInterval>
   <resolution>PT15M</resolution>
   <Point><position>1</position><quantity>100</quantity></Point>
   <Point><position>2</position><quantity>200</quantity></Point>
   <Point><position>3</position><quantity>300</quantity></Point>
   <Point><position>4</position><quantity>400</quantity></Point>
   <Point><position>5</position><quantity>50</quantity></Point>
   <Point><position>6</position><quantity>50</quantity></Point>
   <Point><position>7</position><quantity>50</quantity></Point>
   <Point><position>8</position><quantity>50</quantity></Point>
  </Period></TimeSeries></GL_MarketDocument>"""


def test_flow_parse_and_daily():
    series, _ = fp.parse_entsoe_a44(A11, value_tag="quantity")
    h = fp.to_hourly(series)
    assert h[U("2026-11-22T23:00Z")] == 250 and h[U("2026-11-23T00:00Z")] == 50
    d = fp.flows_to_daily(h)
    # 23:00 UTC = 00:00 CET 23 ноября -> обе часа в сутках 2026-11-23
    assert d == {"2026-11-23": 300.0}


def test_fetch_flow_tries_alternative_codes(monkeypatch):
    calls = []

    class R:
        status_code = 200

        def __init__(self, t):
            self.text = t

    def fake(method, url, params=None, **k):
        calls.append(params["out_Domain"])
        return R(A11 if params["out_Domain"] == "10Y1001C--00003F" else ACK)

    monkeypatch.setattr(fp, "http", fake)
    monkeypatch.setattr(fp.time, "sleep", lambda s: None)
    fp._flow_codes.clear()
    h = fp.fetch_flow("UA", "HU", U("2026-11-22T23:00Z"), U("2026-11-23T01:00Z"), "x")
    assert len(h) == 2
    assert calls == ["10Y1001C--000182", "10Y1001C--00003F"]
    assert fp._flow_codes[("UA", "HU")] == ("10Y1001C--00003F", "10YHU-MAVIR----U")
