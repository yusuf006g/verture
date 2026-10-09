import re
from typing import Any

from bot.config import settings

MI_TO_KM = 1.609344


def _capture(pattern: str, text: str, flags=re.IGNORECASE | re.MULTILINE) -> str | None:
    match = re.search(pattern, text, flags)
    if not match:
        return None
    value = match.group(1).strip().strip("* \t")
    return value or None


def _number(raw: str | None) -> float | None:
    """Parse numbers; handles OCR variants like 3,600.00 / 3,600,00 / 3,600 00."""
    if not raw:
        return None
    cleaned = raw.strip().replace("$", "")
    # "3,600 00" -> "3,600.00" (OCR lost the decimal point, left a space)
    cleaned = re.sub(r"(?<=\d) (?=\d{2}$)", ".", cleaned)
    cleaned = cleaned.replace(" ", "")

    # Last separator followed by exactly 2 digits -> it is the decimal part
    m = re.fullmatch(r"(\d[\d.,]*)[.,](\d{2})", cleaned)
    if m:
        int_part = re.sub(r"[.,]", "", m.group(1))
        try:
            return float(f"{int_part}.{m.group(2)}")
        except ValueError:
            return None

    # No decimal part: remaining separators are thousands separators
    if "." in cleaned:
        cleaned = cleaned.replace(",", "")
    elif cleaned.count(",") == 1:
        left, right = cleaned.split(",")
        cleaned = left + right if len(right) == 3 else left + "." + right
    else:
        cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _clean_value(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().strip("* \t")
    value = re.sub(r"\s+", " ", value)
    return value or None


def _find_stops(text: str) -> list[dict[str, Any]]:
    blocks = re.split(r"(?=\bSTOP\s+\d+\s*:)", text, flags=re.IGNORECASE)
    stops = []
    for block in blocks:
        head = re.search(r"\bSTOP\s+(\d+)\s*:\s*([^\n\r]+)", block, re.IGNORECASE)
        if not head:
            continue
        name = _clean_value(head.group(2))
        address = _capture(r"(?:^|\n)\s*(?:ADDRESS|ADDRESS 1|STREET ADDRESS)\s*:\s*([^\n\r]+)", block)
        # OCR sometimes puts the address on the next line after ADDRESS:.
        if address and address.upper().startswith(("PHONE", "APPT", "APPOINTMENT", "TYPE")):
            address = None
        if not address:
            address = _capture(r"(?:^|\n)\s*ADDRESS\s*:\s*\n\s*([^\n\r]+)", block)
        # Never mistake a phone number or another label for an address.
        if address and (re.search(r"\(?\d{3}\)?[- .]?\d{3}[- .]?\d{4}", address) or re.match(r"(?:PHONE|APPT|TYPE|COMMODITY|EQUIPMENT)\b", address, re.I)):
            address = None
        stops.append({
            "stop_number": int(head.group(1)),
            "name": name,
            "address": _clean_value(address),
            "type": _clean_value(_capture(r"(?:STOP\s+TYPE|TYPE)\s*:\s*([^\n\r]+)", block)),
        })
    return stops


def calc_dispatcher(rate: float | None, percent: float) -> tuple[float | None, float | None]:
    """Returns (dispatcher_fee, net_rate)."""
    if not isinstance(rate, (int, float)):
        return None, None
    fee = round(rate * percent / 100, 2)
    return fee, round(rate - fee, 2)


def parse_load(text: str) -> dict[str, Any]:
    """Rule-based parser. Missing fields stay None; no generated guesses."""
    trip = _capture(r"(?:NEW\s+)?TRIP\s*#?\s*(\d+)\s+HAS\s+BEEN\s+ASSIGNED", text)
    if not trip:
        trip = _capture(r"TRIP\s*#\s*:?\s*(\d+)", text)

    ref = _capture(r"\bREF\s*#\s*:?\s*([A-Z0-9-]+)", text)
    # Restrict numeric captures to the same line and stop at the unit/next field.
    distance_raw = _capture(r"LOADED\s+DISTANCE\s*:\s*\$?\s*([\d,]+(?:\.\d+)?)\s*(?:mi\b|miles?\b)", text)
    distance_mi = _number(distance_raw)
    distance_km = round(distance_mi * MI_TO_KM, 1) if distance_mi is not None else None

    rate_raw = _capture(r"\bRATE\s*:\s*\$?\s*(\d[\d,]*(?:[.,]\d{2}|[ ]\d{2}\b)?)", text)
    rate_usd = _number(rate_raw)
    rate_per_mile_raw = _capture(r"\bRATE\s*:[^\n\r]*?/\s*\$?\s*([\d,]+(?:\.\d{1,2})?)", text)
    rate_per_mile = _number(rate_per_mile_raw)

    commodity = _capture(r"\bCOMMODITY\s*:\s*([^\n\r]+)", text)
    # Avoid a duplicate leading quantity if OCR includes it in the commodity label.
    if commodity:
        commodity = re.sub(r"^\s*\d+(?:\.\d+)?\s*[xX]?\s+", "", commodity).strip()

    equipment_type = _capture(r"EQUIPMENT\s+TYPE\s*:\s*([^\n\r]+)", text)
    if equipment_type:
        equipment_type = equipment_type.replace("Flat Bed", "Flatbed").replace("Flat bed", "Flatbed")

    quantity = _capture(r"\bQUANTITY\s*:\s*([\d,]+(?:\.\d+)?)", text)
    weight = _capture(r"(?:TOTAL\s+)?WEIGHT\s*:\s*([^\n\r]+)", text)

    return {
        "trip_number": trip,
        "reference_number": ref,
        "shipment_type": _capture(r"SHIPMENT\s+TYPE\s*:\s*([^\n\r]+)", text),
        "commodity": commodity,
        "loaded_distance_mi": distance_mi,
        "loaded_distance_km": distance_km,
        "rate_usd": rate_usd,
        "rate_per_mile_usd": rate_per_mile,
        "equipment_type": equipment_type,
        "equipment_id": _capture(r"\bEQUIPMENT\s*:\s*([^\n\r]+)", text),
        "quantity": quantity,
        "weight": weight,
        "stops": _find_stops(text),
        "original_text": text.strip(),
    }


def format_load(load: dict[str, Any]) -> str:
    def safe(value: Any) -> str:
        if value is None or value == "":
            return "Не указан"
        return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    trip = safe(load.get("trip_number"))
    commodity = safe(load.get("commodity"))
    equipment = safe(load.get("equipment_type"))

    rate = load.get("rate_usd")
    rate_text = f"${rate:,.2f}" if isinstance(rate, (int, float)) else "Не указана"
    fee, net = calc_dispatcher(rate, settings.dispatcher_percent)
    fee_text = f"-${fee:,.2f}" if fee is not None else "—"
    net_text = f"${net:,.2f}" if net is not None else "—"

    miles = load.get("loaded_distance_mi")
    km = load.get("loaded_distance_km")
    distance_text = f"{miles:,.0f} миль · ≈ {km:,.0f} км" if isinstance(miles, (int, float)) and isinstance(km, (int, float)) else "Не указано"

    stops = load.get("stops") or []
    pickup = next((s for s in stops if re.search(r"pickup|pick.?up|load", s.get("type") or "", re.I)), None)
    delivery = next((s for s in stops if re.search(r"delivery|deliver|drop.?off", s.get("type") or "", re.I)), None)
    # If stop types are absent or unclear, use the first and last named stops.
    named_stops = [s for s in stops if s.get("name")]
    if pickup is None and named_stops:
        pickup = named_stops[0]
    if delivery is None and len(named_stops) > 1:
        delivery = named_stops[-1]

    def stop_text(stop: dict[str, Any] | None) -> str:
        if not stop:
            return "Не указан"
        name = safe(stop.get("name"))
        address = safe(stop.get("address"))
        if address != "Не указан" and address.lower() not in name.lower():
            return f"{name}\n   Адрес: {address}"
        return name

    lines = [
        f"<b>🚚 Рейс № {trip}</b>",
        "",
        "<b>📍 Маршрут</b>",
        f"<b>Загрузка:</b> {stop_text(pickup)}",
        f"<b>Выгрузка:</b> {stop_text(delivery)}",
        "",
        "<b>📦 Груз:</b> " + commodity,
        "<b>🚛 Прицеп:</b> " + equipment,
        f"<b>💵 Ставка:</b> {rate_text}",
        f"<b>🧾 Диспетчер ({settings.dispatcher_percent:g}%):</b> {fee_text}",
        f"<b>💰 К получению:</b> {net_text}",
        f"<b>🛣 Расстояние:</b> {distance_text}",
    ]
    return "\n".join(lines)