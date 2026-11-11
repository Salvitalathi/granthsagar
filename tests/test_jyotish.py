"""
कुंडली गणित तपासणी: jyotish.py (Skyfield + DE421) विरुद्ध Swiss Ephemeris (pyswisseph, फक्त चाचणीसाठी).
  pip install skyfield pyswisseph
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for st in (sys.stdout, sys.stderr):
    try: st.reconfigure(encoding="utf-8")
    except Exception: pass

import swisseph as swe
import jyotish as J

swe.set_sid_mode(swe.SIDM_LAHIRI)
IDS = {"सूर्य": swe.SUN, "चंद्र": swe.MOON, "मंगळ": swe.MARS, "बुध": swe.MERCURY, "गुरु": swe.JUPITER,
       "शुक्र": swe.VENUS, "शनि": swe.SATURN, "राहू": swe.MEAN_NODE}

CASES = [("1990-08-15", "06:30", "पुणे"), ("1947-08-15", "00:00", "दिल्ली"), ("2001-01-01", "12:00", "मुंबई"),
         ("1975-03-21", "18:45", "नागपूर"), ("2024-11-01", "23:10", "कोलकाता"), ("1962-12-31", "04:05", "बेंगळुरू"),
         ("2010-06-21", "13:00", "जयपूर"), ("1985-10-10", "21:20", "कोल्हापूर")]


def diff(a, b):
    return abs((a - b + 180) % 360 - 180)


worst = {"planet": 0, "lagna": 0, "ayan": 0}
fail = []
for d, t, city in CASES:
    lat, lon = J.CITIES[city]
    c = J.compute_chart(d, t, lat, lon, name=city)
    y, m, dd = map(int, d.split("-")); hh, mm = map(int, t.split(":"))
    jd = swe.julday(y, m, dd, hh + mm / 60 - 5.5)
    ayan = swe.get_ayanamsa_ut(jd)
    worst["ayan"] = max(worst["ayan"], abs(ayan - c["ayanamsa_deg"]))
    print(f"\n{d} {t} {city}: अयनांश swe {ayan:.5f}  आपले {c['ayanamsa_deg']:.5f}  फरक {(c['ayanamsa_deg']-ayan)*3600:+.1f}\"")
    P = {p["graha"]: p for p in c["planets"]}
    for g, pid in IDS.items():
        L = swe.calc_ut(jd, pid, swe.FLG_SIDEREAL | swe.FLG_MOSEPH)[0][0]
        e = diff(L, P[g]["lon"])
        worst["planet"] = max(worst["planet"], e)
        flag = "" if e < 5 / 3600 else "  ❌"
        print(f"  {g:6} swe {L:9.4f}  आपले {P[g]['lon']:9.4f}  फरक {e*3600:6.1f}\"{flag}")
        if e >= 5 / 3600:
            fail.append(f"{d} {g} {e:.4f}°")
        if int(L // 30) != P[g]["sign"] and min(L % 30, 30 - L % 30) > 0.05:
            fail.append(f"{d} {g} राशी चुकली")
    cusps, ascmc = swe.houses_ex(jd, lat, lon, b"W", swe.FLG_SIDEREAL)
    e = diff(ascmc[0], c["lagna"]["lon"])
    worst["lagna"] = max(worst["lagna"], e)
    print(f"  लग्न   swe {ascmc[0]:9.4f}  आपले {c['lagna']['lon']:9.4f}  फरक {e*3600:6.1f}\"")
    if e >= 5 / 3600:
        fail.append(f"{d} लग्न {e:.4f}°")
    print("  " + J.summary_text(c).replace("\n", "\n  "))

print("\nकमाल फरक:", {k: f"{v*3600:.1f}\"" for k, v in worst.items()})

# विंशोत्तरी: एकूण १२० वर्षे, क्रम बरोबर
c = J.compute_chart("1990-08-15", "06:30", *J.CITIES["पुणे"])
per = c["dasha"]["periods"]
assert [p["graha"] for p in per][:2] and sum(p["years"] for p in per) == 120
assert J.chart_svg(c).startswith("<svg") and "ल" in J.chart_svg(c)
assert J.search_queries(c)
print("दशा:", [(p["graha"], p["from"]) for p in per[:3]])

b = J.parse_birth("नाव - मंगेश साळवी, जन्माची वेळ (12 जुलै, 1977, रात्री 8:30 pm) ठिकाण- अलिबाग, जिल्हा- रायगड")
c = J.compute_chart(b["date"], b["time"], *J.CITIES[b["place"]])
print("\nchat मधून:", b, "\n" + J.summary_text(c))
print("दशा:", ", ".join(f"{p['graha']} {p['from']}–{p['to']}" for p in c["dasha"]["periods"]))
lat, lon = J.CITIES["अलिबाग"]
jd = swe.julday(1977, 7, 12, 20.5 - 5.5)
asc = swe.houses_ex(jd, lat, lon, b"W", swe.FLG_SIDEREAL)[1][0]
if abs(((asc - c["lagna"]["lon"]) + 180) % 360 - 180) > 5 / 3600:
    fail.append("अलिबाग लग्न")

# चालू दशा-अंतर्दशा + गोचर (भविष्याच्या प्रश्नांसाठी)
import datetime as _dt
c = J.compute_chart("1977-07-12", "20:30", *J.CITIES["अलिबाग"])
for p in c["dasha"]["periods"]:
    ads = J.antardashas(p["graha"], _dt.datetime.strptime(p["start"], "%Y-%m-%d"))
    if ads[0]["graha"] != p["graha"] or abs((ads[-1]["to"] - ads[0]["from"]).days / 365.25 - p["years"]) > 0.01:
        fail.append(f"अंतर्दशा {p['graha']}")
on = _dt.datetime(2026, 11, 11)
cd = J.current_dasha(c, on)
if not cd or not (cd["antar_from"] <= "2026-11-11" < cd["antar_to"]) or len(cd["next"]) != 3:
    fail.append(f"चालू दशा {cd}")
g = J.gochar(c, on)
jd = swe.julday(2026, 11, 11, 0)
for x in g["grahas"]:
    pid = {"शनि": swe.SATURN, "गुरु": swe.JUPITER, "राहू": swe.MEAN_NODE}.get(x["graha"])
    if pid is not None:
        L = swe.calc_ut(jd, pid, swe.FLG_SIDEREAL | swe.FLG_MOSEPH)[0][0]
        if J.RASHI[int(L // 30)] != x["rashi"] and min(L % 30, 30 - L % 30) > 0.05:
            fail.append(f"गोचर {x['graha']}")
kt = J.kaal_text(c, on)
print("\nसध्याचा काळ:\n" + kt)
if "चालू महादशा" not in kt or "गोचर" not in kt or "लग्नेश" not in J.summary_text(c):
    fail.append("kaal_text")
q = J.search_queries(c, on)
if not any("महादशा" in x for x in q[:8]):
    fail.append("दशा-शोध पहिल्या ८ मध्ये नाही")

import json as _json
try:                                       # browser ला जाणारी कुंडली साध्या json ने (numpy bool नको)
    _json.dumps(J.compute_chart("1990-08-15", "06:30", *J.CITIES["पुणे"]), ensure_ascii=False)
except TypeError as e:
    fail.append(f"कुंडली JSON: {e}")
if worst["ayan"] > 1 / 3600:
    fail.append(f"अयनांश फरक {worst['ayan']*3600:.1f}\"")
if fail:
    print("\n❌ चुका:", fail); sys.exit(1)
print("\n✅ कुंडली गणित Swiss Ephemeris शी जुळते")
