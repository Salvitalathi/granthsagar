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
    """*.png.desc -> चित्र_वर्णन_XX.txt (२० चित्रे एका फाइलमध्ये; फक्त शेवटची फाइल बदलते)"""
    rows = []
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
#agentBar{display:flex;gap:6px;flex-wrap:wrap;padding:8px 16px;background:#e8e2d4;border-bottom:1px solid #d6ccb6}
#agentBar button{background:#fff;color:#1f4e5f;border:1px solid #c9bda3;padding:6px 12px}
#agentBar button.on{background:#1f4e5f;color:#fff;border-color:#1f4e5f}
#agentAbout{font-size:13px;color:#555;align-self:center}
#kPanel{background:#f3f0fb;border-bottom:1px solid #d7cff0;padding:10px 16px;font-size:14px}
#kPanel input,#kPanel select{font:inherit;padding:6px;border:1px solid #bbb;border-radius:6px}
#kPanel .row{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px;align-items:center}
.kchart{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-start}.kchart svg{max-width:100%;height:auto}
.figs{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}.figs img{max-height:180px;max-width:240px;border:1px solid #ccc;border-radius:6px;background:#fff}
.pada{margin-top:8px;font-size:14px}.pada summary{cursor:pointer;color:#1f4e5f;font-weight:600}.pada .pl{margin:6px 0 2px;font-weight:600}
.pada table{border-collapse:collapse}.pada td{border:1px solid #ddd;padding:2px 8px}.pada td:nth-child(3){color:#555}
.chip{display:inline-block;background:#fff;border:1px solid #c9bda3;border-radius:14px;padding:3px 10px;margin:3px;cursor:pointer;font-size:13px}
textarea{flex:1;font:inherit;font-size:16px;padding:10px;border-radius:10px;border:1px solid #bbb;resize:none;height:52px}
</style></head><body>
<header><h1>🪔 ग्रंथसागर <small id="st"></small> <small style="opacity:.5">v__VERSION__</small></h1>
<button class="ghost" onclick="pdfPanel.hidden=!pdfPanel.hidden">📄 PDF जोडा</button>
<button class="ghost" onclick="openInbox()">📂 PDF folder उघडा</button>
<button class="ghost" onclick="reindex()">📂 फाइल्स पुन्हा वाचा</button>
<button class="ghost" onclick="hist=[];chat.innerHTML=''">🧹 नवीन</button></header>
<div id="agentBar"></div>
<div id="kPanel" hidden>
 <b>🪐 जन्मकुंडली</b> — गणित तुमच्या संगणकावरच होते (लाहिरी अयनांश, राशी-भाव पद्धत). मग प्रश्नांची उत्तरे या कुंडलीनुसार ग्रंथांतून.
 <div class="row"><input id="kName" placeholder="नाव (ऐच्छिक)" style="width:140px">
 <input id="kDate" type="date" min="1900-01-01" max="2050-12-31"> <input id="kTime" type="time">
 <select id="kPlace" onchange="kLL.hidden=this.value!=='__other'"></select>
 <span id="kLL" hidden><input id="kLat" placeholder="अक्षांश उदा. 18.52" style="width:120px"> <input id="kLon" placeholder="रेखांश उदा. 73.86" style="width:120px"></span>
 <label title="भारत = 5.5">UTC+<input id="kTz" value="5.5" style="width:50px"></label>
 <button onclick="makeKundali()">कुंडली बनवा</button>
 <button id="kClear" class="ghost" style="color:#553;border-color:#9a8" hidden onclick="clearKundali()">✖ कुंडली काढा</button></div>
 <div id="kmsg" style="margin-top:6px;color:#555"></div>
</div>
<div id="pdfPanel" hidden>
 <b>📄 PDF ग्रंथ जोडा</b> — scan केलेली किंवा कोणत्याही font मधील PDF, किंवा PDF असलेली zip चालते. मजकूर आपोआप <code>granth/pdf/</code> मध्ये save होईल.
 <div class="row"><input type="file" id="pf" accept=".pdf,.zip,application/pdf,application/zip" multiple onchange="pfName()">
 <input id="pn" placeholder="ग्रंथाचे नाव (उदा. चरक संहिता हिंदी टीका भाग 1)">
 <select id="ps" title="विषय — त्या agent ला हा ग्रंथ मिळेल"><option value="">विषय: सामान्य</option></select>
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
 x.open('POST','/upload?file='+encodeURIComponent(file.name)+'&name='+encodeURIComponent(name)+'&lang='+pl.value+'&subject='+encodeURIComponent(document.getElementById('ps').value));
 x.upload.onprogress=e=>{if(e.lengthComputable)pmsg.textContent=`⬆ ${file.name}: ${Math.round(e.loaded*100/e.total)}%`};
 x.onload=()=>{try{res(JSON.parse(x.responseText).msg)}catch(e){res('⚠️ '+x.responseText)}};x.onerror=()=>res('⚠️ अपलोड अयशस्वी');x.send(file)})}
async function uploadPdfs(){if(!pf.files.length){pmsg.textContent='आधी PDF निवडा.';return}
 const out=[];for(const f of pf.files){out.push(await upOne(f,pf.files.length===1?pn.value:''))}
 pmsg.textContent=out.join('\n');pf.value='';status()}
let warned=false,ocrErr='';
async function status(){try{const r=await (await fetch('/status')).json();
 st.textContent=r.ok?`· ${r.model} · ${r.files} फाइल्स · ${r.chunks} तुकडे`:'· Ollama चालू नाही!';
 const pg=document.getElementById('prog');
 if(r.ocr||r.indexing||r.fig){pg.hidden=false;
  pg.innerHTML=(r.ocr?`📄 <b>PDF मजकूर बनत आहे</b>: ${r.ocr_msg}<br>`:'')+(r.indexing?`📖 <b>ग्रंथ वाचणे</b>: ${r.progress}<br>`:'')+(r.fig?`${r.fig_msg}<br>`:'')+
   '<small>हे पार्श्वभूमीत चालू आहे — तोपर्यंत आधी वाचलेल्या ग्रंथांवर प्रश्न विचारू शकता. ही खिडकी बंद केली तरी काम चालू राहते; काळी खिडकी (command) बंद करू नका.</small>'}
 else pg.hidden=true;
 if(r.warn&&!warned){add('sys',r.warn);warned=true}
 if(r.ocr_error&&r.ocr_error!==ocrErr){ocrErr=r.ocr_error;add('sys','⚠️ '+r.ocr_error);pmsg.textContent='⚠️ '+r.ocr_error}
 if(!pdfPanel.hidden&&r.ocr)pmsg.textContent=r.ocr_msg;
 setTimeout(status,(r.indexing||r.ocr||r.fig)?4000:30000)}catch(e){st.textContent='· server बंद';setTimeout(status,10000)}}
async function openInbox(){try{const r=await (await fetch('/open-inbox',{method:'POST'})).json();add('sys',r.msg)}catch(e){add('sys','⚠️ '+e)}}
async function reindex(){const s=add('sys','फाइल्स वाचत आहे…');const r=await (await fetch('/reindex',{method:'POST'})).json();s.textContent=r.msg;status()}
q.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}});
async function send(){const t=q.value.trim();if(!t||busy)return;busy=true;q.value='';add('user',t);
 const b=add('bot','…');let ans='',srcs=[],imgs=[],pada=null;
 try{const r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({q:t,history:hist.slice(-6),agent:agent,birth:(AG[agent]&&AG[agent].kundali)?birth:null})});
  const rd=r.body.getReader(),dec=new TextDecoder();let buf='';
  while(true){const {done,value}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});let i;
   while((i=buf.indexOf('\n'))>=0){const line=buf.slice(0,i);buf=buf.slice(i+1);if(!line)continue;const m=JSON.parse(line);
    if(m.type==='sources')srcs=srcs.concat(m.sources);else if(m.type==='images')imgs=m.images;else if(m.type==='padaccheda')pada=m;else if(m.type==='kundali'){const w=document.createElement('div');w.className='kchart';w.innerHTML=m.svg;
     const t=document.createElement('div');t.style.whiteSpace='pre-wrap';t.textContent=m.text;w.appendChild(t);b.parentNode.insertBefore(w,b)}else if(m.type==='token'){ans+=m.t;b.textContent=ans;chat.scrollTop=1e9}
    else if(m.type==='alert'){const a=document.createElement('div');a.className='alert';a.textContent=m.msg;chat.insertBefore(a,b)}
    else if(m.type==='error'){ans+='\n⚠️ '+m.msg;b.textContent=ans}}}
 }catch(e){b.textContent='⚠️ '+e}
 if(pada){const d=document.createElement('details');d.className='pada';const sm=document.createElement('summary');sm.textContent='📝 पदच्छेद आणि व्याकरण';d.appendChild(sm);
  pada.items.forEach(it=>it.parts.forEach(p=>{const h=document.createElement('div');h.className='pl';h.textContent=p.t+(p.g?'  ('+p.g+(p.r?' '+p.r:'')+')':'');d.appendChild(h);
   const t=document.createElement('table');p.words.forEach(w=>{const tr=document.createElement('tr');w.forEach(x=>{const td=document.createElement('td');td.textContent=x;tr.appendChild(td)});t.appendChild(tr)});d.appendChild(t)}));
  const c=document.createElement('div');c.className='src';c.textContent=pada.credit;d.appendChild(c);b.appendChild(d)}
 if(imgs.length){const g=document.createElement('div');g.className='figs';imgs.forEach(p=>{const a=document.createElement('a');a.href='/img?p='+encodeURIComponent(p);a.target='_blank';
  const im=document.createElement('img');im.src=a.href;im.title=p;a.appendChild(im);g.appendChild(a)});b.appendChild(g)}
 if(srcs.length){const s=document.createElement('div');s.className='src';s.textContent='📄 संदर्भ: '+srcs.join(', ');b.appendChild(s)}
 hist.push({role:'user',content:t},{role:'assistant',content:ans});busy=false;q.focus()}
let agent=localStorage.getItem('gs_agent')||'sarva',AG={},birth=null;
const kPanel=document.getElementById('kPanel'),kmsg=document.getElementById('kmsg');
async function loadAgents(){try{const r=await (await fetch('/agents')).json();const bar=document.getElementById('agentBar');
 r.agents.forEach(a=>{AG[a.id]=a;const b=document.createElement('button');b.textContent=a.icon+' '+a.name;b.dataset.id=a.id;b.onclick=()=>pickAgent(a.id);bar.appendChild(b);
  if(a.inbox){const o=document.createElement('option');o.value=a.inbox;o.textContent='विषय: '+a.name;document.getElementById('ps').appendChild(o)}});
 const ab=document.createElement('span');ab.id='agentAbout';bar.appendChild(ab);
 const kp=document.getElementById('kPlace');r.cities.forEach(c=>{const o=document.createElement('option');o.textContent=c;kp.appendChild(o)});
 const o=document.createElement('option');o.value='__other';o.textContent='इतर ठिकाण (अक्षांश/रेखांश)';kp.appendChild(o);
 if(!AG[agent])agent='sarva';pickAgent(agent,true)}catch(e){}}
function pickAgent(id,quiet){agent=id;try{localStorage.setItem('gs_agent',id)}catch(e){}
 document.querySelectorAll('#agentBar button').forEach(b=>b.classList.toggle('on',b.dataset.id===id));
 const a=AG[id];document.getElementById('agentAbout').textContent=a.about||'';kPanel.hidden=!a.kundali;
 if(a.inbox)document.getElementById('ps').value=a.inbox;
 if(!quiet&&a.examples.length){const d=add('sys','');d.append(a.icon+' '+a.name+' — उदाहरणे: ');
  a.examples.forEach(x=>{const c=document.createElement('span');c.className='chip';c.textContent=x;c.onclick=()=>{q.value=x;send()};d.appendChild(c)})}}
function birthInput(){const pl=document.getElementById('kPlace').value;
 const b={name:kName.value,date:kDate.value,time:kTime.value,tz:kTz.value};
 if(pl==='__other'){b.lat=kLat.value;b.lon=kLon.value}else b.place=pl;return b}
async function makeKundali(){const b=birthInput();if(!b.date||!b.time){kmsg.textContent='जन्म तारीख आणि वेळ द्या.';return}
 kmsg.textContent='⏳ गणित चालू आहे… (पहिल्यांदा ग्रह-तक्ता ~17 MB उतरतो)';
 try{const r=await (await fetch('/kundali',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})).json();
  if(!r.ok){kmsg.textContent=r.msg;return}
  birth=b;kmsg.textContent='✅ कुंडली तयार — आता विचारलेले प्रश्न या कुंडलीनुसार उत्तरले जातील.';document.getElementById('kClear').hidden=false;
  const d=add('bot','');const w=document.createElement('div');w.className='kchart';w.innerHTML=r.svg;
  const t=document.createElement('div');t.style.whiteSpace='pre-wrap';t.textContent=r.text;w.appendChild(t);d.appendChild(w);
  const tbl=document.createElement('div');tbl.className='src';tbl.textContent='विंशोत्तरी महादशा: '+r.chart.dasha.periods.map(p=>p.graha+' '+p.from.slice(0,4)+'–'+p.to.slice(0,4)).join(' · ');d.appendChild(tbl);
  const c=document.createElement('div');['या कुंडलीचे ग्रंथानुसार मुख्य फल सांगा','लग्न राशीचे फल ग्रंथांनुसार','कुंडलीतील योगांचे फल'].forEach(x=>{const s=document.createElement('span');s.className='chip';s.textContent=x;s.onclick=()=>{q.value=x;send()};c.appendChild(s)});d.appendChild(c);
  chat.scrollTop=1e9}catch(e){kmsg.textContent='⚠️ '+e}}
function clearKundali(){birth=null;document.getElementById('kClear').hidden=true;kmsg.textContent='कुंडली काढली — आता सामान्य प्रश्न.'}
loadAgents();
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
        self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
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
            try:
                for ev in answer_events((data.get("q") or "").strip(), data.get("history", []),
                                        data.get("agent"), chart):
                    self._send(ev)
            finally:
                ACTIVE_ASKS[0] -= 1
        except (BrokenPipeError, ConnectionResetError):
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
