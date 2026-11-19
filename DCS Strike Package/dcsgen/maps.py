"""Map registry.

`terrain_class` is the pydcs terrain class name. `default_airbase` is only a
convenience default; pass --start to choose any airbase on the map, and use
`python -m dcsgen list-airbases --map <key>` to see the real names (needs pydcs).
Names written here are from memory and checked by `check-units`.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MapInfo:
    key: str
    display: str
    terrain_class: str
    default_airbase: str = ""
    notes: str = ""
    lat: float = 40.0          # rough centre, for sunrise and sunset
    lon: float = 0.0
    utc_offset: float = 0.0    # the map's clock offset from UTC, hours
    blue_bases: tuple = ()     # three sensible starts for the blue side
    red_bases: tuple = ()      # three sensible starts for the red side
    sea: tuple = ()            # (lat, lng) points of open water, for naval targets; empty = no sea

    def suggested(self, side):
        return self.blue_bases if side == "blue" else self.red_bases


MAPS = {m.key: m for m in [
    MapInfo("caucasus", "Caucasus", "Caucasus", "Kobuleti", "Black Sea coast and mountains",
            42.5, 41.5, 4, ("Kobuleti", "Batumi", "Senaki-Kolkhi"),
            ("Mozdok", "Maykop-Khanskaya", "Krymsk"),
            ((43.2, 37.8), (42.0, 40.0))),
    MapInfo("persian_gulf", "Persian Gulf", "PersianGulf", "Al Dhafra AFB", "Gulf, good for carriers",
            25.5, 55.5, 4, ("Al Dhafra AFB", "Al Minhad AFB", "Fujairah Intl"),
            ("Bandar Abbas Intl", "Shiraz Intl", "Lar"),
            ((25.0, 57.3), (26.0, 53.0))),
    MapInfo("syria", "Syria", "Syria", "Incirlik", "Eastern Mediterranean and Levant",
            35.4, 36.0, 3, ("Incirlik", "Ramat David", "Akrotiri"),
            ("Bassel Al-Assad", "Damascus", "Tabqa"),
            ((34.6, 34.8), (35.9, 35.3))),
    MapInfo("nevada", "Nevada", "Nevada", "Nellis", "Desert test and training range",
            36.5, -115.5, -8, ("Nellis", "Creech", "Tonopah Test Range"),
            ("Groom Lake", "Tonopah", "Mina")),
    MapInfo("marianas", "Mariana Islands", "MarianaIslands", "Andersen AFB",
            "Pacific islands, carriers", 14.5, 145.0, 10,
            ("Andersen AFB", "Antonio B. Won Pat Intl", "Saipan Intl"),
            ("Tinian Intl", "Rota Intl", "North West Field"),
            ((14.5, 143.6), (16.0, 144.5))),
    MapInfo("sinai", "Sinai", "Sinai", "Ramon Airbase", "Sinai and the Nile delta",
            30.0, 32.5, 2, ("Ramon Airbase", "Nevatim", "Tel Nof"),
            ("Cairo West", "Bilbeis Air Base", "Inshas Airbase"),
            ((32.3, 32.5),)),
    MapInfo("kola", "Kola", "Kola", "Bodo", "Northern Cold War theatre", 68.8, 25.0, 3,
            ("Bodo", "Bardufoss", "Evenes"),
            ("Severomorsk-3", "Olenya", "Murmansk International"),
            ((70.5, 32.0), (70.6, 19.0))),
    MapInfo("afghanistan", "Afghanistan", "Afghanistan", "Bagram", "Mountainous, landlocked",
            33.5, 66.5, 4.5, ("Bagram", "Kandahar", "Herat"),
            ("Kabul", "Shindand", "Jalalabad")),
    MapInfo("germany_cw", "Germany (Cold War)", "Germany", "Fulda",
            "Central Europe, 1980s style", 51.0, 10.0, 2,
            ("Fulda", "Giebelstadt", "Spangdahlem"),
            ("Dessau", "Cochstedt", "Finow")),
    MapInfo("south_atlantic", "South Atlantic", "Falklands", "Mount Pleasant",
            "Falklands theatre", -51.7, -59.0, -3, ("Mount Pleasant", "Port Stanley", "Goose Green"),
            ("Rio Grande", "Rio Gallegos", "Ushuaia"),
            ((-51.5, -56.0), (-53.0, -58.0))),
    MapInfo("iraq", "Iraq", "Iraq", "", "Iraq and the northern Gulf", 33.0, 44.0, 3),
]}
