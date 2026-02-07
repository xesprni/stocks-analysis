from __future__ import annotations


def normalize_symbol(symbol: str, market: str) -> str:
    raw = symbol.strip().upper()
    market = market.strip().upper()
    if market == "US":
        return raw
    if market == "HK":
        code = raw[:-3] if raw.endswith(".HK") else raw.split(".")[0]
        code = code.zfill(4)
        return f"{code}.HK"
    if market == "CN":
        if raw.endswith(".SS"):
            raw = raw[:-3] + ".SH"
        if raw.endswith(".SH") or raw.endswith(".SZ") or raw.endswith(".BJ"):
            return raw
        code = raw.split(".")[0]
        if code.startswith(("6", "9")):
            return f"{code}.SH"
        if code.startswith(("4", "8")):
            return f"{code}.BJ"
        return f"{code}.SZ"
    return raw


def to_yfinance_symbol(symbol: str, market: str) -> str:
    normalized = normalize_symbol(symbol, market)
    if market.upper() == "CN":
        if normalized.endswith(".SH"):
            return normalized.replace(".SH", ".SS")
        if normalized.endswith(".SZ") or normalized.endswith(".BJ"):
            return normalized
    return normalized


def strip_market_suffix(symbol: str) -> str:
    raw = symbol.strip().upper()
    for suffix in (".SH", ".SZ", ".BJ", ".HK", ".SS"):
        if raw.endswith(suffix):
            return raw[: -len(suffix)]
    return raw
