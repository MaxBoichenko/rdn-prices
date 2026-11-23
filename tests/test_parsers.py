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


OREE_HTML = """
<table><tr><th>Година</th><th>Ціна, грн/МВт·год</th><th>Обсяг</th></tr>
<tr><td>1</td><td>4 520,10</td><td>1000</td></tr>
<tr><td>2</td><td>4&nbsp;300,00</td><td>900</td></tr>
<tr><td>24</td><td>6000</td><td>900</td></tr>
<tr><td>Base</td><td>5000</td><td></td></tr>
</table>"""

OREE_HTML_RANGE = "<tr><td>00-01</td><td>1000</td></tr><tr><td>23-24</td><td>2000</td></tr>"


def test_oree_parse():
    p = fp.parse_oree_html(OREE_HTML)
    assert p == {1: 4520.10, 2: 4300.0, 24: 6000.0}
    p2 = fp.parse_oree_html(OREE_HTML_RANGE)
    assert p2 == {1: 1000.0, 24: 2000.0}


def test_oree_timezone(monkeypatch):
    monkeypatch.setattr(fp, "nbu_eur_rate", lambda d: 50.0)

    class R:
        text = OREE_HTML

        def json(self):
            raise ValueError

    monkeypatch.setattr(fp, "http", lambda *a, **k: R())
    out = fp.fetch_oree_day(date(2026, 11, 23))
    # час 1 по Киеву (UTC+2 зимой) = 22:00 UTC предыдущих суток
    assert out[U("2026-11-22T22:00Z")] == round(4520.10 / 50, 2)
    assert out[U("2026-11-23T21:00Z")] == 120.0


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
