"""
GRETIL वरून ग्रंथ उतरवणे (copyright-मुक्त संस्कृत मजकूर).

  python scripts/download_granth.py            -> ठरलेले ग्रंथ granth_raw/ मध्ये
  python scripts/download_granth.py --list     -> GRETIL वरील सगळ्या .txt फाइल्सची यादी
  python scripts/download_granth.py purana     -> नावात 'purana' असलेल्या सगळ्या फाइल्स

GRETIL चे links बदलू शकतात, म्हणून हा script आधी index पान वाचून links शोधतो.
"""
import os, re, sys, time, urllib.request, urllib.parse

INDEX = "https://gretil.sub.uni-goettingen.de/gretil.html"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "granth_raw")
UA = {"User-Agent": "granthsagar-downloader/1.0 (personal study project)"}

# फाइल-नावात हे शब्द असतील तर उतरवा (GRETIL च्या नावांमध्ये z = ś, S = ṣ, A = ā इ.)
DEFAULT = [
    r"atharva",          # अथर्ववेद
    r"caraka",           # चरक संहिता
    r"su[sz]ruta",       # सुश्रुत संहिता
    r"a[sS][tT]A?[nG]g?ahRd|astangahrd",   # अष्टांगहृदय
]


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def all_txt_links():
    html = get(INDEX).decode("utf-8", "replace")
    links = set()
    for href in re.findall(r'href="([^"]+)"', html, flags=re.I):
        if href.lower().endswith(".txt"):
            links.add(urllib.parse.urljoin(INDEX, href))
    return sorted(links)


def main():
    args = sys.argv[1:]
    links = all_txt_links()
    print(f"GRETIL वर {len(links)} .txt फाइल्स सापडल्या")
    if "--list" in args:
        for l in links:
            print(" ", l)
        return
    patterns = args or DEFAULT
    want = [l for l in links if any(re.search(p, os.path.basename(l), flags=re.I) for p in patterns)]
    if not want:
        print("जुळणारी फाइल नाही. '--list' वापरून नावे पाहा.")
        sys.exit(1)
    os.makedirs(RAW, exist_ok=True)
    for url in want:
        name = urllib.parse.unquote(os.path.basename(url))
        dst = os.path.join(RAW, name)
        if os.path.exists(dst):
            print(f"= आधीच आहे: {name}"); continue
        try:
            data = get(url)
            with open(dst, "wb") as f:
                f.write(data)
            print(f"⬇ {name} ({len(data) // 1024} KB)")
        except Exception as e:
            print(f"! {name}: {e}")
        time.sleep(1)   # server वर ताण नको


if __name__ == "__main__":
    for st in (sys.stdout, sys.stderr):
        try: st.reconfigure(encoding="utf-8")
        except Exception: pass
    main()
