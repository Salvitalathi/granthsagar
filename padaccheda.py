"""
पदच्छेद (संधी-विग्रह) + प्रत्येक पदाचा मूळ शब्द आणि व्याकरण.

स्रोत: Digital Corpus of Sanskrit (DCS, Oliver Hellwig), CC BY 4.0 — विद्वानांनी तपासलेले विश्लेषण,
अंदाज नाही. data/padaccheda/*.jsonl.gz (repo मध्ये) -> पहिल्या वापराला tools/padaccheda.db (sqlite) बनतो.

श्लोक DCS मधील ग्रंथांतील असेल (महाभारत/गीता, रामायण, पुराणे, चरक-सुश्रुत, अष्टाध्यायी, काशिका…) तर
OCR च्या लहान चुका असूनही तो ओळखून पदच्छेद देतो. DCS मध्ये नसलेला श्लोक -> काहीही अंदाजाने देत नाही.
"""
import difflib
import glob
import gzip
import json
import os
import re
import sqlite3
import threading
import zlib

from kosha import deva_to_slp1

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("GS_PADA_DATA", os.path.join(HERE, "data", "padaccheda"))
DB = os.environ.get("GS_PADA_DB", os.path.join(HERE, "tools", "padaccheda.db"))
CREDIT = "Digital Corpus of Sanskrit (O. Hellwig), CC BY 4.0"
STATUS = {"state": "", "msg": ""}
_LOCK = threading.Lock()

try:
    from granth_tayar import iast_to_deva
except Exception:                                    # चाचणीसाठी
    iast_to_deva = None

# ---------------------------------------------------------------- व्याकरण -> मराठी
CASE = {"Nom": "प्रथमा", "Acc": "द्वितीया", "Ins": "तृतीया", "Dat": "चतुर्थी", "Abl": "पंचमी", "Gen": "षष्ठी",
        "Loc": "सप्तमी", "Voc": "संबोधन", "Cpd": "समासातील पूर्वपद"}
NUM = {"Sing": "एकवचन", "Dual": "द्विवचन", "Plur": "बहुवचन"}
GEN = {"Masc": "पुं.", "Fem": "स्त्री.", "Neut": "नपुं."}
TENSE = {"Pres": "वर्तमान (लट्)", "Past": "भूत", "Fut": "भविष्य (लृट्)", "Impf": "अनद्यतन भूत (लङ्)",
         "Perf": "परोक्ष भूत (लिट्)", "Aor": "अद्यतन भूत (लुङ्)"}
MOOD = {"Imp": "आज्ञार्थ (लोट्)", "Opt": "विध्यर्थ (विधिलिङ्)", "Cnd": "संकेतार्थ (लृङ्)", "Sub": "लेट्",
        "Ind": "", "Ben": "आशीर्लिङ्"}
PERSON = {"1": "उत्तम पुरुष", "2": "मध्यम पुरुष", "3": "प्रथम पुरुष"}
VFORM = {"Part": "कृदन्त (विशेषण)", "Conv": "अव्यय कृदन्त (क्त्वा/ल्यप्)", "Inf": "तुमुन्", "Gdv": "कृत्य (तव्य/अनीय/य)"}
UPOS = {"NOUN": "नाम", "ADJ": "विशेषण", "PRON": "सर्वनाम", "VERB": "क्रियापद", "ADV": "क्रियाविशेषण",
        "CCONJ": "अव्यय (समुच्चय)", "SCONJ": "अव्यय", "PART": "अव्यय", "ADP": "अव्यय", "NUM": "संख्या",
        "DET": "सर्वनाम", "PROPN": "विशेषनाम", "INTJ": "उद्गार", "AUX": "क्रियापद"}


def grammar_mr(upos, feats):
    f = dict(x.split("=", 1) for x in feats.split("|") if "=" in x) if feats else {}
    parts = []
    if f.get("VerbForm") in VFORM:
        parts.append(VFORM[f["VerbForm"]])
    elif upos in UPOS:
        parts.append(UPOS[upos])
    if "Tense" in f or "Mood" in f:
        t = MOOD.get(f.get("Mood", ""), "") or TENSE.get(f.get("Tense", ""), "")
        if t:
            parts.append(t)
    if f.get("Person") in PERSON:
        parts.append(PERSON[f["Person"]])
    if f.get("Gender") in GEN:
        parts.append(GEN[f["Gender"]])
    if f.get("Case") in CASE:
        parts.append(CASE[f["Case"]])
    if f.get("Number") in NUM:
        parts.append(NUM[f["Number"]])
    if f.get("Voice") == "Pass":
        parts.append("कर्मणि")
    return ", ".join(parts)


# ---------------------------------------------------------------- तुलनेसाठी सामान्यीकरण
_KEEP = re.compile(r"[^अ-हा-्ंःॠ-ॣ]")


def norm(deva):
    """फक्त अक्षरे; अनुस्वार/वर्गीय अनुनासिक एकसारखे (सङ्गो = संगो), शेवटचा म् = ं"""
    s = deva.replace("ॐ", "")
    s = re.sub(r"(?<=[\u0915-\u0939\u093E-\u094C\u0902])\s?:", "ः", s)     # OCR: नित्य: -> नित्यः
    s = re.sub(r"[ङञणनम]्(?=[क-ह])", "ं", s)
    s = re.sub(r"म्(?=\s|$|[।॥])", "ं", s)
    s = _KEEP.sub("", s)
    # 'कर्मण्य् एवा' (DCS, शब्द वेगळे) = 'कर्मण्येवा' (छापील): व्यंजन+् + स्वर -> मात्रा
    s = re.sub("्([अआइईउऊऋएऐओऔ])", lambda m: _MATRA[m.group(1)], s)
    return s


_MATRA = {"अ": "", "आ": "ा", "इ": "ि", "ई": "ी", "उ": "ु", "ऊ": "ू", "ऋ": "ृ", "ए": "े", "ऐ": "ै", "ओ": "ो", "औ": "ौ"}


def key(deva):
    """तुलनेची किल्ली — लहान (ASCII SLP1), त्यामुळे डेटाबेस लहान"""
    return deva_to_slp1(norm(deva))


def to_deva(iast):
    return iast_to_deva(iast) if iast_to_deva else iast


# ---------------------------------------------------------------- डेटाबेस
def build(progress=print, data_dir=None):
    files = sorted(glob.glob(os.path.join(data_dir or DATA, "*.jsonl.gz")))
    if not files:
        raise RuntimeError("data/padaccheda मध्ये माहिती नाही")
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    tmp = DB + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    con.execute("CREATE TABLE s (id INTEGER PRIMARY KEY, g TEXT, r TEXT, t TEXT, k TEXT, w BLOB)")
    try:
        con.execute("CREATE VIRTUAL TABLE f USING fts5(k, content='', tokenize='trigram')")
        fts = True
    except sqlite3.OperationalError:
        fts = False
    n = 0
    for path in files:
        progress(f"📝 पदच्छेद-माहिती: {os.path.basename(path)}")
        rows = []
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                s = json.loads(line)
                k = key(to_deva(s["t"]))
                if len(k) < 6:
                    continue
                n += 1
                w = zlib.compress(json.dumps(s["w"], ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)
                rows.append((n, s.get("g", ""), s.get("r") or "", s["t"], k, w))
                if len(rows) >= 5000:
                    con.executemany("INSERT INTO s VALUES (?,?,?,?,?,?)", rows)
                    if fts:
                        con.executemany("INSERT INTO f(rowid, k) VALUES (?,?)", [(r[0], r[4]) for r in rows])
                    rows = []
        if rows:
            con.executemany("INSERT INTO s VALUES (?,?,?,?,?,?)", rows)
            if fts:
                con.executemany("INSERT INTO f(rowid, k) VALUES (?,?)", [(r[0], r[4]) for r in rows])
    con.execute("CREATE INDEX ik ON s(k)")
    con.commit()
    con.close()
    os.replace(tmp, DB)
    progress(f"✅ पदच्छेद-माहिती तयार: {n} श्लोकार्ध")
    return n


def ready():
    return os.path.exists(DB)


def available():
    return bool(glob.glob(os.path.join(DATA, "*.jsonl.gz")))


def ensure_background(progress=print):
    if ready() or not available() or STATUS["state"] == "building":
        return False

    def work():
        if not _LOCK.acquire(blocking=False):
            return
        STATUS.update(state="building")
        try:
            build(lambda m: (STATUS.update(msg=m), progress(m)))
            STATUS.update(state="ready", msg="")
        except Exception as e:
            STATUS.update(state="error", msg=f"पदच्छेद-माहिती बनवता आली नाही: {e}")
            progress("⚠️ " + STATUS["msg"])
        finally:
            _LOCK.release()

    threading.Thread(target=work, daemon=True).start()
    return True


# ---------------------------------------------------------------- शोध
def _candidates(con, key, limit=40):
    rows = con.execute("SELECT id, g, r, t, k, w FROM s WHERE k=?", (key,)).fetchall()
    if rows:
        return rows
    try:
        grams = [key[i:i + 6] for i in range(0, max(1, len(key) - 5), 4)][:12]
        q = " OR ".join('"' + g.replace('"', "") + '"' for g in grams if len(g) >= 3)
        ids = [r[0] for r in con.execute("SELECT rowid FROM f WHERE f MATCH ? ORDER BY rank LIMIT 300", (q,))]
    except sqlite3.OperationalError:
        return []
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    return con.execute(f"SELECT id, g, r, t, k, w FROM s WHERE id IN ({marks})", ids).fetchall()


def analyze_line(line, con=None):
    """एक श्लोक-ओळ -> [{g, r, t, words:[(पद, मूळ, व्याकरण)]}] (ओळ झाकणारे DCS श्लोकार्ध, क्रमाने)"""
    qk = key(line)
    if len(qk) < 8 or not ready():
        return []
    own = con is None
    con = con or sqlite3.connect(DB)
    try:
        cands = _candidates(con, qk)
        scored = []
        for row in cands:
            ck = row[4]
            sm = difflib.SequenceMatcher(None, ck, qk, autojunk=False)
            cover = sum(b.size for b in sm.get_matching_blocks()) / max(len(ck), 1)
            matched = cover * len(ck)
            if cover >= 0.8 and len(ck) <= len(qk) * 1.25 and len(ck) >= min(12, len(qk) * 0.8):
                pos = qk.find(ck[:6]) if ck[:6] in qk else sm.find_longest_match(0, len(ck), 0, len(qk)).b
                scored.append((matched, pos, row))
        scored.sort(key=lambda x: (-x[0], x[1]))
        chosen, used = [], []
        for cover, pos, row in scored:              # ओळ झाकणारे, एकमेकांवर न येणारे
            span = (pos, pos + len(row[4]))
            if any(not (span[1] <= a or span[0] >= b) for a, b in used):
                continue
            used.append(span)
            chosen.append((pos, row))
            if sum(b - a for a, b in used) >= len(qk) * 0.9:
                break
        if sum(b - a for a, b in used) < len(qk) * 0.6:     # ओळीचा मोठा भाग DCS मध्ये नाही — अंदाज नको
            return []
        out = []
        for pos, (_id, g, r, t, k, w) in sorted(chosen):
            ws = json.loads(zlib.decompress(w).decode("utf-8"))
            words = [(to_deva(f), to_deva(lem), grammar_mr(up, ft)) for f, lem, up, ft in ws]
            out.append({"g": g, "r": r, "t": to_deva(t), "words": words})
        return out
    finally:
        if own:
            con.close()


_HI = set("है हैं के में की और को से का यह वह नहीं था थे हो कर लिए आहे आहेत आणि नाही म्हणजे काय कसा सांगा अर्थ".split())


def sanskrit_lines(text, limit=4):
    """मजकुरातील संस्कृत श्लोक-ओळी (हिंदी/मराठी गद्य वगळून)"""
    out = []
    for ln in re.split(r"\n|(?<=[।॥])\s*", text):       # श्लोकार्धानुसार
        ln = re.sub(r"^\[[^\]]*\]\s*", "", ln.strip())
        ln = re.sub(r"[।॥\s०-९\d]+$", "", ln).strip()
        words = re.findall(r"[ऀ-ॣॱ-ॿ]+", ln)
        if len(words) < 3 or any(w in _HI for w in words):
            continue
        out.append(ln)
        if len(out) >= limit:
            break
    return out


def analyze_text(text, limit=4):
    if not ready():
        return []
    con = sqlite3.connect(DB)
    try:
        res = []
        for ln in sanskrit_lines(text, limit):
            a = analyze_line(ln, con)
            if a:
                res.append({"line": ln, "parts": a})
        return res
    finally:
        con.close()


def context_text(results):
    """AI साठी: 'पद (मूळ शब्द; व्याकरण)'"""
    out = []
    for r in results:
        for p in r["parts"]:
            ws = "; ".join(f"{f} ({lem}{', ' + gr if gr else ''})" for f, lem, gr in p["words"])
            out.append(f"{p['t']}\n  पदच्छेद: {ws}")
    return "\n".join(out)
