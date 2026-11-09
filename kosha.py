"""
संस्कृत-संस्कृत शब्दकोश: वाचस्पत्यम् (1873) आणि शब्दकल्पद्रुम (1886)
Cologne Digital Sanskrit Dictionaries (csl-orig), CC BY-SA 4.0.

पहिल्या वापराला मूळ फाइल्स (~25 MB प्रत्येकी, SLP1 लिपी) उतरवून tools/kosha/kosha.db (sqlite) बनवतो.
शोध शब्दानुसार (embedding नाही) — त्यामुळे ५० MB चे कोश काही मिलिसेकंदांत उघडतात.
"""
import os
import re
import sqlite3
import threading
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
KOSHA_DIR = os.environ.get("GS_KOSHA_DIR", os.path.join(HERE, "tools", "kosha"))
DB = os.path.join(KOSHA_DIR, "kosha.db")
SRC = "https://raw.githubusercontent.com/sanskrit-lexicon/csl-orig/master/v02/{0}/{0}.txt"
DICTS = {"vcp": "वाचस्पत्यम्", "skd": "शब्दकल्पद्रुमः"}
CREDIT = "Cologne Digital Sanskrit Dictionaries, CC BY-SA 4.0"
STATUS = {"state": "", "msg": ""}
_LOCK = threading.Lock()

# ---------------------------------------------------------------- SLP1 -> देवनागरी
_V = {"a": "अ", "A": "आ", "i": "इ", "I": "ई", "u": "उ", "U": "ऊ", "f": "ऋ", "F": "ॠ", "x": "ऌ", "X": "ॡ",
      "e": "ए", "E": "ऐ", "o": "ओ", "O": "औ"}
_M = {"a": "", "A": "ा", "i": "ि", "I": "ी", "u": "ु", "U": "ू", "f": "ृ", "F": "ॄ", "x": "ॢ", "X": "ॣ",
      "e": "े", "E": "ै", "o": "ो", "O": "ौ"}
_C = {"k": "क", "K": "ख", "g": "ग", "G": "घ", "N": "ङ", "c": "च", "C": "छ", "j": "ज", "J": "झ", "Y": "ञ",
      "w": "ट", "W": "ठ", "q": "ड", "Q": "ढ", "R": "ण", "t": "त", "T": "थ", "d": "द", "D": "ध", "n": "न",
      "p": "प", "P": "फ", "b": "ब", "B": "भ", "m": "म", "y": "य", "r": "र", "l": "ल", "v": "व", "S": "श",
      "z": "ष", "s": "स", "h": "ह", "L": "ळ"}
_O = {"M": "ं", "H": "ः", "~": "ँ", "'": "ऽ"}
_DIG = str.maketrans("0123456789", "०१२३४५६७८९")


def slp1_to_deva(s):
    out, i, n = [], 0, len(s)
    while i < n:
        ch = s[i]
        if ch in _C:
            out.append(_C[ch])
            if i + 1 < n and s[i + 1] in _M:
                out.append(_M[s[i + 1]]); i += 2
            else:
                out.append("्"); i += 1
            continue
        if ch in _V:
            out.append(_V[ch])
        elif ch in _O:
            out.append(_O[ch])
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def deva_to_slp1(s):
    rv = {v: k for k, v in _V.items()}
    rm = {v: k for k, v in _M.items() if v}
    rc = {v: k for k, v in _C.items()}
    ro = {v: k for k, v in _O.items()}
    out, i = [], 0
    while i < len(s):
        ch = s[i]
        if ch in rc:
            out.append(rc[ch])
            nx = s[i + 1] if i + 1 < len(s) else ""
            if nx == "्":
                i += 2; continue
            if nx in rm:
                out.append(rm[nx]); i += 2; continue
            out.append("a"); i += 1; continue
        out.append(rv.get(ch) or ro.get(ch) or ch)
        i += 1
    return "".join(out)


def body_to_deva(b):
    """कोशातील SLP1 मजकूर -> देवनागरी (इंग्रजी/खुणा सांभाळून)"""
    b = re.sub(r"<[^>]+>", "", b).replace("¦", " —").replace("--", "—")
    b = re.sub(r"\{[#@%]|[#@%]\}", "", b)
    b = b.replace("..", "॥").replace(" .", " ।")
    out = []
    for tok in re.split(r"(\s+|—|-)", b):
        if re.fullmatch(r"[a-zA-Z~']+[0-9]?", tok) and not re.fullmatch(r"[A-Z][a-z]+", tok):
            m = re.fullmatch(r"([a-zA-Z~']+)0", tok)        # pu0 -> पुं० (संक्षेप)
            out.append(slp1_to_deva(m.group(1)) + "०" if m else slp1_to_deva(tok))
        elif re.fullmatch(r"[“‘\"(]?[a-zA-Z~']+[”’\").,;:!?]*", tok):
            pre = re.match(r"^[“‘\"(]?", tok).group(0)
            post = re.search(r"[”’\").,;:!?]*$", tok).group(0)
            core = tok[len(pre):len(tok) - len(post)]
            out.append(pre + slp1_to_deva(core) + post.replace(".", " ।"))
        else:
            out.append(tok.translate(_DIG) if re.fullmatch(r"\d+", tok) else tok)
    return re.sub(r"[ \t]+", " ", "".join(out)).strip()


# ---------------------------------------------------------------- डेटाबेस
def parse(path):
    """csl-orig .txt -> (key_slp1, body) ; <L>..<k1>KEY<k2>.. नंतर <LEND> पर्यंत"""
    key, buf = None, []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("<L>"):
                m = re.search(r"<k1>([^<]+)", line)
                key, buf = (m.group(1).strip() if m else None), []
            elif line.startswith("<LEND>"):
                if key:
                    body = ""
                    for l in buf:                       # ओळीच्या शेवटी 'niHkzattriyAmaka-' + 'rot' -> एक शब्द
                        l = l.strip()
                        body = body[:-1] + l if body.endswith("-") and not body.endswith("--") else \
                            (body + " " + l if body else l)
                    yield key, body
                key = None
            elif key is not None:
                buf.append(line)


def build(progress=print, sources=None):
    """sources: {dict: path} (चाचणीसाठी) ; नाहीतर उतरवा"""
    os.makedirs(KOSHA_DIR, exist_ok=True)
    tmp = DB + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    con.execute("CREATE TABLE e (d TEXT, k TEXT, deva TEXT, body TEXT)")
    for d, name in DICTS.items():
        path = (sources or {}).get(d) or os.path.join(KOSHA_DIR, d + ".txt")
        if not os.path.exists(path):
            progress(f"📚 {name} उतरवत आहे (~25 MB, एकदाच)…")
            req = urllib.request.Request(SRC.format(d), headers={"User-Agent": "granthsagar"})
            with urllib.request.urlopen(req, timeout=300) as r, open(path + ".part", "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            os.replace(path + ".part", path)
        progress(f"📚 {name}: शब्द-सूची बनवत आहे…")
        rows = ((d, k, slp1_to_deva(k), b) for k, b in parse(path))
        con.executemany("INSERT INTO e VALUES (?,?,?,?)", rows)
    con.execute("CREATE INDEX ik ON e(deva)")
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM e").fetchone()[0]
    con.close()
    os.replace(tmp, DB)
    progress(f"✅ शब्दकोश तयार: {n} शब्द")
    return n


def ready():
    return os.path.exists(DB)


def ensure_background(progress=print):
    """कोश नसेल तर पार्श्वभूमीत उतरवा/बनवा (इंटरनेट लागते)"""
    if ready() or STATUS["state"] == "building":
        return False

    def work():
        if not _LOCK.acquire(blocking=False):
            return
        STATUS.update(state="building")
        try:
            build(lambda m: (STATUS.update(msg=m), progress(m)))
            STATUS.update(state="ready", msg="")
        except Exception as e:
            STATUS.update(state="error", msg=f"शब्दकोश उतरवता आला नाही: {e}")
            progress("⚠️ " + STATUS["msg"])
        finally:
            _LOCK.release()

    threading.Thread(target=work, daemon=True).start()
    return True


# ---------------------------------------------------------------- शोध
_MR_SUFFIX = ("ामध्ये", "मध्ये", "ाचा", "ाची", "ाचे", "ाच्या", "ाला", "ाने", "ात", "चा", "ची", "चे", "च्या", "ला", "ने")
STOP = set("""काय कोणते कोणता कोणती अर्थ शब्द शब्दाचा शब्दाची शब्दाचे सांगा सांग आहे आहेत आणि किंवा मध्ये म्हणजे कसा कशी
कसे कोशात कोशानुसार वाचस्पत्यम् वाचस्पत्य शब्दकल्पद्रुम शब्दकल्पद्रुमः व्युत्पत्ती व्युत्पत्ति धातू धातु रूप रूपे
संस्कृत संस्कृतमध्ये याचा याची याचे त्याचा दोन्ही कोश""".split())


def candidates(word):
    w = word.strip("\"'“”‘’()[]।॥,.?!:;")
    out = [w]
    for suf in _MR_SUFFIX:                       # मराठी विभक्ती: 'धर्माचा' -> 'धर्म'
        if w.endswith(suf) and len(w) - len(suf) >= 2:
            out.append(w[:-len(suf)])
    for x in list(out):                          # संस्कृत प्रथमा: रामः -> राम, फलम् -> फल, ज्ञानं -> ज्ञान
        for end, rep in (("ः", ""), ("म्", ""), ("ं", ""), ("ाः", ""), ("ानि", "")):
            if x.endswith(end) and len(x) - len(end) >= 2:
                out.append(x[:len(x) - len(end)] + rep)
    for x in list(out):                          # शब्दकल्पद्रुमात शीर्षशब्द प्रथमेत: राम -> रामः
        if re.search(r"[\u0915-\u0939]$", x):
            out += [x + "ः", x + "म्"]
    for x in list(out):                          # जुने लेखन: धर्म -> धर्म्म, कार्य -> कार्य्य
        y = re.sub(r"र्([\u0915-\u0939])(?!्)", r"र्\1्\1", x)
        if y != x:
            out.append(y)
    seen, res = set(), []
    for x in out:
        if x and x not in seen:
            seen.add(x); res.append(x)
    return res


def lookup(word, limit_chars=900):
    """[(कोशाचे नाव, शब्द, देवनागरी मजकूर)]"""
    if not ready():
        return []
    con = sqlite3.connect(DB)
    try:
        for c in candidates(word):
            rows = con.execute("SELECT d, deva, body FROM e WHERE deva=? LIMIT 6", (c,)).fetchall()
            if rows:
                out, per = [], {}
                for d, k, b in rows:
                    if per.get(d, 0) >= 2:
                        continue
                    per[d] = per.get(d, 0) + 1
                    t = body_to_deva(b)
                    out.append((DICTS[d], k, t[:limit_chars] + ("…" if len(t) > limit_chars else "")))
                return out
    finally:
        con.close()
    return []


def words_in(question):
    """प्रश्नातील संस्कृत शब्द (अवतरणातील आधी)"""
    quoted = re.findall(r"[\"'“‘]([ऀ-ॿ]+)[\"'”’]", question)
    toks = quoted + [t for t in re.findall(r"[ऀ-ॣॱ-ॿ]+", question) if t not in quoted]
    return [t for t in dict.fromkeys(toks) if len(t) >= 2 and t not in STOP]


def context_for(question, max_words=3):
    """प्रश्नातील शब्दांचे कोशातील अर्थ -> (मजकूर, [स्रोत])"""
    found, srcs = [], []
    for w in words_in(question):
        hits = lookup(w)
        for name, k, t in hits:
            found.append(f"[{name} — {k}]\n{t}")
            srcs.append(f"{name}: {k}")
        if hits and len({s.split(':')[1] for s in srcs}) >= max_words:
            break
    return "\n\n".join(found), srcs
