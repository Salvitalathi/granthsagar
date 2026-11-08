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
import argparse, glob, json, os, re, shutil, subprocess, sys, tempfile, urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_TESSDATA = os.path.join(HERE, "tessdata")
TESSDATA_URL = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/{}.traineddata"
DEVA = re.compile(r"[\u0900-\u097F]")
WORD = re.compile(r"[\u0900-\u097F]+")
LANGS = {"hin": "हिंदी / संस्कृत", "mar": "मराठी", "san": "संस्कृत (विशेष)"}


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


def ensure_lang(tess, lang):
    """भाषा फाइल (hin/mar) उपलब्ध करा. tessdata-dir परत देतो (None = Tesseract चा स्वतःचा)."""
    have = run([tess, "--list-langs"]).stdout.split()
    if lang in have:
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
            raise OCRSetupError(f"{LANGS.get(lang, lang)} भाषेची OCR फाइल मिळाली नाही ({e}). "
                                f"इंटरनेट चालू ठेवून पुन्हा प्रयत्न करा, किंवा Tesseract install करताना "
                                f"'Additional language data' मध्ये Hindi/Marathi निवडा.")
    return LOCAL_TESSDATA


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
def page_count(pdf):
    if renderer() == "pdfium":
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(pdf)
        n = len(doc); doc.close()
        return n
    m = re.search(r"Pages:\s+(\d+)", run(["pdfinfo", pdf]).stdout)
    return int(m.group(1)) if m else 0


def page_text(pdf, page):
    """PDF चा स्वतःचा मजकूर (OCR शिवाय)"""
    if renderer() == "pdfium":
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(pdf)
        try:
            tp = doc[page - 1].get_textpage()
            return tp.get_text_range()
        finally:
            doc.close()
    return run(["pdftotext", "-f", str(page), "-l", str(page), "-layout", pdf, "-"]).stdout


def render_page(pdf, page, png, dpi):
    if renderer() == "pdfium":
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(pdf)
        try:
            img = doc[page - 1].render(scale=dpi / 72, grayscale=True).to_pil()
            img.save(png)
        finally:
            doc.close()
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
def clean(text):
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
        words = WORD.findall(line)
        if len(words) >= 10 and max(words.count(w) for w in set(words)) / len(words) > 0.4:
            continue                                         # 'आरोग्य-अड्ड आरोग्य-अड्ड …' सजावट
        if words:
            short = sum(len(w) <= 2 for w in words) / len(words)
            if len(words) >= 6 and short > 0.6:            # 'ली नली लक कि ल्‍' सारखी सजावट
                continue
        elif not re.search(r"\d", line) or len(line) < 3:
            continue
        out.append(line.replace("\u200d", "").replace("\u200c", ""))
    text = "\n".join(out).strip()
    return re.sub(r"(\S)-\n(\S)", r"\1\2", text)


def slugify(name):
    return re.sub(r"[^\w\u0900-\u097F]+", "_", name).strip("_") or "granth"


# ---------------- मुख्य काम ----------------
def process_pdf(pdf, name, out_dir, lang="hin", jobs=None, dpi=300, force_ocr=False, progress=print):
    """PDF -> out_dir/<slug>/part_XX.txt. परत: (पाने, output folder)"""
    jobs = jobs or max(1, (os.cpu_count() or 2) - 1)
    n = page_count(pdf)
    if n == 0:
        raise OCRSetupError("ही PDF उघडता आली नाही (खराब किंवा password असलेली?).")
    slug = slugify(name)
    work = os.path.join(tempfile.gettempdir(), "granth_ocr", slug)
    os.makedirs(work, exist_ok=True)

    if not force_ocr and text_layer_ok(pdf, n):
        progress(f"📄 {name}: PDF मध्ये चांगला मजकूर आहे — OCR ची गरज नाही")
        for p in range(1, n + 1):
            with open(os.path.join(work, f"p{p:05d}.txt"), "w", encoding="utf-8") as f:
                f.write(clean(page_text(pdf, p)))
    else:
        ok, tess = check_setup(lang)
        if not ok:
            raise OCRSetupError(tess)
        tessdata = ensure_lang(tess, lang)
        env = dict(os.environ, OMP_THREAD_LIMIT="1")

        def one(p):
            txt = os.path.join(work, f"p{p:05d}.txt")
            if os.path.exists(txt):
                return
            png = render_page(pdf, p, os.path.join(work, f"img{p:05d}.png"), dpi)
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
        with ThreadPoolExecutor(jobs) as ex:
            for i, _ in enumerate(ex.map(one, range(1, n + 1)), 1):
                if i % 10 == 0 or i == n:
                    progress(f"🔍 {name}: {i}/{n} पाने")

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
    ap.add_argument("--lang", default="hin", help="hin (हिंदी/संस्कृत), mar (मराठी), san")
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
