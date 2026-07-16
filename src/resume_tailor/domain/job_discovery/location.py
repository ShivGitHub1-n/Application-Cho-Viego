from __future__ import annotations

import re

from resume_tailor.domain.job_discovery.models import NormalizedLocation

_COUNTRIES = {
    "ca": ("CA", "Canada"),
    "canada": ("CA", "Canada"),
    "us": ("US", "United States"),
    "u.s.": ("US", "United States"),
    "usa": ("US", "United States"),
    "united states": ("US", "United States"),
    "united states of america": ("US", "United States"),
}

_CANADIAN_REGIONS = {
    "ab": "ab",
    "alberta": "ab",
    "bc": "bc",
    "british columbia": "bc",
    "mb": "mb",
    "manitoba": "mb",
    "nb": "nb",
    "new brunswick": "nb",
    "nl": "nl",
    "newfoundland and labrador": "nl",
    "newfoundland": "nl",
    "nt": "nt",
    "northwest territories": "nt",
    "ns": "ns",
    "nova scotia": "ns",
    "nu": "nu",
    "nunavut": "nu",
    "on": "on",
    "ontario": "on",
    "pe": "pe",
    "pei": "pe",
    "prince edward island": "pe",
    "qc": "qc",
    "quebec": "qc",
    "sk": "sk",
    "saskatchewan": "sk",
    "yt": "yt",
    "yukon": "yt",
}

_US_REGIONS = {
    "al": "al",
    "alabama": "al",
    "ak": "ak",
    "alaska": "ak",
    "az": "az",
    "arizona": "az",
    "ar": "ar",
    "arkansas": "ar",
    "ca": "ca",
    "california": "ca",
    "co": "co",
    "colorado": "co",
    "ct": "ct",
    "connecticut": "ct",
    "de": "de",
    "delaware": "de",
    "fl": "fl",
    "florida": "fl",
    "ga": "ga",
    "georgia": "ga",
    "hi": "hi",
    "hawaii": "hi",
    "id": "id",
    "idaho": "id",
    "il": "il",
    "illinois": "il",
    "in": "in",
    "indiana": "in",
    "ia": "ia",
    "iowa": "ia",
    "ks": "ks",
    "kansas": "ks",
    "ky": "ky",
    "kentucky": "ky",
    "la": "la",
    "louisiana": "la",
    "me": "me",
    "maine": "me",
    "md": "md",
    "maryland": "md",
    "ma": "ma",
    "massachusetts": "ma",
    "mi": "mi",
    "michigan": "mi",
    "mn": "mn",
    "minnesota": "mn",
    "ms": "ms",
    "mississippi": "ms",
    "mo": "mo",
    "missouri": "mo",
    "mt": "mt",
    "montana": "mt",
    "ne": "ne",
    "nebraska": "ne",
    "nv": "nv",
    "nevada": "nv",
    "nh": "nh",
    "new hampshire": "nh",
    "nj": "nj",
    "new jersey": "nj",
    "nm": "nm",
    "new mexico": "nm",
    "ny": "ny",
    "new york": "ny",
    "nc": "nc",
    "north carolina": "nc",
    "nd": "nd",
    "north dakota": "nd",
    "oh": "oh",
    "ohio": "oh",
    "ok": "ok",
    "oklahoma": "ok",
    "or": "or",
    "oregon": "or",
    "pa": "pa",
    "pennsylvania": "pa",
    "ri": "ri",
    "rhode island": "ri",
    "sc": "sc",
    "south carolina": "sc",
    "sd": "sd",
    "south dakota": "sd",
    "tn": "tn",
    "tennessee": "tn",
    "tx": "tx",
    "texas": "tx",
    "ut": "ut",
    "utah": "ut",
    "vt": "vt",
    "vermont": "vt",
    "va": "va",
    "virginia": "va",
    "wa": "wa",
    "washington": "wa",
    "wv": "wv",
    "west virginia": "wv",
    "wi": "wi",
    "wisconsin": "wi",
    "wy": "wy",
    "wyoming": "wy",
}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().strip())


def _unknown(raw: str) -> NormalizedLocation:
    return NormalizedLocation(raw=raw, parseable=False)


def parse_location(raw: str | None) -> NormalizedLocation:
    """Parse only unambiguous comma-delimited location forms."""

    if raw is None or not raw.strip():
        return _unknown(raw or "")
    cleaned_raw = re.sub(r"\s+", " ", raw.strip())
    parts = [_clean(part) for part in cleaned_raw.split(",")]
    if any(not part for part in parts) or len(parts) > 3:
        return _unknown(cleaned_raw)

    if len(parts) == 1:
        if parts[0] in _COUNTRIES:
            code, name = _COUNTRIES[parts[0]]
            return NormalizedLocation(
                country_code=code,
                country_name=name,
                raw=cleaned_raw,
                parseable=True,
            )
        if parts[0] in _CANADIAN_REGIONS:
            return NormalizedLocation(
                region=_CANADIAN_REGIONS[parts[0]], raw=cleaned_raw, parseable=True
            )
        if parts[0] in _US_REGIONS:
            return NormalizedLocation(
                region=_US_REGIONS[parts[0]], raw=cleaned_raw, parseable=True
            )
        return _unknown(cleaned_raw)

    if len(parts) == 2:
        if parts[1] in _CANADIAN_REGIONS:
            return NormalizedLocation(
                city=parts[0], region=_CANADIAN_REGIONS[parts[1]], raw=cleaned_raw, parseable=True
            )
        if parts[1] in _US_REGIONS:
            return NormalizedLocation(
                city=parts[0], region=_US_REGIONS[parts[1]], raw=cleaned_raw, parseable=True
            )
        second_country = _COUNTRIES.get(parts[1])
        if second_country:
            code, name = second_country
            if parts[0] in _CANADIAN_REGIONS:
                return NormalizedLocation(
                    region=_CANADIAN_REGIONS[parts[0]],
                    country_code=code,
                    country_name=name,
                    raw=cleaned_raw,
                    parseable=True,
                )
            if parts[0] in _US_REGIONS:
                return NormalizedLocation(
                    region=_US_REGIONS[parts[0]],
                    country_code=code,
                    country_name=name,
                    raw=cleaned_raw,
                    parseable=True,
                )
            return NormalizedLocation(
                city=parts[0],
                country_code=code,
                country_name=name,
                raw=cleaned_raw,
                parseable=True,
            )
        return _unknown(cleaned_raw)

    country = _COUNTRIES.get(parts[2])
    region = _CANADIAN_REGIONS.get(parts[1]) or _US_REGIONS.get(parts[1])
    if country is None or region is None:
        return _unknown(cleaned_raw)
    code, name = country
    return NormalizedLocation(
        city=parts[0],
        region=region,
        country_code=code,
        country_name=name,
        raw=cleaned_raw,
        parseable=True,
    )
