"""
ग्रंथसागर — तुमच्या संगणकावर offline चालणारा, तुमच्या फाइल्स वाचून उत्तर देणारा मराठी chat.

लागणारे:
  1. Ollama (https://ollama.com) install करा
  2. मॉडेल्स download करा (एकदाच, इंटरनेट लागते):
        ollama pull qwen2.5:7b      <- बोलणारा मॉडेल (8 GB RAM असेल तर qwen2.5:3b)
        ollama pull bge-m3          <- फाइल्स शोधणारा मॉडेल (मराठी समजतो)
  3. "granth" folder मध्ये तुमच्या फाइल्स (.txt .md .pdf .docx .csv) टाका
  4. चालवा:  python granthsagar.py
     browser मध्ये http://127.0.0.1:8765 उघडेल

फक्त Python (3.8+) लागतो. PDF वाचण्यासाठी हवे असल्यास:  pip install pypdf
"""
import json, os, re, sys, subprocess, math, time, hashlib, shutil, threading, webbrowser, zipfile, urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# ===================== सेटिंग्ज (हवे तसे बदला) =====================
# MODE = "granth" -> ग्रंथांचा अर्थ मराठीत समजावणे + आरोग्य सुरक्षितता; "general" -> साधा मदतनीस
MODE = os.environ.get("GS_MODE", "granth")
# अर्थ नीट समजण्यासाठी 7B चांगला (8 GB RAM असेल तर "qwen2.5:3b" ठेवा)
def total_ram_gb():
    """संगणकाची एकूण RAM (GB) — Windows, Linux, Mac"""
    try:
        if os.name == "nt":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS(); m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.ullTotalPhys / 2 ** 30
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30
    except Exception:
        return 8.0


# तुलनेत (2026-11) मराठीसाठी सर्वोत्तम: gemma3:4b (8 GB RAM पुरेशी). 6 GB पेक्षा कमी RAM असेल तर gemma3:1b.
CHAT_MODEL = os.environ.get("GS_CHAT_MODEL") or ("gemma3:4b" if total_ram_gb() >= 6 else "gemma3:1b")
EMBED_MODEL = os.environ.get("GS_EMBED_MODEL", "bge-m3")
OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
if not OLLAMA.startswith("http"):
    OLLAMA = "http://" + OLLAMA
VERSION = "2026-11-09.2"      # सुरू होताना दिसते — कोणता code चालू आहे ते ओळखण्यासाठी
HERE = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.environ.get("GS_DOCS", os.path.join(HERE, "granth"))
INDEX_FILE = os.path.join(HERE, "index.json")
PDF_INBOX = os.path.join(HERE, "pdf_inbox")          # इथे टाकलेल्या PDF आपोआप मजकुरात बदलतात
PDF_OUT = os.path.join(DOCS_DIR, "pdf")             # OCR चा मजकूर इथे जातो
PORT = int(os.environ.get("GS_PORT", "8765"))
CHUNK = 800        # एका तुकड्यात किती अक्षरे
OVERLAP = 150      # तुकड्यांमध्ये किती अक्षरे सामायिक
TOP_K = 5          # प्रत्येक प्रश्नासाठी किती तुकडे AI ला द्यायचे
MIN_SCORE = 0.35   # यापेक्षा कमी जुळणारे तुकडे सोडून द्या
NUM_CTX = 4096     # मॉडेलची context window (जास्त = जास्त RAM)
NUM_PREDICT = 900  # उत्तराची कमाल लांबी (tokens)

SYSTEM_PROMPT = """तू "ग्रंथसागर" आहेस — एक मदतनीस सहाय्यक. वापरकर्ता ज्या भाषेत विचारेल त्याच भाषेत उत्तर दे (सहसा मराठी).
जर खाली "संदर्भ" दिला असेल, तर उत्तर मुख्यतः त्यावरूनच दे आणि कोणत्या फाइलमधून माहिती घेतली ते [फाइलचे नाव] असे सांग.
संदर्भात उत्तर नसेल तर तसे स्पष्ट सांग, आणि मग तुझ्या सामान्य माहितीवरून उत्तर देत असशील तर तसे नमूद कर.
माहिती नसताना अंदाजाने आकडे, तारखा किंवा नियम बनवू नकोस. उत्तरे सोपी आणि मुद्देसूद ठेव."""

GRANTH_PROMPT = """तू "ग्रंथसागर" आहेस — वेद, उपनिषदे, पुराणे, महाभारत-रामायण, आयुर्वेद आणि मंत्र-तंत्र ग्रंथांचा अभ्यास सहाय्यक. नेहमी सोप्या मराठीत उत्तर दे.

उत्तराची रचना:
1. **ग्रंथ काय सांगतो** — संदर्भातील संबंधित श्लोक/वाक्य [ग्रंथ अध्याय.श्लोक] सह थोडक्यात उद्धृत कर.
2. **अर्थ** — शब्दशः अर्थ आणि भावार्थ मराठीत. कठीण संस्कृत शब्द (दोष, धातु, अग्नि, ऋत, यज्ञ इ.) समजावून सांग. कथा असेल तर ती थोडक्यात सांग.
3. **संदर्भ/उपयोग** — प्रश्नानुसार: आयुर्वेदात ग्रंथानुसार आहार, विहार, उपाय; पुराणकथांमध्ये कथेचा संदेश; मंत्रांमध्ये तो कोणत्या परंपरेत, कशासाठी म्हटला जातो.
4. आरोग्याचा प्रश्न असेल तर शेवटी एक ओळ: हे अभ्यासासाठी आहे; उपचारापूर्वी प्रमाणित वैद्य/डॉक्टरांचा सल्ला घ्या.

कडक नियम:
- संदर्भात नसलेला श्लोक, संदर्भ क्रमांक, कथा किंवा औषधाचे प्रमाण कधीही बनवू नकोस. संदर्भात उत्तर नसेल तर "उपलब्ध ग्रंथांमध्ये हे सापडले नाही" असे स्पष्ट सांग, आणि मग सामान्य माहिती देत असशील तर तसे नमूद कर.
- ग्रंथातील दावे "ग्रंथानुसार…" / "परंपरेनुसार…" असे मांड; ते सिद्ध सत्य किंवा खात्रीचा परिणाम म्हणून सांगू नकोस.
- आयुर्वेद: रसौषधी / भस्म (पारा, शिसे, आर्सेनिक, गंधक इ.) यांचे प्रमाण किंवा घरी बनवण्याची पद्धत सांगू नकोस — "वैद्यांच्या देखरेखीखालीच" असे सांग. गर्भवती, लहान मुले, वृद्ध, किंवा BP/साखर/रक्त पातळ करणारी औषधे घेणारे — यांना वैद्य/डॉक्टरांना विचारण्यास ठळकपणे सांग. डॉक्टरांनी दिलेली औषधे बंद करायला कधीही सांगू नकोस.
- मंत्र-तंत्र ग्रंथ: मंत्राचा अर्थ, परंपरा आणि ऐतिहासिक संदर्भ समजाव. पण धोतरा, कुचला, पारा यांसारखे विषारी पदार्थ खाऊ घालण्याची किंवा वापरण्याची कृती, किंवा कोणाला इजा पोहोचवण्याची प्रत्यक्ष पद्धत सांगू नकोस."""

# गंभीर लक्षणे — यांपैकी काही दिसले तर उत्तराआधी लाल सूचना दाखवली जाते
# आपत्कालीन लक्षणे — AI उपाय सांगत नाही, फक्त डॉक्टरांकडे जाण्याची सूचना
EMERGENCY = [
    "छातीत दुख", "छाती दुख", "छातीत कळ", "श्वास घ्यायला", "श्वास लाग", "दम लाग", "धाप", "बेशुद्ध",
    "शुद्ध हरप", "झटके", "फिट येत", "अर्धांग", "लकवा", "तोंड वाकड", "रक्ताची उलटी", "रक्त उलटी",
    "शौचातून रक्त", "काळी शौच", "खूप रक्तस्त्राव", "रक्तस्त्राव थांबत", "विषबाधा", "विष प्य", "विष खा",
    "साप चाव", "सर्पदंश", "विंचू", "भाजल", "अपघात", "डोक्याला मार", "तीव्र पोटदुख", "असह्य",
    "आत्महत्या", "जीव द्याव", "chest pain", "can't breathe", "unconscious", "seizure", "stroke",
    "poison", "snake bite", "suicide",
]
# सावधगिरी — AI उत्तर देतो, पण आधी सूचना
CAUTION = ["गर्भवती", "गरोदर", "बाळ", "नवजात", "लहान मुल", "102", "103", "104", "तीन दिवस ताप",
           "३ दिवस ताप", "pregnan", "infant", "बीपी", "मधुमेह", "साखरेच", "रक्त पातळ"]
EMERGENCY_MSG = ("⚠️ तुम्ही सांगितलेली लक्षणे आपत्कालीन असू शकतात. अशा वेळी ग्रंथातील किंवा घरगुती उपाय करू नका — "
                 "लगेच डॉक्टरांना दाखवा किंवा जवळच्या दवाखान्यात जा. आपत्कालीन स्थितीत 108 वर फोन करा.")
EMERGENCY_ANSWER = ("ग्रंथसागर अशा आपत्कालीन लक्षणांवर उपाय सांगत नाही, कारण इथे एक-एक मिनिट महत्त्वाचा असतो.\n\n"
                    "• रुग्णाला शांत बसवा/झोपवा, एकटे सोडू नका.\n"
                    "• 108 (रुग्णवाहिका) वर फोन करा किंवा लगेच जवळच्या रुग्णालयात न्या.\n"
                    "• डॉक्टरांनी आधी दिलेली औषधे असतील तर ती डॉक्टरांना दाखवा.\n\n"
                    "धोका टळल्यानंतर आयुर्वेदातील आहार-विहाराबद्दल अभ्यास म्हणून विचारू शकता.")
CAUTION_MSG = ("⚠️ गर्भवती स्त्रिया, लहान मुले, जास्त ताप किंवा आधीपासून औषधे (BP/साखर इ.) घेणारे — "
               "यांच्यासाठी कोणताही उपाय करण्यापूर्वी डॉक्टर/वैद्यांचा सल्ला नक्की घ्या.")


def _has(text, words):
    t = text.lower()
    return any(w.lower() in t for w in words)


def red_flag(text):
    return _has(text, EMERGENCY)


RED_FLAG_MSG = EMERGENCY_MSG   # जुन्या नावासाठी


MARATHI_REMINDER = ("\n\n(सूचना: उत्तर फक्त शुद्ध मराठीत लिहा — 'है', 'हैं', 'का', 'की', 'में', 'किया', "
                    "'इस प्रकार' असे हिंदी शब्द वापरू नका. एकच वाक्य पुन्हा लिहू नका. "
                    "इंग्रजी शब्द वापरू नका, कंसातही नाही (Whitney भाषांतर फक्त समजण्यासाठी आहे, उद्धृत करू नका). "
                    "संदर्भ जसाच्या तसा पूर्ण छापू नका — फक्त संबंधित १-२ ओळी उद्धृत करा आणि बाकी मराठीत समजावा. "
                    "संदर्भात नसलेला श्लोक, क्रमांक किंवा ग्रंथ-नाव बनवू नका; शब्दाचा अर्थ खात्री नसेल तर तसे सांगा.)")

SUPPORTED = (".txt", ".md", ".csv", ".docx")   # PDF थेट नाही — आधी pdf_ocr ने मजकूर बनतो


# ===================== Ollama शी बोलणे =====================
def ollama_post(path, payload, stream=False, timeout=600):
    req = urllib.request.Request(
        OLLAMA + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=timeout)
    if stream:
        return resp
    with resp:
        return json.loads(resp.read().decode("utf-8"))


def ollama_ok():
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=3) as r:
            names = [m["name"] for m in json.loads(r.read()).get("models", [])]
        return True, names
    except Exception:
        return False, []


def embed(texts, progress=None):
    out, t0 = [], time.time()
    for i in range(0, len(texts), 32):
        res = ollama_post("/api/embed", {"model": EMBED_MODEL, "input": texts[i:i + 32]})
        out.extend(res["embeddings"])
        if progress and len(texts) > 64:
            done = len(out); rate = done / max(time.time() - t0, 1e-6)
            progress(f"      {done}/{len(texts)} तुकडे, {rate:.1f}/सेकंद, "
                     f"उरलेला वेळ ~{(len(texts) - done) / max(rate, 1e-6) / 60:.0f} मिनिटे")
    return out


# ===================== फाइल्स वाचणे =====================
def read_docx(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    paras = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S):
        p = re.sub(r"<w:tab/>", "\t", p)
        p = re.sub(r"<w:br[^>]*/>", "\n", p)
        t = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", p, flags=re.S))
        paras.append(t)
    text = "\n".join(paras)
    for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'"), ("&amp;", "&")):
        text = text.replace(a, b)
    return text


def read_pdf(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        print(f"  ! {os.path.basename(path)}: PDF वाचण्यासाठी 'pip install pypdf' करा — ही फाइल सोडली")
        return ""
    reader = PdfReader(path)
    return "\n".join((pg.extract_text() or "") for pg in reader.pages)


def read_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        return read_docx(path)
    if ext == ".pdf":
        return read_pdf(path)
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except (UnicodeError, UnicodeDecodeError):
            continue
    return ""


HEAD = re.compile(r"^\[[^\]\n]{2,60}\]", re.M)


def chunk_text(text):
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    chunks, start = [], 0
    while start < len(text):
        end = min(start + CHUNK, len(text))
        if end < len(text):   # शक्यतो परिच्छेद/वाक्याच्या शेवटी तोडा
            cut = max(text.rfind("\n", start + CHUNK // 2, end),
                      text.rfind("।", start + CHUNK // 2, end),
                      text.rfind(". ", start + CHUNK // 2, end))
            if cut > start:
                end = cut + 1
        piece = text[start:end].strip()
        if piece and not piece.startswith("["):
            # तुकड्याला त्याचे शीर्षक (उदा. [अथर्ववेद 1.2]) जोडा, म्हणजे AI ला संदर्भ कळतो
            heads = HEAD.findall(text, 0, start + 1)
            if heads:
                piece = heads[-1] + " (पुढे)\n" + piece
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        nxt = max(end - OVERLAP, start + 1)
        sp = text.find("\n", nxt, end)          # overlap ओळीच्या सुरुवातीपासून
        if sp == -1:
            sp = text.find(" ", nxt, end)
        start = sp + 1 if sp != -1 else nxt
    return chunks


# ===================== Index (फाइल्सचा "नकाशा") =====================
INDEX = {"embed_model": EMBED_MODEL, "files": {}}
VECS = []       # [(file, text, vec, norm)]
LOCK = threading.Lock()


def load_index():
    global INDEX
    if os.path.exists(INDEX_FILE):
        try:
            with open(INDEX_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("embed_model") == EMBED_MODEL:
                INDEX = data
        except Exception:
            pass


try:
    import numpy as np
except ImportError:
    np = None
MAT = None


def rebuild_vecs():
    global VECS, MAT
    v = []
    for name, info in INDEX["files"].items():
        for c in info["chunks"]:
            vec = c["vec"]
            v.append((name, c["text"], vec, math.sqrt(sum(x * x for x in vec)) or 1.0))
    if np is not None and v:
        m = np.array([x[2] for x in v], dtype=np.float32)
        MAT = m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-8)
        v = [(name, text, None, 1.0) for name, text, _, _ in v]   # duplicate lists नकोत
    else:
        MAT = None
    VECS = v


def build_index(log=print):
    os.makedirs(DOCS_DIR, exist_ok=True)
    found = {}
    for root, _, files in os.walk(DOCS_DIR):
        for fn in files:
            if fn.lower().endswith(SUPPORTED) and not fn.startswith("~$"):
                full = os.path.join(root, fn)
                found[os.path.relpath(full, DOCS_DIR)] = full
    def save():
        tmp = INDEX_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(INDEX, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, INDEX_FILE)

    changed = False
    for name in list(INDEX["files"]):
        if name not in found:
            del INDEX["files"][name]; changed = True
            log(f"  - काढली: {name}")
    todo = []
    for name, full in sorted(found.items()):
        with open(full, "rb") as f:
            digest = hashlib.sha1(f.read()).hexdigest()
        old = INDEX["files"].get(name)
        if not (old and old.get("sha1") == digest):
            todo.append((name, full, digest))
    for k, (name, full, digest) in enumerate(todo, 1):
        try:
            chunks = chunk_text(read_file(full))
            log(f"  [{k}/{len(todo)}] {name}: {len(chunks)} तुकडे वाचत आहे…")
            vecs = embed(chunks, progress=log) if chunks else []
        except Exception as e:
            log(f"  ! {name}: वाचता आली नाही ({e})")
            continue
        INDEX["files"][name] = {"sha1": digest, "chunks": [
            {"text": t, "vec": [round(x, 5) for x in v]} for t, v in zip(chunks, vecs)]}
        save()   # प्रत्येक फाइलनंतर save — मध्येच बंद पडले तरी केलेले काम राहते
        rebuild_vecs()   # वाचलेले भाग लगेच शोधासाठी उपलब्ध
        changed = False
    if changed:
        save()
    rebuild_vecs()
    return len(INDEX["files"]), len(VECS)


# ===================== थेट श्लोक-शोध आणि शब्द-जुळणी =====================
DEVA_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
GRANTH_NAMES = [("अथर्व", "अथर्ववेद"), ("सुश्रुत", "सुश्रुत संहिता"), ("चरक", "चरक संहिता")]
STHANA = {"सूत्र": "Sū.", "निदान": "Nid.", "शारीर": "Śār.", "चिकित्सा": "Cik.", "कल्प": "Ka.",
          "उत्तर": "Utt.", "विमान": "Vim.", "इंद्रिय": "Indr.", "इन्द्रिय": "Indr.", "सिद्धि": "Si."}
STHANA_MR = {"Sū.": "सूत्रस्थान", "Nid.": "निदानस्थान", "Śār.": "शारीरस्थान", "Cik.": "चिकित्सास्थान",
             "Ka.": "कल्पस्थान", "Utt.": "उत्तरतंत्र", "Vim.": "विमानस्थान", "Indr.": "इंद्रियस्थान",
             "Si.": "सिद्धिस्थान"}
STOP = set("""काय कोणते कोणता कोणती कोणत्या आहेत आहे आणि किंवा त्यांचा त्यांची त्याचा त्याची अर्थ मराठीत सांगा
सांगावे होण्यासाठी कोणाला म्हणतात किती प्रमाणात घ्यावा घ्यावी माझ्या माझे माझी उपाय सांगितले पहिल्या
कसा कशी कसे काही याचा यांचा मध्ये मधील नुसार साठी करावे करावा द्या आम्हाला मला बरा मंत्र व्यक्ती ग्रंथात
श्लोक सूक्त अध्याय""".split())
MATRA = "\u093e\u093f\u0940\u0941\u0942\u0943\u0944\u0947\u0948\u094b\u094c\u094d\u0902\u0903\u0901"


def mr_refs(text):
    """Sū. 15 -> सूत्रस्थान 15 (AI ला समजावे म्हणून)"""
    for ab, mr in STHANA_MR.items():
        text = text.replace(f" {ab} ", f" {mr} ")
    return text


def direct_lookup(question):
    """'अथर्ववेद 1.1' / 'सुश्रुत सूत्रस्थान १५' -> त्या सूक्त/अध्यायाचे तुकडे"""
    q = question.translate(DEVA_DIGITS)
    name = next((full for key, full in GRANTH_NAMES if key in q), None)
    m = re.search(r"(\d+)\s*[.:]\s*(\d+)|(\d+)", q)
    if not name or not m:
        return []
    if name == "अथर्ववेद":
        if not m.group(1):
            return []
        head = f"[अथर्ववेद {int(m.group(1))}.{int(m.group(2))}"
    else:
        ab = next((v for k, v in STHANA.items() if k in q), None)
        if not ab:
            return []
        num = m.group(1) or m.group(3)
        head = f"[{name} {ab} {int(num)}"
    found = [(name_, text) for name_, text, _, _ in VECS
             if text.startswith(head + "]") or (name == "चरक संहिता" and text.startswith(head + " "))]
    keys = keywords(question)
    if keys:   # लांब अध्याय: प्रश्नातील शब्द असलेले तुकडे आधी
        found.sort(key=lambda x: -sum(any(k in x[1] for k in alts) for alts in keys))
    return [(1.0, n, t) for n, t in found[:3]]


def keywords(question):
    """प्रश्नातील ग्रंथ-शब्द, प्रत्येकी [रूप, पर्यायी मूळ रूप]: तक्मन् -> [तक्मन, तक्म]"""
    keys = []
    for w in re.findall(r"[\u0900-\u097F]{3,}", question):
        if w in STOP or any(k in w for k, _ in GRANTH_NAMES) or w.endswith("नुसार"):
            continue
        base = w.rstrip(MATRA)
        if len(base) < 3:
            continue
        alts = [base]
        if len(base) >= 5 and base[-1] in "नमतसरय":
            alts.append(base[:-1].rstrip(MATRA))
        if alts not in keys:
            keys.append(alts)
    return keys


def search(query):
    if not VECS:
        return []
    direct = direct_lookup(query)
    q = embed([query])[0]
    keys = keywords(query)
    if MAT is not None:
        qv = np.array(q, dtype=np.float32); qv /= max(float(np.linalg.norm(qv)), 1e-8)
        sims = MAT @ qv
        if keys:   # ग्रंथातील नेमका शब्द (उदा. तक्मन्, स्वस्थ) असलेल्या तुकड्यांना थोडे झुकते माप
            boost = np.array([min(0.12, 0.04 * sum(any(k in t for k in alts) for alts in keys))
                              for _, t, _, _ in VECS],
                             dtype=np.float32)
            sims = sims + boost
        top = np.argsort(-sims)[:TOP_K]
        hits = [(float(sims[i]), VECS[i][0], VECS[i][1]) for i in top if sims[i] >= MIN_SCORE]
        if direct:   # नेमका श्लोक/अध्याय सापडला — तोच द्या, इतर सूक्ते गोंधळ घालतात
            return direct
        return hits
    qn = math.sqrt(sum(x * x for x in q)) or 1.0
    scored = []
    for name, text, vec, n in VECS:
        s = sum(a * b for a, b in zip(q, vec)) / (qn * n) + min(0.12, 0.04 * sum(any(k in text for k in alts) for alts in keys))
        scored.append((s, name, text))
    scored.sort(reverse=True)
    return direct or [x for x in scored[:TOP_K] if x[0] >= MIN_SCORE]



# ===================== Folder तपासणी + पार्श्वभूमीत वाचन =====================
INDEX_STATUS = {"running": False, "msg": "", "again": False}
OCR_STATUS = {"running": False, "msg": "", "error": "", "done": []}
OCR_LOCK = threading.Lock()
try:
    import pdf_ocr
except ImportError:
    pdf_ocr = None


def docs_report():
    """ग्रंथसागर कोणता folder वाचतो, त्यात काय आहे, आणि चुकीच्या ठिकाणी काही आहे का"""
    lines = [f"📂 ग्रंथ folder: {DOCS_DIR}"]
    counts = {}
    zips = []
    for root, _, files in os.walk(DOCS_DIR):
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), DOCS_DIR)
            top = rel.split(os.sep)[0] if os.sep in rel else "(मुख्य)"
            if fn.lower().endswith(SUPPORTED):
                counts[top] = counts.get(top, 0) + 1
            elif fn.lower().endswith(".zip"):
                zips.append(rel)
    for top, n in sorted(counts.items()):
        lines.append(f"   • {top}: {n} फाइल्स")
    if not counts:
        lines.append("   (इथे एकही .txt/.docx फाइल नाही)")
    pdfs = pending_pdfs()
    if pdfs:
        ready, why = (pdf_ocr.check_setup() if pdf_ocr else (False, "pdf_ocr.py सापडली नाही"))
        lines.append(f"📄 {len(pdfs)} PDF मजकुरात बदलायच्या आहेत" + ("" if ready else f" — पण: {why}"))
    for z in zips:
        lines.append(f"📦 {z} — ही zip आपोआप extract होऊन आतील PDF मजकुरात बदलतील")
    # नेहमीची चूक: granth च्या बाहेर बनवलेला folder
    for name in os.listdir(HERE):
        p = os.path.join(HERE, name)
        if os.path.isdir(p) and os.path.abspath(p) != os.path.abspath(DOCS_DIR) and \
                name.lower() not in ("scripts", "tests", "tiny_ai", ".git", ".github", ".cache", "__pycache__",
                             "pdf_inbox", "tessdata"):
            n = sum(f.lower().endswith(".txt") for _, _, fs in os.walk(p) for f in fs)
            if n:
                lines.append(f"⚠️ '{name}' folder मध्ये {n} फाइल्स आहेत, पण तो 'granth' च्या बाहेर आहे — "
                             f"तो 'granth' folder च्या आत हलवा")
    return "\n".join(lines)


def start_indexing():
    """पार्श्वभूमीत ग्रंथ वाचणे — chat चालू राहतो"""
    if INDEX_STATUS["running"]:
        INDEX_STATUS["again"] = True     # चालू वाचन संपल्यावर पुन्हा एकदा (नवीन फाइल्ससाठी)
        return False

    def work():
        INDEX_STATUS.update(running=True, msg="फाइल्स तपासत आहे…")
        def log(m):
            print(m, flush=True)
            INDEX_STATUS["msg"] = m.strip()
        try:
            while True:
                INDEX_STATUS["again"] = False
                with LOCK:
                    nf, nc = build_index(log)
                if not INDEX_STATUS["again"]:
                    break
            INDEX_STATUS["msg"] = f"✅ {nf} फाइल्स, {nc} तुकडे तयार."
        except Exception as e:
            INDEX_STATUS["msg"] = f"⚠️ फाइल्स वाचताना अडचण: {e}"
            print(INDEX_STATUS["msg"], flush=True)
        finally:
            INDEX_STATUS["running"] = False

    threading.Thread(target=work, daemon=True).start()
    return True


TEXT_EXT = (".txt", ".md", ".csv", ".docx")


def pending_zips():
    out = []
    for base in (PDF_INBOX, DOCS_DIR):
        if os.path.isdir(base):
            for root, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if d not in ("done", "failed")]
                out += [os.path.join(root, f) for f in sorted(files) if f.lower().endswith(".zip")]
    return out


def unpack_zips(log=print):
    """zip -> pdf_inbox/<नाव>/ (PDF OCR साठी), आतील मजकूर-फाइल्स थेट granth/pdf/<नाव>/. परत: मजकूर-फाइल्स संख्या"""
    texts = 0
    for z in pending_zips():
        stem = os.path.splitext(os.path.basename(z))[0]
        safe = re.sub(r'[\\/:*?"<>|]+', "_", stem).strip(" .") or "zip"
        log(f"📦 {os.path.basename(z)} extract करत आहे…")
        try:
            files = pdf_ocr.extract_zip(z, os.path.join(PDF_INBOX, safe))
        except Exception as e:
            log(f"⚠️ {os.path.basename(z)}: zip उघडता आली नाही ({e})")
            files = None
        if files is not None:
            for f in files:
                if f.lower().endswith(TEXT_EXT):
                    d = os.path.join(PDF_OUT, safe)
                    os.makedirs(d, exist_ok=True)
                    shutil.move(f, os.path.join(d, os.path.basename(f))); texts += 1
            if not any(f.lower().endswith((".pdf",) + TEXT_EXT) for f in files):
                log(f"⚠️ {os.path.basename(z)} मध्ये PDF/मजकूर फाइल नाही")
        done = os.path.join(PDF_INBOX, "done")
        os.makedirs(done, exist_ok=True)
        target = os.path.join(done, os.path.basename(z))
        if os.path.exists(target):
            target = os.path.join(done, f"{int(time.time())}_{os.path.basename(z)}")
        shutil.move(z, target)
    return texts


def pending_pdfs():
    """pdf_inbox आणि granth मध्ये टाकलेल्या, अजून मजकूर न झालेल्या PDF"""
    out = []
    for base in (PDF_INBOX, DOCS_DIR):
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in ("done", "failed")]
            out += [os.path.join(root, f) for f in sorted(files) if f.lower().endswith(".pdf")]
    return out


FAIL_COUNT = {}


def file_is_stable(path, wait=3):
    """copy/download चालू असेल तर आकार बदलतो — तो स्थिर आहे का"""
    try:
        a = os.path.getsize(path); time.sleep(wait); b = os.path.getsize(path)
        return a == b and a > 0
    except OSError:
        return False


def move_aside(pdf, sub, note=None):
    """PDF ला pdf_inbox/<sub>/ मध्ये हलवा (done किंवा failed). कारण .txt मध्ये."""
    dest_dir = os.path.join(PDF_INBOX, sub)
    os.makedirs(dest_dir, exist_ok=True)
    target = os.path.join(dest_dir, os.path.basename(pdf))
    if os.path.exists(target):
        target = os.path.join(dest_dir, f"{int(time.time())}_{os.path.basename(pdf)}")
    shutil.move(pdf, target)
    if os.path.exists(pdf + ".json"):
        os.remove(pdf + ".json")
    if note:
        with open(target + ".कारण.txt", "w", encoding="utf-8") as f:
            f.write(note + "\n")
    parent = os.path.dirname(pdf)                       # zip मधून आलेले रिकामे folders साफ
    while os.path.abspath(parent).startswith(os.path.abspath(PDF_INBOX) + os.sep):
        try:
            os.rmdir(parent)
        except OSError:
            break
        parent = os.path.dirname(parent)
    return target


def start_ocr():
    """पार्श्वभूमीत PDF -> मजकूर, मग आपोआप वाचन"""
    if pdf_ocr is None or OCR_STATUS["running"]:
        return False
    if pending_zips() and unpack_zips(lambda m: (print(m, flush=True), OCR_STATUS.update(msg=m))):
        start_indexing()                  # zip मधील तयार मजकूर लगेच वाचा
    if not pending_pdfs():
        return False

    def work():
        OCR_STATUS.update(running=True, error="")
        def log(m):
            print(m, flush=True)
            OCR_STATUS["msg"] = m.strip()
        tried, failed = set(), []
        try:
            while True:
                todo = [p for p in pending_pdfs() if p not in tried]
                if not todo:
                    break
                pdf = todo[0]
                tried.add(pdf)
                if not file_is_stable(pdf):
                    log(f"⏳ {os.path.basename(pdf)} अजून copy होत आहे — थोड्या वेळाने घेतो")
                    continue
                meta = {}
                if os.path.exists(pdf + ".json"):
                    with open(pdf + ".json", encoding="utf-8") as f:
                        meta = json.load(f)
                name = meta.get("name") or os.path.splitext(os.path.basename(pdf))[0].replace("_", " ")
                try:
                    with OCR_LOCK:
                        pdf_ocr.process_pdf(pdf, name, PDF_OUT, lang=meta.get("lang", "auto"), progress=log)
                except pdf_ocr.OCRSetupError:
                    raise                               # Tesseract/भाषा नाही — फाइल खराब नाही
                except Exception as e:
                    why = str(e)
                    FAIL_COUNT[pdf] = FAIL_COUNT.get(pdf, 0) + 1
                    # खात्रीने खराब (PdfFileError) किंवा ३ वेळा अपयश -> बाजूला; नाहीतर नंतर पुन्हा प्रयत्न
                    if isinstance(e, pdf_ocr.PdfFileError) or FAIL_COUNT[pdf] >= 3:
                        dest = move_aside(pdf, "failed", note=why)
                        failed.append(os.path.basename(pdf))
                        log(f"⚠️ {os.path.basename(pdf)}: {why} → {os.path.relpath(dest, HERE)}")
                    else:
                        log(f"⚠️ {os.path.basename(pdf)}: {why} — थोड्या वेळाने पुन्हा प्रयत्न "
                            f"({FAIL_COUNT[pdf]}/3, झालेली पाने जपली आहेत)")
                    continue
                move_aside(pdf, "done")
                OCR_STATUS["done"].append(name)
                start_indexing()          # तयार मजकूर लगेच वाचायला घ्या
            if failed:
                OCR_STATUS.update(error=f"{len(failed)} PDF उघडल्या नाहीत: {', '.join(failed)} "
                                        f"(pdf_inbox\\failed मध्ये कारणासह ठेवल्या)",
                                  msg=f"⚠️ {len(failed)} PDF अयशस्वी, बाकी तयार")
            else:
                OCR_STATUS["msg"] = "✅ सर्व PDF मजकुरात बदलल्या."
        except Exception as e:
            msg = str(e) if pdf_ocr and isinstance(e, pdf_ocr.OCRSetupError) else f"PDF मध्ये अडचण: {e}"
            OCR_STATUS.update(error=msg, msg="⚠️ " + msg, blocked=msg)   # watcher पुन्हा-पुन्हा प्रयत्न करणार नाही
            print("⚠️ " + msg, flush=True)
        finally:
            OCR_STATUS["running"] = False

    threading.Thread(target=work, daemon=True).start()
    return True


def save_upload(rfile, length, filename, name, lang):
    os.makedirs(PDF_INBOX, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]+', "_", os.path.basename(filename or "granth.pdf"))
    is_zip = safe.lower().endswith(".zip")
    if not is_zip and not safe.lower().endswith(".pdf"):
        safe += ".pdf"
    path = os.path.join(PDF_INBOX, safe)
    if os.path.exists(path):
        path = os.path.join(PDF_INBOX, f"{int(time.time())}_{safe}")
    left = length
    with open(path + ".part", "wb") as f:
        while left > 0:
            chunk = rfile.read(min(1 << 20, left))
            if not chunk:
                break
            f.write(chunk); left -= len(chunk)
    with open(path + ".part", "rb") as f:
        head = f.read(5)
    if (is_zip and head[:2] != b"PK") or (not is_zip and head != b"%PDF-"):
        os.remove(path + ".part")
        raise ValueError("ही फाइल PDF/zip नाही.")
    if is_zip:
        os.replace(path + ".part", path)
        return path
    with open(path + ".json", "w", encoding="utf-8") as f:
        json.dump({"name": name.strip() or os.path.splitext(safe)[0], "lang": lang}, f, ensure_ascii=False)
    os.replace(path + ".part", path)
    return path


def watch_folders():
    """दर 20 सेकंदांनी pdf_inbox/granth तपासा — नवीन PDF/zip आली की आपोआप काम सुरू"""
    while True:
        time.sleep(20)
        try:
            if pdf_ocr and not OCR_STATUS["running"] and not OCR_STATUS.get("blocked") \
                    and (pending_zips() or pending_pdfs()):
                print("📥 नवीन PDF/zip सापडली — काम सुरू", flush=True)
                start_ocr()
        except Exception:
            pass


# ===================== Web chat =====================
PAGE = r"""<!DOCTYPE html><html lang="mr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ग्रंथसागर</title><style>
*{box-sizing:border-box}body{margin:0;font-family:"Nirmala UI","Noto Sans Devanagari","Mangal",system-ui,sans-serif;background:#f4f1ea;color:#222;display:flex;flex-direction:column;height:100vh}
header{background:#1f4e5f;color:#fff;padding:10px 16px;display:flex;align-items:center;gap:12px}
header h1{font-size:20px;margin:0;flex:1}header small{opacity:.8;font-size:13px}
button{font:inherit;border:0;border-radius:8px;padding:8px 14px;cursor:pointer;background:#e07a2f;color:#fff}
button.ghost{background:transparent;border:1px solid #fff8}
#chat{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px;max-width:900px;width:100%;margin:0 auto}
.msg{padding:10px 14px;border-radius:12px;line-height:1.6;white-space:pre-wrap;max-width:85%}
.user{align-self:flex-end;background:#1f4e5f;color:#fff}
.bot{align-self:flex-start;background:#fff;box-shadow:0 1px 3px #0002}
.src{font-size:13px;color:#666;margin-top:6px;border-top:1px dashed #ccc;padding-top:4px}
.alert{align-self:stretch;background:#fde2e1;color:#8a1c1c;border:1px solid #e9a3a0;border-radius:10px;padding:10px 14px;font-weight:600}
#pdfPanel{background:#fff8ec;border-bottom:1px solid #e6d3b3;padding:10px 16px;font-size:14px}
#pdfPanel .row{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}#pdfPanel input,#pdfPanel select{font:inherit;padding:6px;border:1px solid #bbb;border-radius:6px}
#pn{flex:1;min-width:220px}#pmsg{margin-top:6px;color:#555;white-space:pre-wrap}
.sys{align-self:center;font-size:14px;color:#555;background:#e8e2d4;border-radius:8px;padding:6px 12px}
form{display:flex;gap:8px;padding:12px;max-width:900px;width:100%;margin:0 auto}
textarea{flex:1;font:inherit;font-size:16px;padding:10px;border-radius:10px;border:1px solid #bbb;resize:none;height:52px}
</style></head><body>
<header><h1>🪔 ग्रंथसागर <small id="st"></small> <small style="opacity:.5">v__VERSION__</small></h1>
<button class="ghost" onclick="pdfPanel.hidden=!pdfPanel.hidden">📄 PDF जोडा</button>
<button class="ghost" onclick="openInbox()">📂 PDF folder उघडा</button>
<button class="ghost" onclick="reindex()">📂 फाइल्स पुन्हा वाचा</button>
<button class="ghost" onclick="hist=[];chat.innerHTML=''">🧹 नवीन</button></header>
<div id="pdfPanel" hidden>
 <b>📄 PDF ग्रंथ जोडा</b> — scan केलेली किंवा कोणत्याही font मधील PDF, किंवा PDF असलेली zip चालते. मजकूर आपोआप <code>granth/pdf/</code> मध्ये save होईल.
 <div class="row"><input type="file" id="pf" accept=".pdf,.zip,application/pdf,application/zip" multiple onchange="pfName()">
 <input id="pn" placeholder="ग्रंथाचे नाव (उदा. चरक संहिता हिंदी टीका भाग 1)">
 <select id="pl"><option value="auto">भाषा आपोआप ओळखा</option><option value="hin">हिंदी / संस्कृत</option><option value="mar">मराठी</option></select>
 <button onclick="uploadPdfs()">अपलोड</button></div>
 <div id="pmsg"></div>
</div>
<div id="prog" hidden style="max-width:900px;margin:10px auto 0;width:calc(100% - 32px);background:#fff4e5;border:1px solid #e9b872;border-radius:10px;padding:10px 14px;font-size:15px"></div>
<div id="chat"></div>
<form onsubmit="send();return false"><textarea id="q" placeholder="उदा. चरक संहितेनुसार अपचनावर काय उपाय आहेत? / गायत्री मंत्राचा अर्थ काय? (Enter = पाठवा, Shift+Enter = नवी ओळ)"></textarea><button>पाठवा</button></form>
<div style="text-align:center;font-size:12px;color:#777;padding:0 0 8px">हा AI अभ्यासासाठी आहे — चुका होऊ शकतात. उपचारापूर्वी प्रमाणित वैद्य/डॉक्टरांचा सल्ला घ्या.</div>
<script>
const chat=document.getElementById('chat'),q=document.getElementById('q'),st=document.getElementById('st');let hist=[],busy=false;
function add(cls,t){const d=document.createElement('div');d.className='msg '+cls;d.textContent=t;chat.appendChild(d);chat.scrollTop=1e9;return d}
const pdfPanel=document.getElementById('pdfPanel'),pf=document.getElementById('pf'),pn=document.getElementById('pn'),pl=document.getElementById('pl'),pmsg=document.getElementById('pmsg');
function pfName(){if(pf.files.length===1){pn.value=pf.files[0].name.replace(/\.(pdf|zip)$/i,'').replace(/[_-]+/g,' ')}else if(pf.files.length>1){pn.value='';pn.placeholder='अनेक फाइल्स — प्रत्येकीचे नाव फाइल-नावावरून'}}
function upOne(file,name){return new Promise(res=>{const x=new XMLHttpRequest();
 x.open('POST','/upload?file='+encodeURIComponent(file.name)+'&name='+encodeURIComponent(name)+'&lang='+pl.value);
 x.upload.onprogress=e=>{if(e.lengthComputable)pmsg.textContent=`⬆ ${file.name}: ${Math.round(e.loaded*100/e.total)}%`};
 x.onload=()=>{try{res(JSON.parse(x.responseText).msg)}catch(e){res('⚠️ '+x.responseText)}};x.onerror=()=>res('⚠️ अपलोड अयशस्वी');x.send(file)})}
async function uploadPdfs(){if(!pf.files.length){pmsg.textContent='आधी PDF निवडा.';return}
 const out=[];for(const f of pf.files){out.push(await upOne(f,pf.files.length===1?pn.value:''))}
 pmsg.textContent=out.join('\n');pf.value='';status()}
let warned=false,ocrErr='';
async function status(){try{const r=await (await fetch('/status')).json();
 st.textContent=r.ok?`· ${r.model} · ${r.files} फाइल्स · ${r.chunks} तुकडे`:'· Ollama चालू नाही!';
 const pg=document.getElementById('prog');
 if(r.ocr||r.indexing){pg.hidden=false;
  pg.innerHTML=(r.ocr?`📄 <b>PDF मजकूर बनत आहे</b>: ${r.ocr_msg}<br>`:'')+(r.indexing?`📖 <b>ग्रंथ वाचणे</b>: ${r.progress}<br>`:'')+
   '<small>हे पार्श्वभूमीत चालू आहे — तोपर्यंत आधी वाचलेल्या ग्रंथांवर प्रश्न विचारू शकता. ही खिडकी बंद केली तरी काम चालू राहते; काळी खिडकी (command) बंद करू नका.</small>'}
 else pg.hidden=true;
 if(r.warn&&!warned){add('sys',r.warn);warned=true}
 if(r.ocr_error&&r.ocr_error!==ocrErr){ocrErr=r.ocr_error;add('sys','⚠️ '+r.ocr_error);pmsg.textContent='⚠️ '+r.ocr_error}
 if(!pdfPanel.hidden&&r.ocr)pmsg.textContent=r.ocr_msg;
 setTimeout(status,(r.indexing||r.ocr)?4000:30000)}catch(e){st.textContent='· server बंद';setTimeout(status,10000)}}
async function openInbox(){try{const r=await (await fetch('/open-inbox',{method:'POST'})).json();add('sys',r.msg)}catch(e){add('sys','⚠️ '+e)}}
async function reindex(){const s=add('sys','फाइल्स वाचत आहे…');const r=await (await fetch('/reindex',{method:'POST'})).json();s.textContent=r.msg;status()}
q.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}});
async function send(){const t=q.value.trim();if(!t||busy)return;busy=true;q.value='';add('user',t);
 const b=add('bot','…');let ans='',srcs=[];
 try{const r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({q:t,history:hist.slice(-6)})});
  const rd=r.body.getReader(),dec=new TextDecoder();let buf='';
  while(true){const {done,value}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});let i;
   while((i=buf.indexOf('\n'))>=0){const line=buf.slice(0,i);buf=buf.slice(i+1);if(!line)continue;const m=JSON.parse(line);
    if(m.type==='sources')srcs=m.sources;else if(m.type==='token'){ans+=m.t;b.textContent=ans;chat.scrollTop=1e9}
    else if(m.type==='alert'){const a=document.createElement('div');a.className='alert';a.textContent=m.msg;chat.insertBefore(a,b)}
    else if(m.type==='error'){ans+='\n⚠️ '+m.msg;b.textContent=ans}}}
 }catch(e){b.textContent='⚠️ '+e}
 if(srcs.length){const s=document.createElement('div');s.className='src';s.textContent='📄 संदर्भ: '+srcs.join(', ');b.appendChild(s)}
 hist.push({role:'user',content:t},{role:'assistant',content:ans});busy=false;q.focus()}
status();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path == "/":
            body = PAGE.replace("__VERSION__", VERSION).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/status":
            ok, names = ollama_ok()
            warn = ""
            if ok:
                missing = [m for m in (CHAT_MODEL, EMBED_MODEL)
                           if not any(n == m or n == m + ":latest" for n in names)]
                if missing:
                    warn = "हे मॉडेल्स नाहीत, terminal मध्ये चालवा: " + "  ".join(f"ollama pull {m}" for m in missing)
            else:
                warn = "Ollama चालू नाही. Ollama app सुरू करा, मग हे पान refresh करा."
            self._json({"ok": ok, "model": CHAT_MODEL, "files": len(INDEX["files"]), "chunks": len(VECS),
                        "warn": warn, "indexing": INDEX_STATUS["running"], "progress": INDEX_STATUS["msg"],
                        "ocr": OCR_STATUS["running"], "ocr_msg": OCR_STATUS["msg"], "ocr_error": OCR_STATUS["error"],
                        "ocr_ready": pdf_ocr is not None and pdf_ocr.check_setup()[0], "version": VERSION})
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path.startswith("/upload"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            try:
                OCR_STATUS["blocked"] = ""
                path = save_upload(self.rfile, int(self.headers.get("Content-Length", 0)),
                                   qs.get("file", ["granth.pdf"])[0], qs.get("name", [""])[0],
                                   qs.get("lang", ["auto"])[0])
                start_ocr()
                self._json({"ok": True, "msg": f"📥 {os.path.basename(path)} मिळाली — मजकूर बनवणे सुरू (प्रगती वर दिसेल)."})
            except Exception as e:
                self._json({"ok": False, "msg": f"⚠️ {e}"})
            return
        if self.path == "/open-inbox":
            os.makedirs(PDF_INBOX, exist_ok=True)
            try:
                if os.name == "nt":
                    os.startfile(PDF_INBOX)                       # Windows Explorer मध्ये folder उघडा
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", PDF_INBOX])
                else:
                    subprocess.Popen(["xdg-open", PDF_INBOX])
            except Exception:
                pass
            OCR_STATUS["blocked"] = ""
            return self._json({"ok": True, "msg": f"📂 हा folder उघडला आहे: {PDF_INBOX}\n"
                                                   "यात PDF किंवा PDF ची ZIP टाका — 20 सेकंदांत काम आपोआप सुरू होईल."})
        if self.path == "/reindex":
            OCR_STATUS["blocked"] = ""            # बटण दाबले — पुन्हा प्रयत्न
            start_ocr()
            started = start_indexing()
            msg = docs_report() + "\n" + ("⏳ वाचन सुरू झाले — प्रगती वरच्या पट्टीत दिसेल. तोपर्यंत प्रश्न विचारू शकता."
                                          if started else "⏳ वाचन आधीच चालू आहे.")
            self._json({"msg": msg})
        elif self.path == "/ask":
            self.answer(self._body())
        else:
            self.send_error(404)

    def _send(self, obj):
        self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        self.wfile.flush()

    def answer(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            for ev in answer_events((data.get("q") or "").strip(), data.get("history", [])):
                self._send(ev)
        except (BrokenPipeError, ConnectionResetError):
            return


def answer_events(question, history=()):
    """एका प्रश्नाचे उत्तर — sources, alert, token, error, done असे events देतो."""
    history = [m for m in history if m.get("role") in ("user", "assistant")][-6:]
    try:
        hits = search(question)
    except Exception as e:
        hits = []
        yield {"type": "error", "msg": f"फाइल्स शोधता आल्या नाहीत ({e}) — सामान्य उत्तर देत आहे."}
    yield {"type": "sources", "sources": list(dict.fromkeys(name for _, name, _ in hits))}
    if MODE == "granth" and red_flag(question):
        # आपत्कालीन लक्षणे: AI कडून उपाय नाही — ठरलेला सुरक्षित संदेश
        yield {"type": "alert", "msg": EMERGENCY_MSG}
        yield {"type": "token", "t": EMERGENCY_ANSWER}
        yield {"type": "done"}
        return
    if MODE == "granth" and _has(question, CAUTION):
        yield {"type": "alert", "msg": CAUTION_MSG}
    if hits:
        ctx = "\n\n".join(mr_refs(text) for _, _, text in hits)
        user_msg = f"संदर्भ:\n{ctx}\n\n---\nप्रश्न: {question}"
    else:
        user_msg = question
    if MODE == "granth":
        user_msg += MARATHI_REMINDER
    prompt = GRANTH_PROMPT if MODE == "granth" else SYSTEM_PROMPT
    messages = [{"role": "system", "content": prompt}] + list(history) + \
               [{"role": "user", "content": user_msg}]
    payload = {"model": CHAT_MODEL, "messages": messages, "stream": True,
               "options": {"num_ctx": NUM_CTX, "num_predict": NUM_PREDICT, "temperature": 0.2,
                           "top_p": 0.9, "repeat_penalty": 1.05, "repeat_last_n": 64}}
    if CHAT_MODEL.startswith(("qwen3", "deepseek-r1", "gemma4")):
        payload["think"] = False      # "विचार" मोड बंद — थेट उत्तर
    answer = ""
    try:
        resp = ollama_post("/api/chat", payload, stream=True)
        with resp:
            for line in resp:
                if not line.strip():
                    continue
                part = json.loads(line)
                if part.get("error"):
                    yield {"type": "error", "msg": part["error"]}; break
                tok = part.get("message", {}).get("content", "")
                if tok:
                    answer += tok
                    yield {"type": "token", "t": tok}
                    if is_looping(answer):
                        yield {"type": "token", "t": "\n…"}
                        break
                if part.get("done"):
                    break
    except Exception as e:
        yield {"type": "error", "msg": f"Ollama शी संपर्क झाला नाही: {e}"}
    yield {"type": "done"}


def is_looping(text, span=70):
    """उत्तरात तोच मजकूर पुन्हा पुन्हा येऊ लागला की खरे"""
    if len(text) < 3 * span:
        return False
    tail = text[-span:]
    if text[:-span].count(tail) >= 1:
        return True
    lines = [l.strip() for l in text.split("\n") if len(l.strip()) > 25]
    return len(lines) >= 3 and lines[-1] in lines[:-1]


HINDI_MARKS = (" है", " हैं", " में ", "किया", " इस ", " यह ", "जाता है", "होता है", "चाहिए", " था ", " और ")
MARATHI_MARKS = (" आहे", "आहेत", " आणि ", "करावे", "म्हणजे", " होते", " नाही", "असते", " हे ", " या ")


def lang_score(text):
    """हिंदीचे प्रमाण (0 = पूर्ण मराठी, 1 = पूर्ण हिंदी)"""
    h = sum(text.count(m) for m in HINDI_MARKS)
    m = sum(text.count(x) for x in MARATHI_MARKS)
    return h / (h + m) if h + m else 0.0


def ask_cli(questions):
    """python granthsagar.py --ask "प्रश्न" ["प्रश्न 2" ...]  -> उत्तर Markdown मध्ये छापतो"""
    load_index(); rebuild_vecs(); build_index(lambda *_: None)
    rows = []
    for q in questions:
        print(f"\n## ❓ {q}\n")
        t0, ans, srcs = time.time(), "", []
        for ev in answer_events(q):
            if ev["type"] == "token":
                ans += ev["t"]
                print(ev["t"], end="", flush=True)
            elif ev["type"] == "sources" and ev["sources"]:
                srcs = ev["sources"]
                print("📄 संदर्भ: " + ", ".join(ev["sources"]) + "\n")
            elif ev["type"] in ("alert", "error"):
                print(f"> {ev['msg']}\n")
        rows.append((q, time.time() - t0, len(ans), lang_score(ans), ans.endswith("…")))
        print()
    print(f"\n## 📊 सारांश — `{CHAT_MODEL}`\n")
    print("| प्रश्न | वेळ (से.) | अक्षरे | हिंदी % | पुनरावृत्ती थांबवली |\n|---|---|---|---|---|")
    for q, dt, n, h, loop in rows:
        print(f"| {q[:40]}… | {dt:.0f} | {n} | {h * 100:.0f}% | {'हो' if loop else '—'} |")


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")   # Windows console मध्ये मराठी दिसावे
        except Exception:
            pass
    if "--check-setup" in sys.argv:     # start.bat साठी: साधने आहेत का
        ok = True
        try:
            import pypdfium2
            print(f"✅ pypdfium2 (PDF वाचणे) — आवृत्ती {getattr(getattr(pypdfium2, 'version', None), 'PYPDFIUM_INFO', 'ok')}")
        except ImportError:
            print("❌ pypdfium2 नाही — 'python -m pip install pypdfium2 pillow' चालवा"); ok = False
        try:
            import PIL  # noqa: F401
            print("✅ pillow (चित्र)")
        except ImportError:
            print("❌ pillow नाही"); ok = False
        t = pdf_ocr.find_tesseract() if pdf_ocr else None
        if t:
            print(f"✅ Tesseract OCR — {t}")
        else:
            print("❌ Tesseract OCR नाही — PDF साठी लागेल"); ok = False
        try:
            import numpy  # noqa: F401
            print("✅ numpy (जलद शोध)")
        except ImportError:
            print("⚠️ numpy नाही — शोध थोडा हळू होईल")
        sys.exit(0 if ok else 1)
    if "--print-model" in sys.argv:     # start.bat साठी
        print(CHAT_MODEL); return
    if "--index" in sys.argv:           # फक्त ग्रंथ वाचणे (embedding), chat नाही
        load_index()
        nf, nc = build_index(lambda m: print(m, flush=True))
        print(f"✅ {nf} फाइल्स, {nc} तुकडे तयार.")
        return
    if "--ask" in sys.argv:
        ask_cli(sys.argv[sys.argv.index("--ask") + 1:])
        return
    print(f"🪔 ग्रंथसागर सुरू होत आहे… (आवृत्ती {VERSION})")
    print(f"   folder: {HERE}")
    try:                                   # आधी port घ्या — जुना ग्रंथसागर चालू असेल तर इथेच थांबा
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        old_ver = "जुनी"
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/status", timeout=3) as r:
                old_ver = json.loads(r.read()).get("version", "जुनी (आवृत्ती क्रमांक नसलेली)")
        except Exception:
            pass
        print(f"\n❌ दुसरा ग्रंथसागर आधीच चालू आहे (आवृत्ती: {old_ver}).\n"
              f"   आधीची काळी खिडकी बंद करा (किंवा तिथे Ctrl+C), मग ही फाइल पुन्हा चालवा.\n"
              f"   नाहीतर browser मध्ये जुनाच ग्रंथसागर दिसत राहील.")
        sys.exit(1)
    ok, _ = ollama_ok()
    if not ok:
        print(f"⚠️  Ollama ({OLLAMA}) चालू नाही. Ollama सुरू करा — chat पान तरी उघडेल.")
    os.makedirs(PDF_INBOX, exist_ok=True)              # ZIP मधून आल्यावरही folder असावा
    os.makedirs(DOCS_DIR, exist_ok=True)
    load_index()
    rebuild_vecs()
    print(docs_report())
    print(f"📥 PDF/ZIP इथे टाका: {PDF_INBOX}")
    if ok:
        print("📖 नवीन/बदललेले ग्रंथ पार्श्वभूमीत वाचत आहे — chat लगेच वापरता येईल.")
        start_ocr()
        start_indexing()
    if pdf_ocr:
        threading.Thread(target=watch_folders, daemon=True).start()
    url = f"http://127.0.0.1:{PORT}"
    print(f"🌐 {url}  (बंद करण्यासाठी Ctrl+C)")
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nबंद केले. 🙏")


if __name__ == "__main__":
    main()
