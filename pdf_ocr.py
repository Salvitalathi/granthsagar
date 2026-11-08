"""
PDF ग्रंथ -> स्वच्छ मजकूर (ग्रंथसागरसाठी).

ग्रंथसागर app हे आपोआप वापरते (📄 PDF जोडा बटण, किंवा pdf_inbox / granth folder मध्ये PDF टाका).
हाताने चालवायचे असल्यास:
  python pdf_ocr.py "चरक संहिता भाग 2.pdf" --name "चरक संहिता हिंदी टीका भाग 2" --lang hin

काय करतो:
  * PDF मध्ये खरा युनिकोड मजकूर असेल तर तो थेट घेतो (जलद)
  * scan केलेली / जुन्या font (Chanakya, Kruti Dev) / बिघडलेल्या Mangal PDF साठी OCR (Tesseract)
  * प्रत्येक पानाला [ग्रंथ पृ. N] असे शीर्षक — AI उत्तरात पान क्रमांक सांगू शकतो
  * OCR मधील सजावट / निरर्थक ओळी काढतो
  * पानवार save — मध्येच थांबले तरी पुन्हा चालवल्यावर पुढे सुरू

लागते: Tesseract (Windows: https://github.com/UB-Mannheim/tesseract/wiki) आणि
       pip install pypdfium2 pillow   (Poppler असेल तर तेही चालते)
हिंदी/मराठी भाषेची फाइल नसेल तर ती एकदाच इंटरनेटवरून "tessdata" folder मध्ये उतरवली जाते.
"""
import argparse, contextlib, glob, json, os, re, shutil, subprocess, sys, tempfile, threading, time, urllib.request, zipfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_TESSDATA = os.path.join(HERE, "tessdata")
TESSDATA_URL = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/{}.traineddata"
DEVA = re.compile(r"[\u0900-\u097F]")
WORD = re.compile(r"[\u0900-\u097F]+")
LETTERS = re.compile(r"[\u0900-\u094F\u0951-\u0963\u0971-\u097F]+")     # ॐ, दंड, आकडे वगळून
MANTRA_LINE = re.compile(r"ॐ|नमः|नम:|नमो|स्वाहा|फट्|ह्रीं|क्लीं|श्रीं|ऐं|॥")
LANGS = {"hin": "हिंदी / संस्कृत", "mar": "मराठी", "san": "संस्कृत (विशेष)"}


class PdfFileError(Exception):
    """ही विशिष्ट PDF फाइल खराब आहे (setup ठीक आहे) — फाइल बाजूला ठेवा, बाकीचे काम चालू ठेवा"""


class OCRSetupError(Exception):
    """Tesseract / भाषा फाइल नसल्यास — संदेश मराठीत"""


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


# ---------------- साधने शोधणे ----------------
def find_tesseract():
    exe = shutil.which("tesseract")
    if exe:
        return exe
    for p in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
              r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
              os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
              "/usr/local/bin/tesseract", "/opt/homebrew/bin/tesseract"):
        if os.path.exists(p):
            return p
    return None


_LANG_FAILED = {}


def ensure_lang(tess, lang, force_local=False):
    """भाषा फाइल (hin/mar/san) उपलब्ध करा. tessdata-dir परत देतो (None = Tesseract चा स्वतःचा)."""
    if lang in _LANG_FAILED:                      # या वेळी आधीच अपयशी — पुन्हा उतरवू नका
        raise OCRSetupError(_LANG_FAILED[lang])
    have = run([tess, "--list-langs"]).stdout.split()
    if lang in have and not force_local:
        return None
    os.makedirs(LOCAL_TESSDATA, exist_ok=True)
    path = os.path.join(LOCAL_TESSDATA, f"{lang}.traineddata")
    if not os.path.exists(path):
        try:
            print(f"⬇ {LANGS.get(lang, lang)} भाषा फाइल उतरवत आहे (एकदाच)…", flush=True)
            req = urllib.request.Request(TESSDATA_URL.format(lang), headers={"User-Agent": "granthsagar"})
            with urllib.request.urlopen(req, timeout=120) as r, open(path + ".tmp", "wb") as f:
                f.write(r.read())
            os.replace(path + ".tmp", path)
        except Exception as e:
            _LANG_FAILED[lang] = (f"{LANGS.get(lang, lang)} भाषेची OCR फाइल मिळाली नाही ({e}). "
                                  f"इंटरनेट चालू ठेवून ग्रंथसागर पुन्हा सुरू करा.")
            raise OCRSetupError(f"{LANGS.get(lang, lang)} भाषेची OCR फाइल मिळाली नाही ({e}). "
                                f"इंटरनेट चालू ठेवून पुन्हा प्रयत्न करा, किंवा Tesseract install करताना "
                                f"'Additional language data' मध्ये Hindi/Marathi निवडा.")
    return LOCAL_TESSDATA


def ensure_langs(tess, langs):
    """अनेक भाषा एकत्र (उदा. hin+san). सगळ्या एकाच tessdata-dir मध्ये हव्यात — नसतील तर स्थानिक जागेत उतरवतो."""
    have = set(run([tess, "--list-langs"]).stdout.split())
    if all(l in have for l in langs):
        return None
    for l in langs:                                     # स्थानिक जागेत सगळ्या
        if not os.path.exists(os.path.join(LOCAL_TESSDATA, f"{l}.traineddata")):
            sys_dir = _system_tessdata(tess)
            src = os.path.join(sys_dir, f"{l}.traineddata") if sys_dir else ""
            if src and os.path.exists(src):
                os.makedirs(LOCAL_TESSDATA, exist_ok=True)
                shutil.copy2(src, os.path.join(LOCAL_TESSDATA, f"{l}.traineddata"))
            else:
                ensure_lang(tess, l, force_local=True)
    return LOCAL_TESSDATA


def _system_tessdata(tess):
    out = run([tess, "--list-langs"]).stdout
    m = re.search(r'"([^"]+)"', out)                    # List of available languages in "/usr/share/…/tessdata/"
    return m.group(1) if m else None


def ocr_lang_spec(tess, lang, progress=print):
    """OCR साठी भाषा: hin -> hin+san (ॐ आणि संस्कृत श्लोक ओळखण्यासाठी). (spec, tessdata-dir)"""
    if lang in ("hin", "mar"):
        try:
            return f"{lang}+san", ensure_langs(tess, [lang, "san"])
        except OCRSetupError as e:
            progress(f"⚠️ संस्कृत OCR भाषा मिळाली नाही — फक्त {LANGS[lang]} वापरत आहे (ॐ कमी ओळखला जाईल). {e}")
    return lang, ensure_lang(tess, lang)


def check_setup(lang="hin"):
    """(ok, संदेश) — app मध्ये दाखवण्यासाठी"""
    tess = find_tesseract()
    if not tess:
        return False, ("PDF OCR साठी Tesseract लागतो, तो सापडला नाही. "
                       "https://github.com/UB-Mannheim/tesseract/wiki वरून install करा "
                       "(किंवा command prompt मध्ये: winget install UB-Mannheim.TesseractOCR), "
                       "मग ग्रंथसागर पुन्हा सुरू करा.")
    if renderer() is None:
        return False, "PDF ची पाने वाचण्यासाठी 'pip install pypdfium2 pillow' चालवा, मग ग्रंथसागर पुन्हा सुरू करा."
    return True, tess


def renderer():
    try:
        import pypdfium2  # noqa: F401
        return "pdfium"
    except ImportError:
        return "poppler" if shutil.which("pdftoppm") else None


# ---------------- PDF वाचणे ----------------
_PDFIUM_LOCK = threading.RLock()     # PDFium thread-safe नाही — एका वेळी एकच thread


@contextlib.contextmanager
def _pdfium_doc(pdf):
    """file handle ने उघडा (Windows वर देवनागरी path सुरक्षित), आणि lock धरून — समांतर OCR मध्ये
    एकाच वेळी अनेक threads नी PDFium वापरले तर 'Failed to load page' / 'Data format error' येतात."""
    import pypdfium2 as pdfium
    with _PDFIUM_LOCK:
        fh = open(pdf, "rb")
        try:
            doc = pdfium.PdfDocument(fh)
            try:
                yield doc
            finally:
                doc.close()
        finally:
            fh.close()


def prepare_pdf(pdf, work):
    """PDF उघडते का ते तपासा; सुरुवातीला कचरा असेल तर दुरुस्त प्रत बनवा. परत: वापरायचा path."""
    size = os.path.getsize(pdf)
    if size < 100:
        raise PdfFileError("फाइल रिकामी/खूप लहान आहे")
    with open(pdf, "rb") as f:
        head = f.read(1 << 20)
        f.seek(max(0, size - 4096))
        tail = f.read()
    use = pdf
    off = head.find(b"%PDF-")
    if off < 0:
        if head[:2] == b"PK":
            raise PdfFileError("ही zip फाइल आहे पण नाव .pdf आहे — नाव बदलून .zip करा")
        if head.lstrip()[:1] == b"<":
            raise PdfFileError("ही PDF नाही, web पान (HTML) आहे — download पुन्हा नीट करा")
        raise PdfFileError("ही PDF फाइल नाही (सुरुवातीला %PDF नाही)")
    if off > 0:                                     # सुरुवातीला कचरा — तो काढून प्रत
        use = os.path.join(work, "repaired.pdf")
        with open(pdf, "rb") as src, open(use, "wb") as dst:
            src.seek(off); shutil.copyfileobj(src, dst)
    if renderer() == "pdfium":
        try:
            with _pdfium_doc(use) as doc:
                if len(doc) == 0:
                    raise PdfFileError("PDF मध्ये एकही पान नाही")
        except PdfFileError:
            raise
        except Exception as e:
            msg = str(e)
            if "password" in msg.lower():
                raise PdfFileError("PDF ला password आहे — password काढून पुन्हा टाका")
            if b"%%EOF" not in tail:
                raise PdfFileError("PDF अर्धवट आहे (download/copy पूर्ण झाले नाही) — फाइल पुन्हा download करा")
            raise PdfFileError(f"PDF उघडता आली नाही, फाइल खराब असावी ({msg})")
    return use


def page_count(pdf):
    if renderer() == "pdfium":
        with _pdfium_doc(pdf) as doc:
            return len(doc)
    m = re.search(r"Pages:\s+(\d+)", run(["pdfinfo", pdf]).stdout)
    return int(m.group(1)) if m else 0


def page_text(pdf, page):
    """PDF चा स्वतःचा मजकूर (OCR शिवाय)"""
    if renderer() == "pdfium":
        with _pdfium_doc(pdf) as doc:
            return doc[page - 1].get_textpage().get_text_range()
    return run(["pdftotext", "-f", str(page), "-l", str(page), "-layout", pdf, "-"]).stdout


def render_page(pdf, page, png, dpi):
    if renderer() == "pdfium":
        with _pdfium_doc(pdf) as doc:
            doc[page - 1].render(scale=dpi / 72, grayscale=True).to_pil().save(png)
        return png
    base = png[:-4]
    run(["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(dpi), "-gray", "-png", "-singlefile", pdf, base])
    return png if os.path.exists(png) else None


def text_layer_ok(pdf, n):
    """PDF चा मजकूर वापरण्यासारखा आहे का? (बिघडलेले Mangal / Chanakya / scan नको)"""
    t = "".join(page_text(pdf, p) for p in range(1, min(n, 15) + 1))
    deva = len(DEVA.findall(t))
    if deva < 500:
        return False
    common = sum(t.count(w) for w in (" है", " के ", " में ", " और ", " आहे", " आणि ", " की ", " च "))
    return common / max(deva, 1) > 0.01 and "आयोग्म" not in t


# ---------------- स्वच्छता ----------------
# ---------------- ॐ दुरुस्ती ----------------
# हिंदी OCR मॉडेल ॐ ओळखत नाही; तो ऊ, $, $*, *, #, 3, ३, 5, 3१, ३४ असा येतो.
# मंत्राचा संदर्भ असेल तेव्हाच ॐ करतो (पुढे नमः/ह्रीं/भूर्भुवः…, किंवा "१-२ शब्द + नमः",
# किंवा मंत्राच्या शेवटी) — "5 ग्राम", "३ बार" असे खरे आकडे बदलत नाहीत.
_DEVA = "ऀ-ॿ"
_OM_SYM = (r"(?:\$\*\*|\$\*|\$5|\$|3\*|3७|३७|3&|३&|3»|३»|3%|३%|\*|#|&|%|3१|३१|३४|3४|35|३५|3|३|5|५"
           r"|ऊँ|ऊ|उँ|ओं|<|>|«|»)")
_OM_SYM_NODIGIT = r"(?:\$\*\*|\$\*|\$|\*|#|ऊँ|ऊ|उँ|ओं)"       # आकडे नाहीत — 'अर्थ'/'जप' नियमांसाठी
_OM_PRE = r"(?<![\w" + _DEVA + r".,/\d$*#&%])"
_UNITS = (r"(?!\s*(?:बार|दिन|ग्राम|मिनट|भाग|घंटे|घण्टे|घंटा|माला|बूँद|बूंद|चम्मच|तोला|तोले|माशा|मासे|रत्ती"
          r"|मि\.|मिली|किलो|वर्ष|साल|महीने|महीना|सप्ताह|हफ्ते|पत्ते|दाने|लीटर|कप|गिलास|चुटकी|प्रकार"
          r"|लोग|व्यक्ति|प्रतिशत|से|या|और|तथा|वेळा|दिवस|ग्रॅम|मिनिटे|पाने|थेंब)(?![" + _DEVA + r"]))")
_MANTRA = (r"(?:नमः|नम:|नमो|नमस्ते|हां|हाँ|ह्रां|ह्रीं|हीं|ह्रूं|ह्रैं|हौं|ह्रौं|क्लीं|ऐं|श्रीं|भूर्भुव|भूः|भू:"
           r"|तत्सत्|शान्तिः|शान्ति:|शांतिः|शांति|शान्ति|जूँ|जूं|त्र्यम्बकं|तयम्बकं|त्रयम्बकं|त्र्यम्बकम्|हुं|हूं|फट्|स्वाहा"
           r"|गं|गँ|आदेश|सहनाववतु|पूर्णमदः|हरिः|असतो|चक्षुः|नमश्|नमःशिवाय|भगवते|विष्णवे|गणेशाय|शिवाय"
           r"|हंसं|हंसः|सोऽहं|सोहं|राम)")
_W = "[" + _DEVA + "]+"
_NAMAH_END = (r"\s*(?:नमः|नम:|नमो|स्वाहा|(?:हूँ|हुं|हूं)\s+फट्|फट्)"
              r"(?![\u0900-\u0963\u0966-\u097F])")      # दंड (।) चालतो
_OM_RULES = [
    # 1. चिन्ह + (नवी ओळ चालेल) + मंत्र-शब्द
    (re.compile(_OM_PRE + "(" + _OM_SYM + ")" + _UNITS + r"(\s+)(?=" + _MANTRA + ")"), r"ॐ\2"),
    # 2. चिन्ह + १-२ शब्द + नमः  ($ रवये नमः, * मरीचये नमः, 5 कौरा देव्ये नमः)
    (re.compile(_OM_PRE + "(" + _OM_SYM + ")" + _UNITS + r"(\s+)(?=(?:" + _W + r"\s+)?" + _W + _NAMAH_END + ")"),
     r"ॐ\2"),
    # 2b. मंत्राचा हिंदी/मराठी अर्थ: '* करुणा करने वाले … को नमस्कार है'
    (re.compile(_OM_PRE + "(" + _OM_SYM_NODIGIT + r")(\s+)(?=[^।]{0,100}?(?:को|ला|यांना)\s+नमस्कार)"), r"ॐ\2"),
    # 2c. '# शब्द का उच्चारण', 'पवित्र * का जप', '# अथवा अपना … मंत्र जपने'
    (re.compile(_OM_PRE + "(" + _OM_SYM_NODIGIT +
                r")(\s+)(?=(?:अथवा|या|शब्द|का|की|चा|ची|चे)\s[^।]{0,60}?(?:जप|उच्चार|मंत्र|मन्त्र|गुंजन))"), r"ॐ\2"),
    # 3. मंत्राच्या शेवटी: '… भू: $5।', '… हां #।'
    (re.compile(r"((?:भू:|भूः|सः|हां|हाँ|हौं|जूँ|जूं|स्वाहा|फट्|नमः|नम:)\s)" + _OM_SYM + r"(?=\s*[।॥])"), r"\1ॐ"),
    # 4. अवतरण चिन्हांत एकटे चिन्ह, आणि जवळ उच्चारण/जप/मंत्र: केवल '*' का उच्चारण
    (re.compile(r"(['‘\"“])\s*(?:\$\*|\$|\*|#|ऊ)\s*(['’\"”])(?=\s*(?:का|की|के|चा|ची|चे|या)?\s*"
                r"(?:उच्चार|जप|ध्यान|पाठ|स्मरण|मंत्र|मन्त्र|गुंजन|नाद))"), r"\1ॐ\2"),
    (re.compile(r"((?:केवल|मंत्र|मन्त्र|बीज|जपें|जप|उच्चारण)\s*:?\s*['‘\"“])\s*(?:\$\*|\$|\*|#|ऊ)\s*(?=['’\"”])"),
     r"\1ॐ"),
]


# प्रसिद्ध मंत्रांतील नेहमीच्या OCR चुका (फक्त पूर्ण शब्द)
_MANTRA_WORDS = {
    "तयम्बकं": "त्र्यम्बकं", "त्रयम्बकं": "त्र्यम्बकं", "तयम्बकम्": "त्र्यम्बकम्",
    "उर्व्वारुकमिव": "उर्वारुकमिव", "भूर्भुव": "भूर्भुवः", "भूर्भुव:": "भूर्भुवः",
    "सवितुर्वरेण्य": "सवितुर्वरेण्यं", "प्रचोदयातू": "प्रचोदयात्",
    "नमःशिवाय": "नमः शिवाय", "नम:": "नमः",
}
_MANTRA_RX = re.compile(r"(?<![\u0900-\u097F])(" + "|".join(map(re.escape, sorted(_MANTRA_WORDS, key=len, reverse=True)))
                        + r")(?![\u0900-\u0950\u0955-\u0963\u0966-\u097F])")   # स्वर-चिन्ह (॑ ॒) व दंड चालतात


_HRIM_RX = re.compile(r"(?:(?<=ॐ )|(?<=ॐ))हीं(?![\u0900-\u0963\u0966-\u097F])"
                      r"|(?<![\u0900-\u097F])हीं(?=\s+(?:क्लीं|श्रीं|ऐं|हुं|हूं|फट्|[\u0900-\u097F]+\s*नमः))")


def fix_om(text):
    """OCR मधील चुकलेले ॐ आणि प्रसिद्ध मंत्रांतील शब्द दुरुस्त करा"""
    for rx, rep in _OM_RULES:
        text = rx.sub(rep, text)
    text = _MANTRA_RX.sub(lambda m: _MANTRA_WORDS[m.group(1)], text)
    # ओळीत 'ॐ X नमः' अनेकदा आणि सुरुवातीचा ॐ गळलेला: 'मित्राय नमः। ॐ रवये नमः। …' -> 'ॐ मित्राय …'
    def lead(m):
        line = m.group(0)
        if line.count("ॐ") >= 2 and len(re.findall(r"ॐ\s*[\u0900-\u097F]+\s*(?:नमः|नम:)", line)) >= 2:
            return re.sub(r"^(\s*)(?=[\u0900-\u097F]+\s*(?:नमः|नम:))", r"\1ॐ ", line, count=1)
        return line
    text = re.sub(r"^(?!\s*ॐ).*$", lead, text, flags=re.M)
    # 'हीं' (हिंदीत 'ही' सुद्धा) -> 'ह्रीं' फक्त मंत्रात: ॐ हीं …, हीं क्लीं …, हीं सूर्याय नमः
    return _HRIM_RX.sub("ह्रीं", text)


def clean(text):
    text = fix_om(text)                                    # आधी ॐ — मग गाळणी (मंत्र ओळी वाचतात)
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            if out and out[-1]:
                out.append("")
            continue
        line = re.sub(r"(.)\1{5,}", r"\1", line)          # फफफफफफ -> फ
        if line.startswith("["):                           # [ग्रंथ पृ.] शीर्षकाशी गोंधळ नको
            line = "(" + line[1:]
        if not MANTRA_LINE.search(line):                   # मंत्र/श्लोक ओळी कधीच गाळू नका
            words = LETTERS.findall(line)
            if len(words) >= 10 and max(words.count(w) for w in set(words)) / len(words) > 0.4:
                continue                                     # 'आरोग्य-अड्ड आरोग्य-अड्ड …' सजावट
            if words:
                short = sum(len(w) <= 2 for w in words) / len(words)
                if len(words) >= 6 and short > 0.6:        # 'ली नली लक कि ल्‍' सारखी सजावट
                    continue
            elif not re.search(r"\d", line) or len(line) < 3:
                continue
        out.append(line.replace("\u200d", "").replace("\u200c", ""))
    text = "\n".join(out).strip()
    return fix_om(re.sub(r"(\S)-\n(\S)", r"\1\2", text))


def slugify(name):
    return re.sub(r"[^\w\u0900-\u097F]+", "_", name).strip("_") or "granth"


# ---------------- मुख्य काम ----------------
MARATHI_MARKS = ("आहे", "आहेत", "आणि", "नाही", "होते", "म्हणजे", "करावे", "असते", "त्यामुळे", "पाहिजे")
HINDI_MARKS = ("है", "हैं", "में", "और", "नहीं", "होता", "करना", "चाहिए", "जाता", "किया")


def detect_lang(pdf, n, tess, work, progress=print):
    """मधली 2 पाने वाचून हिंदी की मराठी ते ठरवा.
    आधी भाषेचे खुणेचे शब्द (आहे/आणि… विरुद्ध है/में…), बरोबरी असेल तर OCR-confidence (हिंदीला थोडे झुकते माप)."""
    pages = sorted({max(1, n // 3), max(1, (2 * n) // 3)})
    conf, words = {}, {}
    for lang in ("hin", "mar"):
        try:
            tessdata = ensure_lang(tess, lang)
        except OCRSetupError:
            continue
        confs, ws = [], []
        for p in pages:
            png = render_page(pdf, p, os.path.join(work, f"lang{p}.png"), 200)
            if not png:
                continue
            # 'tsv' config-फाइल स्थानिक tessdata मध्ये नसते — म्हणून थेट setting
            cmd = [tess, png, "stdout", "-l", lang, "--psm", "3", "-c", "tessedit_create_tsv=1"] + \
                  (["--tessdata-dir", tessdata] if tessdata else [])
            for row in run(cmd).stdout.splitlines()[1:]:
                c = row.split("\t")
                if len(c) == 12 and DEVA.search(c[11]):
                    ws.append(c[11].strip(" ।,.;:!?\"'"))
                    try:
                        confs.append(float(c[10]))
                    except ValueError:
                        pass
        conf[lang] = sum(confs) / len(confs) if confs else 0.0
        words[lang] = ws
    for f in glob.glob(os.path.join(work, "lang*.png")):
        os.remove(f)
    if not conf:
        raise OCRSetupError("हिंदी/मराठी OCR भाषा उपलब्ध नाही (इंटरनेट चालू ठेवून पुन्हा प्रयत्न करा).")
    if len(conf) == 1:
        best = next(iter(conf))
    else:
        all_words = words.get("hin", []) + words.get("mar", [])
        mr = sum(all_words.count(w) for w in MARATHI_MARKS)
        hi = sum(all_words.count(w) for w in HINDI_MARKS)
        if mr + hi >= 4 and max(mr, hi) >= 2 * min(mr, hi):
            best = "mar" if mr > hi else "hin"
        else:                                   # संस्कृत/मिश्र — confidence, पण मराठीला ३ गुण जास्त हवेत
            best = "mar" if conf.get("mar", 0) > conf.get("hin", 0) + 3 else "hin"
        progress(f"🔤 भाषा ओळखली: {LANGS[best]} (खुणा: मराठी {mr}, हिंदी {hi}; "
                 f"confidence: {', '.join(f'{k} {v:.0f}' for k, v in conf.items())})")
        return best
    progress(f"🔤 भाषा: {LANGS[best]}")
    return best


def _zip_member_name(info):
    if info.flag_bits & 0x800:
        return info.filename
    try:                                  # Windows Explorer च्या zip मधील देवनागरी नावे
        return info.filename.encode("cp437").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def extract_zip(path, dest, depth=0):
    """zip-slip सुरक्षित extract (आतील zip एका पातळीपर्यंत). परत: काढलेल्या फाइल्स"""
    files = []
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            parts = [re.sub(r'[<>:"|?*\x00-\x1f]+', "_", p).strip(" .") or "_"
                     for p in _zip_member_name(info).replace("\\", "/").split("/") if p not in ("", ".", "..")]
            if not parts:
                continue
            target = os.path.join(dest, *parts)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            if target.lower().endswith(".zip") and depth < 1:
                files += extract_zip(target, target[:-4], depth + 1)
                os.remove(target)
            else:
                files.append(target)
    return files


def process_pdf(pdf, name, out_dir, lang="auto", jobs=None, dpi=300, force_ocr=False, progress=print):
    """PDF -> out_dir/<slug>/part_XX.txt. परत: (पाने, output folder)"""
    # कमाल 4 समांतर: chat मॉडेल (12B ~8 GB) सोबत RAM पुरावी. GS_OCR_JOBS ने बदलता येते.
    jobs = jobs or int(os.environ.get("GS_OCR_JOBS", 0)) or max(1, min(4, (os.cpu_count() or 2) - 1))
    slug = slugify(name)
    work = os.path.join(tempfile.gettempdir(), "granth_ocr", slug)
    os.makedirs(work, exist_ok=True)
    pdf = prepare_pdf(pdf, work)                      # खराब असेल तर PdfFileError (कारणासह)
    n = page_count(pdf)
    if n == 0:
        raise PdfFileError("ही PDF उघडता आली नाही")

    if not force_ocr and text_layer_ok(pdf, n):
        progress(f"📄 {name}: PDF मध्ये चांगला मजकूर आहे — OCR ची गरज नाही")
        for p in range(1, n + 1):
            with open(os.path.join(work, f"p{p:05d}.txt"), "w", encoding="utf-8") as f:
                f.write(clean(page_text(pdf, p)))
    else:
        ok, tess = check_setup(lang)
        if not ok:
            raise OCRSetupError(tess)
        if lang == "auto":
            lang_file = os.path.join(work, "lang")
            if os.path.exists(lang_file):
                lang = open(lang_file).read().strip()
            else:
                lang = detect_lang(pdf, n, tess, work, progress)
                open(lang_file, "w").write(lang)
        lang, tessdata = ocr_lang_spec(tess, lang, progress)     # hin -> hin+san
        progress(f"🔤 OCR भाषा: {lang}")
        env = dict(os.environ, OMP_THREAD_LIMIT="1")

        def one(p):
            txt = os.path.join(work, f"p{p:05d}.txt")
            if os.path.exists(txt):
                return
            png = None
            for attempt in range(3):                   # पान कधी अपयशी झाले तर पुन्हा प्रयत्न
                try:
                    png = render_page(pdf, p, os.path.join(work, f"img{p:05d}.png"), dpi)
                    break
                except Exception as e:
                    if attempt == 2:
                        progress(f"⚠️ {name}: पान {p} वाचता आले नाही ({e}) — ते सोडून पुढे")
                    time.sleep(1)
            text = ""
            if png:
                cmd = [tess, png, "stdout", "-l", lang, "--psm", "3"]
                if tessdata:
                    cmd += ["--tessdata-dir", tessdata]
                text = run(cmd, env=env).stdout
                os.remove(png)
            with open(txt + ".tmp", "w", encoding="utf-8") as f:
                f.write(clean(text))
            os.replace(txt + ".tmp", txt)

        done = len(glob.glob(os.path.join(work, "p*.txt")))
        progress(f"🔍 {name}: {n} पाने OCR ({jobs} समांतर){f', आधी झालेली {done}' if done else ''}")
        t0, new = time.time(), 0
        with ThreadPoolExecutor(jobs) as ex:
            for i, _ in enumerate(ex.map(one, range(1, n + 1)), 1):
                if i > done:
                    new += 1
                if i % 5 == 0 or i == n:
                    rate = new / max(time.time() - t0, 1e-6)
                    left = (n - i) / rate / 60 if rate > 0 else 0
                    progress(f"🔍 {name}: {i}/{n} पाने" + (f", उरलेला वेळ ~{left:.0f} मिनिटे" if i < n else ""))

    # भागांत लिहा (प्रत्येक ~150 KB), प्रत्येक पानाला शीर्षक
    dest = os.path.join(out_dir, slug)
    os.makedirs(dest, exist_ok=True)
    for old in glob.glob(os.path.join(dest, "part_*.txt")):
        os.remove(old)
    part, size, k, total = [], 0, 1, 0
    pages = sorted(f for f in os.listdir(work) if re.match(r"p\d{5}\.txt$", f))
    for i, fn in enumerate(pages):
        t = clean(open(os.path.join(work, fn), encoding="utf-8").read())
        if len(DEVA.findall(t)) >= 40:
            block = f"[{name} पृ. {int(fn[1:6])}]\n{t}"
            part.append(block); size += len(block); total += 1
        if part and (size > 150_000 or i == len(pages) - 1):
            with open(os.path.join(dest, f"part_{k:02d}.txt"), "w", encoding="utf-8") as f:
                f.write("\n\n".join(part) + "\n")
            part, size, k = [], 0, k + 1
    shutil.rmtree(work, ignore_errors=True)
    progress(f"✅ {name}: {total} पाने → {dest}")
    return total, dest


def main():
    for st in (sys.stdout, sys.stderr):
        try: st.reconfigure(encoding="utf-8")
        except Exception: pass
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--name", help="ग्रंथाचे नाव (शीर्षकात येईल); नसेल तर फाइलचे नाव")
    ap.add_argument("--out", default=os.path.join(HERE, "granth", "pdf"))
    ap.add_argument("--lang", default="auto", help="auto (आपोआप), hin (हिंदी/संस्कृत), mar (मराठी), san")
    ap.add_argument("--jobs", type=int)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--force-ocr", action="store_true")
    a = ap.parse_args()
    name = a.name or os.path.splitext(os.path.basename(a.pdf))[0]
    try:
        process_pdf(a.pdf, name, a.out, a.lang, a.jobs, a.dpi, a.force_ocr)
    except OCRSetupError as e:
        print("⚠️ " + str(e)); sys.exit(1)


if __name__ == "__main__":
    main()
