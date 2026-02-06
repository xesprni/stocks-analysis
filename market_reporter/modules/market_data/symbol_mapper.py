from __future__ import annotations


def normalize_symbol(symbol: str, market: str) -> str:
    raw = symbol.strip().upper()
    market = market.strip().upper()
    if market == "US":
        return raw
    if market == "HK":
        code = raw.replace(".HK", "")
        code = code.zfill(4)
        return f"{code}.HK"
    if market == "CN":
        if raw.endswith(".SH") or raw.endswith(".SZ"):
            return raw
        code = raw.split(".")[0]
        if code.startswith("6"):
            return f"{code}.SH"
        return f"{code}.SZ"
    return raw


def to_yfinance_symbol(symbol: str, market: str) -> str:
    normalized = normalize_symbol(symbol, market)
    if market.upper() == "CN":
        if normalized.endswith(".SH"):
            return normalized.replace(".SH", ".SS")
        if normalized.endswith(".SZ"):
            return normalized
    return normalized


def strip_market_suffix(symbol: str) -> str:
    return symbol.replace(".SH", "").replace(".SZ", "").replace(".HK", "")
