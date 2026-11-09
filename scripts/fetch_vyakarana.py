"""
व्याकरण ग्रंथ उतरवणे -> granth/vyakarana/

  python scripts/fetch_vyakarana.py

  अष्टाध्यायी        — sa.wikisource (CC BY-SA 4.0)          [अष्टाध्यायी 1.1.1]
  काशिका             — sa.wikisource (CC BY-SA 4.0)          [काशिका 1.1.4]
  लघुसिद्धान्तकौमुदी  — GRETIL (IAST -> देवनागरी)              [लघुसिद्धान्तकौमुदी 70 = 8.4.41]
  व्याकरणमहाभाष्य    — GRETIL, Kielhorn/Abhyankar (CC BY-NC-SA 4.0 — व्यावसायिक वापर नाही)  [महाभाष्य 1.1.1]
  अमरकोश             — GRETIL                                [अमरकोश 1.0.1]

वाचस्पत्यम् आणि शब्दकल्पद्रुम (प्रत्येकी ~25 MB) इथे नाहीत — ते ग्रंथसागर पहिल्यांदा लागतील तेव्हा
थेट तुमच्या संगणकावर उतरवतो (kosha.py), कारण ते शोधासाठी वेगळ्या पद्धतीने (शब्दानुसार) वापरले जातात.
"""
import os, re, sys, time, urllib.parse

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "scripts"))
sys.path.insert(0, HERE)
from fetch_jyotish import get, write_parts, wiki_clean  # noqa: E402
from granth_tayar import iast_to_deva  # noqa: E402

OUT = os.path.join(HERE, "granth", "vyakarana")
G = "https://gretil.sub.uni-goettingen.de/gretil/corpustei/transformations/plaintext/"
W = "https://sa.wikisource.org/w/index.php?"
DN = str.maketrans("०१२३४५६७८९", "0123456789")
ADHYAYA = ["प्रथम", "द्वितीय", "तृतीय", "चतुर्थ", "पञ्चम", "षष्ठ", "सप्तम", "अष्टम"]
PADA = ["प्रथमः", "द्वितीयः", "तृतीयः", "चतुर्थः"]


def raw(title):
    return get(W + urllib.parse.urlencode({"title": title, "action": "raw"})).decode("utf-8", "replace")


def allpages(prefix):
    import json
    out, cont = [], {}
    while True:
        d = json.loads(get("https://sa.wikisource.org/w/api.php?" + urllib.parse.urlencode(
            dict({"action": "query", "list": "allpages", "format": "json", "aplimit": 500, "apprefix": prefix}, **cont))))
        out += [p["title"] for p in d["query"]["allpages"]]
        if "continue" not in d:
            return out
        cont = d["continue"]


def gretil_body(name):
    t = get(G + name + ".txt").decode("utf-8", "replace")
    i = t.find("# Text")
    return t[i + 6:] if i >= 0 else t


def deva(iast):
    s = iast.replace("-", "").replace("+", "").replace("ẖ", "ḥ").replace("ḫ", "ḥ")
    return iast_to_deva(s).replace("//", "॥").replace("/", "।")


# ---------------------------------------------------------------- अष्टाध्यायी
def ashtadhyayi():
    blocks, n = [], 0
    pages = [t for t in allpages("अष्टाध्यायी/") if t.count("/") == 1]
    print("   अष्टाध्यायी पाने:", pages)
    seen = set()
    for k, title in enumerate(pages, 1):
        try:
            t = raw(title)
        except Exception as e:
            print(f"⚠️ {title}: {e}"); continue
        sutras = []
        for m in re.finditer(r"^\s*([०-९0-9]+)[.।]([०-९0-9]+)[.।]([०-९0-9]+)\s+(.+?)\s*$", t, flags=re.M):
            a, b, c = (int(x.translate(DN)) for x in m.groups()[:3])
            s = re.sub(r"<[^>]+>|\[\[|\]\]|'''?", "", m.group(4)).strip(" ।")
            if (a, b, c) not in seen:
                seen.add((a, b, c)); sutras.append(((a, b, c), f"[अष्टाध्यायी {a}.{b}.{c}] {s} ।"))
        n += len(sutras)
        blocks += sutras
        time.sleep(0.5)
    blocks.sort()
    lines = [b for _, b in blocks]
    blocks = ["\n".join(lines[i:i + 40]) for i in range(0, len(lines), 40)]   # ४० सूत्रांचा एक गट
    write_parts(os.path.join(OUT, "ashtadhyayi"), blocks)
    print(f"✅ अष्टाध्यायी: {n} सूत्रे")
    return n


# ---------------------------------------------------------------- काशिका
def kashika():
    blocks, n, empty = [], 0, 0
    pages = [t for t in allpages("काशिका/") if t.count("/") == 2]
    print(f"   काशिका पाने ({len(pages)}):", pages)
    for title in pages:
        if True:
            try:
                txt = raw(title)
            except Exception as e:
                print(f"⚠️ {title}: {e}"); continue
            txt = txt.replace("`", "")
            txt = re.sub(r"</?poem>|\{\{[^}]*\}\}|'{2,3}|</\s*[०-९0-9]+\s*-\s*[०-९0-9]+\s*-\s*[०-९0-9]+\s*>", "", txt)
            parts = re.split(r"<\s*([०-९0-9]+)\s*-\s*([०-९0-9]+)\s*-\s*([०-९0-9]+)\s*>", txt)
            for i in range(1, len(parts) - 3, 4):
                ref = ".".join(str(int(x.translate(DN))) for x in parts[i:i + 3])
                prev = [l.strip() for l in parts[i - 1].splitlines() if l.strip()]
                sutra = prev[-1].replace("।।", "").strip(" ।") if prev else ""
                lines = [l.strip() for l in parts[i + 3].splitlines() if l.strip()]
                if i + 4 < len(parts) and lines and lines[-1].rstrip().endswith("।।"):
                    lines = lines[:-1]                      # ही पुढच्या सूत्राची ओळ
                lines = [l.lstrip("। ").strip() for l in lines if l.strip("। ")]
                if not lines:
                    empty += 1
                blocks.append((tuple(int(x) for x in ref.split(".")), f"[काशिका {ref}]\n{sutra} ।\n" + "\n".join(lines)))
                n += 1
            time.sleep(0.5)
    blocks = [b for _, b in sorted(dict(blocks).items())]
    write_parts(os.path.join(OUT, "kashika"), blocks)
    print(f"✅ काशिका: {n} सूत्रे ({empty} सूत्रांवर Wikisource वर वृत्ती अजून नाही)")
    return n


# ---------------------------------------------------------------- लघुसिद्धान्तकौमुदी
def laghu():
    body = gretil_body("sa_varadarAja-laghusiddhAntakaumudI")
    blocks, cur, head = [], [], None
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(.*?)\s*//\s*vlk_(\d+)\s*=\s*p_(\d+),(\d+)\.(\d+)\s*//\s*$", line)
        if m:
            if head:
                blocks.append(head + "\n" + "\n".join(cur))
            head = (f"[लघुसिद्धान्तकौमुदी {m.group(2)} = {m.group(3)}.{m.group(4)}.{m.group(5)}]\n"
                    f"{deva(m.group(1))} ॥")
            cur = []
        elif head:
            cur.append(deva(line))
        elif re.match(r"^atha .*prakaraṇam", line):
            blocks.append(f"[लघुसिद्धान्तकौमुदी प्रकरण]\n{deva(line)}")
    if head:
        blocks.append(head + "\n" + "\n".join(cur))
    write_parts(os.path.join(OUT, "laghusiddhantakaumudi"), blocks)
    print(f"✅ लघुसिद्धान्तकौमुदी: {len(blocks)} सूत्रे")
    return len(blocks)


# ---------------------------------------------------------------- महाभाष्य
def mahabhashya():
    body = gretil_body("sa_pataJjali-vyAkaraNamahAbhASya")
    segs = re.split(r"\((p_\d+,\d+\.\d+(?:\.\d+)?|pas_[\d.]+|śs_[\d.]+)\)\s*", body)
    groups, order = {}, []
    for i in range(1, len(segs) - 1, 2):
        ref, txt = segs[i], segs[i + 1]
        txt = re.sub(r"\b(?:ka|ro)_[ivx]+,[\d.,\-]+\s*", "", txt)
        txt = re.sub(r"\{\d+/\d+\}\s*", "", txt).strip()
        m = re.match(r"p_(\d+),(\d+)\.(\d+)", ref)
        key = f"{m.group(1)}.{m.group(2)}.{m.group(3)}" if m else ("पस्पशाह्निक" if ref.startswith("pas") else
                                                                   "शिवसूत्र " + ref.split("_")[1])
        if key not in groups:
            groups[key] = []; order.append(key)
        if txt:
            groups[key].append(txt)
    blocks = []
    for key in order:
        text = deva(" ".join(groups[key])).replace(" . ", " । ").replace(" .", " ।")
        blocks.append(f"[महाभाष्य {key}]\n{text}")
    write_parts(os.path.join(OUT, "mahabhashya"), blocks)
    print(f"✅ महाभाष्य: {len(blocks)} सूत्रांवर भाष्य")
    return len(blocks)


# ---------------------------------------------------------------- अमरकोश
def amara():
    body = gretil_body("sa_amarasiMha-nAmaliGgAnuzAsana")
    blocks, cur = [], []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        refs = re.split(r"\((\d+\.\d+\.\d+)\)\s*", line)
        if len(refs) < 3:
            if len(line) < 60 and ("varga" in line or "kāṇḍa" in line):
                cur.append(f"— {deva(line)} —")
            continue
        for i in range(1, len(refs) - 1, 2):
            cur.append(f"({refs[i]}) {deva(refs[i + 1].strip())}")
        if len(cur) >= 30:
            first = re.search(r"\((\d+\.\d+\.\d+)\)", "\n".join(cur)).group(1)
            blocks.append(f"[अमरकोश {first}]\n" + "\n".join(cur)); cur = []
    if cur:
        first = re.search(r"\((\d+\.\d+\.\d+)\)", "\n".join(cur))
        blocks.append(f"[अमरकोश {first.group(1) if first else ''}]\n" + "\n".join(cur))
    write_parts(os.path.join(OUT, "amarakosha"), blocks)
    print(f"✅ अमरकोश: {len(blocks)} गट")


def main():
    for st in (sys.stdout, sys.stderr):
        try: st.reconfigure(encoding="utf-8")
        except Exception: pass
    for f in (ashtadhyayi, kashika, laghu, mahabhashya, amara):
        try:
            f()
        except Exception as e:
            print(f"⚠️ {f.__name__}: {e}")
    with open(os.path.join(HERE, "SOURCES_vyakarana.md"), "w", encoding="utf-8") as f:
        f.write("# व्याकरण ग्रंथांचे स्रोत\n\n"
                "- अष्टाध्यायी, काशिका: sa.wikisource.org contributors, CC BY-SA 4.0 (मूळ ग्रंथ प्राचीन).\n"
                "- लघुसिद्धान्तकौमुदी, अमरकोश: GRETIL, Göttingen (IAST -> देवनागरी रूपांतर: ग्रंथसागर).\n"
                "- व्याकरणमहाभाष्य: GRETIL — Kielhorn/Abhyankar आवृत्ती, input George Cardona; "
                "CC BY-NC-SA 4.0 (**व्यावसायिक वापर नाही**).\n"
                "- वाचस्पत्यम्, शब्दकल्पद्रुम: Cologne Digital Sanskrit Dictionaries (csl-orig), CC BY-SA 4.0 — "
                "ग्रंथसागर पहिल्या वापराला थेट उतरवतो (repo मध्ये नाहीत).\n")


if __name__ == "__main__":
    main()
