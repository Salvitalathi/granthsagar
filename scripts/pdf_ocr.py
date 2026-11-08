"""
PDF ग्रंथ -> स्वच्छ मजकूर (ग्रंथसागरसाठी).

  python scripts/pdf_ocr.py "चरक संहिता भाग 2.pdf" --name "चरक संहिता (हिंदी टीका) भाग 2"
  python scripts/pdf_ocr.py file.pdf --name "..." --lang hin --jobs 4

काय करतो:
  * PDF मध्ये खरा युनिकोड मजकूर असेल तर तो थेट घेतो
  * scan केलेली / जुन्या font (Chanakya, Kruti Dev) / बिघडलेल्या Mangal PDF साठी OCR (tesseract)
  * प्रत्येक पानाला [ग्रंथ पृ. N] असे शीर्षक — AI उत्तरात पान क्रमांक सांगू शकतो
  * OCR मधील निरर्थक ओळी (सजावट, रेषा) काढून टाकतो
  * काम पानानुसार save होते — मध्येच थांबले तरी पुन्हा चालवल्यावर पुढे सुरू

लागते: poppler (pdftoppm, pdftotext) आणि tesseract + भाषा (hin = हिंदी/संस्कृत देवनागरी, mar = मराठी).
Windows: https://github.com/UB-Mannheim/tesseract/wiki (install करताना Hindi/Marathi निवडा)
         poppler: https://github.com/oschwartz10612/poppler-windows/releases
"""
import argparse, os, re, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

DEVA = re.compile(r"[ऀ-ॿ]")
WORD = re.compile(r"[ऀ-ॿ]+")


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def page_count(pdf):
    out = run(["pdfinfo", pdf]).stdout
    m = re.search(r"Pages:\s+(\d+)", out)
    return int(m.group(1)) if m else 0


def text_layer_ok(pdf):
    """PDF चा स्वतःचा मजकूर वापरण्यासारखा आहे का? (बिघडलेले Mangal / Chanakya नको)"""
    t = run(["pdftotext", "-f", "1", "-l", "15", pdf, "-"]).stdout
    deva = len(DEVA.findall(t))
    if deva < 500:
        return False
    # बिघडलेल्या Mangal मध्ये 'म्' ऐवजी 'भ', 'य' ऐवजी 'म' — सामान्य हिंदी/मराठी शब्द तपासा
    common = sum(t.count(w) for w in (" है", " के ", " में ", " और ", " आहे", " आणि ", " की "))
    return common / max(deva, 1) > 0.01 and "आयोग्म" not in t


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
            if len(words) >= 6 and short > 0.6:      # 'ली नली लक कि ल्‍' सारखी सजावट
                continue
        elif not re.search(r"\d", line) or len(line) < 3:
            continue
        line = line.replace("‍", "").replace("‌", "")
        out.append(line)
    text = "\n".join(out).strip()
    return re.sub(r"(\S)-\n(\S)", r"\1\2", text)


def ocr_page(pdf, page, lang, workdir, dpi):
    txt = os.path.join(workdir, f"p{page:05d}.txt")
    if os.path.exists(txt):
        return
    base = os.path.join(workdir, f"img{page:05d}")
    run(["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(dpi), "-gray", "-png", pdf, base])
    imgs = [f for f in os.listdir(workdir) if f.startswith(f"img{page:05d}") and f.endswith(".png")]
    text = ""
    if imgs:
        img = os.path.join(workdir, imgs[0])
        r = run(["tesseract", img, "stdout", "-l", lang, "--psm", "3"])
        text = r.stdout
        os.remove(img)
    with open(txt + ".tmp", "w", encoding="utf-8") as f:
        f.write(clean(text))
    os.replace(txt + ".tmp", txt)


def main():
    for st in (sys.stdout, sys.stderr):
        try: st.reconfigure(encoding="utf-8")
        except Exception: pass
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--name", required=True, help="ग्रंथाचे नाव (शीर्षकात येईल)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                  "granth", "pdf"))
    ap.add_argument("--lang", default="hin")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--force-ocr", action="store_true")
    a = ap.parse_args()

    n = page_count(a.pdf)
    slug = re.sub(r"[^\wऀ-ॿ]+", "_", a.name).strip("_")
    work = os.path.join(tempfile.gettempdir(), "granth_ocr", slug)
    os.makedirs(work, exist_ok=True)

    if not a.force_ocr and text_layer_ok(a.pdf):
        print(f"📄 {a.name}: PDF मध्ये चांगला मजकूर आहे — OCR नाही")
        for p in range(1, n + 1):
            t = run(["pdftotext", "-f", str(p), "-l", str(p), "-layout", a.pdf, "-"]).stdout
            with open(os.path.join(work, f"p{p:05d}.txt"), "w", encoding="utf-8") as f:
                f.write(clean(t))
    else:
        done = len([f for f in os.listdir(work) if f.endswith(".txt")])
        print(f"🔍 {a.name}: {n} पाने OCR ({a.jobs} समांतर), आधी झालेली: {done}", flush=True)
        with ThreadPoolExecutor(a.jobs) as ex:
            for i, _ in enumerate(ex.map(lambda p: ocr_page(a.pdf, p, a.lang, work, a.dpi),
                                         range(1, n + 1)), 1):
                if i % 25 == 0 or i == n:
                    print(f"   {i}/{n} पाने", flush=True)

    # भागांत लिहा (प्रत्येक ~150 KB), प्रत्येक पानाला शीर्षक
    os.makedirs(os.path.join(a.out, slug), exist_ok=True)
    part, size, k, total = [], 0, 1, 0
    pages = sorted(f for f in os.listdir(work) if f.endswith(".txt"))
    for i, fn in enumerate(pages):
        t = clean(open(os.path.join(work, fn), encoding="utf-8").read())
        if len(DEVA.findall(t)) >= 40:
            block = f"[{a.name} पृ. {int(fn[1:6])}]\n{t}"
            part.append(block); size += len(block); total += 1
        if part and (size > 150_000 or i == len(pages) - 1):
            with open(os.path.join(a.out, slug, f"part_{k:02d}.txt"), "w", encoding="utf-8") as f:
                f.write("\n\n".join(part) + "\n")
            part, size, k = [], 0, k + 1
    print(f"✅ {a.name}: {total} पाने → {os.path.join(a.out, slug)} ({k - 1} फाइल्स)")


if __name__ == "__main__":
    main()
