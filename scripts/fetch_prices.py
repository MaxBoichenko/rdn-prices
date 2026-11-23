#!/usr/bin/env python3
"""
Сборщик цен РДН (day-ahead) для PL, RO, SK, HU, UA.

Источники:
  * ENTSO-E Transparency Platform (A44, Day-ahead prices) — PL, RO, SK, HU и UA.
  * ОРЕЕ (oree.com.ua) — запасной источник для Украины (цены в грн),
    перевод в EUR по официальному курсу НБУ на дату поставки.

Все цены сохраняются по часам (UTC) в EUR/MWh в docs/data/YYYY-MM.json.
Если рынок торгуется 15-минутками, часовая цена = среднее четырёх 15-минуток.

Запуск:
  ENTSOE_TOKEN=xxxx python scripts/fetch_prices.py                 # вчера..завтра
  ENTSOE_TOKEN=xxxx python scripts/fetch_prices.py --start 2026-01-01 --end 2026-11-23
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"

ENTSOE_URL = "https://web-api.tp.entsoe.eu/api"
NBU_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange"

CET = ZoneInfo("Europe/Budapest")   # CET/CEST — время торгов SDAC
KYIV = ZoneInfo("Europe/Kyiv")

# EIC-коды ценовых зон
ZONES = {
    "PL": "10YPL-AREA-----S",
    "RO": "10YRO-TEL------P",
    "SK": "10YSK-SEPS-----K",
    "HU": "10YHU-MAVIR----U",
    "UA": "10Y1001C--000182",   # ОЭС Украины
}

_tls = threading.local()


def _session() -> requests.Session:
    if not hasattr(_tls, "s"):
        _tls.s = requests.Session()
        _tls.s.headers["User-Agent"] = "rdn-prices-bot/1.0 (+github actions)"
    return _tls.s


WORKERS = 6   # параллельных запросов к ENTSO-E (лимит платформы — 400 запросов/мин)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- HTTP

def http(method: str, url: str, retries: int = 4, **kw) -> requests.Response:
    """Запрос с повторами при перегрузке сервера (429, любые 5xx, в т.ч. 599 у ENTSO-E)."""
    last = None
    for i in range(retries):
        try:
            r = _session().request(method, url, timeout=90, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                snippet = re.sub(r"\s+", " ", r.text)[:200]
                raise requests.HTTPError(f"HTTP {r.status_code}: {snippet}")
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            if i < retries - 1:
                time.sleep(5 * 2 ** i)   # 5, 10, 20 c
    raise RuntimeError(f"{url.split('?')[0]}: {last}")


# ---------------------------------------------------------------- ENTSO-E

_RES = {"PT15M": timedelta(minutes=15), "PT30M": timedelta(minutes=30), "PT60M": timedelta(hours=1)}


def _strip_ns(root: ET.Element) -> ET.Element:
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def _ts(s: str) -> datetime:
    # 2026-11-22T23:00Z
    return datetime.strptime(s, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)


def parse_entsoe_a44(xml_text: str, value_tag: str = "price.amount", quiet: bool = False
                     ) -> tuple[dict[str, dict[datetime, float]], str | None]:
    """Разбор документа ENTSO-E. Возвращает ({resolution: {utc_start: value}}, currency).
    value_tag: 'price.amount' для цен (A44), 'quantity' для перетоков (A11)."""
    root = _strip_ns(ET.fromstring(xml_text))
    if root.tag.startswith("Acknowledgement"):
        reason = root.findtext(".//Reason/text") or "no data"
        if not quiet:
            log(f"    ENTSO-E: {reason.strip()[:160]}")
        return {}, None
    out: dict[str, dict[datetime, float]] = defaultdict(dict)
    currency = None
    for tsr in root.iter("TimeSeries"):
        cur = tsr.findtext("currency_Unit.name")
        currency = currency or cur
        curve = tsr.findtext("curveType") or "A01"
        for per in tsr.iter("Period"):
            start = _ts(per.findtext("timeInterval/start"))
            end = _ts(per.findtext("timeInterval/end"))
            res_code = per.findtext("resolution")
            step = _RES.get(res_code)
            if step is None:
                continue
            pts = {}
            for p in per.iter("Point"):
                pos = int(p.findtext("position"))
                val = p.findtext(value_tag)
                if val is not None:
                    pts[pos] = float(val)
            n = int((end - start) / step)
            last_val = None
            target = out[res_code]
            for pos in range(1, n + 1):
                if pos in pts:
                    last_val = pts[pos]
                elif curve != "A03":
                    continue  # A01: пропуски не заполняем
                if last_val is None:
                    continue
                t = start + (pos - 1) * step
                target.setdefault(t, last_val)  # первая серия имеет приоритет
    return dict(out), currency


def to_hourly(series: dict[str, dict[datetime, float]]) -> dict[datetime, float]:
    """15-мин -> час (среднее). Если 15-минуток нет — берём часовые."""
    hourly: dict[datetime, float] = {}
    fine = series.get("PT15M") or series.get("PT30M") or {}
    buckets: dict[datetime, list[float]] = defaultdict(list)
    for t, v in fine.items():
        buckets[t.replace(minute=0)].append(v)
    for h, vals in buckets.items():
        hourly[h] = round(sum(vals) / len(vals), 2)
    for t, v in (series.get("PT60M") or {}).items():
        hourly.setdefault(t, round(v, 2))
    return hourly


def fetch_entsoe(zone: str, start_utc: datetime, end_utc: datetime, token: str):
    eic = ZONES[zone]
    hourly: dict[datetime, float] = {}
    currency = None
    cur = start_utc
    while cur < end_utc:
        nxt = min(cur + timedelta(days=31), end_utc)
        params = {
            "securityToken": token,
            "documentType": "A44",
            "in_Domain": eic,
            "out_Domain": eic,
            "periodStart": cur.strftime("%Y%m%d%H%M"),
            "periodEnd": nxt.strftime("%Y%m%d%H%M"),
        }
        try:
            r = http("GET", ENTSOE_URL, params=params)
            if r.status_code == 401:
                raise PermissionError("ENTSO-E: неверный токен (401)")
            if r.status_code != 200 and "Acknowledgement" not in r.text:
                snippet = re.sub(r"\s+", " ", r.text)[:300]
                raise RuntimeError(f"HTTP {r.status_code}: {snippet}")
            series, c = parse_entsoe_a44(r.text)
            currency = currency or c
            for t, v in to_hourly(series).items():
                if start_utc <= t < end_utc:
                    hourly[t] = v
        except PermissionError:
            raise
        except Exception as e:  # noqa: BLE001
            # ошибка одного куска не должна обнулять всю загрузку зоны — пропуск дозаполнится позже
            log(f"    [{zone}] {cur:%Y-%m-%d}..{nxt:%Y-%m-%d}: ОШИБКА {type(e).__name__}: {str(e)[:300]}")
        cur = nxt
    return hourly, currency


# ---------------------------------------------------------------- перетоки (A11)

# EIC-коды для перетоков. Для некоторых стран ENTSO-E публикует данные под разными
# кодами (зона торгов / зона регулирования), поэтому перечислены варианты по порядку.
FLOW_AREAS = {
    "PL":  ["10YPL-AREA-----S"],
    "SK":  ["10YSK-SEPS-----K"],
    "HU":  ["10YHU-MAVIR----U"],
    "RO":  ["10YRO-TEL------P"],
    "UA":  ["10Y1001C--000182", "10Y1001C--00003F", "10YUA-WEPS-----0"],
    "MD":  ["10Y1001A1001A990"],
    "DE":  ["10Y1001A1001A82H", "10YDE-VE-------2"],
    "CZ":  ["10YCZ-CEPS-----N"],
    "LT":  ["10YLT-1001A0008Q"],
    "SE4": ["10Y1001A1001A47J"],
    "AT":  ["10YAT-APG------L"],
    "HR":  ["10YHR-HEP------M"],
    "RS":  ["10YCS-SERBIATSOV"],
    "SI":  ["10YSI-ELES-----O"],
    "BG":  ["10YCA-BULGARIA-R"],
}
# Все границы пяти стран (для сальдо нужен полный набор соседей)
BORDERS = [
    ("PL", "DE"), ("PL", "CZ"), ("PL", "SK"), ("PL", "LT"), ("PL", "SE4"), ("PL", "UA"),
    ("SK", "CZ"), ("SK", "HU"), ("SK", "UA"),
    ("HU", "AT"), ("HU", "UA"), ("HU", "RO"), ("HU", "RS"), ("HU", "HR"), ("HU", "SI"),
    ("RO", "UA"), ("RO", "MD"), ("RO", "BG"), ("RO", "RS"),
    ("UA", "MD"),
]
_flow_codes: dict[tuple[str, str], tuple[str, str]] = {}


def _entsoe_raw(params: dict, token: str) -> str | None:
    """Текст ответа; None — если ENTSO-E отверг запрос (неподходящая пара кодов зон).
    Сбои сервера (5xx) пробрасываются как исключение — это ошибка, а не «нет данных»."""
    r = http("GET", ENTSOE_URL, params={"securityToken": token, **params})
    if r.status_code == 401:
        raise RuntimeError("ENTSO-E: неверный токен (401)")
    if r.status_code != 200 and "Acknowledgement" not in r.text:
        return None
    return r.text


def fetch_flow(frm: str, to: str, start_utc: datetime, end_utc: datetime, token: str) -> dict[datetime, float]:
    """Физический переток frm -> to, MW по часам (UTC)."""
    out: dict[datetime, float] = {}
    cur = start_utc
    while cur < end_utc:
        nxt = min(cur + timedelta(days=31), end_utc)
        combos = [_flow_codes[(frm, to)]] if (frm, to) in _flow_codes else \
            [(a, b) for a in FLOW_AREAS[frm] for b in FLOW_AREAS[to]]
        for a, b in combos:
            text = _entsoe_raw({"documentType": "A11", "out_Domain": a, "in_Domain": b,
                                "periodStart": cur.strftime("%Y%m%d%H%M"),
                                "periodEnd": nxt.strftime("%Y%m%d%H%M")}, token)
            if not text:
                continue
            series, _ = parse_entsoe_a44(text, value_tag="quantity", quiet=True)
            hourly = to_hourly(series)
            if hourly:
                _flow_codes[(frm, to)] = (a, b)
                out.update({t: v for t, v in hourly.items() if start_utc <= t < end_utc})
                break
        cur = nxt
        time.sleep(0.15)
    return out


def flows_to_daily(hourly: dict[datetime, float]) -> dict[str, float]:
    """MW по часам -> MWh за сутки (сутки по CET)."""
    days: dict[str, float] = defaultdict(float)
    for t, mw in hourly.items():
        days[t.astimezone(CET).date().isoformat()] += mw
    return {d: round(v, 1) for d, v in days.items()}


def save_flows(daily: dict[str, dict[str, float]]) -> int:
    """daily: {'PL>UA': {'2026-11-01': MWh}} -> docs/data/flows/YYYY-MM.json"""
    fdir = DATA_DIR / "flows"
    fdir.mkdir(parents=True, exist_ok=True)
    by_month: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for key, days in daily.items():
        for d, v in days.items():
            by_month[d[:7]][key][d] = v
    changed = 0
    for m, keys in by_month.items():
        p = fdir / f"{m}.json"
        doc = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"month": m, "unit": "MWh", "day_tz": "CET", "flows": {}}
        for key, vals in keys.items():
            cur = doc["flows"].setdefault(key, {})
            for d, v in vals.items():
                if cur.get(d) != v:
                    cur[d] = v
                    changed += 1
            doc["flows"][key] = dict(sorted(cur.items()))
        doc["flows"] = dict(sorted(doc["flows"].items()))
        p.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return changed


# ---------------------------------------------------------------- Energy-Charts (запасной источник)

EC_URL = "https://api.energy-charts.info/price"
EC_ZONES = {"PL": "PL", "SK": "SK", "HU": "HU", "RO": "RO"}


def fetch_energy_charts(zone: str, d0: date, d1: date) -> dict[datetime, float]:
    """Цены РДН из Energy-Charts (EUR/MWh), часовые (15-мин усредняются). Без ключа."""
    r = http("GET", EC_URL, params={"bzn": EC_ZONES[zone], "start": d0.isoformat(), "end": (d1 + timedelta(days=1)).isoformat()})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    js = r.json()
    ts, pr = js.get("unix_seconds") or [], js.get("price") or []
    if len(ts) < 2:
        return {}
    step = min(b - a for a, b in zip(ts, ts[1:]) if b > a)
    res = {900: "PT15M", 1800: "PT30M", 3600: "PT60M"}.get(step)
    if not res:
        return {}
    series = {res: {datetime.fromtimestamp(t, timezone.utc): float(v) for t, v in zip(ts, pr) if v is not None}}
    return to_hourly(series)


# ---------------------------------------------------------------- биржи (резерв для пропусков)
# Используются только для дней, которых нет в ENTSO-E. Цены те же самые: сверка 30 случайных
# часов с биржами показала совпадение до цента.

OKTE_URL = "https://isot.okte.sk/api/v1/dam/results"
HUPX_URL = "https://labs.hupx.hu/data/v1/dam_aggregated_trading_data_15min"
OPCOM_URL = "https://www.opcom.ro/grafice-ip-raportPIP-si-volumTranzactionat/ro"
BNR_YEAR_URL = "https://curs.bnr.ro/files/xml/years/nbrfxrates{y}.xml"
BNR_LAST_URL = "https://curs.bnr.ro/nbrfxrates10days.xml"


def _iso_z(x: str) -> datetime:
    return datetime.fromisoformat(x.replace("Z", "+00:00")).astimezone(timezone.utc)


def parse_okte(rows: list) -> dict[datetime, float]:
    """OKTE (Словакия): [{deliveryStart, deliveryEnd, price}] -> часовые цены, EUR."""
    series: dict[str, dict[datetime, float]] = defaultdict(dict)
    for x in rows or []:
        if x.get("price") is None or not x.get("deliveryStart"):
            continue
        a, b = _iso_z(x["deliveryStart"]), _iso_z(x.get("deliveryEnd") or x["deliveryStart"])
        res = "PT15M" if (b - a) == timedelta(minutes=15) else "PT60M"
        series[res][a] = float(x["price"])
    return to_hourly(series)


def fetch_okte(d0: date, d1: date) -> dict[datetime, float]:
    r = http("GET", OKTE_URL, params={"deliveryDayFrom": d0.isoformat(), "deliveryDayTo": d1.isoformat()})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    return parse_okte(r.json())


def parse_hupx(js: dict, region: str = "HU") -> dict[datetime, float]:
    """HUPX Labs: {data:[{DeliveryDay, ProductQH, Price, Region}]} -> часовые цены, EUR.
    ProductQH — номер четверти часа от полуночи по CET (в дни перехода их 92 или 100)."""
    q: dict[datetime, float] = {}
    for x in (js or {}).get("data") or []:
        if x.get("Region") != region or x.get("Price") is None:
            continue
        day = date.fromisoformat(x["DeliveryDay"][:10])
        start = datetime(day.year, day.month, day.day, tzinfo=CET).astimezone(timezone.utc)
        q[start + timedelta(minutes=15 * (int(x["ProductQH"]) - 1))] = float(x["Price"])
    return to_hourly({"PT15M": q})


def fetch_hupx(d0: date, d1: date) -> dict[datetime, float]:
    flt = f"DeliveryDay__gte__{d0.isoformat()},DeliveryDay__lte__{d1.isoformat()},Region__in__HU"
    r = http("GET", HUPX_URL, params={"filter": flt},
             headers={"Accept": "application/json", "Referer": "https://labs.hupx.hu/view/DAM_Aggregated_Trading_Data_15min_v1"})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    return parse_hupx(r.json())


_bnr: dict[str, float] = {}


def _load_bnr(url: str) -> None:
    r = http("GET", url)
    if r.status_code != 200:
        return
    for day, body in re.findall(r'<Cube date="([\d-]+)">(.*?)</Cube>', r.text, flags=re.S):
        m = re.search(r'<Rate currency="EUR">([\d.]+)</Rate>', body)
        if m:
            _bnr[day] = float(m.group(1))


def bnr_eur_rate(d: date) -> float:
    """Курс Нацбанка Румынии RON за 1 EUR, установленный в последний рабочий день до d."""
    for back in range(1, 8):
        day = (d - timedelta(days=back)).isoformat()
        if day in _bnr:
            return _bnr[day]
    for url in {BNR_YEAR_URL.format(y=d.year), BNR_YEAR_URL.format(y=(d - timedelta(days=7)).year), BNR_LAST_URL}:
        if url not in _bnr_loaded:
            _bnr_loaded.add(url)
            try:
                _load_bnr(url)
            except Exception as e:  # noqa: BLE001
                log(f"    НБР: {e}")
    for back in range(1, 8):
        day = (d - timedelta(days=back)).isoformat()
        if day in _bnr:
            return _bnr[day]
    raise RuntimeError(f"НБР: нет курса EUR перед {d}")


_bnr_loaded: set[str] = set()


def parse_opcom(html: str, d: date) -> dict[datetime, float]:
    """OPCOM «Rezultate PZU RO»: строки «Romania <интервал> <цена, лей>» за сутки d (CET).
    Возвращает {UTC-интервал: цена в леях} с шагом 15 или 60 минут."""
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    rows = [(int(n), float(p.replace(".", "").replace(",", ".")))
            for n, p in re.findall(r"Romania\s+(\d+)\s+(-?[\d.]+,\d+)", text)]
    if not rows:
        return {}
    n = max(k for k, _ in rows)
    step = 15 if n >= 90 else 60
    start = datetime(d.year, d.month, d.day, tzinfo=CET).astimezone(timezone.utc)
    return {start + timedelta(minutes=step * (k - 1)): v for k, v in rows}


def fetch_opcom_day(d: date) -> dict[datetime, float]:
    """Цены PZU Румынии за сутки d в EUR (леи OPCOM / курс НБР). Часовые."""
    sess = requests.Session()
    sess.headers["User-Agent"] = "Mozilla/5.0 (rdn-prices-bot)"
    g = sess.get(OPCOM_URL, timeout=60)
    tok = re.search(r'name="_token"\s+value="([^"]+)"', g.text) or re.search(r'value="([^"]+)"\s+name="_token"', g.text)
    if not tok:
        raise RuntimeError("OPCOM: не найден _token формы")
    r = sess.post(OPCOM_URL, timeout=60, data={"_token": tok.group(1), "trading_for": d.strftime("%d/%m/%Y"),
                                               "buton": "Refresh", "action": "trading_for", "limba": "ro"})
    lei = parse_opcom(r.text, d)
    if not lei:
        return {}
    rate = bnr_eur_rate(d)
    step = min(b - a for a, b in zip(sorted(lei), sorted(lei)[1:])) if len(lei) > 1 else timedelta(hours=1)
    res = "PT15M" if step == timedelta(minutes=15) else "PT60M"
    return to_hourly({res: {t: v / rate for t, v in lei.items()}})


def fetch_exchange(zone: str, d0: date, d1: date) -> tuple[dict[datetime, float], str]:
    if zone == "SK":
        return fetch_okte(d0, d1), "OKTE"
    if zone == "HU":
        return fetch_hupx(d0, d1), "HUPX"
    if zone == "RO":
        out: dict[datetime, float] = {}
        d = d0
        while d <= d1:
            out.update(fetch_opcom_day(d))
            d += timedelta(days=1)
        return out, "OPCOM (леи → € по курсу НБР)"
    return {}, ""


# ---------------------------------------------------------------- НБУ

_nbu_cache: dict[date, float] = {}


def nbu_eur_rate(d: date) -> float:
    """Официальный курс НБУ UAH за 1 EUR на дату d (или ближайшую предыдущую)."""
    for back in range(0, 7):
        day = d - timedelta(days=back)
        if day in _nbu_cache:
            return _nbu_cache[day]
        r = http("GET", NBU_URL, params={"valcode": "EUR", "date": day.strftime("%Y%m%d"), "json": ""})
        try:
            js = r.json()
        except ValueError:
            js = []
        if js and js[0].get("rate"):
            _nbu_cache[day] = float(js[0]["rate"])
            return _nbu_cache[day]
    raise RuntimeError(f"НБУ: нет курса EUR около {d}")


# ---------------------------------------------------------------- ОРЕЕ



def _to_float(s: str) -> float | None:
    s = unescape(s).replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


OREE_DSAP_URL = "https://www.oree.com.ua/index.php/IDM_graphs/get_data_for_chart_DSAP"
UA_DIR = DATA_DIR / "ua_dam"


def kyiv_hours(d: date) -> int:
    a = datetime(d.year, d.month, d.day, tzinfo=KYIV).astimezone(timezone.utc)
    b = datetime.combine(d + timedelta(days=1), datetime.min.time(), tzinfo=KYIV).astimezone(timezone.utc)
    return int((b - a).total_seconds() // 3600)


def _f(x):
    try:
        return None if x in (None, "") else float(x)
    except (TypeError, ValueError):
        return None


def parse_oree_dsap(js: dict, d: date) -> dict[datetime, dict]:
    """Ответ ОРЕЕ «Попит, пропозиція, акцепт та ціна» (IDM_graphs/get_data_for_chart_DSAP).
    Массивы содержат подряд часы предыдущих суток и суток d (по Киеву).
    Возвращает {UTC-час: {"price": грн/МВт·ч, "buy": МВт·ч, "sell": МВт·ч, "accepted": МВт·ч}}."""
    price = js.get("price") or []
    total = len(price)
    if not total:
        return {}
    n_prev = 25 if kyiv_hours(d - timedelta(days=1)) == 25 else 24   # ОРЕЕ даёт 24 значения и в весенние сутки
    idx = list(range(n_prev, total))
    exp = kyiv_hours(d)
    if exp == 23 and len(idx) == 24:
        idx.pop(3)                       # весенний переход: часа 03:00–04:00 нет
    if len(idx) != exp:
        log(f"    ОРЕЕ {d}: неожиданная длина ответа {total} (ожидалось {n_prev}+{exp})")
        return {}
    start = datetime(d.year, d.month, d.day, tzinfo=KYIV).astimezone(timezone.utc)
    out = {}
    for i, j in enumerate(idx):
        row = {k: _f((js.get(src) or [None] * total)[j]) for k, src in
               (("price", "price"), ("buy", "buy"), ("sell", "sell"), ("accepted", "accepted_volume"))}
        out[start + timedelta(hours=i)] = row
    # ОРЕЕ отдаёт нули, когда данных за день ещё нет
    if all(not r["price"] and not r["accepted"] for r in out.values()):
        return {}
    return out


def fetch_oree_dsap(d: date) -> dict[datetime, dict]:
    """ОРЕЕ при частых запросах иногда отдаёт HTML-страницу вместо данных — тогда ждём и повторяем."""
    last = None
    for attempt in range(4):
        time.sleep(0.7 if attempt == 0 else 10 * attempt)
        r = http("POST", OREE_DSAP_URL, data={"date": d.strftime("%d.%m.%Y"), "shopping_area": "OES", "market": "DAM"},
                 headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json, text/javascript, */*; q=0.01",
                          "Referer": "https://www.oree.com.ua/index.php/IDM_graphs"})
        if r.status_code != 200:
            last = f"HTTP {r.status_code}"
            continue
        try:
            js = r.json()
        except ValueError:
            last = "ответ не JSON (сайт ограничил частоту запросов)"
            continue
        return parse_oree_dsap(js, d)
    raise RuntimeError(last)


def load_ua_month(key: str) -> dict:
    p = UA_DIR / f"{key}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"month": key, "tz": "UTC", "source": "ОРЕЕ, РДН, ОЕС України",
            "units": {"price": "UAH/MWh", "buy": "MWh", "sell": "MWh", "accepted": "MWh"},
            "price": {}, "buy": {}, "sell": {}, "accepted": {}}


def save_ua_dam(rows: dict[datetime, dict]) -> int:
    UA_DIR.mkdir(parents=True, exist_ok=True)
    by_m: dict[str, dict[datetime, dict]] = defaultdict(dict)
    for t, r in rows.items():
        by_m[month_key(t)][t] = r
    changed = 0
    for key, rs in by_m.items():
        doc = load_ua_month(key)
        for t, r in rs.items():
            for k in ("price", "buy", "sell", "accepted"):
                if r.get(k) is not None and doc[k].get(iso(t)) != r[k]:
                    doc[k][iso(t)] = r[k]
                    changed += 1
        for k in ("price", "buy", "sell", "accepted"):
            doc[k] = dict(sorted(doc[k].items()))
        (UA_DIR / f"{key}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return changed


def ua_stored_hours(d: date) -> int:
    s = datetime(d.year, d.month, d.day, tzinfo=KYIV).astimezone(timezone.utc)
    e = s + timedelta(hours=kyiv_hours(d))
    keys = {month_key(s), month_key(e - timedelta(hours=1))}
    n = 0
    for k in keys:
        acc = load_ua_month(k)["accepted"]
        n += sum(1 for x in acc if s <= _ts(x) < e)
    return n


def ua_prices_eur(d: date) -> dict[datetime, float]:
    """Цены РДН Украины из сохранённых данных ОРЕЕ, в EUR по курсу НБУ на дату поставки."""
    s = datetime(d.year, d.month, d.day, tzinfo=KYIV).astimezone(timezone.utc)
    e = s + timedelta(hours=kyiv_hours(d))
    out = {}
    for k in {month_key(s), month_key(e - timedelta(hours=1))}:
        for x, v in load_ua_month(k)["price"].items():
            t = _ts(x)
            if s <= t < e and v:
                out[t] = v
    if not out:
        return {}
    rate = nbu_eur_rate(d)
    return {t: round(v / rate, 2) for t, v in out.items()}


# ---------------------------------------------------------------- хранилище

def month_key(t: datetime) -> str:
    return t.strftime("%Y-%m")


def iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%MZ")


def load_month(key: str) -> dict:
    p = DATA_DIR / f"{key}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"month": key, "unit": "EUR/MWh", "tz": "UTC", "prices": {}}


def save(new: dict[str, dict[datetime, float]], sources: dict[str, str]) -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    by_month: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for zone, series in new.items():
        for t, v in series.items():
            by_month[month_key(t)][zone][iso(t)] = v
    changed = 0
    for key, zones in by_month.items():
        doc = load_month(key)
        for zone, vals in zones.items():
            cur = doc["prices"].setdefault(zone, {})
            for k, v in vals.items():
                if cur.get(k) != v:
                    cur[k] = v
                    changed += 1
            doc["prices"][zone] = dict(sorted(cur.items()))
        doc["prices"] = dict(sorted(doc["prices"].items()))
        (DATA_DIR / f"{key}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    return changed


def write_meta(sources: dict[str, str], changed: bool) -> None:
    """meta.json: время обновления, месяцы с ценами/перетоками, последние данные, источники."""
    months = sorted(p.stem for p in DATA_DIR.glob("????-??.json"))
    flow_months = sorted(p.stem for p in (DATA_DIR / "flows").glob("????-??.json")) if (DATA_DIR / "flows").exists() else []
    ua_months = sorted(p.stem for p in UA_DIR.glob("????-??.json")) if UA_DIR.exists() else []
    last: dict[str, str] = {}
    for key in reversed(months):
        for zone, vals in load_month(key)["prices"].items():
            if zone not in last and vals:
                last[zone] = max(vals)
    flow_last = None
    if flow_months:
        doc = json.loads((DATA_DIR / "flows" / f"{flow_months[-1]}.json").read_text(encoding="utf-8"))
        flow_last = max((max(v) for v in doc["flows"].values() if v), default=None)
    meta_p = DATA_DIR / "meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    if changed or not meta:
        meta.update({
            "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "months": months,
            "last": last,
            "flow_months": flow_months,
            "ua_dam_months": ua_months,
            "flow_last": flow_last,
            "borders": [f"{a}-{b}" for a, b in BORDERS],
            "sources": {**meta.get("sources", {}), **sources},
            "zones": list(ZONES),
        })
        meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", help="первая дата поставки YYYY-MM-DD (по умолчанию: 7 дней назад)")
    ap.add_argument("--end", help="последняя дата поставки YYYY-MM-DD (по умолчанию: завтра)")
    ap.add_argument("--zones", default=",".join(ZONES))
    ap.add_argument("--no-flows", action="store_true", help="не загружать перетоки")
    ap.add_argument("--only-flows", action="store_true", help="загрузить только перетоки")
    ap.add_argument("--budget", type=float, default=95, help="лимит времени работы, минут")
    ap.add_argument("--no-ua-volumes", action="store_true", help="не загружать объёмы РДН Украины (ОРЕЕ)")
    args = ap.parse_args()
    deadline = time.monotonic() + args.budget * 60

    token = os.environ.get("ENTSOE_TOKEN", "").strip()
    if not token:
        sys.exit("Нет ENTSOE_TOKEN (секрет репозитория или переменная окружения)")

    today = datetime.now(CET).date()
    d0 = date.fromisoformat(args.start) if args.start else today - timedelta(days=7)
    d1 = date.fromisoformat(args.end) if args.end else today + timedelta(days=1)
    # берём с запасом в сутки в обе стороны — чтобы покрыть сдвиг часовых поясов Киева
    start_utc = datetime(d0.year, d0.month, d0.day, tzinfo=CET).astimezone(timezone.utc) - timedelta(hours=2)
    end_utc = datetime(d1.year, d1.month, d1.day, tzinfo=CET).astimezone(timezone.utc) + timedelta(days=1)

    zones = [] if args.only_flows else [z.strip().upper() for z in args.zones.split(",") if z.strip()]
    result: dict[str, dict[datetime, float]] = {}
    sources: dict[str, str] = {}
    errors = []

    def fetch_zone(z: str, s_utc: datetime, e_utc: datetime) -> dict[datetime, float]:
        series, currency = fetch_entsoe(z, s_utc, e_utc, token)
        if series and currency and currency.upper() != "EUR":
            if currency.upper() == "UAH":
                series = {t: round(v / nbu_eur_rate(t.astimezone(KYIV).date()), 2) for t, v in series.items()}
            else:
                raise RuntimeError(f"неожиданная валюта {currency}")
        return series

    def run_zone(z: str):
        try:
            return z, fetch_zone(z, start_utc, end_utc), None
        except Exception as e:  # noqa: BLE001
            return z, {}, e

    with ThreadPoolExecutor(WORKERS) as ex:
        for z, series, err in ex.map(run_zone, zones):
            if err:
                log(f"[{z}] ENTSO-E {d0}..{d1}: ОШИБКА {err}")
                errors.append(f"{z}/ENTSO-E: {err}")
                continue
            log(f"[{z}] ENTSO-E {d0}..{d1}: часов {len(series)}")
            if series:
                result[z] = series
                sources[z] = "ENTSO-E Transparency Platform"

    changed = save(result, sources)

    # Украина: почасовые объёмы РДН (спрос, предложение, акцепт) и цены в грн — с сайта ОРЕЕ.
    # Ежедневно: последние 7 суток и завтра; при загрузке истории — только недостающие сутки.
    ua_changed = 0
    if "UA" in zones and not args.no_ua_volumes:
        u0 = d0 if args.start else today - timedelta(days=7)
        u1 = min(d1, today + timedelta(days=1))
        days = []
        d = u0
        while d <= u1:
            if args.start is None or d >= today - timedelta(days=2) or ua_stored_hours(d) < kyiv_hours(d):
                days.append(d)
            d += timedelta(days=1)
        if days:
            log(f"[UA] ОРЕЕ объёмы: суток к загрузке {len(days)}")

        def run_ua(day):
            if time.monotonic() > deadline - 25 * 60:
                return day, None, "время"
            try:
                return day, fetch_oree_dsap(day), None
            except Exception as e:  # noqa: BLE001
                return day, None, e

        rows: dict[datetime, dict] = {}
        empty_days, err_days, late = [], [], 0
        with ThreadPoolExecutor(2) as ex:
            for day, res, err in ex.map(run_ua, days):
                if err == "время":
                    late += 1
                elif err:
                    err_days.append(f"{day}: {err}")
                elif not res:
                    empty_days.append(str(day))
                else:
                    rows.update(res)
        ua_changed = save_ua_dam(rows)
        if days:
            log(f"    получено суток: {len(days) - len(empty_days) - len(err_days) - late}; "
                f"без данных: {', '.join(empty_days[-10:]) or '—'}"
                + (f"; ошибки ({len(err_days)}): {'; '.join(e[:120] for e in err_days[:3])}" if err_days else "")
                + (f"; не успели (время): {late}" if late else ""))
        changed += ua_changed

    # Дозаполнение пропусков: сутки, где меньше 23 часов, запрашиваем повторно по одному дню.
    # Для Украины, если ENTSO-E не помог, пробуем ОРЕЕ.
    check_to = min(d1, today if datetime.now(CET).hour < 14 else today + timedelta(days=1))
    g0 = d0 if args.start else today - timedelta(days=120)   # ежедневно проверяем пропуски за 4 месяца
    month_keys = []
    m = date(g0.year, g0.month, 1) - timedelta(days=1)
    m = date(m.year, m.month, 1)
    while m <= check_to:
        month_keys.append(m.strftime("%Y-%m"))
        m = (m + timedelta(days=32)).replace(day=1)
    for z in zones:
        tz = KYIV if z == "UA" else CET
        per_day: dict[date, int] = defaultdict(int)
        for key in month_keys:
            for k in load_month(key)["prices"].get(z, {}):
                per_day[_ts(k).astimezone(tz).date()] += 1
        gaps = []
        d = g0
        while d <= check_to:
            if per_day.get(d, 0) < 23:
                gaps.append(d)
            d += timedelta(days=1)
        if not gaps:
            continue
        log(f"[{z}] неполных суток: {len(gaps)} ({gaps[0]} … {gaps[-1]})")
        # склеиваем соседние дни в отрезки до 31 дня — так меньше запросов
        ranges = []
        for g in gaps:
            if ranges and (g - ranges[-1][1]).days == 1 and (g - ranges[-1][0]).days < 31:
                ranges[-1][1] = g
            else:
                ranges.append([g, g])
        filled: dict[datetime, float] = {}
        for r0, r1 in ranges:
            if time.monotonic() > deadline - 20 * 60:
                log("    (время: остальные пропуски — в следующем запуске)")
                break
            ds = datetime(r0.year, r0.month, r0.day, tzinfo=tz).astimezone(timezone.utc)
            de = datetime.combine(r1 + timedelta(days=1), datetime.min.time(), tzinfo=tz).astimezone(timezone.utc)
            got: dict[datetime, float] = {}
            try:
                got = {t: v for t, v in fetch_zone(z, ds - timedelta(hours=1), de + timedelta(hours=1)).items() if ds <= t < de}
            except Exception as e:  # noqa: BLE001
                log(f"    {r0}..{r1} ENTSO-E ОШИБКА: {e}")
            exp = int((de - ds).total_seconds() // 3600)
            log(f"    {r0}..{r1}: ENTSO-E дал {len(got)} из {exp} часов")
            filled.update(got)
        # SK/HU/RO: чего нет в ENTSO-E — берём с сайта биржи (OKTE, HUPX, OPCOM)
        if z in ("SK", "HU", "RO"):
            for r0, r1 in ranges:
                if time.monotonic() > deadline - 15 * 60:
                    break
                ds = datetime(r0.year, r0.month, r0.day, tzinfo=tz).astimezone(timezone.utc)
                de = datetime.combine(r1 + timedelta(days=1), datetime.min.time(), tzinfo=tz).astimezone(timezone.utc)
                exp = int((de - ds).total_seconds() // 3600)
                if sum(1 for t in filled if ds <= t < de) >= exp - 1:
                    continue
                if z == "RO" and (r1 - r0).days > 31:
                    log(f"    {r0}..{r1}: OPCOM — слишком длинный отрезок, пропускаю")
                    continue
                try:
                    ex, src = fetch_exchange(z, r0, r1)
                    ex = {t: round(v, 2) for t, v in ex.items() if ds <= t < de and t not in filled}
                    log(f"    {r0}..{r1}: {src} дал {len(ex)} часов")
                    if ex:
                        filled.update(ex)
                        sources[z] = f"ENTSO-E Transparency Platform; {src} (пропуски)"
                except Exception as e:  # noqa: BLE001
                    log(f"    {r0}..{r1} биржа ОШИБКА: {e}")
        # PL/SK/HU/RO: чего нет в ENTSO-E — пробуем Energy-Charts (Fraunhofer ISE, CC BY 4.0)
        if z in EC_ZONES:
            for r0, r1 in ranges:
                ds = datetime(r0.year, r0.month, r0.day, tzinfo=tz).astimezone(timezone.utc)
                de = datetime.combine(r1 + timedelta(days=1), datetime.min.time(), tzinfo=tz).astimezone(timezone.utc)
                exp = int((de - ds).total_seconds() // 3600)
                have_n = sum(1 for t in filled if ds <= t < de)
                if have_n >= exp - 1:
                    continue
                try:
                    ec = fetch_energy_charts(z, r0, r1)
                    ec = {t: v for t, v in ec.items() if ds <= t < de and t not in filled}
                    log(f"    {r0}..{r1}: Energy-Charts дал {len(ec)} часов")
                    if ec:
                        filled.update(ec)
                        sources[z] = "ENTSO-E Transparency Platform; Energy-Charts (пропуски)"
                except Exception as e:  # noqa: BLE001
                    log(f"    {r0}..{r1} Energy-Charts ОШИБКА: {e}")
        # Украина: дни, которых нет в ENTSO-E, берём из данных ОРЕЕ (собраны шагом выше)
        if z == "UA":
            for g in gaps:
                ds = datetime(g.year, g.month, g.day, tzinfo=tz).astimezone(timezone.utc)
                de = ds + timedelta(hours=kyiv_hours(g))
                if sum(1 for t in filled if ds <= t < de) >= 23:
                    continue
                try:
                    o = ua_prices_eur(g)
                    log(f"    {g}: ОРЕЕ дал {len(o)} часов")
                    if o:
                        filled.update(o)
                        sources["UA"] = "ENTSO-E Transparency Platform; ОРЕЕ (грн → EUR по курсу НБУ)"
                except Exception as e:  # noqa: BLE001
                    log(f"    {g} ОРЕЕ ОШИБКА: {e}")
        if filled:
            changed += save({z: filled}, {})
    log(f"Цены: изменено значений: {changed}")

    # Перетоки: только полные прошедшие сутки (по CET), с запасом 3 дня на поздние публикации.
    # Загружаем и сохраняем помесячно; уже полные месяцы пропускаем — так длинную историю
    # можно догружать несколькими запусками.
    f_changed = 0
    n_flow = 0
    stopped = False
    if not args.no_flows:
        f0 = d0 if args.start else today - timedelta(days=120)
        recent = today - timedelta(days=3)    # последние дни перезапрашиваем всегда (поздние публикации)
        f1 = min(d1, today - timedelta(days=1))
        dirs = [fd for a, b in BORDERS for fd in ((a, b), (b, a))]
        m = date(f0.year, f0.month, 1)
        while m <= f1:
            nm = (m + timedelta(days=32)).replace(day=1)
            p0, p1 = max(m, f0), min(nm - timedelta(days=1), f1)
            m = nm
            need_days = {(p0 + timedelta(days=i)).isoformat() for i in range((p1 - p0).days + 1)}
            fpath = DATA_DIR / "flows" / f"{p0:%Y-%m}.json"
            have = json.loads(fpath.read_text(encoding="utf-8"))["flows"] if fpath.exists() else {}
            refresh_all = args.start is None and p1 >= recent
            todo = [fd for fd in dirs if refresh_all or not need_days <= set(have.get(f"{fd[0]}>{fd[1]}", {}))]
            if not todo:
                continue
            if time.monotonic() > deadline:
                stopped = True
                break
            fs = datetime(p0.year, p0.month, p0.day, tzinfo=CET).astimezone(timezone.utc)
            fe = datetime.combine(p1 + timedelta(days=1), datetime.min.time(), tzinfo=CET).astimezone(timezone.utc)

            def run_flow(fd, fs=fs, fe=fe):
                try:
                    return fd, fetch_flow(fd[0], fd[1], fs, fe, token), None
                except Exception as e:  # noqa: BLE001
                    return fd, {}, e

            daily: dict[str, dict[str, float]] = {}
            empty = []
            with ThreadPoolExecutor(WORKERS) as ex:
                for (frm, to), h, err in ex.map(run_flow, todo):
                    if err:
                        log(f"[flow] {frm}>{to} {p0:%Y-%m} ОШИБКА: {err}")
                        errors.append(f"flow {frm}>{to} {p0:%Y-%m}: {err}")
                    elif h:
                        daily[f"{frm}>{to}"] = flows_to_daily(h)
                    else:
                        empty.append(f"{frm}>{to}")
            n_flow = max(n_flow, len(daily))
            c = save_flows(daily)
            f_changed += c
            log(f"[flow] {p0}..{p1}: направлений с данными {len(daily)}/{len(todo)}"
                + (f"; пусто: {', '.join(empty)}" if empty else ""))
        log(f"Перетоки: изменено значений: {f_changed}")
        if stopped:
            log("ВРЕМЯ ЗАПУСКА ЗАКАНЧИВАЕТСЯ: загруженное сохранено. Запустите ещё раз с той же датой — "
                "готовые месяцы будут пропущены, загрузка продолжится с места остановки.")

    write_meta(sources, bool(changed or f_changed))
    if errors:
        log("Ошибки:\n  " + "\n  ".join(errors))
    # падаем только если не получили вообще ничего
    if not result and not n_flow and not stopped:
        sys.exit(1)


if __name__ == "__main__":
    main()
