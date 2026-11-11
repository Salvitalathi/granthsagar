"""
ज्योतिष — जन्मकुंडली गणित (offline).

  ग्रह-स्थिती (निरयन, लाहिरी अयनांश), लग्न, राशी, भाव (राशी-भाव पद्धत), नक्षत्र-चरण,
  तिथी, योग, वार, विंशोत्तरी महादशा, काही प्रमुख योग, उत्तर भारतीय कुंडली (SVG).

खगोल-गणित: Skyfield (MIT) + NASA JPL DE421 ephemeris (पहिल्यांदा ~17 MB उतरते).
  pip install skyfield

उदाहरण:
  python jyotish.py 1990-08-15 06:30 पुणे
"""
import datetime as _dt
import math
import re
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EPH_DIR = os.path.join(HERE, "tools")
EPH_FILE = "de421.bsp"

RASHI = ["मेष", "वृषभ", "मिथुन", "कर्क", "सिंह", "कन्या", "तूळ", "वृश्चिक", "धनु", "मकर", "कुंभ", "मीन"]
RASHI_SA = ["मेष", "वृष", "मिथुन", "कर्कट", "सिंह", "कन्या", "तुला", "वृश्चिक", "धनुः", "मकर", "कुम्भ", "मीन"]
GRAHA = ["सूर्य", "चंद्र", "मंगळ", "बुध", "गुरु", "शुक्र", "शनि", "राहू", "केतू"]
GRAHA_SHORT = {"सूर्य": "सू", "चंद्र": "चं", "मंगळ": "मं", "बुध": "बु", "गुरु": "गु", "शुक्र": "शु",
               "शनि": "श", "राहू": "रा", "केतू": "के"}
NAKSHATRA = ["अश्विनी", "भरणी", "कृत्तिका", "रोहिणी", "मृगशीर्ष", "आर्द्रा", "पुनर्वसू", "पुष्य", "आश्लेषा",
             "मघा", "पूर्वा फाल्गुनी", "उत्तरा फाल्गुनी", "हस्त", "चित्रा", "स्वाती", "विशाखा", "अनुराधा",
             "ज्येष्ठा", "मूळ", "पूर्वाषाढा", "उत्तराषाढा", "श्रवण", "धनिष्ठा", "शततारका", "पूर्वा भाद्रपदा",
             "उत्तरा भाद्रपदा", "रेवती"]
TITHI = ["प्रतिपदा", "द्वितीया", "तृतीया", "चतुर्थी", "पंचमी", "षष्ठी", "सप्तमी", "अष्टमी", "नवमी",
         "दशमी", "एकादशी", "द्वादशी", "त्रयोदशी", "चतुर्दशी"]
YOGA = ["विष्कंभ", "प्रीती", "आयुष्मान", "सौभाग्य", "शोभन", "अतिगंड", "सुकर्मा", "धृती", "शूल", "गंड",
        "वृद्धी", "ध्रुव", "व्याघात", "हर्षण", "वज्र", "सिद्धी", "व्यतिपात", "वरीयान", "परिघ", "शिव",
        "सिद्ध", "साध्य", "शुभ", "शुक्ल", "ब्रह्म", "इंद्र", "वैधृती"]
VARA = ["सोमवार", "मंगळवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"]   # datetime.weekday()
DASHA = [("केतू", 7), ("शुक्र", 20), ("सूर्य", 6), ("चंद्र", 10), ("मंगळ", 7), ("राहू", 18),
         ("गुरु", 16), ("शनि", 19), ("बुध", 17)]
OWN = {"सूर्य": [4], "चंद्र": [3], "मंगळ": [0, 7], "बुध": [2, 5], "गुरु": [8, 11], "शुक्र": [1, 6], "शनि": [9, 10]}
EXALT = {"सूर्य": 0, "चंद्र": 1, "मंगळ": 9, "बुध": 5, "गुरु": 3, "शुक्र": 11, "शनि": 6}
SKYFIELD_KEY = {"सूर्य": "sun", "चंद्र": "moon", "मंगळ": "mars barycenter", "बुध": "mercury",
                "गुरु": "jupiter barycenter", "शुक्र": "venus", "शनि": "saturn barycenter"}

# प्रमुख शहरे (अक्षांश, रेखांश) — इतर ठिकाणी अक्षांश-रेखांश थेट द्या
CITIES = {
    "मुंबई": (19.076, 72.878), "पुणे": (18.520, 73.857), "नागपूर": (21.146, 79.088), "नाशिक": (19.998, 73.790),
    "छत्रपती संभाजीनगर (औरंगाबाद)": (19.876, 75.343), "कोल्हापूर": (16.705, 74.243), "सोलापूर": (17.660, 75.906),
    "अमरावती": (20.937, 77.779), "अकोला": (20.706, 77.002), "जळगाव": (21.008, 75.563), "अहमदनगर (अहिल्यानगर)": (19.095, 74.749),
    "सातारा": (17.680, 74.018), "सांगली": (16.853, 74.581), "लातूर": (18.408, 76.576), "नांदेड": (19.138, 77.321),
    "रत्नागिरी": (16.990, 73.312), "ठाणे": (19.218, 72.978), "चंद्रपूर": (19.962, 79.296), "धुळे": (20.902, 74.775),
    "बीड": (18.989, 75.760), "परभणी": (19.261, 76.773), "यवतमाळ": (20.389, 78.120), "वर्धा": (20.745, 78.602),
    "दिल्ली": (28.614, 77.209), "बेंगळुरू": (12.972, 77.594), "हैदराबाद": (17.385, 78.487), "चेन्नई": (13.083, 80.271),
    "कोलकाता": (22.573, 88.364), "अहमदाबाद": (23.023, 72.571), "जयपूर": (26.912, 75.787), "भोपाळ": (23.260, 77.413),
    "इंदूर": (22.720, 75.858), "वाराणसी": (25.318, 82.974), "लखनौ": (26.847, 80.947), "गोवा (पणजी)": (15.491, 73.828),
    "बेळगाव": (15.850, 74.498), "उज्जैन": (23.180, 75.785), "पाटणा": (25.594, 85.138),
    # रायगड-कोकण
    "अलिबाग": (18.641, 72.872), "पेण": (18.737, 73.096), "पनवेल": (18.989, 73.117), "महाड": (18.083, 73.417),
    "रोहा": (18.437, 73.120), "मुरुड": (18.327, 72.964), "श्रीवर्धन": (18.045, 73.016), "माणगाव": (18.234, 73.284),
    "कर्जत": (18.910, 73.326), "खोपोली": (18.789, 73.343), "उरण": (18.877, 72.940), "चिपळूण": (17.531, 73.515),
    "दापोली": (17.759, 73.188), "कुडाळ": (16.009, 73.687), "सावंतवाडी": (15.906, 73.821), "मालवण": (16.059, 73.462),
    "ओरोस (सिंधुदुर्ग)": (16.106, 73.684), "वसई": (19.391, 72.839), "पालघर": (19.697, 72.765), "कल्याण": (19.244, 73.130),
    "भिवंडी": (19.296, 73.063), "डोंबिवली": (19.218, 73.087), "नवी मुंबई": (19.033, 73.030),
    # इतर महाराष्ट्र
    "पिंपरी-चिंचवड": (18.627, 73.800), "लोणावळा": (18.754, 73.405), "बारामती": (18.151, 74.577), "शिर्डी": (19.766, 74.477),
    "पंढरपूर": (17.679, 75.331), "कराड": (17.289, 74.182), "इचलकरंजी": (16.691, 74.460), "मिरज": (16.826, 74.645),
    "धाराशिव (उस्मानाबाद)": (18.186, 76.042), "जालना": (19.841, 75.886), "हिंगोली": (19.718, 77.149),
    "वाशिम": (20.111, 77.133), "बुलढाणा": (20.531, 76.184), "गोंदिया": (21.460, 80.192), "भंडारा": (21.167, 79.650),
    "गडचिरोली": (20.183, 80.000), "नंदुरबार": (21.370, 74.240), "मालेगाव": (20.552, 74.525),
}


def city_aliases():
    """'अहमदनगर (अहिल्यानगर)' -> अहमदनगर, अहिल्यानगर दोन्ही"""
    out = {}
    for k, v in CITIES.items():
        for a in re.split(r"\s*[()]\s*", k):
            if a.strip():
                out[a.strip()] = (k, v)
    return out


MONTHS = {m: i for i, ms in enumerate([
    ("जानेवारी", "january", "jan"), ("फेब्रुवारी", "फेब्रुवरी", "february", "feb"), ("मार्च", "march", "mar"),
    ("एप्रिल", "april", "apr"), ("मे", "may"), ("जून", "june", "jun"), ("जुलै", "जुलाई", "july", "jul"),
    ("ऑगस्ट", "ओगस्ट", "अगस्त", "august", "aug"), ("सप्टेंबर", "सितंबर", "september", "sep", "sept"),
    ("ऑक्टोबर", "अक्टूबर", "october", "oct"), ("नोव्हेंबर", "नवंबर", "november", "nov"),
    ("डिसेंबर", "दिसंबर", "december", "dec")], 1) for m in ms}
_DIG = str.maketrans("०१२३४५६७८९", "0123456789")


def parse_birth(text):
    """'12 जुलै 1977, रात्री 8:30, अलिबाग' -> {date, time, place} (जे सापडले ते). गणित browser वर नाही, इथे."""
    t = text.translate(_DIG)
    low = t.lower()
    out = {}
    mo = "|".join(sorted(map(re.escape, MONTHS), key=len, reverse=True))
    m = re.search(rf"(\d{{1,2}})\s*(?:-|/|\.)?\s*({mo})(?![a-z\u0900-\u097F])\.?\s*,?\s*(\d{{4}})", low) \
        or re.search(rf"({mo})(?![a-z\u0900-\u097F])\.?\s*(\d{{1,2}})\s*,?\s*(\d{{4}})", low)
    if m:
        g = m.groups()
        d, mon, y = (g[0], g[1], g[2]) if g[0].isdigit() else (g[1], g[0], g[2])
        out["date"] = f"{int(y):04d}-{MONTHS[mon]:02d}-{int(d):02d}"
    else:
        m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t) or re.search(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\b", t)
        if m:
            a, b, c = m.groups()
            y, mm, dd = (a, b, c) if len(a) == 4 else (c, b, a)
            out["date"] = f"{int(y):04d}-{int(mm):02d}-{int(dd):02d}"
    rest = t[m.end():] + " " + t[:m.start()] if m else t
    tm = re.search(r"(पहाटे|सकाळी|दुपारी|संध्याकाळी|सायंकाळी|रात्री)?\s*(\d{1,2})\s*[:.]\s*(\d{2})\s*(am|pm|a\.m\.|p\.m\.)?",
                   rest, re.I) or re.search(r"(पहाटे|सकाळी|दुपारी|संध्याकाळी|सायंकाळी|रात्री)\s*(\d{1,2})()\s*(?:वा|वाजता)?()",
                                             rest)
    if tm:
        part, h, mi, ap = tm.group(1), int(tm.group(2)), int(tm.group(3) or 0), (tm.group(4) or "").lower()
        if ap.startswith("p") and h < 12:
            h += 12
        elif ap.startswith("a") and h == 12:
            h = 0
        elif not ap and part in ("दुपारी", "संध्याकाळी", "सायंकाळी") and h < 12:
            h += 12
        elif not ap and part == "रात्री" and 6 <= h < 12:
            h += 12
        elif not ap and part == "रात्री" and h == 12:
            h = 0
        if 0 <= h < 24 and 0 <= mi < 60:
            out["time"] = f"{h:02d}:{mi:02d}"
    for alias, (key, _) in sorted(city_aliases().items(), key=lambda x: -len(x[0])):
        if alias in text:
            out["place"] = key
            break
    return out



# ---------------------------------------------------------------- खगोल
_EPH = {}


def _load():
    if "eph" not in _EPH:
        try:
            from skyfield.api import Loader
        except ImportError:
            raise RuntimeError("कुंडलीसाठी 'pip install skyfield' लागेल (start.bat हे करतो).")
        os.makedirs(EPH_DIR, exist_ok=True)
        load = Loader(EPH_DIR, verbose=False)
        _EPH["ts"] = load.timescale()
        _EPH["eph"] = load(EPH_FILE)          # पहिल्यांदा ~17 MB उतरते (इंटरनेट लागते)
    return _EPH["ts"], _EPH["eph"]


def ensure_ephemeris():
    _load()
    return os.path.join(EPH_DIR, EPH_FILE)


def _T(t):
    return (t.tt - 2451545.0) / 36525.0          # J2000 पासून शतके (TT)


def lahiri_ayanamsa(t):
    """लाहिरी (चित्रापक्ष) अयनांश, अंशांत. J2000 वरील मूल्य + IAU 2006 अयनचलन (रेखांशात)."""
    T = _T(t)
    return LAHIRI_J2000 + (5028.796195 * T + 1.1054348 * T * T) / 3600.0


LAHIRI_J2000 = 23.857092     # 2000-01-01 12:00 TT ला मध्यम लाहिरी अयनांश (Swiss Ephemeris शी पडताळलेले)


def mean_rahu(t):
    """मध्यम राहू (चंद्राचा आरोही पात) — सायन, Meeus"""
    T = _T(t)
    om = 125.0445479 - 1934.1362891 * T + 0.0020754 * T * T + T ** 3 / 467441.0 - T ** 4 / 60616000.0
    return om % 360.0


def nutation(t):
    """(Δψ, Δε) अंशांत — IAU 2000"""
    from skyfield import nutationlib
    f = getattr(nutationlib, "iau2000b_radians", None) or nutationlib.iau2000a_radians
    dpsi, deps = f(t)
    return math.degrees(dpsi), math.degrees(deps)


def obliquity(t, true=True):
    T = _T(t)
    eps = 23.0 + 26.0 / 60 + (21.448 - 46.8150 * T - 0.00059 * T * T + 0.001813 * T ** 3) / 3600.0
    return eps + (nutation(t)[1] if true else 0.0)


def ascendant(t, lat, lon):
    """सायन लग्न (अंश) — मध्यम विषुवापासून (ग्रहांप्रमाणे)"""
    ramc = math.radians((t.gast * 15.0 + lon) % 360.0)
    eps = math.radians(obliquity(t))
    phi = math.radians(lat)
    asc = math.degrees(math.atan2(math.cos(ramc),
                                  -(math.sin(ramc) * math.cos(eps) + math.tan(phi) * math.sin(eps))))
    return (asc - nutation(t)[0]) % 360.0


def tropical_longitudes(t):
    from skyfield.framelib import ecliptic_frame
    ts, eph = _load()
    earth = eph["earth"]
    out = {}
    dpsi = nutation(t)[0]        # मध्यम विषुवापासून मोजा: अयनांश मध्यम आहे (Swiss Ephemeris/बहुतेक पंचांगांप्रमाणे)
    for g, key in SKYFIELD_KEY.items():
        lat_, lon_, _ = earth.at(t).observe(eph[key]).apparent().frame_latlon(ecliptic_frame)
        out[g] = (lon_.degrees - dpsi) % 360.0
    out["राहू"] = mean_rahu(t)
    out["केतू"] = (out["राहू"] + 180.0) % 360.0
    return out


# ---------------------------------------------------------------- कुंडली
def _dms(x):
    d = int(x); m = int((x - d) * 60); s = int(round(((x - d) * 60 - m) * 60))
    if s == 60:
        m, s = m + 1, 0
    return f"{d}°{m:02d}'{s:02d}\""


def compute_chart(date, time, lat, lon, tz=5.5, name=""):
    """date 'YYYY-MM-DD', time 'HH:MM' (स्थानिक), tz तासांत (भारत 5.5)"""
    ts, _ = _load()
    local = _dt.datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    utc = local - _dt.timedelta(hours=tz)
    # जन्मवेळ = नागरी वेळ ≈ UT1 (1972 पूर्वी UTC चे leap-second नियम लागू नव्हते)
    t = ts.ut1(utc.year, utc.month, utc.day, utc.hour, utc.minute, utc.second)
    ayan = lahiri_ayanamsa(t)
    trop = tropical_longitudes(t)
    t2 = ts.tt_jd(t.tt + 0.5)
    trop2 = tropical_longitudes(t2)
    lagna = (ascendant(t, lat, lon) - ayan) % 360.0
    lagna_sign = int(lagna // 30)
    planets = []
    for g in GRAHA:
        L = (trop[g] - ayan) % 360.0
        sign = int(L // 30)
        nak = int(L // (360 / 27))
        d = ((trop2[g] - trop[g] + 540) % 360) - 180
        retro = g in ("राहू", "केतू") or bool(d < 0)      # numpy bool नको — JSON मध्ये जात नाही
        status = []
        if g in EXALT and sign == EXALT[g]:
            status.append("उच्च")
        if g in EXALT and sign == (EXALT[g] + 6) % 12:
            status.append("नीच")
        if g in OWN and sign in OWN[g]:
            status.append("स्वराशी")
        planets.append({
            "graha": g, "lon": float(L), "rashi": RASHI[sign], "sign": sign, "deg": _dms(L % 30),
            "bhava": (sign - lagna_sign) % 12 + 1,
            "nakshatra": NAKSHATRA[nak], "pada": int((L % (360 / 27)) // (360 / 108)) + 1,
            "vakri": bool(retro and g not in ("राहू", "केतू")), "status": status,
        })
    P = {p["graha"]: p for p in planets}
    sun, moon = P["सूर्य"]["lon"], P["चंद्र"]["lon"]
    tithi_n = int(((moon - sun) % 360) // 12)              # 0..29
    paksha = "शुक्ल" if tithi_n < 15 else "कृष्ण"
    tithi_name = "पौर्णिमा" if tithi_n == 14 else "अमावास्या" if tithi_n == 29 else TITHI[tithi_n % 15]
    chart = {
        "name": name, "date": date, "time": time, "lat": lat, "lon": lon, "tz": tz,
        "ayanamsa": _dms(ayan), "ayanamsa_deg": ayan,
        "lagna": {"lon": lagna, "rashi": RASHI[lagna_sign], "sign": lagna_sign, "deg": _dms(lagna % 30),
                  "nakshatra": NAKSHATRA[int(lagna // (360 / 27))]},
        "planets": planets,
        "panchang": {"tithi": f"{paksha} {tithi_name}", "yoga": YOGA[int(((sun + moon) % 360) // (360 / 27))],
                     "vara": VARA[local.weekday()],
                     "nakshatra": f"{P['चंद्र']['nakshatra']} (चरण {P['चंद्र']['pada']})",
                     "rashi": P["चंद्र"]["rashi"]},
        "dasha": vimshottari(moon, local),
    }
    chart["yogas"] = find_yogas(chart)
    return chart


def vimshottari(moon_lon, birth):
    span = 360 / 27
    n = int(moon_lon // span)
    frac = (moon_lon % span) / span
    i = n % 9
    lord, years = DASHA[i]
    start = birth - _dt.timedelta(days=frac * years * 365.25)
    out = []
    for k in range(9):
        lord, years = DASHA[(i + k) % 9]
        end = start + _dt.timedelta(days=years * 365.25)
        out.append({"graha": lord, "from": max(start, birth).strftime("%Y-%m-%d"), "to": end.strftime("%Y-%m-%d"),
                    "years": years, "start": start.strftime("%Y-%m-%d")})     # start = खरी सुरुवात (जन्माआधीही)
        start = end
    return {"balance": f"{DASHA[i][0]} महादशा, जन्मावेळी उरलेली ~{(1 - frac) * DASHA[i][1]:.1f} वर्षे",
            "periods": out}


SIGN_LORD = ["मंगळ", "शुक्र", "बुध", "चंद्र", "सूर्य", "बुध", "शुक्र", "मंगळ", "गुरु", "शनि", "शनि", "गुरु"]
_DORDER = [g for g, _ in DASHA]
_DYEARS = dict(DASHA)


def _d(s):
    return _dt.datetime.strptime(s, "%Y-%m-%d")


def antardashas(maha, start):
    """एका महादशेतील ९ अंतर्दशा — महादशा-स्वामीपासून विंशोत्तरी क्रमाने, कालावधी = म × अ / १२०"""
    i, out, t = _DORDER.index(maha), [], start
    for k in range(9):
        g = _DORDER[(i + k) % 9]
        end = t + _dt.timedelta(days=_DYEARS[maha] * _DYEARS[g] / 120 * 365.25)
        out.append({"graha": g, "from": t, "to": end})
        t = end
    return out


def current_dasha(c, on=None):
    """दिलेल्या दिवशी (default आज) चालू महादशा-अंतर्दशा + पुढच्या ३ अंतर्दशा"""
    on = on or _dt.datetime.now()
    per = c["dasha"]["periods"]
    for k, p in enumerate(per):
        s = _d(p.get("start", p["from"]))
        if s <= on < _d(p["to"]):
            ads = antardashas(p["graha"], s)
            j = next(n for n, a in enumerate(ads) if a["from"] <= on < a["to"])
            nxt = ads[j + 1:j + 4]
            if len(nxt) < 3 and k + 1 < len(per):
                nm = per[k + 1]
                nxt += [dict(a, maha=nm["graha"]) for a in antardashas(nm["graha"], _d(nm["start"]))][:3 - len(nxt)]
            f = lambda x: x.strftime("%Y-%m-%d")
            return {"maha": p["graha"], "maha_to": p["to"], "antar": ads[j]["graha"],
                    "antar_from": f(ads[j]["from"]), "antar_to": f(ads[j]["to"]),
                    "next": [{"maha": a.get("maha", p["graha"]), "antar": a["graha"], "from": f(a["from"]),
                              "to": f(a["to"])} for a in nxt]}
    return None


def gochar(c, on=None):
    """आजचे (किंवा दिलेल्या दिवशीचे) शनि, गुरु, राहू, केतू — जन्म-चंद्र आणि लग्नापासून कितवे स्थान"""
    ts, _ = _load()
    on = on or _dt.datetime.utcnow()
    t = ts.utc(on.year, on.month, on.day, on.hour, on.minute)
    ayan = lahiri_ayanamsa(t)
    trop = tropical_longitudes(t)
    moon_s = next(p["sign"] for p in c["planets"] if p["graha"] == "चंद्र")
    out = []
    for g in ("शनि", "गुरु", "राहू", "केतू"):
        s = int(((trop[g] - ayan) % 360) // 30)
        out.append({"graha": g, "rashi": RASHI[s], "from_moon": (s - moon_s) % 12 + 1,
                    "from_lagna": (s - c["lagna"]["sign"]) % 12 + 1})
    shani = out[0]["from_moon"]
    notes = []
    if shani in (12, 1, 2):
        notes.append(f"शनि जन्म-चंद्रापासून {shani} व्या स्थानी — परंपरेनुसार साडेसातीचा "
                     f"{ {12: 'पहिला', 1: 'दुसरा', 2: 'तिसरा'}[shani]} टप्पा")
    elif shani in (4, 8):
        notes.append(f"शनि जन्म-चंद्रापासून {shani} व्या स्थानी — परंपरेनुसार {'कंटक' if shani == 4 else 'अष्टम'} शनि")
    return {"date": on.strftime("%Y-%m-%d"), "grahas": out, "notes": notes}


def kaal_text(c, on=None):
    """'सध्याचा काळ' — AI ला भविष्याबद्दल बोलण्यासाठी आधार (दशा + गोचर)"""
    P = {p["graha"]: p for p in c["planets"]}
    lines = []
    d = current_dasha(c, on)
    if d:
        m, a = P[d["maha"]], P[d["antar"]]
        lines.append(f"चालू महादशा: {d['maha']} ({d['maha_to']} पर्यंत) — {d['maha']} कुंडलीत {m['rashi']} राशीत, "
                     f"{m['bhava']} व्या स्थानी")
        lines.append(f"चालू अंतर्दशा: {d['antar']} ({d['antar_from']} ते {d['antar_to']}) — {d['antar']} कुंडलीत "
                     f"{a['rashi']} राशीत, {a['bhava']} व्या स्थानी")
        lines.append("पुढच्या अंतर्दशा: " + "; ".join(f"{n['maha']}-{n['antar']} {n['from']} ते {n['to']}"
                                                   for n in d["next"]))
    try:
        g = gochar(c, on)
        lines.append(f"गोचर ({g['date']}): " + "; ".join(
            f"{x['graha']} {x['rashi']} राशीत (चंद्रापासून {x['from_moon']} वे, लग्नापासून {x['from_lagna']} वे)"
            for x in g["grahas"]))
        lines += g["notes"]
    except Exception:
        pass                                   # ephemeris नसेल तर फक्त दशा
    return "\n".join(lines)


def find_yogas(chart):
    """काही प्रसिद्ध योग (व्याख्या ग्रंथांनुसार; फल ग्रंथांतून agent सांगेल)"""
    P = {p["graha"]: p for p in chart["planets"]}
    L = chart["lagna"]["sign"]
    ys = []
    moon_s = P["चंद्र"]["sign"]
    if (P["गुरु"]["sign"] - moon_s) % 12 in (0, 3, 6, 9):
        ys.append(("गजकेसरी योग", "गुरु चंद्रापासून केंद्रात (१, ४, ७, १०)"))
    if P["सूर्य"]["sign"] == P["बुध"]["sign"]:
        ys.append(("बुधादित्य योग", "सूर्य आणि बुध एकाच राशीत"))
    if P["चंद्र"]["sign"] == P["मंगळ"]["sign"]:
        ys.append(("चंद्र-मंगळ योग", "चंद्र आणि मंगळ एकाच राशीत"))
    names = {"मंगळ": "रुचक", "बुध": "भद्र", "गुरु": "हंस", "शुक्र": "मालव्य", "शनि": "शश"}
    for g, yname in names.items():
        p = P[g]
        if (p["sign"] - L) % 12 in (0, 3, 6, 9) and ("स्वराशी" in p["status"] or "उच्च" in p["status"]):
            ys.append((f"{yname} योग (पंचमहापुरुष)", f"{g} लग्नापासून केंद्रात, {'/'.join(p['status'])}"))
    others = [P[g]["sign"] for g in ("मंगळ", "बुध", "गुरु", "शुक्र", "शनि")]
    # केमद्रुम: चंद्रापासून २ऱ्या व १२व्या स्थानी ग्रह नाही — पण चंद्रासोबत किंवा चंद्रापासून केंद्रात ग्रह असेल
    # तर बहुतेक ग्रंथांनुसार (उदा. फलदीपिका) योग भंग होतो, म्हणून तेव्हा तो दाखवत नाही
    bhanga = any((x - moon_s) % 12 in (0, 3, 6, 9) for x in others)
    if (moon_s + 1) % 12 not in others and (moon_s - 1) % 12 not in others and not bhanga:
        ys.append(("केमद्रुम योग", "चंद्रापासून दुसऱ्या आणि बाराव्या स्थानी (सूर्य, राहू, केतू सोडून) ग्रह नाही"))
    return [{"name": n, "why": w} for n, w in ys]


# ---------------------------------------------------------------- दर्शन
def summary_text(c):
    lines = [f"जन्म: {c['date']} {c['time']} (UTC{'+' if c['tz'] >= 0 else ''}{c['tz']}), "
             f"अक्षांश {c['lat']:.3f}, रेखांश {c['lon']:.3f}; लाहिरी अयनांश {c['ayanamsa']}",
             f"लग्न: {c['lagna']['rashi']} {c['lagna']['deg']} ({c['lagna']['nakshatra']} नक्षत्र)",
             f"चंद्र राशी: {c['panchang']['rashi']}; जन्म नक्षत्र: {c['panchang']['nakshatra']}",
             f"पंचांग: {c['panchang']['vara']}, {c['panchang']['tithi']}, योग {c['panchang']['yoga']}"]
    lord = SIGN_LORD[c["lagna"]["sign"]]
    lp = next(p for p in c["planets"] if p["graha"] == lord)
    lines.append(f"लग्नेश: {lord} — {lp['rashi']} राशीत, {lp['bhava']} व्या स्थानी")
    lines.append("ग्रह:")
    for p in c["planets"]:
        extra = ", ".join(p["status"] + (["वक्री"] if p["vakri"] else []))
        lines.append(f"  {p['graha']}: {p['rashi']} {p['deg']}, {p['bhava']} वे स्थान, "
                     f"{p['nakshatra']} {p['pada']}" + (f" ({extra})" if extra else ""))
    lines.append("योग: " + ("; ".join(f"{y['name']} — {y['why']}" for y in c["yogas"]) or "विशेष योग आढळला नाही"))
    lines.append("विंशोत्तरी: " + c["dasha"]["balance"])
    return "\n".join(lines)


def search_queries(c, on=None):
    """ग्रंथांत शोधण्यासाठी प्रश्न — महत्त्वाच्या क्रमाने (लग्न, चंद्र, योग, लग्नेश, चालू दशा, मग इतर ग्रह).
    answer_events पहिले काहीच वापरतो, म्हणून क्रम महत्त्वाचा."""
    P = {p["graha"]: p for p in c["planets"]}
    lord = SIGN_LORD[c["lagna"]["sign"]]
    q = [f"{RASHI_SA[c['lagna']['sign']]} लग्न फल", f"चंद्र {P['चंद्र']['nakshatra']} नक्षत्र जन्म फल"]
    q += [y["name"] for y in c["yogas"]]
    q.append(f"लग्नेश {P[lord]['bhava']} भावात फल")
    d = current_dasha(c, on)
    if d:
        q.append(f"{d['maha']} महादशा फल")
        q.append(f"{d['maha']} दशायां {d['antar']} अन्तर्दशा फलम्")
    q.append(f"चंद्र {RASHI_SA[P['चंद्र']['sign']]} राशौ फलम्")
    for p in c["planets"]:
        if p["graha"] in ("राहू", "केतू", "चंद्र"):
            continue
        q.append(f"{p['graha']} {p['bhava']} भावात फल")
        q.append(f"{p['graha']} {RASHI_SA[p['sign']]} राशौ फलम्")
    return list(dict.fromkeys(q))


def chart_svg(c, size=320):
    """उत्तर भारतीय (हिऱ्याच्या आकाराची) कुंडली"""
    s = size
    pos = {1: (.5, .27), 2: (.25, .12), 3: (.12, .25), 4: (.27, .5), 5: (.12, .75), 6: (.25, .88),
           7: (.5, .73), 8: (.75, .88), 9: (.88, .75), 10: (.73, .5), 11: (.88, .25), 12: (.75, .12)}
    num = {1: (.5, .44), 2: (.25, .2), 3: (.2, .25), 4: (.44, .5), 5: (.2, .75), 6: (.25, .8),
           7: (.5, .56), 8: (.75, .8), 9: (.8, .75), 10: (.56, .5), 11: (.8, .25), 12: (.75, .2)}
    by_house = {h: [] for h in range(1, 13)}
    for p in c["planets"]:
        by_house[p["bhava"]].append(GRAHA_SHORT[p["graha"]] + ("(व)" if p["vakri"] else ""))
    L = c["lagna"]["sign"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {s} {s}" width="{s}" height="{s}" '
           f'style="background:#fffaf0;font-family:Nirmala UI,Noto Sans Devanagari,sans-serif">',
           f'<rect x="1" y="1" width="{s-2}" height="{s-2}" fill="none" stroke="#7a3e00" stroke-width="2"/>',
           f'<path d="M1 1L{s-1} {s-1}M{s-1} 1L1 {s-1}M{s/2} 1L1 {s/2}L{s/2} {s-1}L{s-1} {s/2}Z" '
           f'fill="none" stroke="#7a3e00" stroke-width="1.5"/>']
    for h in range(1, 13):
        x, y = num[h]
        out.append(f'<text x="{x*s:.0f}" y="{y*s:.0f}" font-size="{s*.04:.0f}" fill="#a0522d" '
                   f'text-anchor="middle" dominant-baseline="middle">{(L + h - 1) % 12 + 1}</text>')
        x, y = pos[h]
        items = (["ल"] if h == 1 else []) + by_house[h]
        for i, it in enumerate(items):
            dy = (i - (len(items) - 1) / 2) * s * .055
            out.append(f'<text x="{x*s:.0f}" y="{y*s+dy:.0f}" font-size="{s*.05:.0f}" text-anchor="middle" '
                       f'dominant-baseline="middle" fill="{"#b00000" if it == "ल" else "#222"}">{it}</text>')
    out.append("</svg>")
    return "".join(out)


if __name__ == "__main__":
    for st in (sys.stdout, sys.stderr):
        try: st.reconfigure(encoding="utf-8")
        except Exception: pass
    d, tm, place = (sys.argv[1:4] + ["1990-08-15", "06:30", "पुणे"][len(sys.argv) - 1:])[:3]
    lat, lon = CITIES.get(place, (18.520, 73.857))
    ch = compute_chart(d, tm, lat, lon)
    print(summary_text(ch))
