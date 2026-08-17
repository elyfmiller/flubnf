"""US state / territory metadata.

Single source of truth for the state list, abbreviations, FIPS codes, and
populations. Populations come from `NAU_Influenza/locations.csv` (the
FluSight-style locations table used by the existing scripts) and are loaded
lazily so this module stays import-cheap.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class StateInfo:
    name: str          # Underscore form used in BNGL filenames (e.g. "New_York")
    abbreviation: str  # 2-letter postal code (e.g. "NY")
    fips: str          # 2-digit FIPS code as a string (e.g. "36")
    population: int

    @property
    def display_name(self) -> str:
        return self.name.replace("_", " ")


# The canonical set of jurisdictions FluSight expects (50 states + DC + PR + US).
# Underscore-joined to match the existing BNGL/conf filename convention.
JURISDICTIONS: tuple[str, ...] = (
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "District_of_Columbia", "Florida", "Georgia",
    "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky",
    "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New_Hampshire", "New_Jersey", "New_Mexico", "New_York", "North_Carolina",
    "North_Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania",
    "Puerto_Rico", "Rhode_Island", "South_Carolina", "South_Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West_Virginia", "Wisconsin", "Wyoming",
)

STATE_TO_ABBREV: dict[str, str] = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "District_of_Columbia": "DC", "Florida": "FL", "Georgia": "GA",
    "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN",
    "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
    "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI",
    "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT",
    "Nebraska": "NE", "Nevada": "NV", "New_Hampshire": "NH", "New_Jersey": "NJ",
    "New_Mexico": "NM", "New_York": "NY", "North_Carolina": "NC",
    "North_Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
    "Pennsylvania": "PA", "Puerto_Rico": "PR", "Rhode_Island": "RI",
    "South_Carolina": "SC", "South_Dakota": "SD", "Tennessee": "TN",
    "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA",
    "Washington": "WA", "West_Virginia": "WV", "Wisconsin": "WI",
    "Wyoming": "WY",
}

ABBREV_TO_STATE: dict[str, str] = {v: k for k, v in STATE_TO_ABBREV.items()}


@lru_cache(maxsize=1)
def load_locations(locations_csv: Path) -> dict[str, StateInfo]:
    """Load FluSight `locations.csv` into a name -> StateInfo lookup.

    The CSV has columns: abbreviation,location,location_name,population,...
    where `location` is the 2-digit FIPS code (string, zero-padded).
    """
    df = pd.read_csv(locations_csv, dtype={"location": str})
    out: dict[str, StateInfo] = {}
    for _, row in df.iterrows():
        abbrev = row["abbreviation"]
        if abbrev == "US":
            continue
        name = ABBREV_TO_STATE.get(abbrev)
        if name is None:
            continue
        out[name] = StateInfo(
            name=name,
            abbreviation=abbrev,
            fips=str(row["location"]).zfill(2),
            population=int(row["population"]),
        )
    return out
