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
}


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
        retro = g in ("राहू", "केतू") or d < 0
        status = []
        if g in EXALT and sign == EXALT[g]:
            status.append("उच्च")
        if g in EXALT and sign == (EXALT[g] + 6) % 12:
            status.append("नीच")
        if g in OWN and sign in OWN[g]:
            status.append("स्वराशी")
        planets.append({
            "graha": g, "lon": L, "rashi": RASHI[sign], "sign": sign, "deg": _dms(L % 30),
            "bhava": (sign - lagna_sign) % 12 + 1,
            "nakshatra": NAKSHATRA[nak], "pada": int((L % (360 / 27)) // (360 / 108)) + 1,
            "vakri": retro and g not in ("राहू", "केतू"), "status": status,
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
                    "years": years})
        start = end
    return {"balance": f"{DASHA[i][0]} महादशा, जन्मावेळी उरलेली ~{(1 - frac) * DASHA[i][1]:.1f} वर्षे",
            "periods": out}


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
    if (moon_s + 1) % 12 not in others and (moon_s - 1) % 12 not in others:
        ys.append(("केमद्रुम योग", "चंद्रापासून दुसऱ्या आणि बाराव्या स्थानी (सूर्य, राहू, केतू सोडून) ग्रह नाही"))
    return [{"name": n, "why": w} for n, w in ys]


# ---------------------------------------------------------------- दर्शन
def summary_text(c):
    lines = [f"जन्म: {c['date']} {c['time']} (UTC{'+' if c['tz'] >= 0 else ''}{c['tz']}), "
             f"अक्षांश {c['lat']:.3f}, रेखांश {c['lon']:.3f}; लाहिरी अयनांश {c['ayanamsa']}",
             f"लग्न: {c['lagna']['rashi']} {c['lagna']['deg']} ({c['lagna']['nakshatra']} नक्षत्र)",
             f"चंद्र राशी: {c['panchang']['rashi']}; जन्म नक्षत्र: {c['panchang']['nakshatra']}",
             f"पंचांग: {c['panchang']['vara']}, {c['panchang']['tithi']}, योग {c['panchang']['yoga']}",
             "ग्रह:"]
    for p in c["planets"]:
        extra = ", ".join(p["status"] + (["वक्री"] if p["vakri"] else []))
        lines.append(f"  {p['graha']}: {p['rashi']} {p['deg']}, {p['bhava']} वे स्थान, "
                     f"{p['nakshatra']} {p['pada']}" + (f" ({extra})" if extra else ""))
    lines.append("योग: " + ("; ".join(f"{y['name']} — {y['why']}" for y in c["yogas"]) or "विशेष योग आढळला नाही"))
    lines.append("विंशोत्तरी: " + c["dasha"]["balance"])
    return "\n".join(lines)


def search_queries(c):
    """ग्रंथांत शोधण्यासाठी प्रश्न — मराठी + संस्कृत रूपे"""
    q = [f"{RASHI_SA[c['lagna']['sign']]} लग्न फल", f"{c['lagna']['rashi']} लग्नाचे फल"]
    for p in c["planets"]:
        if p["graha"] in ("राहू", "केतू"):
            continue
        q.append(f"{p['graha']} {RASHI_SA[p['sign']]} राशौ फलम्")
        q.append(f"{p['graha']} {p['bhava']} भावात फल")
    q.append(f"चंद्र {c['planets'][1]['nakshatra']} नक्षत्र जन्म फल")
    q += [y["name"] for y in c["yogas"]]
    return q


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
