"""
OCR ने चुकून बनवलेली "चित्रे" साफ करा — जी खरेतर मजकुराचे तुकडे आहेत.

जुन्या आवृत्तीत कमी खात्रीचे (जुन्या scan मधील) शब्द "शाई" म्हणून धरले जात, त्यामुळे मजकुराचे भाग चित्र
म्हणून कापले गेले आणि ते शब्द ग्रंथाच्या मजकुरातून गळले. ही script प्रत्येक चित्र Tesseract ने वाचून ठरवते
(खरे चित्र की मजकूर), आणि ज्या पानांवर मजकुराची "चित्रे" आहेत ती **फक्त तीच पाने** पुन्हा OCR साठी ठेवते:

  • अर्धवट OCR झालेले ग्रंथ (Temp मधील cache): ती पाने cache मधून काढते
  • पूर्ण झालेले ग्रंथ (granth/pdf): बाकी पानांचा मजकूर आणि खरी चित्रे part फाइल्समधून cache मध्ये परत
    ठेवते, आणि मूळ PDF pdf_inbox/done मधून त्याच नावाने पुन्हा रांगेत ठेवते

ग्रंथसागर (start.bat) सुरू केला की फक्त ती पाने नव्या पद्धतीने OCR होतात. खऱ्या चित्रांची वर्णने जपली जातात.

चालवा (ग्रंथसागर बंद असताना, ग्रंथसागर folder मधून):
  python scripts\\fix_figures.py            -> फक्त तपासणी, काहीही बदलत नाही
  python scripts\\fix_figures.py --apply    -> दुरुस्ती
"""
import glob
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
for st in (sys.stdout, sys.stderr):
    try: st.reconfigure(encoding="utf-8")
    except Exception: pass

import agents
import page_layout as PL
import pdf_ocr

PDF_OUT = os.path.join(ROOT, "granth", "pdf")
INBOX = os.path.join(ROOT, "pdf_inbox")
BLOCK = re.compile(r"^\[(.+?) पृ\. (\d+)\]\n", re.M)
_SPEC = {}


def lang_spec(tess, lang):
    if lang not in _SPEC:
        _SPEC[lang] = pdf_ocr.ocr_lang_spec(tess, lang, lambda m: None)
    return _SPEC[lang]


def is_text_fig(png, tess, lang):
    """True = हे 'चित्र' खरेतर मजकुराचा तुकडा आहे"""
    import numpy as np
    from PIL import Image
    spec, tessdata = lang_spec(tess, lang)
    if not os.path.abspath(png).isascii():         # Windows वरचा Tesseract देवनागरी path उघडू शकत नाही
        tmp = os.path.join(pdf_ocr._ascii_dir("granthsagar_fixfig"), "fig.png")
        shutil.copy(png, tmp)
        png = tmp
    cmd = [tess, png, "stdout", "-l", spec, "--psm", "3", "-c", "tessedit_create_tsv=1"]
    if tessdata:
        cmd += ["--tessdata-dir", tessdata]
    r = pdf_ocr.run(cmd, env=dict(os.environ, OMP_THREAD_LIMIT="1"))
    if r.returncode != 0:
        return False
    gray = np.asarray(Image.open(png).convert("L"))
    H, W = gray.shape
    return PL.is_text_region(gray, (0, 0, W, H), PL.soft_text_boxes(PL.parse_tsv(r.stdout)))


def bad_pages(pngs, tess, lang, label):
    bad = set()
    for i, png in enumerate(pngs, 1):
        if is_text_fig(png, tess, lang):
            bad.add(int(os.path.basename(png)[1:6]))
        if i % 25 == 0:
            print(f"   {label}: {i}/{len(pngs)} चित्रे तपासली…", flush=True)
    return bad


def read_lang(work):
    f = os.path.join(work, "lang")
    return (open(f).read().strip() if os.path.exists(f) else "") or "hin"


def cache_root():
    return pdf_ocr._ascii_dir("granthsagar_ocr_v3")


def cache_dir(name):
    """_work_dir() सारखाच path, पण folder बनवत नाही"""
    key = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")[:30]
    key = (key + "_" if key else "") + __import__("hashlib").sha1(name.encode("utf-8")).hexdigest()[:12]
    return os.path.join(cache_root(), key)


def find_pdf(name, slug):
    """pdf_inbox/done मधील मूळ PDF (ग्रंथसागर नाव फाइल-नावावरूनच काढतो)"""
    done = os.path.join(INBOX, "done")
    for f in (os.listdir(done) if os.path.isdir(done) else []):
        if f.lower().endswith(".pdf"):
            n = re.sub(r"^\d{9,}_", "", os.path.splitext(f)[0]).replace("_", " ")
            if n == name or pdf_ocr.slugify(n) == slug:
                return os.path.join(done, f)
    return None


def fix_caches(tess, apply):
    """अर्धवट OCR: Temp मधील cache"""
    total = 0
    for work in sorted(glob.glob(os.path.join(cache_root(), "*"))):
        pngs = sorted(glob.glob(os.path.join(work, "figs", "*.png")))
        if not pngs or not glob.glob(os.path.join(work, "p*.txt")):
            continue
        label = os.path.basename(work)
        bad = bad_pages(pngs, tess, read_lang(work), label)
        print(f"⏳ अर्धवट ग्रंथ ({label}): {len(pngs)} चित्रे, {len(bad)} पानांवर मजकुराचे तुकडे")
        total += len(bad)
        if apply:
            for p in bad:
                for f in [os.path.join(work, f"p{p:05d}.txt")] + glob.glob(os.path.join(work, "figs", f"p{p:05d}_*")):
                    if os.path.exists(f):
                        os.remove(f)
    return total


def fix_books(tess, apply):
    """पूर्ण झालेले ग्रंथ: granth/pdf/**/images"""
    total = 0
    books = sorted({os.path.dirname(os.path.dirname(p))
                    for p in glob.glob(os.path.join(PDF_OUT, "**", "images", "*.png"), recursive=True)})
    for book in books:
        rel = os.path.relpath(book, PDF_OUT)
        pages, name = {}, None
        for f in sorted(glob.glob(os.path.join(book, "part_*.txt"))):
            t = open(f, encoding="utf-8").read()
            ms = list(BLOCK.finditer(t))
            for i, m in enumerate(ms):
                name = name or m.group(1)
                end = ms[i + 1].start() if i + 1 < len(ms) else len(t)
                pages[int(m.group(2))] = t[m.end():end].strip()
        if not name:
            print(f"⏭  {rel}: part फाइल्समध्ये ग्रंथाचे नाव सापडले नाही — सोडले"); continue
        work = cache_dir(name)
        if glob.glob(os.path.join(work, "p*.txt")):
            continue                                   # हा ग्रंथ अजून OCR होत आहे — वर हाताळला
        pngs = sorted(glob.glob(os.path.join(book, "images", "*.png")))
        lang = read_lang(work)
        bad = bad_pages(pngs, tess, lang, name)
        print(f"📘 {name}: {len(pngs)} चित्रे, {len(bad)} पानांवर मजकुराचे तुकडे")
        total += len(bad)
        if not bad or not apply:
            continue
        pdf = find_pdf(name, os.path.basename(book))
        if not pdf:
            print(f"   ⚠️ मूळ PDF pdf_inbox\\done मध्ये सापडली नाही — हा ग्रंथ सोडला. PDF परत मिळाली तर ती "
                  f"pdf_inbox\\done मध्ये ठेवून script पुन्हा चालवा."); continue
        n = pdf_ocr.page_count(pdf)
        os.makedirs(os.path.join(work, "figs"), exist_ok=True)
        with open(os.path.join(work, "lang"), "w") as f:
            f.write(lang)
        for p in range(1, n + 1):                      # चांगली पाने cache मध्ये परत -> पुन्हा OCR होणार नाहीत
            if p in bad:
                continue
            with open(os.path.join(work, f"p{p:05d}.txt"), "w", encoding="utf-8") as f:
                f.write(pages.get(p, ""))
            for img in glob.glob(os.path.join(book, "images", f"p{p:05d}_*.png")):
                shutil.copy(img, os.path.join(work, "figs", os.path.basename(img)))
        for f in glob.glob(os.path.join(book, "images", "p*")):           # वाईट पानांची चित्रे + वर्णने
            if int(os.path.basename(f)[1:6]) in bad:
                os.remove(f)
        top = rel.split(os.sep)[0]
        subj = top if top in agents.inbox_subjects() else ""
        dest_dir = os.path.join(INBOX, subj) if subj else INBOX
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, os.path.basename(pdf))
        shutil.move(pdf, dest)
        with open(dest + ".json", "w", encoding="utf-8") as f:
            json.dump({"name": name, "subject": subj, "lang": lang}, f, ensure_ascii=False)
        print(f"   ✅ {len(bad)} पाने पुन्हा OCR साठी रांगेत; बाकी {n - len(bad)} पाने तशीच")
    return total


def main(apply):
    ok, tess = pdf_ocr.check_setup()
    if not ok:
        print("❌ Tesseract सापडला नाही:", tess); return 1
    total = fix_caches(tess, apply) + fix_books(tess, apply)
    if not total:
        print("\n✅ मजकुराची चुकीची चित्रे सापडली नाहीत.")
    elif not apply:
        print(f"\nएकूण {total} पाने दुरुस्त करायची. दुरुस्तीसाठी:  python scripts\\fix_figures.py --apply")
    else:
        print("\n✅ झाले. आता start.bat चालवा — फक्त ती पाने पुन्हा OCR होतील.")
    return 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
