"""
Country name -> ISO3 and State Dept 2-letter codes for Layer 3 data sources.
HDX/HAPI use ISO 3166-1 alpha-3; US State Dept API uses its own 2-letter codes
(most match ISO alpha-2; exceptions are in STATE_DEPT_OVERRIDES).
"""

# (lowercase name, iso3). State Dept uses ISO2 unless in overrides below.
COUNTRY_ISO3: list[tuple[str, str]] = [
    ("afghanistan", "afg"), ("albania", "alb"), ("algeria", "dza"),
    ("andorra", "and"), ("angola", "ago"), ("antigua and barbuda", "atg"),
    ("argentina", "arg"), ("armenia", "arm"), ("australia", "aus"),
    ("austria", "aut"), ("azerbaijan", "aze"), ("bahamas", "bhs"),
    ("bahrain", "bhr"), ("bangladesh", "bgd"), ("barbados", "brb"),
    ("belarus", "blr"), ("belgium", "bel"), ("belize", "blz"),
    ("benin", "ben"), ("bhutan", "btn"), ("bolivia", "bol"),
    ("bosnia and herzegovina", "bih"), ("botswana", "bwa"), ("brazil", "bra"),
    ("brunei", "brn"), ("bulgaria", "bgr"), ("burkina faso", "bfa"),
    ("burundi", "bdi"), ("cabo verde", "cpv"), ("cambodia", "khm"),
    ("cameroon", "cmr"), ("canada", "can"), ("central african republic", "caf"),
    ("chad", "tcd"), ("chile", "chl"), ("china", "chn"), ("colombia", "col"),
    ("comoros", "com"), ("congo", "cog"), ("costa rica", "cri"),
    ("croatia", "hrv"), ("cuba", "cub"), ("cyprus", "cyp"),
    ("czech republic", "cze"), ("czechia", "cze"), ("denmark", "dnk"),
    ("djibouti", "dji"), ("dominica", "dma"), ("dominican republic", "dom"),
    ("ecuador", "ecu"), ("egypt", "egy"), ("el salvador", "slv"),
    ("equatorial guinea", "gnq"), ("eritrea", "eri"), ("estonia", "est"),
    ("eswatini", "swz"), ("ethiopia", "eth"), ("fiji", "fji"),
    ("finland", "fin"), ("france", "fra"), ("gabon", "gab"),
    ("gambia", "gmb"), ("georgia", "geo"), ("germany", "deu"),
    ("ghana", "gha"), ("greece", "grc"), ("grenada", "grd"),
    ("guatemala", "gtm"), ("guinea", "gin"), ("guinea-bissau", "gnb"),
    ("guyana", "guy"), ("haiti", "hti"), ("honduras", "hnd"),
    ("hungary", "hun"), ("iceland", "isl"), ("india", "ind"),
    ("indonesia", "idn"), ("iran", "irn"), ("iraq", "irq"),
    ("ireland", "irl"), ("israel", "isr"), ("italy", "ita"),
    ("jamaica", "jam"), ("japan", "jpn"), ("jordan", "jor"),
    ("kazakhstan", "kaz"), ("kenya", "ken"), ("kiribati", "kir"),
    ("north korea", "prk"), ("south korea", "kor"), ("kosovo", "xxk"),
    ("kuwait", "kwt"), ("kyrgyzstan", "kgz"), ("laos", "lao"),
    ("latvia", "lva"), ("lebanon", "lbn"), ("lesotho", "lso"),
    ("liberia", "lbr"), ("libya", "lby"), ("liechtenstein", "lie"),
    ("lithuania", "ltu"), ("luxembourg", "lux"), ("madagascar", "mdg"),
    ("malawi", "mwi"), ("malaysia", "mys"), ("maldives", "mdv"),
    ("mali", "mli"), ("malta", "mlt"), ("marshall islands", "mhl"),
    ("mauritania", "mrt"), ("mauritius", "mus"), ("mexico", "mex"),
    ("micronesia", "fsm"), ("moldova", "mda"), ("monaco", "mco"),
    ("mongolia", "mng"), ("montenegro", "mne"), ("morocco", "mar"),
    ("mozambique", "moz"), ("myanmar", "mmr"), ("namibia", "nam"),
    ("nauru", "nru"), ("nepal", "npl"), ("netherlands", "nld"),
    ("new zealand", "nzl"), ("nicaragua", "nic"), ("niger", "ner"),
    ("nigeria", "nga"), ("north macedonia", "mkd"), ("norway", "nor"),
    ("oman", "omn"), ("pakistan", "pak"), ("palau", "plw"),
    ("palestine", "pse"), ("panama", "pan"), ("papua new guinea", "png"),
    ("paraguay", "pry"), ("peru", "per"), ("philippines", "phl"),
    ("poland", "pol"), ("portugal", "prt"), ("qatar", "qat"),
    ("romania", "rou"), ("russia", "rus"), ("rwanda", "rwa"),
    ("saint kitts and nevis", "kna"), ("saint lucia", "lca"),
    ("saint vincent and the grenadines", "vct"), ("samoa", "wsm"),
    ("san marino", "smr"), ("sao tome and principe", "stp"),
    ("saudi arabia", "sau"), ("senegal", "sen"), ("serbia", "srb"),
    ("seychelles", "syc"), ("sierra leone", "sle"), ("singapore", "sgp"),
    ("slovakia", "svk"), ("slovenia", "svn"), ("solomon islands", "slb"),
    ("somalia", "som"), ("south africa", "zaf"), ("south sudan", "ssd"),
    ("spain", "esp"), ("sri lanka", "lka"), ("sudan", "sdn"),
    ("suriname", "sur"), ("sweden", "swe"), ("switzerland", "che"),
    ("syria", "syr"), ("taiwan", "twn"), ("tajikistan", "tjk"),
    ("tanzania", "tza"), ("thailand", "tha"), ("timor-leste", "tls"),
    ("togo", "tgo"), ("tonga", "ton"), ("trinidad and tobago", "tto"),
    ("tunisia", "tun"), ("turkey", "tur"), ("turkiye", "tur"),
    ("turkmenistan", "tkm"), ("tuvalu", "tuv"), ("uganda", "uga"),
    ("ukraine", "ukr"), ("united arab emirates", "are"), ("uae", "are"),
    ("united kingdom", "gbr"), ("uk", "gbr"), ("united states", "usa"),
    ("usa", "usa"), ("uruguay", "ury"), ("uzbekistan", "uzb"),
    ("vanuatu", "vut"), ("vatican city", "vat"), ("venezuela", "ven"),
    ("vietnam", "vnm"), ("yemen", "yem"), ("zambia", "zmb"), ("zimbabwe", "zwe"),
    ("democratic republic of the congo", "cod"), ("drc", "cod"),
]

# ISO 3166-1 alpha-2 for each ISO3 (for State Dept when no override).
ISO3_TO_ISO2: dict[str, str] = {
    "afg": "AF", "alb": "AL", "dza": "DZ", "and": "AD", "ago": "AO", "atg": "AG",
    "arg": "AR", "arm": "AM", "aus": "AU", "aut": "AT", "aze": "AZ", "bhs": "BS",
    "bhr": "BH", "bgd": "BD", "brb": "BB", "blr": "BY", "bel": "BE", "blz": "BZ",
    "ben": "BJ", "btn": "BT", "bol": "BO", "bih": "BA", "bwa": "BW", "bra": "BR",
    "brn": "BN", "bgr": "BG", "bfa": "BF", "bdi": "BI", "cpv": "CV", "khm": "KH",
    "cmr": "CM", "can": "CA", "caf": "CF", "tcd": "TD", "chl": "CL", "chn": "CN",
    "col": "CO", "com": "KM", "cog": "CG", "cri": "CR", "hrv": "HR", "cub": "CU",
    "cyp": "CY", "cze": "CZ", "dnk": "DK", "dji": "DJ", "dma": "DM", "dom": "DO",
    "ecu": "EC", "egy": "EG", "slv": "SV", "gnq": "GQ", "eri": "ER", "est": "EE",
    "swz": "SZ", "eth": "ET", "fji": "FJ", "fin": "FI", "fra": "FR", "gab": "GA",
    "gmb": "GM", "geo": "GE", "deu": "DE", "gha": "GH", "grc": "GR", "grd": "GD",
    "gtm": "GT", "gin": "GN", "gnb": "GW", "guy": "GY", "hti": "HT", "hnd": "HN",
    "hun": "HU", "isl": "IS", "ind": "IN", "idn": "ID", "irn": "IR", "irq": "IQ",
    "irl": "IE", "isr": "IL", "ita": "IT", "jam": "JM", "jpn": "JP", "jor": "JO",
    "kaz": "KZ", "ken": "KE", "kir": "KI", "prk": "KP", "kor": "KR", "xxk": "XK",
    "kwt": "KW", "kgz": "KG", "lao": "LA", "lva": "LV", "lbn": "LB", "lso": "LS",
    "lbr": "LR", "lby": "LY", "lie": "LI", "ltu": "LT", "lux": "LU", "mdg": "MG",
    "mwi": "MW", "mys": "MY", "mdv": "MV", "mli": "ML", "mlt": "MT", "mhl": "MH",
    "mrt": "MR", "mus": "MU", "mex": "MX", "fsm": "FM", "mda": "MD", "mco": "MC",
    "mng": "MN", "mne": "ME", "mar": "MA", "moz": "MZ", "mmr": "MM", "nam": "NA",
    "nru": "NR", "npl": "NP", "nld": "NL", "nzl": "NZ", "nic": "NI", "ner": "NE",
    "nga": "NG", "mkd": "MK", "nor": "NO", "omn": "OM", "pak": "PK", "plw": "PW",
    "pse": "PS", "pan": "PA", "png": "PG", "pry": "PY", "per": "PE", "phl": "PH",
    "pol": "PL", "prt": "PT", "qat": "QA", "rou": "RO", "rus": "RU", "rwa": "RW",
    "kna": "KN", "lca": "LC", "vct": "VC", "wsm": "WS", "smr": "SM", "stp": "ST",
    "sau": "SA", "sen": "SN", "srb": "RS", "syc": "SC", "sle": "SL", "sgp": "SG",
    "svk": "SK", "svn": "SI", "slb": "SB", "som": "SO", "zaf": "ZA", "ssd": "SS",
    "esp": "ES", "lka": "LK", "sdn": "SD", "sur": "SR", "swe": "SE", "che": "CH",
    "syr": "SY", "twn": "TW", "tjk": "TJ", "tza": "TZ", "tha": "TH", "tls": "TL",
    "tgo": "TG", "ton": "TO", "tto": "TT", "tun": "TN", "tur": "TR", "tkm": "TM",
    "tuv": "TV", "uga": "UG", "ukr": "UA", "are": "AE", "gbr": "GB", "usa": "US",
    "ury": "UY", "uzb": "UZ", "vut": "VU", "vat": "VA", "ven": "VE", "vnm": "VN",
    "yem": "YE", "zmb": "ZM", "zwe": "ZW", "cod": "CD",
}

# US State Dept API uses different 2-letter codes for some countries.
STATE_DEPT_OVERRIDES: dict[str, str] = {
    "afghanistan": "AF", "bangladesh": "BG", "burkina faso": "UV",
    "central african republic": "CT", "chad": "CD", "colombia": "CO",
    "democratic republic of the congo": "CG", "drc": "CG",
    "egypt": "EG", "ethiopia": "ET", "haiti": "HA", "india": "IN",
    "iraq": "IZ", "iran": "IR", "jordan": "JO", "kenya": "KE",
    "lebanon": "LE", "liberia": "LI", "libya": "LY", "mali": "ML",
    "mozambique": "MZ", "myanmar": "BM", "niger": "NG", "nigeria": "NI",
    "pakistan": "PK", "palestine": "GZ", "sierra leone": "SL",
    "somalia": "SO", "south sudan": "OD", "sudan": "SU", "syria": "SY",
    "turkey": "TU", "turkiye": "TU", "ukraine": "UP", "venezuela": "VE",
    "yemen": "YM", "china": "CH", "nepal": "NP", "philippines": "RP",
    "indonesia": "ID", "japan": "JA", "mexico": "MX", "brazil": "BR",
}


def build_country_maps() -> tuple[dict[str, str], dict[str, str]]:
    """Return (country_lower -> iso3, country_lower -> state_dept_code)."""
    iso3_map: dict[str, str] = {}
    state_map: dict[str, str] = {}
    for name, iso3 in COUNTRY_ISO3:
        iso3_map[name] = iso3
        state_map[name] = STATE_DEPT_OVERRIDES.get(name) or ISO3_TO_ISO2.get(iso3, "")
    return iso3_map, state_map


def list_all_countries() -> list[str]:
    """Return list of canonical country names (as used in API) for ingest-all."""
    return sorted({name.title() for name, _ in COUNTRY_ISO3})
