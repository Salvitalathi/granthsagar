"""
Digital Corpus of Sanskrit (DCS) मधून ग्रंथ तयार करणे.
DCS (Oliver Hellwig) — https://github.com/OliverHellwig/sanskrit — license CC BY 4.0.

  python scripts/dcs_granth.py                 -> अथर्ववेद, सुश्रुत, चरक
  python scripts/dcs_granth.py atharva         -> फक्त अथर्ववेद
  python scripts/dcs_granth.py --list          -> उपलब्ध नावे
  python scripts/dcs_granth.py bhagavata garuda

काय करतो:
  * फक्त हवे ते ग्रंथ GitHub वरून उतरवतो (git sparse checkout, git लागते)
  * संस्कृत मजकूर देवनागरीत, प्रत्येक सूक्त/अध्यायाला [ग्रंथ क्रमांक] असे शीर्षक
  * अथर्ववेदाच्या प्रत्येक सूक्तासोबत Whitney (1905) चे श्लोकवार इंग्रजी भाषांतर
  * granth/<ग्रंथ>/ मध्ये भागवार फाइल्स (मोठ्या ग्रंथाचे लहान भाग)
"""
import os, re, sys, glob, subprocess

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from granth_tayar import iast_to_deva  # noqa: E402

CACHE = os.path.join(HERE, ".cache", "dcs")
OUT = os.path.join(HERE, "granth")
REPO = "https://github.com/OliverHellwig/sanskrit"
FILES = "dcs/data/conllu/files/"
AV_TR = "dcs/data/atharvaveda-shaunaka/translations"

# key: (DCS folder, मराठी नाव, output folder)
TEXTS = {
    "atharva":   ("Atharvaveda (Śaunaka)", "अथर्ववेद", "atharvaveda"),
    "susruta":   ("Suśrutasaṃhitā", "सुश्रुत संहिता", "sushruta"),
    "caraka":    ("Carakasaṃhitā", "चरक संहिता", "charaka"),
    "ashtanga":  ("Aṣṭāṅgahṛdayasaṃhitā", "अष्टांगहृदय", "ashtangahridaya"),
    "bhavaprakasha": ("Bhāvaprakāśa", "भावप्रकाश", "bhavaprakasha"),
    "sharngadhara": ("Śārṅgadharasaṃhitā", "शार्ङ्गधर संहिता", "sharngadhara"),
    "bhagavata": ("Bhāgavatapurāṇa", "भागवत पुराण", "bhagavata"),
    "vishnu":    ("Viṣṇupurāṇa", "विष्णु पुराण", "vishnupurana"),
    "shiva":     ("Śivapurāṇa", "शिव पुराण", "shivapurana"),
    "garuda":    ("Garuḍapurāṇa", "गरुड पुराण", "garudapurana"),
    "agni":      ("Agnipurāṇa", "अग्नि पुराण", "agnipurana"),
    "matsya":    ("Matsyapurāṇa", "मत्स्य पुराण", "matsyapurana"),
    "kurma":     ("Kūrmapurāṇa", "कूर्म पुराण", "kurmapurana"),
    "linga":     ("Liṅgapurāṇa", "लिंग पुराण", "lingapurana"),
    "skanda":    ("Skandapurāṇa", "स्कंद पुराण", "skandapurana"),
    "varaha":    ("Varāhapurāṇa", "वराह पुराण", "varahapurana"),
    "kalika":    ("Kālikāpurāṇa", "कालिका पुराण", "kalikapurana"),
    "narasimha": ("Narasiṃhapurāṇa", "नरसिंह पुराण", "narasimhapurana"),
}
DEFAULT = ["atharva", "susruta", "caraka"]
PART_CHARS = 150_000   # एका output फाइलचा अंदाजे आकार


def git(*args, cwd=None):
    subprocess.run(["git", "-c", "gc.auto=0", "-c", "core.quotepath=off", *args],
                   cwd=cwd, check=True, env=dict(os.environ, GIT_LFS_SKIP_SMUDGE="1"))


def fetch(keys):
    if not os.path.isdir(os.path.join(CACHE, ".git")):
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        print("⬇ DCS repo (फक्त रचना) उतरवत आहे…")
        git("clone", "-q", "--depth", "1", "--filter=blob:none", "--sparse", REPO, CACHE)
    paths = [FILES + TEXTS[k][0] for k in keys]
    if "atharva" in keys:
        paths.append(AV_TR)
    print("⬇ ग्रंथ उतरवत आहे: " + ", ".join(TEXTS[k][1] for k in keys))
    git("sparse-checkout", "set", *paths, cwd=CACHE)


def read_conllu(folder):
    """[(chapter, [verse, ...]), ...] — DCS च्या क्रमानुसार"""
    files = [f for f in glob.glob(os.path.join(folder, "*.conllu"))]

    def order(f):
        m = re.search(r"-(\d{4,})-", os.path.basename(f))
        return int(m.group(1)) if m else 0

    chapters = []
    for f in sorted(files, key=order):
        chap, verses = None, []
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("## chapter:"):
                    chap = line.split(":", 1)[1].strip()
                elif line.startswith("# text ="):
                    verses.append(line.split("=", 1)[1].strip())
        if verses:
            chapters.append((chap or os.path.basename(f), verses))
    return chapters


def av_translations():
    path = os.path.join(CACHE, AV_TR, "whitney.txt")
    tr = {}
    if not os.path.exists(path):
        return tr
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^(\d+)\.(\d+)\.(\d+)\s+(.*)", line)
            if m:
                k, s = (int(m.group(1)), int(m.group(2))), m.group(4).strip()
                tr.setdefault(k, []).append(f"{m.group(1)}.{m.group(2)}.{m.group(3)} {s}")
    return tr


def chapter_ref(label):
    """'AVŚ, 1, 1' -> '1.1';  'Su, Sū., 14' -> 'Sū. 14'"""
    parts = [p.strip() for p in label.split(",")]
    rest = parts[1:] if len(parts) > 1 else parts
    if all(p.isdigit() for p in rest):
        return ".".join(rest)
    return " ".join(rest)


def write_parts(folder, blocks):
    os.makedirs(folder, exist_ok=True)
    for old in glob.glob(os.path.join(folder, "*.txt")):
        os.remove(old)
    part, size, n = [], 0, 1
    for b in blocks + [None]:
        if b is None or (size + len(b) > PART_CHARS and part):
            with open(os.path.join(folder, f"part_{n:02d}.txt"), "w", encoding="utf-8") as f:
                f.write("\n\n".join(part) + "\n")
            part, size, n = [], 0, n + 1
        if b is not None:
            part.append(b); size += len(b)
    return n - 1


def build(key, tr=None):
    dcs_name, mr_name, out_name = TEXTS[key]
    chapters = read_conllu(os.path.join(CACHE, FILES + dcs_name))
    if key == "atharva":
        def num(c):
            ref = chapter_ref(c[0])
            try:
                return tuple(int(x) for x in ref.split("."))
            except ValueError:
                return (999,)
        chapters.sort(key=num)
    blocks, nverse = [], 0
    for label, verses in chapters:
        ref = chapter_ref(label)
        head = f"[{mr_name} {ref}]"
        body = "\n".join(iast_to_deva(v) for v in verses)
        nverse += len(verses)
        block = f"{head}\n{body}"
        if key == "atharva" and tr:
            try:
                k = tuple(int(x) for x in ref.split("."))[:2]
            except ValueError:
                k = None
            if k in tr:
                block += "\nभाषांतर (Whitney, 1905):\n" + "\n".join(tr[k])
        blocks.append(block)
    nparts = write_parts(os.path.join(OUT, out_name), blocks)
    print(f"✅ {mr_name}: {len(chapters)} अध्याय/सूक्ते, {nverse} श्लोक → {nparts} फाइल्स")


def main():
    for st in (sys.stdout, sys.stderr):
        try: st.reconfigure(encoding="utf-8")
        except Exception: pass
    args = sys.argv[1:]
    if "--list" in args:
        for k, (d, mr, _) in TEXTS.items():
            print(f"  {k:14s} {mr}  ({d})")
        return
    keys = args or DEFAULT
    bad = [k for k in keys if k not in TEXTS]
    if bad:
        print("माहीत नसलेली नावे: " + ", ".join(bad) + "  ('--list' पाहा)"); sys.exit(1)
    fetch(keys)
    tr = av_translations() if "atharva" in keys else None
    for k in keys:
        build(k, tr)
    print("\nस्रोत: Digital Corpus of Sanskrit (O. Hellwig), CC BY 4.0. "
          "अथर्ववेद भाषांतर: W. D. Whitney (1905), public domain.")


if __name__ == "__main__":
    main()
