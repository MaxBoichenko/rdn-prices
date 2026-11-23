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
OREE_URL = "https://www.oree.com.ua/index.php/pricectr/data_view"
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

def http(method: str, url: str, retries: int = 3, **kw) -> requests.Response:
    last = None
    for i in range(retries):
        try:
            r = _session().request(method, url, timeout=90, **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}")
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


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
        r = http("GET", ENTSOE_URL, params=params)
        if r.status_code == 401:
            raise RuntimeError("ENTSO-E: неверный токен (401)")
        if r.status_code == 400 and "Acknowledgement" not in r.text:
            raise RuntimeError(f"ENTSO-E 400: {r.text[:300]}")
        series, c = parse_entsoe_a44(r.text)
        currency = currency or c
        for t, v in to_hourly(series).items():
            if start_utc <= t < end_utc:
                hourly[t] = v
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


def parse_oree_html(html: str) -> dict[int, float]:
    """Таблица ОРЕЕ: строки 'Година | Ціна, грн/МВт·год | ...'.
    Возвращает {номер_часа 1..24: цена_грн}."""
    prices: dict[int, float] = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S | re.I):
        cells = [re.sub(r"<[^>]+>", "", c).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.S | re.I)]
        if len(cells) < 2:
            continue
        m = re.match(r"^(\d{1,2})(?:\s*[-–:]\s*\d{1,2})?$", cells[0].replace(":00", ""))
        if not m:
            continue
        hour = int(m.group(1))
        # формат "00-01" -> час 1; формат "1".."24" -> как есть
        if re.match(r"^\d{1,2}\s*[-–]", cells[0]):
            hour += 1
        if not 1 <= hour <= 25:
            continue
        price = _to_float(cells[1])
        if price is not None:
            prices[hour] = price
    return prices


def fetch_oree_day(d: date) -> dict[datetime, float]:
    r = http("POST", OREE_URL, data={"date": d.strftime("%d.%m.%Y"), "market": "DAM", "zone": "IPS"},
             headers={"X-Requested-With": "XMLHttpRequest", "Referer": "https://www.oree.com.ua/index.php/pricectr"})
    text = r.text
    try:
        js = r.json()
        if isinstance(js, dict):
            text = js.get("html") or js.get("data") or json.dumps(js)
    except ValueError:
        pass
    by_hour = parse_oree_html(text)
    if not by_hour:
        snippet = re.sub(r"\s+", " ", text)[:600]
        log(f"    ОРЕЕ: HTTP {r.status_code}, {r.headers.get('content-type')}, {len(text)} байт; начало ответа: {snippet}")
        return {}
    rate = nbu_eur_rate(d)
    out = {}
    midnight = datetime(d.year, d.month, d.day, tzinfo=KYIV)
    for h, uah in sorted(by_hour.items()):
        # час N = интервал (N-1):00–N:00 по Киеву; переход на летнее/зимнее время
        # учитываем через UTC-арифметику
        t_utc = (midnight.astimezone(timezone.utc) + timedelta(hours=h - 1))
        out[t_utc] = round(uah / rate, 2)
    return out


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
    args = ap.parse_args()

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

    # Дозаполнение пропусков: сутки, где меньше 23 часов, запрашиваем повторно по одному дню.
    # Для Украины, если ENTSO-E не помог, пробуем ОРЕЕ.
    check_to = min(d1, today if datetime.now(CET).hour < 14 else today + timedelta(days=1))
    month_keys = []
    m = date(d0.year, d0.month, 1) - timedelta(days=1)
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
        d = d0
        while d <= check_to:
            if per_day.get(d, 0) < 23:
                gaps.append(d)
            d += timedelta(days=1)
        if not gaps:
            continue
        log(f"[{z}] неполные сутки: {', '.join(str(g) for g in gaps[:40])}{' …' if len(gaps) > 40 else ''}")
        filled: dict[datetime, float] = {}
        for g in gaps[:120]:
            ds = datetime(g.year, g.month, g.day, tzinfo=tz).astimezone(timezone.utc)
            de = datetime.combine(g + timedelta(days=1), datetime.min.time(), tzinfo=tz).astimezone(timezone.utc)
            got: dict[datetime, float] = {}
            try:
                got = {t: v for t, v in fetch_zone(z, ds - timedelta(hours=1), de + timedelta(hours=1)).items() if ds <= t < de}
            except Exception as e:  # noqa: BLE001
                log(f"    {g} ENTSO-E ОШИБКА: {e}")
            src = "ENTSO-E"
            if len(got) < 23 and z == "UA":
                try:
                    o = fetch_oree_day(g)
                    if len(o) > len(got):
                        got, src = o, "ОРЕЕ"
                        sources["UA"] = "ENTSO-E Transparency Platform; ОРЕЕ (грн → EUR по курсу НБУ)"
                except Exception as e:  # noqa: BLE001
                    log(f"    {g} ОРЕЕ ОШИБКА: {e}")
            log(f"    {g}: получено часов {len(got)} ({src})")
            filled.update(got)
        if filled:
            changed += save({z: filled}, {})
    log(f"Цены: изменено значений: {changed}")

    # Перетоки: только полные прошедшие сутки (по CET), с запасом 3 дня на поздние публикации
    f_changed = 0
    n_flow = 0
    if not args.no_flows:
        f0 = d0 if args.start else today - timedelta(days=3)
        f1 = min(d1, today - timedelta(days=1))
        if f0 <= f1:
            fs = datetime(f0.year, f0.month, f0.day, tzinfo=CET).astimezone(timezone.utc)
            fe = datetime.combine(f1 + timedelta(days=1), datetime.min.time(), tzinfo=CET).astimezone(timezone.utc)
            daily: dict[str, dict[str, float]] = {}
            dirs = [fd for a, b in BORDERS for fd in ((a, b), (b, a))]

            def run_flow(fd):
                try:
                    return fd, fetch_flow(fd[0], fd[1], fs, fe, token), None
                except Exception as e:  # noqa: BLE001
                    return fd, {}, e

            with ThreadPoolExecutor(WORKERS) as ex:
                for (frm, to), h, err in ex.map(run_flow, dirs):
                    if err:
                        log(f"[flow] {frm}>{to} ОШИБКА: {err}")
                        errors.append(f"flow {frm}>{to}: {err}")
                        continue
                    if h:
                        daily[f"{frm}>{to}"] = flows_to_daily(h)
                        n_flow += 1
                    log(f"[flow] {frm}>{to} {f0}..{f1}: часов {len(h)}")
            f_changed = save_flows(daily)
            log(f"Перетоки: направлений с данными {n_flow}, изменено значений: {f_changed}")

    write_meta(sources, bool(changed or f_changed))
    if errors:
        log("Ошибки:\n  " + "\n  ".join(errors))
    # падаем только если не получили вообще ничего
    if not result and not n_flow:
        sys.exit(1)


if __name__ == "__main__":
    main()
