from __future__ import annotations


def normalize_symbol(symbol: str, market: str) -> str:
    raw = symbol.strip().upper()
    market = market.strip().upper()
    if market == "US":
        # US symbols are mostly consumed as-is.
        return raw
    if market == "HK":
        # Keep Yahoo-style HK index tickers unchanged, for example "^HSI".
        if raw.startswith("^"):
            return raw[:-3] if raw.endswith(".HK") else raw
        # HK equities keep 4-digit codes and .HK suffix.
        code = raw[:-3] if raw.endswith(".HK") else raw.split(".")[0]
        if code.isdigit():
            return f"{code.zfill(4)}.HK"
        return raw
    if market == "CN":
        # Keep Yahoo-style index tickers unchanged.
        if raw.startswith("^"):
            return raw
        # Normalize CN suffixes to .SH/.SZ/.BJ for internal consistency.
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
        # Yahoo uses .SS for Shanghai while internal format uses .SH.
        if normalized.endswith(".SH"):
            return normalized.replace(".SH", ".SS")
        if normalized.endswith(".SZ") or normalized.endswith(".BJ"):
            return normalized
    return normalized


def to_longbridge_symbol(symbol: str, market: str) -> str:
    """Convert internal symbol format to Longbridge format.

    Longbridge uses suffix-based market identifiers:
      AAPL.US, 0700.HK, 000300.SH, 000001.SZ, HSI.HK
    """
    normalized = normalize_symbol(symbol, market)
    market = market.strip().upper()
    if market == "US":
        # Index tickers like ^GSPC are not supported by Longbridge;
        # equities use suffix ".US".
        raw = normalized.lstrip("^")
        return f"{raw}.US"
    if market == "HK":
        if normalized.startswith("^"):
            # Longbridge index tickers: ^HSI → HSI.HK
            raw = normalized.lstrip("^")
            raw = raw[:-3] if raw.endswith(".HK") else raw
            return f"{raw}.HK"
        code = (
            normalized[:-3] if normalized.endswith(".HK") else normalized.split(".")[0]
        )
        return f"{code}.HK"
    if market == "CN":
        if normalized.startswith("^"):
            raw = normalized.lstrip("^")
            return f"{raw}.SH"
        if normalized.endswith(".SH"):
            return f"{normalized[:-3]}.SH"
        if normalized.endswith(".SZ"):
            return f"{normalized[:-3]}.SZ"
        if normalized.endswith(".BJ"):
            return f"{normalized[:-3]}.BJ"
        # Fallback: try to infer exchange from code prefix.
        code = normalized.split(".")[0]
        if code.startswith(("6", "9")):
            return f"{code}.SH"
        if code.startswith(("4", "8")):
            return f"{code}.BJ"
        return f"{code}.SZ"
    return normalized


def strip_market_suffix(symbol: str) -> str:
    raw = symbol.strip().upper()
    for suffix in (".SH", ".SZ", ".BJ", ".HK", ".SS"):
        if raw.endswith(suffix):
            return raw[: -len(suffix)]
    return raw
