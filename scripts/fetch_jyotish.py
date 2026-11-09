"""
ज्योतिष ग्रंथ उतरवणे (copyright-मुक्त मूळ ग्रंथ + जुनी भाषांतरे) -> granth/jyotish/

  python scripts/fetch_jyotish.py

स्रोत:
  * sa.wikisource.org — बृहत्पाराशर होराशास्त्र, बृहज्जातक, सारावली, फलदीपिका, जातकपारिजात
    (मूळ ग्रंथ प्राचीन; Wikisource ची प्रत CC BY-SA 4.0 — श्रेय: Wikisource contributors)
  * GRETIL — बृहत्संहिता, सूर्यसिद्धांत (IAST -> देवनागरी)
  * archive.org — 1929 पूर्वीची इंग्रजी भाषांतरे (public domain)
"""
import json, os, re, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from granth_tayar import iast_to_deva  # noqa: E402

OUT = os.path.join(HERE, "granth", "jyotish")
UA = {"User-Agent": "granthsagar/1.0 (personal study project; github.com/Salvitalathi)"}
PART = 150_000

WIKISOURCE = [   # (पानाचे नाव, मराठी नाव, folder)
    ("बृहत्पाराशरहोराशास्त्रम्", "बृहत्पाराशर होराशास्त्र", "bphs"),
    ("बृहज्जातकम्", "बृहज्जातक", "brihajjataka"),
    ("सारावली", "सारावली", "saravali"),
    ("फलदीपिका", "फलदीपिका", "phaladeepika"),
    ("जातकपारिजातः", "जातकपारिजात", "jatakaparijata"),
]
GRETIL = [
    ("https://gretil.sub.uni-goettingen.de/gretil/corpustei/transformations/plaintext/sa_varAhamihira-bRhatsaMhitA.txt",
     "बृहत्संहिता", "brihatsamhita"),
    ("https://gretil.sub.uni-goettingen.de/gretil/corpustei/transformations/plaintext/sa_sUryasiddhAnta.txt",
     "सूर्यसिद्धांत", "suryasiddhanta"),
    ("https://gretil.sub.uni-goettingen.de/gretil/corpustei/transformations/plaintext/sa_varAhamihira-bRhajjAtaka.txt",
     "बृहज्जातक (GRETIL)", "brihajjataka_gretil"),
]
ARCHIVE = [   # इंग्रजी भाषांतरे (1929 पूर्वी)
    ("brihatjatakavar00iyergoog", "Brihat Jataka — English tr. N. Chidambaram Iyer (1885)", "en_brihat_jataka_1885"),
    ("bihatsahitvarah00iyergoog", "Brihat Samhita — English tr. N. Chidambaram Iyer (1884)", "en_brihat_samhita_1884"),
    ("dli.csl.7956", "Surya Siddhanta — English tr. E. Burgess (1860)", "en_surya_siddhanta_1860"),
]

DEVA_NUM = str.maketrans("०१२३४५६७८९", "0123456789")


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def write_parts(folder, blocks):
    os.makedirs(folder, exist_ok=True)
    for f in os.listdir(folder):
        if f.startswith("part_"):
            os.remove(os.path.join(folder, f))
    part, size, k = [], 0, 1
    for b in blocks + [None]:
        if b is None or (part and size + len(b) > PART):
            if part:
                with open(os.path.join(folder, f"part_{k:02d}.txt"), "w", encoding="utf-8") as f:
                    f.write("\n\n".join(part) + "\n")
                k += 1
            part, size = [], 0
        if b is not None:
            part.append(b); size += len(b)
    return k - 1


# ---------------- Wikisource ----------------
def wiki_clean(t):
    t = re.sub(r"<ref[^>]*?/>|<ref.*?</ref>", "", t, flags=re.S)
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    for _ in range(3):
        t = re.sub(r"\{\{[^{}]*\}\}", "", t)                       # साचे
    t = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", t)        # [[दुवा|मजकूर]]
    t = re.sub(r"\[https?://\S+ ([^\]]+)\]", r"\1", t)
    t = re.sub(r"'''?|<[^>]+>|__[A-Z]+__", "", t)
    t = re.sub(r"^[=]+\s*(.*?)\s*[=]+\s*$", r"\1", t, flags=re.M)
    t = re.sub(r"^\s*[:*#;]+\s*", "", t, flags=re.M)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def wiki_pages(title):
    api = "https://sa.wikisource.org/w/api.php"
    pages, cont = [title], {}
    while True:
        q = {"action": "query", "list": "allpages", "apprefix": title + "/", "apnamespace": 0,
             "aplimit": "500", "format": "json", **cont}
        d = json.loads(get(api + "?" + urllib.parse.urlencode(q)))
        pages += [p["title"] for p in d["query"]["allpages"]]
        if "continue" not in d:
            break
        cont = d["continue"]
    def order(p):
        m = re.search(r"([०-९0-9]+)", p.split("/", 1)[-1])
        return (p != title, int(m.group(1).translate(DEVA_NUM)) if m else 9999, p)
    return sorted(set(pages), key=order)


def fetch_wikisource(title, mr, folder):
    blocks = []
    for p in wiki_pages(title):
        raw = get("https://sa.wikisource.org/w/index.php?" +
                  urllib.parse.urlencode({"title": p, "action": "raw"})).decode("utf-8", "replace")
        text = wiki_clean(raw)
        if len(re.findall(r"[ऀ-ॿ]", text)) < 80:
            continue
        sub = p.split("/", 1)[1] if "/" in p else "प्रस्तावना"
        blocks.append(f"[{mr} — {sub}]\n{text}")
        time.sleep(0.5)
    n = write_parts(os.path.join(OUT, folder), blocks)
    print(f"✅ {mr}: {len(blocks)} पाने/अध्याय → {n} फाइल्स")


# ---------------- GRETIL ----------------
REF = re.compile(r"^\s*([A-Za-zĀŚṢ_]{1,8})[_\s.]?(\d[\d.,:]*[a-f]?)\s*[:.]?\s+(.*)$")
TRAIL = re.compile(r"\s*//\s*([A-Za-zĀŚṢ_]{1,8})[_\s.]?(\d[\d.,:]*[a-f]?)\s*//\s*$")


def fetch_gretil(url, mr, folder):
    lines = get(url).decode("utf-8", "replace").splitlines()
    for k, ln in enumerate(lines):
        if re.match(r"^\s*#\s*text\s*$", ln, flags=re.I):
            lines = lines[k + 1:]
            break
    blocks, cur, chap = [], [], None
    for ln in lines:
        ln = ln.rstrip()
        if not ln.strip():
            continue
        ref = None
        m = TRAIL.search(ln)
        if m:
            ref, ln = m.group(2), ln[:m.start()]
        else:
            m = REF.match(ln)
            if m:
                ref, ln = m.group(2), m.group(3)
        c = ref.replace(",", ".").split(".")[0] if ref else chap
        if c != chap and cur:
            blocks.append(f"[{mr} अध्याय {chap}]\n" + "\n".join(cur)); cur = []
        chap = c
        cur.append((f"({ref.replace(',', '.')}) " if ref else "") + iast_to_deva(ln))
    if cur:
        blocks.append(f"[{mr} अध्याय {chap}]\n" + "\n".join(cur))
    n = write_parts(os.path.join(OUT, folder), blocks)
    print(f"✅ {mr}: {len(blocks)} अध्याय → {n} फाइल्स")


# ---------------- archive.org ----------------
def fetch_archive(ident, title, folder):
    meta = json.loads(get(f"https://archive.org/metadata/{ident}"))
    txt = [f["name"] for f in meta.get("files", []) if f["name"].endswith("_djvu.txt")]
    if not txt:
        print(f"⚠️ {title}: मजकूर फाइल नाही"); return
    t = get(f"https://archive.org/download/{ident}/{urllib.parse.quote(txt[0])}").decode("utf-8", "replace")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"(?im)^.*(digitized by|google|generated .* (on|by)).*$", "", t)     # scan च्या खुणा
    paras = [p.strip() for p in re.split(r"\n\s*\n", t) if len(p.strip()) > 40]
    blocks, cur, size, k = [], [], 0, 1
    for p in paras:
        cur.append(p); size += len(p)
        if size > 2500:
            blocks.append(f"[{title} — भाग {k}]\n" + "\n\n".join(cur)); cur, size, k = [], 0, k + 1
    if cur:
        blocks.append(f"[{title} — भाग {k}]\n" + "\n\n".join(cur))
    n = write_parts(os.path.join(OUT, folder), blocks)
    print(f"✅ {title}: {len(t) // 1024} KB → {n} फाइल्स")


def main():
    for st in (sys.stdout, sys.stderr):
        try: st.reconfigure(encoding="utf-8")
        except Exception: pass
    for args in WIKISOURCE:
        try: fetch_wikisource(*args)
        except Exception as e: print(f"⚠️ {args[1]}: {e}")
    for args in GRETIL:
        try: fetch_gretil(*args)
        except Exception as e: print(f"⚠️ {args[1]}: {e}")
    for args in ARCHIVE:
        try: fetch_archive(*args)
        except Exception as e: print(f"⚠️ {args[1]}: {e}")
    with open(os.path.join(HERE, "SOURCES_jyotish.md"), "w", encoding="utf-8") as f:
        f.write("# ज्योतिष ग्रंथांचे स्रोत\n\n"
                "- संस्कृत (बृहत्पाराशर होराशास्त्र, बृहज्जातक, सारावली, फलदीपिका, जातकपारिजात): "
                "sa.wikisource.org contributors, CC BY-SA 4.0. मूळ ग्रंथ प्राचीन (public domain).\n"
                "- बृहत्संहिता, सूर्यसिद्धांत, बृहज्जातक (IAST): GRETIL, Göttingen — देवनागरीत रूपांतर ग्रंथसागर.\n"
                "- इंग्रजी भाषांतरे (1860–1885): archive.org, public domain.\n")


if __name__ == "__main__":
    main()
