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
import agents
import kosha
import padaccheda

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
VERSION = "2026-11-10.1"      # सुरू होताना दिसते — कोणता code चालू आहे ते ओळखण्यासाठी
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
# कुंडली-फलादेश: ८ तुकडे + कुंडली + दशा/गोचर — 4096 मध्ये मावत नाही (Ollama सुरुवात कापतो = system prompt जातो)
KUNDALI_CTX = int(os.environ.get("GS_KUNDALI_CTX") or (8192 if total_ram_gb() >= 8 else 6144))
KUNDALI_PREDICT = 1400

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
- संदर्भात संस्कृत श्लोक आणि त्याखाली हिंदी/मराठी अनुवाद असेल तर: श्लोक मूळ संस्कृतमध्येच उद्धृत कर (बदलू नकोस), आणि अर्थ सांगताना तो अनुवाद आधार म्हणून वापर — स्वतःचा वेगळा अर्थ बनवू नकोस.
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
            para = text.rfind("\n\n", start + CHUNK // 3, end)     # श्लोक + अनुवाद एकत्र राहावा
            cut = para if para > start else max(text.rfind("\n", start + CHUNK // 2, end),
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
# प्रश्नातील सर्वसाधारण शब्द — हे संदर्भात नसले तरी 'सापडले नाही' अशी सूचना नको
GENERIC_TERMS = set("""योग फल फळ लग्न लग्नाचे राशी राशीचे ग्रह भाव स्थान कुंडली कुंडलीचे जन्म नक्षत्र दशा
म्हणजे समजाव समजावा उदाहरणासह सूत्र शब्द शब्दाचा पदच्छेद ग्रंथानुसार मुख्य आयुर्वेद उपचार रोग""".split())
MATRA = "\u093e\u093f\u0940\u0941\u0942\u0943\u0944\u0947\u0948\u094b\u094c\u094d\u0902\u0903\u0901"
GENERIC_BASE = {g.rstrip(MATRA) for g in GENERIC_TERMS}


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


_MASKS = {}


def agent_mask(agent):
    """या agent च्या फाइल्समधील तुकडे (numpy bool). None = सर्व."""
    if agent is None or not agent["folders"]:
        return None
    key = (agent["id"], len(VECS), id(VECS))
    if key not in _MASKS:
        _MASKS.clear()
        _MASKS[key] = np.array([agents.owns(agent, n) for n, _, _, _ in VECS], dtype=bool) \
            if np is not None else [agents.owns(agent, n) for n, _, _, _ in VECS]
    return _MASKS[key]


SUTRA_WORDS = ("सूत्र", "अष्टाध्यायी", "अष्टाध्याय", "काशिका", "महाभाष्य", "पाणिनि", "पाणिनी", "कौमुदी", "वार्तिक")
SUTRA_ORDER = ("[अष्टाध्यायी", "[काशिका", "[लघुसिद्धान्तकौमुदी", "[महाभाष्य")


def sutra_lookup(question, agent=None):
    """'अष्टाध्यायी 6.1.77' / 'सूत्र १-१-१' -> सूत्र, काशिका, कौमुदी, महाभाष्य"""
    q = question.translate(DEVA_DIGITS)
    if not ((agent and agent["id"] == "vyakarana") or any(w in question for w in SUTRA_WORDS)):
        return []
    m = re.search(r"(?<![\d.])([1-8])\s*[.\-,।]\s*([1-4])\s*[.\-,।]\s*(\d{1,3})(?![\d])", q)
    if not m:
        return []
    ref = f"{m.group(1)}.{m.group(2)}.{int(m.group(3))}"
    rx = re.compile(r"^\[[^\]\n]*? (?:= )?" + re.escape(ref) + r"\]", re.M)
    found = []
    for name, text, _, _ in VECS:
        hit = rx.search(text)
        if hit and (agent is None or agents.owns(agent, name)):
            rank = next((i for i, p in enumerate(SUTRA_ORDER) if hit.group(0).startswith(p)), 9)
            nxt = re.search(r"^\[", text[hit.end():], re.M)            # फक्त याच सूत्राचा भाग
            seg = text[hit.start():hit.end() + nxt.start() if nxt else len(text)].strip()
            if rank == 0:                                               # अष्टाध्यायी: आधीचे-नंतरचे एक सूत्र (अनुवृत्ती)
                lines = text.splitlines()
                i = next((k for k, l in enumerate(lines) if l.startswith(hit.group(0))), 0)
                seg = "\n".join(lines[max(0, i - 1):i + 2])
            found.append((rank, name, seg))
    found.sort(key=lambda x: x[0])
    out, seen = [], set()
    for rank, name, text in found:              # प्रत्येक ग्रंथातून पहिला तुकडा
        if rank not in seen:
            seen.add(rank); out.append((1.0, name, text))
    return out[:4]


def search(query, agent=None, qvec=None, top_k=TOP_K):
    if not VECS:
        return []
    direct = direct_lookup(query) or sutra_lookup(query, agent)
    if agent is not None:
        direct = [h for h in direct if agents.owns(agent, h[1])]
    q = qvec if qvec is not None else embed([query])[0]
    keys = keywords(query)
    mask = agent_mask(agent)
    if MAT is not None:
        qv = np.array(q, dtype=np.float32); qv /= max(float(np.linalg.norm(qv)), 1e-8)
        sims = MAT @ qv
        if keys:   # ग्रंथातील नेमका शब्द (उदा. तक्मन्, स्वस्थ) असलेल्या तुकड्यांना थोडे झुकते माप
            boost = np.array([min(0.12, 0.04 * sum(any(k in t for k in alts) for alts in keys))
                              for _, t, _, _ in VECS],
                             dtype=np.float32)
            sims = sims + boost
        if mask is not None:
            sims = np.where(mask, sims, -1.0)
        top = np.argsort(-sims)[:top_k]
        hits = [(float(sims[i]), VECS[i][0], VECS[i][1]) for i in top if sims[i] >= MIN_SCORE]
        if direct:   # नेमका श्लोक/अध्याय सापडला — तोच द्या, इतर सूक्ते गोंधळ घालतात
            return direct
        return hits
    qn = math.sqrt(sum(x * x for x in q)) or 1.0
    scored = []
    for i, (name, text, vec, n) in enumerate(VECS):
        if mask is not None and not mask[i]:
            continue
        s = sum(a * b for a, b in zip(q, vec)) / (qn * n) + min(0.12, 0.04 * sum(any(k in text for k in alts) for alts in keys))
        scored.append((s, name, text))
    scored.sort(reverse=True)
    return direct or [x for x in scored[:top_k] if x[0] >= MIN_SCORE]


def search_multi(queries, agent=None, total=TOP_K + 1):
    """अनेक प्रश्न (उदा. कुंडलीतील ग्रह-स्थिती) — एकाच embedding call मध्ये, प्रत्येकाचे सर्वोत्तम तुकडे"""
    if not VECS or not queries:
        return []
    vecs = embed(queries)
    seen, out = set(), []
    per = [search(q, agent, qvec=v, top_k=2) for q, v in zip(queries, vecs)]
    for rank in range(2):                       # आधी प्रत्येक प्रश्नाचा पहिला तुकडा, मग दुसरा
        for hits in per:
            if rank < len(hits) and hits[rank][2] not in seen and len(out) < total:
                seen.add(hits[rank][2]); out.append(hits[rank])
    return out


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


# ===================== चित्रांचे वर्णन (gemma3 ची दृष्टी) =====================
# OCR ने ग्रंथातील चित्रे (कुंडली, नक्षत्र-चक्र, तक्ते) granth/pdf/<ग्रंथ>/images/ मध्ये जशीच्या तशी ठेवली.
# इथे दृष्टी असलेले मॉडेल (gemma3:4b/12b) प्रत्येक चित्राचे मराठी वर्णन लिहिते -> 'चित्र_वर्णन_XX.txt'
# (शोधता येते). gemma3:1b ला दृष्टी नाही — तेव्हा चित्रे फक्त उत्तरासोबत दाखवली जातात.
VISION_MODEL = os.environ.get("GS_VISION_MODEL", "") or ("" if CHAT_MODEL.endswith(":1b") else CHAT_MODEL)
FIG_STATUS = {"running": False, "msg": ""}
ACTIVE_ASKS = [0]                 # प्रश्नाचे उत्तर चालू असताना चित्र-वर्णन थांबवा (CPU मोकळा)
_VISION = {}
_FIG_SIG = [None]
FIG_RX = re.compile(r"🖼 चित्र (\d+): (images/p(\d{5})_\d+\.png)(?: — चित्रातील अक्षरे: (.*))?")
DESC_PER_FILE = 20
FIG_PROMPT = ("हे चित्र '{book}' या ग्रंथाच्या पान {page} वरील आहे{labels}. चित्रात नेमके काय आहे ते सोप्या मराठीत लिही:\n"
              "- कुंडली/चक्र असेल तर: कोणत्या पद्धतीची (उत्तर/दक्षिण भारतीय, नक्षत्र-चक्र), आणि प्रत्येक घरात/भागात "
              "दिसणारे अंक व अक्षरे (उदा. सू, चं, मं) घराप्रमाणे;\n- तक्ता असेल तर: ओळीनुसार मजकूर;\n"
              "- आकृती/फोटो असेल तर: त्याचे थोडक्यात वर्णन.\n"
              "जे स्पष्ट वाचता येत नाही ते अंदाजाने लिहू नकोस — 'अस्पष्ट' असे लिही. 120 शब्दांपेक्षा जास्त नको.")


def vision_ok():
    if not VISION_MODEL:
        return False
    if VISION_MODEL not in _VISION:
        try:
            info = ollama_post("/api/show", {"model": VISION_MODEL}, timeout=30)
        except Exception:
            return False                                   # Ollama बंद — नंतर पुन्हा तपासू
        _VISION[VISION_MODEL] = "vision" in (info.get("capabilities") or [])
    return _VISION[VISION_MODEL]


def figure_books():
    """चित्रे असलेले ग्रंथ-folders: [(folder, ग्रंथाचे नाव, [(पान, क्र., png-rel, labels)])]"""
    out = []
    for root, dirs, files in os.walk(DOCS_DIR):
        if "images" not in dirs:
            continue
        figs = []
        for fn in sorted(f for f in files if f.startswith("part_") and f.endswith(".txt")):
            try:
                text = open(os.path.join(root, fn), encoding="utf-8").read()
            except OSError:
                continue
            book = None
            for line in text.splitlines():
                h = re.match(r"^\[(.+?) पृ\. (\d+)\]", line)
                if h:
                    book = h.group(1)
                m = FIG_RX.search(line)
                if m:
                    figs.append((int(m.group(3)), int(m.group(1)), m.group(2), m.group(4) or "", book))
        if figs:
            out.append((root, figs))
    return out


def write_fig_descs(root, figs):
    """*.png.desc -> चित्र_वर्णन_XX.txt (२० चित्रे एका फाइलमध्ये; फक्त शेवटची फाइल बदलते).
    चित्रे काढली गेली असतील (उदा. scripts/fix_figures.py) तर उरलेल्या जुन्या वर्णन-फाइल्स काढते. परत: काही बदलले का"""
    rows, changed = [], False
    for page, k, rel, labels, book in figs:
        d = os.path.join(root, rel + ".desc")
        if os.path.exists(d):
            rows.append(f"[{book or os.path.basename(root)} पृ. {page} — चित्र {k}]\n"
                        f"🖼 {rel}\n(चित्राचे AI-वर्णन — चूक असू शकते, मूळ चित्र पाहा)\n"
                        + open(d, encoding="utf-8").read().strip())
    for i in range(0, len(rows), DESC_PER_FILE):
        path = os.path.join(root, f"चित्र_वर्णन_{i // DESC_PER_FILE + 1:02d}.txt")
        body = "\n\n".join(rows[i:i + DESC_PER_FILE]) + "\n"
        old = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if old != body:
            with open(path + ".tmp", "w", encoding="utf-8") as f:
                f.write(body)
            os.replace(path + ".tmp", path)
            changed = True
    n = -(-len(rows) // DESC_PER_FILE)
    for f in os.listdir(root):
        m = re.match(r"चित्र_वर्णन_(\d+)\.txt$", f)
        if m and int(m.group(1)) > n:
            os.remove(os.path.join(root, f)); changed = True
    return changed


def describe_figure(png, book, page, labels):
    import base64
    with open(png, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    lab = f" (OCR ला दिसलेली अक्षरे: {labels})" if labels else ""
    res = ollama_post("/api/chat", {
        "model": VISION_MODEL, "stream": False,
        "messages": [{"role": "user", "content": FIG_PROMPT.format(book=book, page=page, labels=lab), "images": [b64]}],
        "options": {"temperature": 0.1, "num_predict": 350, "num_ctx": 4096}}, timeout=900)
    return (res.get("message") or {}).get("content", "").strip()


def start_figures():
    """पार्श्वभूमीत: वर्णन नसलेल्या चित्रांचे वर्णन (एकावेळी एक; उत्तर देताना थांबते)"""
    if FIG_STATUS["running"] or OCR_STATUS["running"] or not vision_ok():
        return False
    sig = []                                        # काही बदलले नसेल तर part फाइल्स पुन्हा वाचू नका
    for root, dirs, files in os.walk(DOCS_DIR):
        if os.path.basename(root) == "images":
            sig.append((root, len(files), os.path.getmtime(root)))
    if sig == _FIG_SIG[0]:
        return False
    books = figure_books()
    todo = [(root, f) for root, figs in books for f in figs if not os.path.exists(os.path.join(root, f[2] + ".desc"))]
    if not todo:
        if any([write_fig_descs(r, figs) for r, figs in books]):    # काढलेल्या चित्रांची वर्णने साफ
            start_indexing()
        _FIG_SIG[0] = sig
        return False

    def work():
        FIG_STATUS.update(running=True)
        try:
            for i, (root, (page, k, rel, labels, book)) in enumerate(todo, 1):
                while ACTIVE_ASKS[0] > 0 or OCR_STATUS["running"]:
                    time.sleep(2)
                FIG_STATUS["msg"] = f"🖼 चित्रांचे वर्णन: {i}/{len(todo)} ({book or ''} पृ. {page})"
                png = os.path.join(root, rel)
                try:
                    desc = describe_figure(png, book or os.path.basename(root), page, labels)
                except Exception as e:
                    print(f"⚠️ चित्र {rel}: वर्णन जमले नाही ({e})", flush=True)
                    continue
                if desc:
                    with open(png + ".desc", "w", encoding="utf-8") as f:
                        f.write(desc)
                if i % 5 == 0 or i == len(todo):
                    for r, figs in books:
                        write_fig_descs(r, figs)
                    start_indexing()
            FIG_STATUS["msg"] = f"✅ {len(todo)} चित्रांचे वर्णन तयार"
        finally:
            FIG_STATUS["running"] = False

    threading.Thread(target=work, daemon=True).start()
    return True


def answer_images(hits, limit=4):
    """उत्तरासाठी वापरलेल्या तुकड्यांतील चित्रे -> granth/ पासूनचे relative paths"""
    out = []
    for _, name, text in hits:
        base = os.path.dirname(agents.norm(name))
        for rel in re.findall(r"images/p\d{5}_\d+\.png", text):
            p = f"{base}/{rel}" if base else rel
            if p not in out and os.path.exists(os.path.join(DOCS_DIR, p)):
                out.append(p)
    return out[:limit]


ZIP_LOCK = threading.Lock()


def _zip_marker(z):
    """extract झालेल्या zip ची खूण (Windows ने zip हलवू दिली नाही तरी ती पुन्हा extract होऊ नये)"""
    st = os.stat(z)
    return os.path.join(PDF_INBOX, "done", f".{os.path.basename(z)}.{st.st_size}.extracted")


def subject_of(path):
    """pdf_inbox/ज्योतिष/… -> 'ज्योतिष' (agents.json मधील inbox). नाहीतर ''"""
    try:
        rel = os.path.relpath(path, PDF_INBOX)
    except ValueError:
        return ""
    first = rel.replace("\\", "/").split("/")[0]
    return first if first in agents.inbox_subjects() and first != rel else ""


def subject_out(subject):
    return os.path.join(PDF_OUT, subject) if subject else PDF_OUT


def pending_zips():
    out = []
    for base in (PDF_INBOX, DOCS_DIR):
        if os.path.isdir(base):
            for root, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if d not in ("done", "failed")]
                for f in sorted(files):
                    p = os.path.join(root, f)
                    if f.lower().endswith(".zip"):
                        try:
                            if os.path.exists(_zip_marker(p)):
                                continue
                        except OSError:
                            continue
                        out.append(p)
    return out


def unpack_zips(log=print):
    """zip -> pdf_inbox/<नाव>/ (PDF OCR साठी), आतील मजकूर-फाइल्स थेट granth/pdf/<नाव>/. परत: मजकूर-फाइल्स संख्या"""
    if not ZIP_LOCK.acquire(blocking=False):        # दुसरीकडे आधीच extract चालू आहे
        return 0
    try:
        texts = 0
        for z in pending_zips():
            if not file_is_stable(z):
                log(f"⏳ {os.path.basename(z)} अजून copy होत आहे — थोड्या वेळाने घेतो")
                continue
            stem = os.path.splitext(os.path.basename(z))[0]
            safe = re.sub(r'[\\/:*?"<>|]+', "_", stem).strip(" .") or "zip"
            subj = subject_of(z)                      # pdf_inbox/ज्योतिष/x.zip -> pdf_inbox/ज्योतिष/x/
            log(f"📦 {os.path.basename(z)} extract करत आहे…")
            try:
                files = pdf_ocr.extract_zip(z, os.path.join(PDF_INBOX, subj, safe))
            except Exception as e:
                log(f"⚠️ {os.path.basename(z)}: zip उघडता आली नाही ({e})")
                files = None
            if files is not None:
                for f in files:
                    if f.lower().endswith(TEXT_EXT):
                        d = os.path.join(subject_out(subj), safe)
                        os.makedirs(d, exist_ok=True)
                        shutil.move(f, os.path.join(d, os.path.basename(f))); texts += 1
                n_pdf = sum(f.lower().endswith(".pdf") for f in files)
                log(f"📦 {os.path.basename(z)}: {n_pdf} PDF मिळाल्या" if n_pdf
                    else f"⚠️ {os.path.basename(z)} मध्ये PDF नाही")
            done = os.path.join(PDF_INBOX, "done")
            os.makedirs(done, exist_ok=True)
            marker = _zip_marker(z)
            open(marker, "w").close()                  # आधी खूण — मग हलवा
            target = os.path.join(done, os.path.basename(z))
            if os.path.exists(target):
                target = os.path.join(done, f"{int(time.time())}_{os.path.basename(z)}")
            try:
                shutil.move(z, target)
            except OSError as e:                       # Windows: फाइल वापरात (antivirus/explorer)
                log(f"ℹ️ {os.path.basename(z)} done मध्ये हलवता आली नाही ({e.__class__.__name__}) — "
                    f"ती तिथेच राहील, पण पुन्हा extract होणार नाही. नंतर हाताने काढू शकता.")
        return texts
    finally:
        ZIP_LOCK.release()


def recover_empty_done():
    """जुन्या आवृत्तीत '0 पाने' होऊन done मध्ये गेलेल्या PDF पुन्हा रांगेत आणा"""
    done = os.path.join(PDF_INBOX, "done")
    if not (pdf_ocr and os.path.isdir(done)):
        return 0
    back = 0
    for f in os.listdir(done):
        if not f.lower().endswith(".pdf"):
            continue
        name = re.sub(r"^\d{9,}_", "", os.path.splitext(f)[0]).replace("_", " ")
        out = os.path.join(PDF_OUT, pdf_ocr.slugify(name))
        if os.path.isdir(out) and not any(x.startswith("part_") for x in os.listdir(out)):
            try:
                shutil.move(os.path.join(done, f), os.path.join(PDF_INBOX, f))
                back += 1
            except OSError:
                pass
    if back:
        print(f"♻️ {back} PDF चा OCR आधी रिकामा झाला होता — त्या पुन्हा रांगेत घेतल्या", flush=True)
    return back


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
    keep = {os.path.abspath(os.path.join(PDF_INBOX, x)) for x in agents.inbox_subjects()}
    while os.path.abspath(parent).startswith(os.path.abspath(PDF_INBOX) + os.sep) \
            and os.path.abspath(parent) not in keep:
        try:
            os.rmdir(parent)
        except OSError:
            break
        parent = os.path.dirname(parent)
    return target


def safe_start_ocr():
    try:
        return start_ocr()
    except Exception as e:
        print(f"⚠️ PDF काम सुरू करताना अडचण: {e}", flush=True)
        return False


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
                        subj = meta.get("subject") if meta.get("subject") in agents.inbox_subjects() \
                            else subject_of(pdf)
                        pdf_ocr.process_pdf(pdf, name, subject_out(subj), lang=meta.get("lang", "auto"),
                                            progress=log)
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
            threading.Timer(5, start_figures).start()      # OCR संपल्यावर चित्रांचे वर्णन
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


def save_upload(rfile, length, filename, name, lang, subject=""):
    base = os.path.join(PDF_INBOX, subject) if subject in agents.inbox_subjects() else PDF_INBOX
    os.makedirs(base, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]+', "_", os.path.basename(filename or "granth.pdf"))
    is_zip = safe.lower().endswith(".zip")
    if not is_zip and not safe.lower().endswith(".pdf"):
        safe += ".pdf"
    path = os.path.join(base, safe)
    if os.path.exists(path):
        path = os.path.join(base, f"{int(time.time())}_{safe}")
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
                safe_start_ocr()
            elif not OCR_STATUS["running"] and not FIG_STATUS["running"]:
                start_figures()
        except Exception:
            pass


# ===================== कुंडली =====================
def kundali_from(b):
    """browser मधून आलेली जन्म-माहिती -> कुंडली (गणित नेहमी इथेच, browser वर विश्वास नाही)"""
    import jyotish
    date, tm = str(b.get("date", "")), str(b.get("time", ""))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) or not re.fullmatch(r"\d{1,2}:\d{2}", tm):
        raise ValueError("जन्म तारीख (YYYY-MM-DD) आणि वेळ (HH:MM) द्या")
    if b.get("place") in jyotish.CITIES:
        lat, lon = jyotish.CITIES[b["place"]]
    else:
        lat, lon = float(b.get("lat")), float(b.get("lon"))
    if not (-66 <= lat <= 66 and -180 <= lon <= 180):
        raise ValueError("अक्षांश -66 ते 66 आणि रेखांश -180 ते 180 असावा")
    tz = float(b.get("tz", 5.5))
    y = int(date[:4])
    if not 1900 <= y <= 2050:
        raise ValueError("वर्ष 1900 ते 2050 दरम्यान असावे (DE421 ची मर्यादा)")
    return jyotish.compute_chart(date, tm, lat, lon, tz=tz, name=str(b.get("name", ""))[:60])


# ===================== Web chat =====================
PAGE = r"""<!DOCTYPE html><html lang="mr" data-theme="pothi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ग्रंथसागर</title><style>
:root{--body:"Nirmala UI","Noto Sans Devanagari","Mangal",system-ui,sans-serif;--head:"Aparajita","Kokila","Noto Serif Devanagari","Nirmala UI",serif;
 --noise:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 .42  0 0 0 0 .3  0 0 0 0 .14  0 0 0 .10 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>")}
[data-theme=pothi]{--bg:#e9dcbd;--bg2:#d9c597;--leaf:#f7eed8;--leaf2:#efe1bf;--ink:#2b1d0e;--muted:#6f5a3c;--edge:#d2bb8c;--accent:#8b1e1e;--accent-ink:#fff6e6;--gold:#a8741a;
 --side:#2f1d12;--side2:#3d271a;--side-ink:#efe2c8;--side-muted:#b59d78;--user:#7a2a1c;--user-ink:#fff4e2;--shadow:#5a3b1466;--line:#8b1e1e;--chip:#fbf4e3}
[data-theme=ratra]{--bg:#13110d;--bg2:#1b1812;--leaf:#1e1a14;--leaf2:#25201a;--ink:#ece3cf;--muted:#a8997c;--edge:#3a3226;--accent:#e0a34a;--accent-ink:#1a140c;--gold:#e0a34a;
 --side:#0d0b08;--side2:#1a1610;--side-ink:#e9dfc9;--side-muted:#8f826a;--user:#3a2f22;--user-ink:#f3e9d4;--shadow:#000a;--line:#c98a3a;--chip:#221d16}
[data-theme=sadha]{--bg:#f6f6f3;--bg2:#efefea;--leaf:#ffffff;--leaf2:#ffffff;--ink:#1d1d1b;--muted:#6b6b66;--edge:#e3e3dd;--accent:#1f4e5f;--accent-ink:#fff;--gold:#1f4e5f;
 --side:#efeee9;--side2:#e4e3dc;--side-ink:#24241f;--side-muted:#77776f;--user:#1f4e5f;--user-ink:#fff;--shadow:#0002;--line:transparent;--chip:#fff}
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;font-family:var(--body);color:var(--ink);background:radial-gradient(ellipse at 50% 30%,var(--bg) 0%,var(--bg2) 100%) fixed;display:flex;overflow:hidden}
[data-theme=pothi] body,[data-theme=pothi] .leaf{background-image:var(--noise),radial-gradient(ellipse at 50% 30%,var(--bg) 0%,var(--bg2) 100%)}
button{font:inherit;color:inherit;cursor:pointer;border:0;background:none}
input,select,textarea{font:inherit;color:var(--ink)}
/* ---------- बाजूपट्टी ---------- */
#side{width:272px;flex:none;background:var(--side);color:var(--side-ink);display:flex;flex-direction:column;transition:transform .25s}
.brand{display:flex;align-items:center;gap:10px;padding:18px 16px 12px}
.brand b{font-family:var(--head);font-size:30px;font-weight:700;letter-spacing:.5px;line-height:1}
.brand small{color:var(--side-muted);font-size:11px}
.newbtn{margin:4px 12px 10px;padding:10px 12px;border:1px solid var(--side-muted);border-radius:12px;display:flex;gap:8px;align-items:center;color:var(--side-ink)}
.newbtn:hover{background:var(--side2)}
.sect{padding:10px 16px 4px;font-size:12px;color:var(--side-muted);letter-spacing:.3px}
#convs{flex:1;overflow-y:auto;padding:0 8px}
.cv{display:flex;align-items:center;gap:6px;padding:8px 10px;border-radius:10px;cursor:pointer;font-size:14px;color:var(--side-ink)}
.cv:hover,.cv.on{background:var(--side2)}.cv span{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cv .x{opacity:0;color:var(--side-muted);padding:0 4px}.cv:hover .x{opacity:1}
.tools{border-top:1px solid #ffffff1a;padding:8px}
.tool{display:flex;width:100%;gap:10px;padding:8px 10px;border-radius:10px;font-size:14px;text-align:left;color:var(--side-ink)}
.tool:hover{background:var(--side2)}
.themes{display:flex;gap:6px;padding:8px 10px}
.themes button{flex:1;padding:6px 0;border-radius:8px;font-size:12px;border:1px solid #ffffff22;color:var(--side-ink)}
.themes button.on{border-color:var(--side-ink);background:var(--side2)}
#st{padding:4px 12px 12px;font-size:11.5px;color:var(--side-muted);display:flex;gap:6px;align-items:center}
.dot{width:8px;height:8px;border-radius:50%;background:#999;flex:none}.dot.ok{background:#4caf50}.dot.bad{background:#e53935}
/* ---------- मुख्य ---------- */
main{flex:1;display:flex;flex-direction:column;min-width:0;position:relative}
#top{display:flex;align-items:center;gap:8px;padding:10px 16px;border-bottom:1px solid var(--edge)}
#menu{display:none;font-size:22px;padding:2px 8px}
#agentBar{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;flex:1}
#agentBar button{white-space:nowrap;padding:7px 14px;border-radius:999px;border:1px solid var(--edge);background:var(--chip);font-size:14px}
#agentBar button.on{background:var(--accent);color:var(--accent-ink);border-color:var(--accent)}
#kBar{border-bottom:1px solid var(--edge);background:color-mix(in srgb,var(--leaf) 70%,transparent)}
#kBar summary{cursor:pointer;padding:8px 18px;font-size:14px;list-style:none;color:var(--muted)}#kBar summary::-webkit-details-marker{display:none}
#kBar summary b{color:var(--ink)}
.krow{display:flex;flex-wrap:wrap;gap:8px;padding:2px 18px 12px;align-items:center}
.krow input,.krow select,dialog input,dialog select{padding:7px 9px;border:1px solid var(--edge);border-radius:8px;background:var(--leaf)}
.btn{padding:8px 16px;border-radius:10px;background:var(--accent);color:var(--accent-ink)}
.btn.ghost{background:transparent;color:var(--ink);border:1px solid var(--edge)}
#kmsg{padding:0 18px 10px;font-size:13px;color:var(--muted)}
#prog{margin:10px auto 0;width:min(780px,calc(100% - 32px));background:var(--leaf);border:1px solid var(--gold);border-radius:12px;padding:10px 14px;font-size:14px}
#prog small{color:var(--muted)}
#chat{flex:1;overflow-y:auto;padding:22px 16px 30px;scroll-behavior:smooth}
.col{max-width:780px;margin:0 auto;display:flex;flex-direction:column;gap:18px}
/* रिकामे पान */
.empty{text-align:center;padding:9vh 10px 0}
.empty .diya{font-size:46px}
.empty h2{font-family:var(--head);font-size:44px;font-weight:700;margin:6px 0 2px;color:var(--accent)}
.empty p{color:var(--muted);margin:0 0 22px}
.ex{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;text-align:left}
.ex button{padding:12px 14px;border:1px solid var(--edge);border-radius:12px;background:var(--leaf);font-size:14px;line-height:1.5}
.ex button:hover{border-color:var(--accent)}
/* प्रश्न */
.turn.user{align-self:flex-end;max-width:82%;display:flex;flex-direction:column;align-items:flex-end}
.bubble{background:var(--user);color:var(--user-ink);padding:10px 16px;border-radius:18px 18px 4px 18px;white-space:pre-wrap;line-height:1.6}
.acts{display:flex;gap:2px;opacity:0;transition:opacity .15s;margin-top:4px}
.turn:hover .acts,.leaf:hover .acts,.acts.show{opacity:1}
.acts button{padding:4px 8px;border-radius:8px;font-size:13px;color:var(--muted)}.acts button:hover{background:var(--leaf2);color:var(--ink)}
.edit{width:100%;min-width:min(560px,80vw);display:flex;flex-direction:column;gap:8px;background:var(--leaf);border:1px solid var(--accent);border-radius:14px;padding:10px}
.edit textarea{border:0;outline:0;resize:vertical;min-height:70px;background:transparent;font-size:16px;line-height:1.6}
.edit div{display:flex;gap:8px;justify-content:flex-end}
/* पोथीचे पान (उत्तर) */
.leaf{position:relative;background:var(--leaf);border:1px solid var(--edge);border-radius:6px;padding:30px 46px 16px;box-shadow:0 1px 0 var(--edge),0 14px 34px -16px var(--shadow);line-height:1.75;font-size:16.5px}
[data-theme=pothi] .leaf{background-image:var(--noise),linear-gradient(180deg,var(--leaf) 0%,var(--leaf2) 100%)}
.leaf::before,.leaf::after{content:"";position:absolute;top:16px;bottom:16px;width:5px;border-left:2px solid var(--line);border-right:1px solid var(--line);opacity:.5}
.leaf::before{left:18px}.leaf::after{right:18px}
.hole{position:absolute;top:9px;left:50%;width:9px;height:9px;margin-left:-4.5px;border-radius:50%;background:var(--bg2);box-shadow:inset 0 1px 2px #0005}
[data-theme=sadha] .leaf{border-radius:14px;padding:22px 26px 12px}[data-theme=sadha] .hole{display:none}
.pno{text-align:center;font-family:var(--head);font-size:19px;color:var(--accent);margin:-12px 0 6px;letter-spacing:1px}
[data-theme=sadha] .pno{font-family:var(--body);font-size:12px;color:var(--muted);text-align:left;margin:-8px 0 4px}
.leaf.turn{animation:turn .85s cubic-bezier(.2,.75,.25,1) both;transform-origin:50% 0}
@keyframes turn{0%{transform:perspective(1600px) rotateX(-92deg);opacity:0;filter:brightness(.75)}45%{opacity:1}100%{transform:perspective(1600px) rotateX(0);filter:none}}
#chat.flip .col{animation:flip .6s ease both;transform-origin:0 50%}
@keyframes flip{0%{transform:perspective(1800px) rotateY(-70deg);opacity:0}100%{transform:none;opacity:1}}
@media (prefers-reduced-motion:reduce){.leaf.turn,#chat.flip .col{animation:none}}
.md p{margin:.45em 0}.md h4{font-family:var(--head);font-size:23px;margin:.8em 0 .2em;color:var(--accent)}
[data-theme=sadha] .md h4{font-family:var(--body);font-size:17px}
.md ul,.md ol{margin:.4em 0;padding-left:1.5em}.md li{margin:.2em 0}
.md blockquote{margin:.6em 0;padding:4px 14px;border-left:3px solid var(--gold);color:var(--muted);background:color-mix(in srgb,var(--gold) 7%,transparent);border-radius:0 8px 8px 0}
.md strong{color:var(--accent)}[data-theme=ratra] .md strong{color:var(--gold)}
.md code{background:var(--leaf2);padding:1px 5px;border-radius:5px;font-size:.92em}
.md hr{border:0;border-top:1px dashed var(--edge);margin:12px 0}
.ref{font-size:.82em;padding:1px 7px;border-radius:999px;border:1px solid var(--edge);color:var(--muted);white-space:nowrap}
.cursor::after{content:"▍";color:var(--accent);animation:blink 1s steps(2) infinite}
@keyframes blink{50%{opacity:0}}
.think{color:var(--muted);font-style:italic}.think i{animation:blink 1.2s infinite}
.src{font-size:13px;color:var(--muted);margin-top:10px;border-top:1px dashed var(--edge);padding-top:6px}
.stopped{font-size:12.5px;color:var(--muted);margin-top:6px}
.alert{background:#fde2e1;color:#8a1c1c;border:1px solid #e9a3a0;border-radius:10px;padding:10px 14px;font-weight:600;margin-bottom:10px;line-height:1.5}
.err{color:#b3261e}
.kchart{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-start;margin:4px 0 8px}.kchart svg{max-width:100%;height:auto;border-radius:6px}
.kchart .kt{white-space:pre-wrap;font-size:14px;line-height:1.6;flex:1;min-width:240px}
.figs{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.figs img{max-height:180px;max-width:240px;border:1px solid var(--edge);border-radius:6px;background:#fff}
.pada{margin-top:10px;font-size:14px}.pada summary{cursor:pointer;color:var(--accent);font-weight:600}.pada .pl{margin:6px 0 2px;font-weight:600}
.pada table{border-collapse:collapse}.pada td{border:1px solid var(--edge);padding:2px 8px}.pada td:nth-child(3){color:var(--muted)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.chip{background:var(--chip);border:1px solid var(--edge);border-radius:999px;padding:4px 12px;font-size:13px;cursor:pointer}
.chip:hover{border-color:var(--accent)}
/* लिहिण्याची जागा */
#composer{padding:6px 16px 10px}
.box{max-width:780px;margin:0 auto;background:var(--leaf);border:1px solid var(--edge);border-radius:22px;box-shadow:0 8px 28px -14px var(--shadow);padding:10px 10px 8px 16px;display:flex;flex-direction:column;gap:4px}
.box:focus-within{border-color:var(--accent)}
#q{border:0;outline:0;background:transparent;resize:none;font-size:16px;line-height:1.55;max-height:220px;min-height:28px;padding:4px 0}
.boxrow{display:flex;align-items:center;gap:8px}
#agentTag{font-size:12.5px;color:var(--muted);flex:1}
#go{width:38px;height:38px;border-radius:50%;background:var(--accent);color:var(--accent-ink);display:grid;place-items:center;font-size:18px;flex:none}
#go:disabled{opacity:.35;cursor:default}#go.stop{background:var(--ink);color:var(--leaf)}
.note{text-align:center;font-size:11.5px;color:var(--muted);padding:6px 0 0}
/* dialog, toast */
dialog{border:1px solid var(--edge);border-radius:16px;background:var(--leaf);color:var(--ink);padding:20px 22px;width:min(560px,92vw);box-shadow:0 24px 60px -20px #000a}
dialog::backdrop{background:#0006}
dialog h3{font-family:var(--head);font-size:26px;margin:0 0 6px;color:var(--accent)}
dialog .row{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}dialog .row>*{flex:1 1 200px}
#pmsg{margin-top:10px;font-size:13.5px;color:var(--muted);white-space:pre-wrap}
#toasts{position:fixed;top:14px;right:14px;display:flex;flex-direction:column;gap:8px;z-index:20;max-width:min(420px,90vw)}
.toast{background:var(--ink);color:var(--leaf);padding:10px 14px;border-radius:12px;font-size:14px;white-space:pre-wrap;box-shadow:0 10px 30px -10px #000a;animation:tin .25s ease}
@keyframes tin{from{transform:translateY(-8px);opacity:0}}
@media (max-width:860px){#side{position:fixed;inset:0 auto 0 0;z-index:15;transform:translateX(-100%)}#side.open{transform:none;box-shadow:0 0 0 100vw #0006}
 #menu{display:block}.leaf{padding:28px 30px 14px}.leaf::before{left:10px}.leaf::after{right:10px}}
</style></head><body>
<aside id="side">
 <div class="brand"><span style="font-size:26px">🪔</span><div><b>ग्रंथसागर</b><br><small>v__VERSION__ · ग्रंथांचा अभ्यास-सहाय्यक</small></div></div>
 <button class="newbtn" onclick="newConv()">✚ &nbsp;नवीन संवाद</button>
 <div class="sect">मागील संवाद</div>
 <div id="convs"></div>
 <div class="tools">
  <button class="tool" onclick="pdfDlg.showModal()">📄 PDF ग्रंथ जोडा</button>
  <button class="tool" onclick="openInbox()">📂 PDF folder उघडा</button>
  <button class="tool" onclick="reindex()">🔄 फाइल्स पुन्हा वाचा</button>
  <div class="themes"><button data-t="pothi">📜 पोथी</button><button data-t="ratra">🌙 रात्र</button><button data-t="sadha">☀️ साधा</button></div>
 </div>
 <div id="st"><span class="dot"></span><span>जोडत आहे…</span></div>
</aside>
<main>
 <div id="top"><button id="menu" onclick="side.classList.toggle('open')">☰</button><div id="agentBar"></div></div>
 <details id="kBar" hidden><summary>🪐 <b>जन्मकुंडली</b> <span id="kSum">— जन्म तारीख, वेळ, ठिकाण द्या; मग प्रश्नांची उत्तरे कुंडलीनुसार</span></summary>
  <div class="krow"><input id="kName" placeholder="नाव (ऐच्छिक)" style="width:140px">
   <input id="kDate" type="date" min="1900-01-01" max="2050-12-31"> <input id="kTime" type="time">
   <select id="kPlace" onchange="kLL.hidden=this.value!=='__other'"></select>
   <span id="kLL" hidden><input id="kLat" placeholder="अक्षांश उदा. 18.52" style="width:130px"> <input id="kLon" placeholder="रेखांश उदा. 73.86" style="width:130px"></span>
   <label title="भारत = 5.5" style="font-size:13px;color:var(--muted)">UTC+<input id="kTz" value="5.5" style="width:52px"></label>
   <button class="btn" onclick="makeKundali()">कुंडली बनवा</button>
   <button id="kClear" class="btn ghost" hidden onclick="clearKundali()">✖ काढा</button></div>
  <div id="kmsg">गणित तुमच्या संगणकावरच होते (लाहिरी अयनांश, राशी-भाव पद्धत).</div>
 </details>
 <div id="prog" hidden></div>
 <div id="chat"><div class="col" id="col"></div></div>
 <div id="composer"><div class="box">
  <textarea id="q" rows="1" placeholder="ग्रंथांना प्रश्न विचारा…  (Enter = पाठवा, Shift+Enter = नवी ओळ)"></textarea>
  <div class="boxrow"><span id="agentTag"></span><button id="go" title="पाठवा" onclick="goClick()">➤</button></div>
 </div><div class="note">हा AI अभ्यासासाठी आहे — चुका होऊ शकतात. उपचार किंवा मोठ्या निर्णयांपूर्वी तज्ज्ञांचा सल्ला घ्या.</div></div>
</main>
<dialog id="pdfDlg"><h3>📄 PDF ग्रंथ जोडा</h3>
 <div style="font-size:14px;color:var(--muted)">scan केलेली किंवा कोणत्याही font मधील PDF, किंवा PDF असलेली zip चालते. मजकूर आपोआप <code>granth/pdf/</code> मध्ये save होईल.</div>
 <div class="row"><input type="file" id="pf" accept=".pdf,.zip,application/pdf,application/zip" multiple onchange="pfName()"></div>
 <div class="row"><input id="pn" placeholder="ग्रंथाचे नाव (उदा. चरक संहिता हिंदी टीका भाग 1)"></div>
 <div class="row"><select id="ps" title="विषय — त्या agent ला हा ग्रंथ मिळेल"><option value="">विषय: सामान्य</option></select>
  <select id="pl"><option value="auto">भाषा आपोआप ओळखा</option><option value="hin">हिंदी / संस्कृत</option><option value="mar">मराठी</option></select></div>
 <div class="row" style="justify-content:flex-end"><button class="btn ghost" style="flex:none" onclick="pdfDlg.close()">बंद</button><button class="btn" style="flex:none" onclick="uploadPdfs()">अपलोड</button></div>
 <div id="pmsg"></div></dialog>
<div id="toasts"></div>
<script>
const $=id=>document.getElementById(id),chat=$('chat'),col=$('col'),q=$('q'),go=$('go'),side=$('side'),pdfDlg=$('pdfDlg');
const DIG='०१२३४५६७८९',dn=n=>String(n).replace(/\d/g,d=>DIG[d]);
function ls(k,v){try{if(v===undefined)return localStorage.getItem(k);localStorage.setItem(k,v)}catch(e){return null}}
function el(tag,cls,txt){const e=document.createElement(tag);if(cls)e.className=cls;if(txt!=null)e.textContent=txt;return e}
function toast(t,ms){const d=el('div','toast',t);$('toasts').appendChild(d);setTimeout(()=>d.remove(),ms||6000)}
/* ---------- theme ---------- */
function setTheme(t){document.documentElement.dataset.theme=t;ls('gs_theme',t);document.querySelectorAll('.themes button').forEach(b=>b.classList.toggle('on',b.dataset.t===t))}
document.querySelectorAll('.themes button').forEach(b=>b.onclick=()=>setTheme(b.dataset.t));setTheme(ls('gs_theme')||'pothi');
/* ---------- markdown (सुरक्षित: आधी escape) ---------- */
function esc(s){return s.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function inl(s){return s.replace(/`([^`\n]+)`/g,'<code>$1</code>').replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>')
 .replace(/(^|[^*\w])\*([^*\n]+)\*(?![*\w])/g,'$1<em>$2</em>').replace(/\[([^\]\n]{2,80})\]/g,'<span class="ref">$1</span>')}
function md(src){const L=esc(src||'').split('\n');let h='',list=null,para=[];
 const flush=()=>{if(para.length){h+='<p>'+inl(para.join('<br>'))+'</p>';para=[]}},close=()=>{if(list){h+='</'+list+'>';list=null}};
 for(const raw of L){const l=raw.replace(/\s+$/,'');let m;
  if(!l.trim()){flush();close();continue}
  if(m=l.match(/^\s*#{1,4}\s+(.*)/)){flush();close();h+='<h4>'+inl(m[1])+'</h4>';continue}
  if(m=l.match(/^\s*&gt;\s?(.*)/)){flush();close();h+='<blockquote>'+inl(m[1])+'</blockquote>';continue}
  if(/^\s*(-{3,}|\*{3,})\s*$/.test(l)){flush();close();h+='<hr>';continue}
  if(m=l.match(/^\s*[-*•]\s+(.*)/)){flush();if(list!=='ul'){close();h+='<ul>';list='ul'}h+='<li>'+inl(m[1])+'</li>';continue}
  if(m=l.match(/^\s*[0-9०-९]{1,2}[.)]\s+(.*)/)){flush();if(list!=='ol'){close();h+='<ol>';list='ol'}h+='<li>'+inl(m[1])+'</li>';continue}
  close();para.push(l)}
 flush();close();return h}
/* ---------- संवाद (browser मध्ये जपलेले) ---------- */
let convs=[];try{convs=JSON.parse(ls('gs_convs')||'[]')}catch(e){}
let cur=null,ctrl=null,busy=false,AG={},agent=ls('gs_agent')||'sarva',birth=null;
function save(){if(cur&&cur.msgs.length){convs=convs.filter(c=>c!==cur);convs.unshift(cur)}
 for(let n=40;n>=5;n-=10){try{localStorage.setItem('gs_convs',JSON.stringify(convs.slice(0,n)));break}catch(e){}}drawConvs()}
function drawConvs(){const box=$('convs');box.innerHTML='';
 if(!convs.length){box.appendChild(el('div','sect','अजून संवाद नाहीत'));return}
 convs.forEach(c=>{const d=el('div','cv'+(c===cur?' on':''));d.appendChild(el('b','',(AG[c.agent]||{}).icon||'🪔'));d.appendChild(el('span','',c.title||'नवीन संवाद'));
  const x=el('button','x','✕');x.title='काढा';x.onclick=e=>{e.stopPropagation();convs=convs.filter(z=>z!==c);if(c===cur)newConv();save()};d.appendChild(x);
  d.onclick=()=>openConv(c);box.appendChild(d)})}
function newConv(){if(busy)stop();cur={id:Date.now().toString(36),title:'',agent,birth:null,msgs:[]};birth=null;kState();render(true);side.classList.remove('open');q.focus()}
function openConv(c){if(busy)stop();cur=c;birth=c.birth||null;pickAgent(c.agent||'sarva',true);kState();render(true);side.classList.remove('open')}
/* ---------- दाखवणे ---------- */
function render(flip){col.innerHTML='';drawConvs();
 if(flip){chat.classList.remove('flip');void chat.offsetWidth;chat.classList.add('flip')}
 if(!cur.msgs.length){col.appendChild(emptyPage());return}
 let page=0;cur.msgs.forEach((m,i)=>{if(m.role!=='user')page++;col.appendChild(m.role==='user'?userNode(m,i):leafNode(m,i,page))});chat.scrollTop=1e9}
function emptyPage(){const a=AG[agent]||{},d=el('div','empty');d.appendChild(el('div','diya','🪔'));
 d.appendChild(el('h2','',a.kundali?'कुंडली आणि ग्रंथ':'आज कोणता ग्रंथ उघडूया?'));
 d.appendChild(el('p','',(a.icon?a.icon+' '+a.name+' — ':'')+(a.about||'वेद, आयुर्वेद, पुराणे, ज्योतिष — तुमचे ग्रंथ, तुमच्या संगणकावर')));
 const g=el('div','ex');(a.examples||[]).forEach(x=>{const b=el('button','',x);b.onclick=()=>ask(x);g.appendChild(b)});d.appendChild(g);return d}
function userNode(m,i){const t=el('div','turn user');t.appendChild(el('div','bubble',m.content));
 const a=el('div','acts');a.appendChild(btn('✏️ संपादित',()=>editAt(i,t)));a.appendChild(btn('📋',()=>copy(m.content),'कॉपी'));t.appendChild(a);return t}
function btn(t,f,title){const b=el('button','',t);b.onclick=f;if(title)b.title=title;return b}
function leafNode(m,i,page){const L=el('article','leaf');L.appendChild(el('div','hole'));
 L.appendChild(el('div','pno',m.role==='card'?'॥ जन्मकुंडली ॥':'॥ पान '+dn(page)+' ॥'));
 const x=m.x||{};(x.alerts||[]).forEach(t=>L.appendChild(el('div','alert',t)));
 if(x.kundali||m.role==='card'){const k=x.kundali||m,w=el('div','kchart');w.innerHTML=k.svg;w.appendChild(el('div','kt',k.text));L.appendChild(w);
  if(m.role==='card'){L.appendChild(el('div','src','विंशोत्तरी महादशा: '+m.dasha));const c=el('div','chips');
   ['या कुंडलीचे ग्रंथानुसार मुख्य फल सांगा','माझ्या कुंडलीनुसार पुढची २ वर्षे कशी जातील?','कुंडलीतील योगांचे फल'].forEach(s=>{const b=el('span','chip',s);b.onclick=()=>ask(s);c.appendChild(b)});L.appendChild(c);return L}}
 const body=el('div','md');body.innerHTML=md(m.content)||'';if(x.error)body.appendChild(el('div','err','⚠️ '+x.error));L.appendChild(body);
 if(x.pada){const d=el('details','pada');d.appendChild(el('summary','','📝 पदच्छेद आणि व्याकरण'));
  x.pada.items.forEach(it=>it.parts.forEach(p=>{d.appendChild(el('div','pl',p.t+(p.g?'  ('+p.g+(p.r?' '+p.r:'')+')':'')));
   const t=el('table');p.words.forEach(w=>{const tr=el('tr');w.forEach(v=>tr.appendChild(el('td','',v)));t.appendChild(tr)});d.appendChild(t)}));
  d.appendChild(el('div','src',x.pada.credit));L.appendChild(d)}
 if(x.imgs&&x.imgs.length){const g=el('div','figs');x.imgs.forEach(p=>{const a=el('a');a.href='/img?p='+encodeURIComponent(p);a.target='_blank';const im=el('img');im.src=a.href;im.title=p;a.appendChild(im);g.appendChild(a)});L.appendChild(g)}
 if(x.srcs&&x.srcs.length)L.appendChild(el('div','src','📄 संदर्भ: '+x.srcs.join(', ')));
 if(x.stopped)L.appendChild(el('div','stopped','⏹ उत्तर मध्येच थांबवले'));
 const a=el('div','acts');a.appendChild(btn('📋 कॉपी',()=>copy(m.content)));
 if(i===cur.msgs.length-1&&i>0&&cur.msgs[i-1].role==='user')a.appendChild(btn('🔄 पुन्हा उत्तर',regen));L.appendChild(a);return L}
function copy(t){(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(()=>toast('📋 कॉपी केले',1500)).catch(()=>{const a=el('textarea');a.value=t;document.body.appendChild(a);a.select();document.execCommand('copy');a.remove();toast('📋 कॉपी केले',1500)})}
function editAt(i,node){if(busy)return;const m=cur.msgs[i],e=el('div','edit'),ta=el('textarea');ta.value=m.content;e.appendChild(ta);
 const r=el('div');r.appendChild(btn('रद्द',()=>render()));const s=btn('पाठवा',()=>{const t=ta.value.trim();if(!t)return;cur.msgs=cur.msgs.slice(0,i);if(!cur.msgs.some(z=>z.role==='user'))cur.title='';ask(t)});s.className='btn';r.appendChild(s);e.appendChild(r);
 node.replaceWith(e);ta.focus();ta.setSelectionRange(ta.value.length,ta.value.length);
 ta.onkeydown=ev=>{if(ev.key==='Enter'&&!ev.shiftKey){ev.preventDefault();s.click()}else if(ev.key==='Escape')render()}}
function regen(){if(busy)return;const i=cur.msgs.length-1,t=cur.msgs[i-1].content;cur.msgs=cur.msgs.slice(0,i-1);ask(t)}
/* ---------- विचारणे ---------- */
function setBusy(b){busy=b;go.classList.toggle('stop',b);go.textContent=b?'■':'➤';go.title=b?'थांबवा':'पाठवा';go.disabled=!b&&!q.value.trim()}
function goClick(){busy?stop():ask(q.value)}
function stop(){if(ctrl)ctrl.abort()}
async function ask(text){text=(text||'').trim();if(!text||busy)return;q.value='';grow();
 if(!cur.title)cur.title=text.slice(0,48);cur.agent=agent;
 const hist=cur.msgs.filter(m=>m.role==='user'||m.role==='assistant').map(m=>({role:m.role,content:m.content})).slice(-6);
 cur.msgs.push({role:'user',content:text});const m={role:'assistant',content:'',x:{srcs:[],alerts:[]}};cur.msgs.push(m);
 render();const L=col.lastChild;L.classList.add('turn');const body=L.querySelector('.md');body.innerHTML='<span class="think">ग्रंथ उघडत आहे<i>…</i></span>';
 setBusy(true);ctrl=new AbortController();let last=0;
 const paint=()=>{body.innerHTML=md(m.content);body.lastElementChild?body.lastElementChild.classList.add('cursor'):0;
  if(chat.scrollHeight-chat.scrollTop-chat.clientHeight<160)chat.scrollTop=1e9};
 try{const r=await fetch('/ask',{method:'POST',signal:ctrl.signal,headers:{'Content-Type':'application/json'},
   body:JSON.stringify({q:text,history:hist,agent:agent,birth:(AG[agent]&&AG[agent].kundali)?birth:null})});
  const rd=r.body.getReader(),dec=new TextDecoder();let buf='';
  while(true){const {done,value}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});let i;
   while((i=buf.indexOf('\n'))>=0){const line=buf.slice(0,i);buf=buf.slice(i+1);if(!line)continue;const e=JSON.parse(line);
    if(e.type==='token'){m.content+=e.t;const now=Date.now();if(now-last>50){last=now;paint()}}
    else if(e.type==='sources')m.x.srcs=m.x.srcs.concat(e.sources);
    else if(e.type==='images')m.x.imgs=e.images;
    else if(e.type==='padaccheda')m.x.pada=e;
    else if(e.type==='kundali'){m.x.kundali={svg:e.svg,text:e.text};const w=el('div','kchart');w.innerHTML=e.svg;w.appendChild(el('div','kt',e.text));L.insertBefore(w,body)}
    else if(e.type==='alert'){m.x.alerts.push(e.msg);L.insertBefore(el('div','alert',e.msg),body)}
    else if(e.type==='error')m.x.error=(m.x.error?m.x.error+'\n':'')+e.msg}}
 }catch(err){if(err.name==='AbortError')m.x.stopped=true;else m.x.error=String(err)}
 ctrl=null;setBusy(false);
 const fresh=leafNode(m,cur.msgs.length-1,col.querySelectorAll('.leaf').length);L.replaceWith(fresh);save();q.focus()}
function grow(){q.style.height='auto';q.style.height=Math.min(q.scrollHeight,220)+'px';if(!busy)go.disabled=!q.value.trim()}
q.addEventListener('input',grow);
q.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();if(!busy)ask(q.value)}});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&busy)stop()});
/* ---------- agents ---------- */
async function loadAgents(){try{const r=await (await fetch('/agents')).json(),bar=$('agentBar');
 r.agents.forEach(a=>{AG[a.id]=a;const b=el('button','',a.icon+' '+a.name);b.dataset.id=a.id;b.title=a.about||'';b.onclick=()=>{pickAgent(a.id);if(!cur.msgs.length)render()};bar.appendChild(b);
  if(a.inbox){const o=el('option','','विषय: '+a.name);o.value=a.inbox;$('ps').appendChild(o)}});
 const kp=$('kPlace');r.cities.forEach(c=>kp.appendChild(el('option','',c)));const o=el('option','','इतर ठिकाण (अक्षांश/रेखांश)');o.value='__other';kp.appendChild(o);
 if(!AG[agent])agent='sarva';pickAgent(agent,true);render()}catch(e){toast('⚠️ agents मिळाले नाहीत: '+e)}}
function pickAgent(id,quiet){agent=AG[id]?id:'sarva';ls('gs_agent',agent);if(cur&&!cur.msgs.length)cur.agent=agent;
 document.querySelectorAll('#agentBar button').forEach(b=>b.classList.toggle('on',b.dataset.id===agent));
 const a=AG[agent]||{};$('kBar').hidden=!a.kundali;$('agentTag').textContent=(a.icon||'')+' '+(a.name||'')+(a.kundali&&birth?' · 🪐 कुंडलीनुसार':'');
 if(a.inbox)$('ps').value=a.inbox}
/* ---------- कुंडली ---------- */
function birthInput(){const p=$('kPlace').value,b={name:$('kName').value,date:$('kDate').value,time:$('kTime').value,tz:$('kTz').value};
 if(p==='__other'){b.lat=$('kLat').value;b.lon=$('kLon').value}else b.place=p;return b}
function kState(){$('kClear').hidden=!birth;$('kSum').textContent=birth?'— '+[birth.name,birth.date,birth.time,birth.place||''].filter(Boolean).join(' · '):'— जन्म तारीख, वेळ, ठिकाण द्या; मग प्रश्नांची उत्तरे कुंडलीनुसार';pickAgent(agent,true)}
async function makeKundali(){const b=birthInput();if(!b.date||!b.time){$('kmsg').textContent='जन्म तारीख आणि वेळ द्या.';return}
 $('kmsg').textContent='⏳ गणित चालू आहे… (पहिल्यांदा ग्रह-तक्ता ~17 MB उतरतो)';
 try{const r=await (await fetch('/kundali',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})).json();
  if(!r.ok){$('kmsg').textContent=r.msg;return}
  birth=b;cur.birth=b;if(!cur.title)cur.title='🪐 '+(b.name||'कुंडली')+' '+b.date;cur.agent=agent;
  cur.msgs.push({role:'card',svg:r.svg,text:r.text,dasha:r.chart.dasha.periods.map(p=>p.graha+' '+p.from.slice(0,4)+'–'+p.to.slice(0,4)).join(' · ')});
  $('kmsg').textContent='✅ कुंडली तयार — आता विचारलेले प्रश्न या कुंडलीनुसार उत्तरले जातील.';$('kBar').open=false;kState();save();render();
  col.lastChild.classList.add('turn')}catch(e){$('kmsg').textContent='⚠️ '+e}}
function clearKundali(){birth=null;if(cur)cur.birth=null;kState();save();$('kmsg').textContent='कुंडली काढली — आता सामान्य प्रश्न.'}
/* ---------- PDF ---------- */
const pf=$('pf'),pn=$('pn'),pl=$('pl'),pmsg=$('pmsg');
function pfName(){if(pf.files.length===1){pn.value=pf.files[0].name.replace(/\.(pdf|zip)$/i,'').replace(/[_-]+/g,' ')}else if(pf.files.length>1){pn.value='';pn.placeholder='अनेक फाइल्स — प्रत्येकीचे नाव फाइल-नावावरून'}}
function upOne(file,name){return new Promise(res=>{const x=new XMLHttpRequest();
 x.open('POST','/upload?file='+encodeURIComponent(file.name)+'&name='+encodeURIComponent(name)+'&lang='+pl.value+'&subject='+encodeURIComponent($('ps').value));
 x.upload.onprogress=e=>{if(e.lengthComputable)pmsg.textContent=`⬆ ${file.name}: ${Math.round(e.loaded*100/e.total)}%`};
 x.onload=()=>{try{res(JSON.parse(x.responseText).msg)}catch(e){res('⚠️ '+x.responseText)}};x.onerror=()=>res('⚠️ अपलोड अयशस्वी');x.send(file)})}
async function uploadPdfs(){if(!pf.files.length){pmsg.textContent='आधी PDF निवडा.';return}
 const out=[];for(const f of pf.files)out.push(await upOne(f,pf.files.length===1?pn.value:''));pmsg.textContent=out.join('\n');pf.value='';status()}
async function openInbox(){try{const r=await (await fetch('/open-inbox',{method:'POST'})).json();toast(r.msg,9000)}catch(e){toast('⚠️ '+e)}}
async function reindex(){toast('🔄 फाइल्स वाचत आहे…',2500);try{const r=await (await fetch('/reindex',{method:'POST'})).json();toast(r.msg,9000)}catch(e){toast('⚠️ '+e)}status()}
/* ---------- स्थिती ---------- */
let warned=false,ocrErr='';
async function status(){const s=$('st');try{const r=await (await fetch('/status')).json();
 s.innerHTML='';s.appendChild(el('span','dot '+(r.ok?'ok':'bad')));s.appendChild(el('span','',r.ok?`${r.model} · ${r.files} फाइल्स · ${r.chunks} तुकडे`:'Ollama चालू नाही!'));
 const pg=$('prog');
 if(r.ocr||r.indexing||r.fig){pg.hidden=false;
  pg.innerHTML=(r.ocr?`📄 <b>PDF मजकूर बनत आहे</b>: ${esc(r.ocr_msg)}<br>`:'')+(r.indexing?`📖 <b>ग्रंथ वाचणे</b>: ${esc(r.progress)}<br>`:'')+(r.fig?`${esc(r.fig_msg)}<br>`:'')+
   '<small>हे पार्श्वभूमीत चालू आहे — तोपर्यंत आधी वाचलेल्या ग्रंथांवर प्रश्न विचारू शकता. काळी खिडकी (command) बंद करू नका.</small>'}
 else pg.hidden=true;
 if(r.warn&&!warned){toast(r.warn,12000);warned=true}
 if(r.ocr_error&&r.ocr_error!==ocrErr){ocrErr=r.ocr_error;toast('⚠️ '+r.ocr_error,12000);pmsg.textContent='⚠️ '+r.ocr_error}
 if(pdfDlg.open&&r.ocr)pmsg.textContent=r.ocr_msg;
 setTimeout(status,(r.indexing||r.ocr||r.fig)?4000:30000)}catch(e){s.innerHTML='<span class="dot bad"></span><span>server बंद</span>';setTimeout(status,10000)}}
cur={id:Date.now().toString(36),title:'',agent,birth:null,msgs:[]};setBusy(false);drawConvs();loadAgents();status();q.focus();
</script></body></html>"""


class QuietServer(ThreadingHTTPServer):
    """browser ने connection मध्येच तोडले (Windows: ConnectionAbortedError 10053) तर लांब traceback नको"""
    daemon_threads = True

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return
        super().handle_error(request, client_address)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False, default=_plain).encode("utf-8")
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
                        "ocr_ready": pdf_ocr is not None and pdf_ocr.check_setup()[0], "version": VERSION,
                        "fig": FIG_STATUS["running"] or "building" in (kosha.STATUS.get("state"), padaccheda.STATUS.get("state")),
                        "fig_msg": FIG_STATUS["msg"] if FIG_STATUS["running"] else
                        (kosha.STATUS.get("msg", "") if kosha.STATUS.get("state") == "building"
                         else padaccheda.STATUS.get("msg", ""))})
        elif self.path.startswith("/img?"):
            from urllib.parse import urlparse, parse_qs
            rel = parse_qs(urlparse(self.path).query).get("p", [""])[0]
            full = os.path.realpath(os.path.join(DOCS_DIR, rel))
            root = os.path.realpath(DOCS_DIR)
            if not (full.startswith(root + os.sep) and full.lower().endswith(".png") and os.path.isfile(full)):
                return self.send_error(404)
            with open(full, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "max-age=3600")
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/agents":
            import jyotish
            self._json({"agents": agents.public_list(), "cities": list(jyotish.CITIES)})
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
                                   qs.get("lang", ["auto"])[0], qs.get("subject", [""])[0])
                safe_start_ocr()
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
            safe_start_ocr()
            started = start_indexing()
            msg = docs_report() + "\n" + ("⏳ वाचन सुरू झाले — प्रगती वरच्या पट्टीत दिसेल. तोपर्यंत प्रश्न विचारू शकता."
                                          if started else "⏳ वाचन आधीच चालू आहे.")
            self._json({"msg": msg})
        elif self.path == "/kundali":
            try:
                import jyotish
                c = kundali_from(self._body())
                self._json({"ok": True, "chart": c, "svg": jyotish.chart_svg(c), "text": jyotish.summary_text(c)})
            except Exception as e:
                self._json({"ok": False, "msg": f"⚠️ {e}"})
        elif self.path == "/ask":
            self.answer(self._body())
        else:
            self.send_error(404)

    def _send(self, obj):
        self.wfile.write((json.dumps(obj, ensure_ascii=False, default=_plain) + "\n").encode("utf-8"))
        self.wfile.flush()

    def answer(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            chart = None
            if data.get("birth"):
                try:
                    chart = kundali_from(data["birth"])
                except Exception as e:
                    self._send({"type": "error", "msg": f"कुंडली बनवता आली नाही: {e}"})
            ACTIVE_ASKS[0] += 1
            gen = answer_events((data.get("q") or "").strip(), data.get("history", []), data.get("agent"), chart)
            try:
                for ev in gen:
                    self._send(ev)
            finally:
                gen.close()                 # browser गेला/थांबवले -> Ollama चे उत्तरही लगेच थांबते (CPU वाचतो)
                ACTIVE_ASKS[0] -= 1
        except (ConnectionError, OSError):  # 'थांबवा' दाबले, नवे पान उघडले किंवा tab बंद केला — चूक नाही
            return


def answer_events(question, history=(), agent_id=None, kundali=None):
    """एका प्रश्नाचे उत्तर — sources, alert, token, error, done असे events देतो.
    agent_id: विषय-agent (agents.json); kundali: jyotish.compute_chart() चे उत्तर (ज्योतिष agent साठी)"""
    history = [m for m in history if m.get("role") in ("user", "assistant")][-6:]
    agent = agents.get(agent_id)
    if kundali is None and agent["id"] in ("jyotish", "sarva"):
        import jyotish                           # chat मध्येच जन्म-माहिती लिहिली असेल तर कुंडली आपोआप
        b = jyotish.parse_birth(question)
        if "date" in b and "time" in b:
            if "place" not in b:
                yield {"type": "token", "t": "जन्म तारीख आणि वेळ समजली, पण ठिकाण माझ्या यादीत सापडले नाही. "
                       "वरच्या 🪐 जन्मकुंडली भागात 'इतर ठिकाण' निवडून अक्षांश-रेखांश द्या (Google Maps वर ठिकाणावर "
                       "बोट ठेवल्यावर दिसतात), किंवा जवळच्या मोठ्या शहराचे नाव लिहा."}
                yield {"type": "done"}
                return
            try:
                kundali = kundali_from(b)
                agent = agents.get("jyotish")
                yield {"type": "kundali", "chart": kundali, "svg": jyotish.chart_svg(kundali),
                       "text": jyotish.summary_text(kundali)}
                rest = re.sub(r"[\d०-९:./,\-()]|नाव|जन्म\w*|वेळ|ठिकाण|जिल्हा|तारीख|pm|am|रात्री|सकाळी|दुपारी|"
                              r"संध्याकाळी|पहाटे", " ", question, flags=re.I)
                if not re.search(r"काय|कसे|कसा|कशी|कधी|सांगा|सांग|फल|फळ|\?", rest):
                    question = "या कुंडलीचे ग्रंथानुसार मुख्य फल सांगा"
            except Exception as e:
                yield {"type": "error", "msg": f"कुंडली बनवता आली नाही: {e}"}
    if not agent.get("kundali"):
        kundali = None
    try:
        if kundali:
            import jyotish
            hits = search_multi([question] + jyotish.search_queries(kundali)[:11], agent, total=TOP_K + 3)
        else:
            hits = search(question, agent if agent["folders"] else None)
    except Exception as e:
        hits = []
        yield {"type": "error", "msg": f"फाइल्स शोधता आल्या नाहीत ({e}) — सामान्य उत्तर देत आहे."}
    yield {"type": "sources", "sources": list(dict.fromkeys(name for _, name, _ in hits))}
    imgs = answer_images(hits)
    if imgs:
        yield {"type": "images", "images": imgs}
    if MODE == "granth" and red_flag(question):
        # आपत्कालीन लक्षणे: AI कडून उपाय नाही — ठरलेला सुरक्षित संदेश
        yield {"type": "alert", "msg": EMERGENCY_MSG}
        yield {"type": "token", "t": EMERGENCY_ANSWER}
        yield {"type": "done"}
        return
    if MODE == "granth" and agent.get("refuse") and \
            any(re.search(p, question, re.I) for p in agent["refuse"]):
        yield {"type": "token", "t": agent.get("refuse_answer", "हा प्रश्न ग्रंथसागर उत्तरत नाही.")}
        yield {"type": "done"}
        return
    if MODE == "granth" and _has(question, CAUTION):
        yield {"type": "alert", "msg": CAUTION_MSG}
    if hits:
        ctx = "\n\n".join(f"({agents.source_tag(name)})\n{mr_refs(text)}" for _, name, text in hits)
        user_msg = f"संदर्भ:\n{ctx}\n\n---\n"
        missing = [alts[0] for alts in keywords(question)
                   if alts[0] not in GENERIC_BASE and not any(any(k in t for k in alts) for _, _, t in hits)]
        if missing and not kundali:
            user_msg += (f"(सूचना: संदर्भात '{'/'.join(missing[:3])}' हा शब्द कुठेही नाही. म्हणून याबद्दल ग्रंथ काय सांगतो "
                         "ते बनवू नकोस — 'उपलब्ध ग्रंथांमध्ये याचे वर्णन सापडले नाही' असे स्पष्ट सांग; संदर्भात "
                         "जवळचे काही असेल तर तेवढेच सांग.)\n\n")
    else:
        user_msg = ""
    pres = []
    if padaccheda.ready():                      # श्लोकांचा पदच्छेद (DCS — तपासलेले विश्लेषण)
        try:
            pres = padaccheda.analyze_text(question, 3)
            if pres and not direct_lookup(question) and not sutra_lookup(question, agent):
                # प्रश्नातच श्लोक आहे: शोधलेले इतर तुकडे असंबंधित असतात (उदा. भलतेच सूत्र) — ते काढा
                hits = []
                user_msg = ("(सूचना: हा प्रश्न खालील श्लोकाच्या अर्थाबद्दल आहे. 'सूत्र/नियम' रचना वापरू नकोस, कोणतेही "
                            "सूत्र उद्धृत करू नकोस. रचना: 1. अन्वय (शब्दांचा गद्य क्रम) 2. प्रत्येक मुख्य शब्दाचा अर्थ "
                            "(कोश दिला असेल तर त्यावरून) 3. मराठी भावार्थ.)\n\n")
            if not pres and hits:
                pres = padaccheda.analyze_text("\n".join(t for _, _, t in hits[:2]), 3)
        except Exception:
            pres = []
        if pres:
            user_msg += ("पदच्छेद आणि व्याकरण (Digital Corpus of Sanskrit — विद्वानांनी तपासलेले; अर्थ सांगताना "
                         "हेच वापर):\n" + padaccheda.context_text(pres) + "\n\n---\n")
            yield {"type": "padaccheda", "items": pres, "credit": padaccheda.CREDIT}
    if agent.get("kosha"):
        if kosha.ready():
            if pres:                      # श्लोक असेल तर: अव्यये सोडून मूळ शब्दांचे अर्थ
                lem = [w[1] for it in pres for p in it["parts"] for w in p["words"]
                       if not w[2].startswith(("अव्यय", "सर्वनाम")) and len(w[1]) >= 3]
                kctx, ksrc = kosha.context_for(" ".join(dict.fromkeys(lem)))
            else:
                kctx, ksrc = kosha.context_for(question)
            if kctx:
                user_msg += f"शब्दकोश (संस्कृत-संस्कृत, मूळ ग्रंथ):\n{kctx}\n\n---\n"
                yield {"type": "sources", "sources": ksrc + [f"({kosha.CREDIT})"]}
        else:
            kosha.ensure_background()
            if kosha.STATUS.get("state") == "error":
                yield {"type": "error", "msg": kosha.STATUS["msg"]}
    if kundali:
        import jyotish
        user_msg += "जन्मकुंडली (गणिताने काढलेली — हीच ग्रह-स्थिती वापर):\n" + jyotish.summary_text(kundali) + "\n\n---\n"
        kaal = jyotish.kaal_text(kundali)
        if kaal:
            user_msg += "सध्याचा काळ (आजच्या तारखेला, गणिताने काढलेला):\n" + kaal + "\n\n---\n"
    user_msg = (user_msg + f"प्रश्न: {question}") if user_msg else question
    if "🖼" in user_msg:
        user_msg += ("\n\n(संदर्भातील '🖼 चित्र' म्हणजे ग्रंथातील चित्र/कुंडली/तक्ता — ते उत्तराखाली दाखवले जाईल. "
                     "चित्राचा उल्लेख 'पृ. N वरील चित्र पाहा' असा कर; AI-वर्णन चुकीचे असू शकते असे सांग.)")
    if kundali:
        user_msg += ("\n\n(सूचना: वरील कुंडली, सध्याचा काळ आणि ग्रंथ-संदर्भ एकत्र वापरून या व्यक्तीचा फलादेश सांग. "
                     "फक्त संदर्भांची यादी किंवा श्लोकांचा अर्थ देऊ नकोस — प्रत्येक मुद्दा कुंडलीतील स्थितीशी जोड.)")
    if MODE == "granth":
        user_msg += MARATHI_REMINDER
    prompt = agents.prompt(agent, GRANTH_PROMPT, kundali=bool(kundali)) if MODE == "granth" else SYSTEM_PROMPT
    messages = [{"role": "system", "content": prompt}] + list(history) + \
               [{"role": "user", "content": user_msg}]
    payload = {"model": CHAT_MODEL, "messages": messages, "stream": True,
               "options": {"num_ctx": KUNDALI_CTX if kundali else NUM_CTX,
                           "num_predict": KUNDALI_PREDICT if kundali else NUM_PREDICT, "temperature": 0.2,
                           "top_p": 0.9, "repeat_penalty": 1.05, "repeat_last_n": 64,
                           # उत्तरानंतर मॉडेल स्वतःच नवा 'प्रश्न:' / सूचना लिहू लागते — तिथे थांबवा
                           "stop": ["\n---\nप्रश्न", "\nप्रश्न:", "(सूचना: उत्तर फक्त", "\n---\n"]}}
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
    if agent["id"] == "jyotish" and GEM_ADVICE.search(answer):
        yield {"type": "token", "t": "\n\n> ⚠️ वरील रत्न/अंगठी/उपायांचा उल्लेख फक्त ग्रंथात काय लिहिले आहे ते आहे — "
                                   "ग्रंथसागर असे काही विकत घेण्याचा किंवा धारण करण्याचा सल्ला देत नाही."}
    yield {"type": "done"}


GEM_ADVICE = re.compile(r"(रत्न|अंगठी|मूंगा|मोती|पोवळ|पुष्कराज|नीलम|माणिक|पाचू|हिरा|गोमेद|लसण्या|यंत्र|ताईत|"
                        r"रुद्राक्ष|दान|उपाय)[^।\n]{0,40}(घाला|घालावी|घालावा|जडव|धारण|करावे|करा|द्यावे|आवश्यक)")


def _plain(o):
    """numpy चे bool/float/int (उदा. Skyfield मधून) -> साधे Python, म्हणजे JSON मध्ये जातात"""
    if hasattr(o, "item"):
        return o.item()
    if hasattr(o, "tolist"):
        return o.tolist()
    raise TypeError(f"{type(o).__name__} JSON मध्ये जात नाही")


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
        agent_id, chart = None, None
        m = re.match(r"^@(\w+)(?:\[([^\]]*)\])?\s+(.*)$", q)     # "@jyotish[1990-08-15 06:30 पुणे] प्रश्न"
        if m:
            agent_id, birth, q = m.group(1), m.group(2), m.group(3)
            if birth:
                d, t, place = birth.split(None, 2)
                chart = kundali_from({"date": d, "time": t, "place": place})
        print(f"\n## ❓ {q}" + (f"  · agent: {agent_id}" if agent_id else "") + "\n")
        if chart:
            import jyotish
            print("```\n" + jyotish.summary_text(chart) + "\n```\n")
        t0, ans, srcs = time.time(), "", []
        for ev in answer_events(q, (), agent_id, chart):
            if ev["type"] == "padaccheda":
                print("📝 पदच्छेद: " + " / ".join(" ".join(w[0] for w in p["words"])
                                                  for it in ev["items"] for p in it["parts"]) + "\n")
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
        srv = QuietServer(("127.0.0.1", PORT), Handler)
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
    for subj in agents.inbox_subjects():               # विषय-folders: pdf_inbox\ज्योतिष इ.
        os.makedirs(os.path.join(PDF_INBOX, subj), exist_ok=True)
    os.makedirs(DOCS_DIR, exist_ok=True)
    load_index()
    rebuild_vecs()
    print(docs_report())
    print(f"📥 PDF/ZIP इथे टाका: {PDF_INBOX}")
    if ok:
        print("📖 नवीन/बदललेले ग्रंथ पार्श्वभूमीत वाचत आहे — chat लगेच वापरता येईल.")
        recover_empty_done()
        safe_start_ocr()
        start_indexing()
        threading.Timer(3, start_figures).start()     # चित्रांचे राहिलेले वर्णन
    if any(a.get("kosha") for a in agents.AGENTS) and not kosha.ready():
        kosha.ensure_background()                     # वाचस्पत्यम्/शब्दकल्पद्रुम (~50 MB, एकदाच)
    padaccheda.ensure_background()                    # DCS पदच्छेद-माहिती -> sqlite (एकदाच, इंटरनेट नको)
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
