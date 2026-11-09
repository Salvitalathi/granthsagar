"""Ollama शिवाय चालणाऱ्या tests (बनावट Ollama server वापरून).  चालवा: python tests/test_offline.py"""
import os, re, sys, json, time, shutil, zipfile, tempfile, subprocess, urllib.request, urllib.parse, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
for st in (sys.stdout, sys.stderr):
    try: st.reconfigure(encoding="utf-8")
    except Exception: pass

import granth_tayar as gt

failures = 0


def check(name, cond):
    global failures
    print(("✅ " if cond else "❌ ") + name)
    failures += 0 if cond else 1


# ---- 1. IAST -> देवनागरी ----
check("IAST रूपांतर", gt.iast_to_deva("ye triṣaptāḥ pariyanti viśvā rūpāṇi bibhrataḥ |")
      == "ये त्रिषप्ताः परियन्ति विश्वा रूपाणि बिभ्रतः ।")
check("अनुस्वार/संयुक्त", gt.iast_to_deva("vācaspatir balā teṣāṃ") == "वाचस्पतिर् बला तेषां")

# ---- 2. GRETIL फाइल रूपांतर ----
tmp = tempfile.mkdtemp()
src = os.path.join(tmp, "av.txt")
with open(src, "w", encoding="utf-8") as f:
    f.write("header\n# Text\nAVŚ_1,1.1a ye triṣaptāḥ pariyanti |\n"
            "oṃ śaṃ no devīr abhiṣṭaya // AVS_1.6.1 //\n"
            "The thrice-seven that go about, and the lord of speech.\n")
dst = os.path.join(tmp, "out", "av.txt")
gt.convert_file(src, dst)
out = open(dst, encoding="utf-8").read()
check("संदर्भ क्रमांक", "[अथर्ववेद (शौनक) 1.1.1a] ये त्रिषप्ताः" in out and "[अथर्ववेद (शौनक) 1.6.1]" in out)
check("header काढला", "header" not in out)
check("इंग्रजी ओळ तशीच", "The thrice-seven" in out)

# ---- 2b. ग्रंथसागर: थेट शोध, शब्द, पुनरावृत्ती ----
import glob
import granthsagar as gs
gs.VECS = [(f, t, None, 1.0) for f in sorted(glob.glob(os.path.join(ROOT, "granth", "*", "*.txt")))
           for t in gs.chunk_text(open(f, encoding="utf-8").read())]
if gs.VECS:
    r = gs.direct_lookup("अथर्ववेदाच्या पहिल्या सूक्ताचा (१.१) अर्थ सांगा")
    check("थेट शोध: अथर्ववेद १.१", r and r[0][2].startswith("[अथर्ववेद 1.1]"))
    r = gs.direct_lookup("सुश्रुत सूत्रस्थान १५ मध्ये स्वस्थ कोणाला म्हणतात?")
    check("थेट शोध: सुश्रुत सू. १५ (स्वस्थ असलेला तुकडा आधी)", r and "समदोष" in r[0][2])
check("शब्द: तक्मन् -> तक्म", ["तक्मन", "तक्म"] in gs.keywords("अथर्ववेदात तक्मन् वरील मंत्र"))
check("पुनरावृत्ती ओळखली", gs.is_looping("ही एक लांब ओळ आहे जी पुन्हा पुन्हा येते आणि थांबत नाही, अजिबात नाही.\n" * 4))
check("साधे उत्तर पुनरावृत्ती नाही", not gs.is_looping(open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()[:2000]))
check("स्थान मराठीत", gs.mr_refs("[सुश्रुत संहिता Sū. 15]") == "[सुश्रुत संहिता सूत्रस्थान 15]")

# ---- 2b2. ॐ दुरुस्ती (OCR नंतर) ----
import pdf_ocr as _po
_om_cases = {
    "ऊ मित्राय नमः। $ रवये नमः। * मरीचये नमः। 3१ भानवे नमः। # भास्कराय नमः।":
        "ॐ मित्राय नमः। ॐ रवये नमः। ॐ मरीचये नमः। ॐ भानवे नमः। ॐ भास्कराय नमः।",
    "3 हाँ जूँ सः। ऊ भूर्भुव स्वः। ३ तयम्बकं यजामहे। स्वः भुवः भू: $5। सः जूँ हां #।":
        "ॐ हाँ जूँ सः। ॐ भूर्भुवः स्वः। ॐ त्र्यम्बकं यजामहे। स्वः भुवः भू: ॐ। सः जूँ हां ॐ।",
    "केवल '*' का उच्चारण करें। $ अरुणाय हूँ फट् स्वाहा। पवित्र * का जप। '# राम... 5 राम....' का जप":
        "केवल 'ॐ' का उच्चारण करें। ॐ अरुणाय हूँ फट् स्वाहा। पवित्र ॐ का जप। 'ॐ राम... ॐ राम....' का जप",
    "निर्मूल्य। 3\nनमः करुणाकराय। $* नमो आदेश गुरु का": "निर्मूल्य। ॐ\nनमः करुणाकराय। ॐ नमो आदेश गुरु का",
    "3७ हीं राहवे नम: |3& हीं सूर्याय नम:| ३» हीं गुरवे नमः। ३ तयम्बकं॑ यजामहे":
        "ॐ ह्रीं राहवे नमः |ॐ ह्रीं सूर्याय नमः| ॐ ह्रीं गुरवे नमः। ॐ त्र्यम्बकं॑ यजामहे",
}
check("ॐ: मंत्रांतील चुकलेले ॐ दुरुस्त", all(_po.fix_om(a) == b for a, b in _om_cases.items()))
_om_keep = ["3 बार दिन में लें। ३ ग्राम चूर्ण। 5 मिनट तक। सूत्र ३ में कहा है।", "* यह टिप्पणी है।",
            "5 लोगों को नमस्कार करें। ३ बार नमो कहें। ३ बार स्वाहा कहें।", "मैं 3 करता हूँ। कह ५ हूँ।",
            "अ आ इ ई उ ऊ ऋ ए", "पादावशेषितम् ॥ पाययैत्'*'। यथा बल्म ।'*'पतन्न", "का मत) हीं है"]
check("ॐ: आकडे/टीपा/स्वर बदलत नाहीत", all(_po.fix_om(x) == x for x in _om_keep))

# ---- 2c. PDF -> मजकूर (Tesseract असेल तर) ----
import pdf_ocr
FONT = next((f for f in ("/usr/share/fonts/truetype/freefont/FreeSans.ttf",
                         "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
                         r"C:\Windows\Fonts\Nirmala.ttf") if os.path.exists(f)), None)
if pdf_ocr.check_setup()[0] and FONT:
    from PIL import Image, ImageDraw, ImageFont
    tmp_pdf = tempfile.mkdtemp()
    img = Image.new("L", (1700, 2200), 255)
    d = ImageDraw.Draw(img)
    fnt = ImageFont.truetype(FONT, 64)
    for i, line in enumerate(["नाक को रोगरहित रखने के लिये", "हमेशा नाक में सरसों का तेल डालें।",
                              "गले की सूजन में नमक के पानी से गरारे करें।"] * 3):
        d.text((120, 150 + i * 110), line, font=fnt, fill=0)
    pdf_path = os.path.join(tmp_pdf, "नमुना.pdf")
    img.save(pdf_path, resolution=200)
    n, dest = pdf_ocr.process_pdf(pdf_path, "नमुना ग्रंथ", os.path.join(tmp_pdf, "out"), jobs=1, progress=lambda m: None)
    txt = open(os.path.join(dest, "part_01.txt"), encoding="utf-8").read()
    check("PDF OCR: पान आणि शीर्षक", n == 1 and txt.startswith("[नमुना ग्रंथ पृ. 1]"))
    check("PDF OCR: मजकूर ओळखला", "रोगरहित" in txt and "गरारे" in txt)
    shutil.rmtree(tmp_pdf, ignore_errors=True)
else:
    print("⏭  PDF OCR test सोडला (Tesseract/pypdfium2/font नाही)")

# ---- 2c2. ॐ थेट OCR मध्ये (hin+san) — संस्कृत भाषा-फाइल मिळाली तरच ----
if pdf_ocr.check_setup()[0]:
    _t = pdf_ocr.find_tesseract()
    try:
        pdf_ocr.ensure_langs(_t, ["hin", "san"]); _have_san = True
    except Exception:
        _have_san = False
    if _have_san:
        _od = tempfile.mkdtemp()
        _logs = []
        n, dest = pdf_ocr.process_pdf(os.path.join(ROOT, "tests", "data", "om_mantra.pdf"), "ॐ नमुना", _od,
                                      lang="auto", jobs=1, progress=_logs.append)
        _txt = open(os.path.join(dest, "part_01.txt"), encoding="utf-8").read()
        print("   OCR:", [l for l in _logs if "भाषा" in l], "| ॐ:", _txt.count("ॐ"))
        check("OCR (hin+san): ॐ थेट ओळखला (11 पैकी ≥10)", _txt.count("ॐ") >= 10)
        check("OCR (hin+san): मंत्र-ओळी गाळल्या नाहीत", "खगाय" in _txt and "यजामहे" in _txt)
        check("OCR (hin+san): आकडे बदलले नाहीत", "3 बार दिन में 5 ग्राम" in _txt)
        # संस्कृत श्लोक + हिंदी अनुवाद (स्वच्छ + धूसर पान)
        import difflib
        _truth = [l for l in open(os.path.join(ROOT, "tests", "data", "sanskrit_hindi.txt"), encoding="utf-8")
                  .read().splitlines() if l]
        n, dest = pdf_ocr.process_pdf(os.path.join(ROOT, "tests", "data", "sanskrit_hindi.pdf"), "गीता नमुना", _od,
                                      lang="auto", jobs=2, progress=lambda m: None)
        _txt = open(os.path.join(dest, "part_01.txt"), encoding="utf-8").read()
        for _pg in (1, 2):
            _part = _txt.split(f"[गीता नमुना पृ. {_pg}]")[1].split("[गीता नमुना पृ.")[0]
            _got = [l for l in _part.splitlines() if l.strip()]
            _sc = {"sa": [], "hi": []}
            for _l in _truth:
                _b = max(difflib.SequenceMatcher(None, _l, _g).ratio() for _g in _got)
                _sc["sa" if "॥" in _l or pdf_ocr.is_sanskrit_line(_l) else "hi"].append(_b)
            _sa, _hi = (sum(v) / len(v) * 100 for v in (_sc["sa"], _sc["hi"]))
            print(f"   पान {_pg}: संस्कृत {_sa:.1f}%, हिंदी {_hi:.1f}%")
            check(f"संस्कृत+हिंदी OCR पान {_pg} ({'स्वच्छ' if _pg == 1 else 'धूसर'}): संस्कृत ≥{97 if _pg == 1 else 95}%, "
                  f"हिंदी ≥{97 if _pg == 1 else 95}%", _sa >= (97 if _pg == 1 else 95) and _hi >= (97 if _pg == 1 else 95))
        check("संस्कृत: विसर्ग/अवग्रह/श्लोक-क्रमांक (नित्यः, शाश्वतोऽयं, ॥२०॥)",
              "नित्यः" in _txt and "शाश्वतोऽयं" in _txt and "॥२०॥" in _txt)
        shutil.rmtree(_od, ignore_errors=True)
    else:
        print("⏭  hin+san OCR test सोडला (संस्कृत भाषा-फाइल नाही/उतरवता आली नाही)")

check("संस्कृत दुरुस्ती: : -> ः, S -> ऽ, || -> ॥, सड़गो -> सङ्गो (फक्त संस्कृत ओळीत)",
      pdf_ocr.fix_sanskrit("अजो नित्य: शाश्वतोSयं पुराणो ||२०||") == "अजो नित्यः शाश्वतोऽयं पुराणो ॥२०॥"
      and "सङ्गोऽस्त्वकर्मणि ॥४७॥" in pdf_ocr.fix_sanskrit("मा ते सड़गो ऽस्त्वकर्मणि ॥ 47 ॥")
      and pdf_ocr.fix_sanskrit("जैसे: राम और श्याम") == "जैसे: राम और श्याम")
check("हिंदी अनुवादाची छोट्या शब्दांची ओळ गाळली जात नाही",
      "मत बन" in pdf_ocr.clean("इसलिए तु कर्मफल का कारण मत बन और कर्म न करन मं भी"))
check("श्लोक+अनुवाद गट: नवा श्लोक रिकाम्या ओळीने सुरू",
      "कभी नहीं।\n\nन जायते" in pdf_ocr.fix_sanskrit("तेरा अधिकार कर्म में है, फल में कभी नहीं।\nन जायते म्रियते वा कदाचिन् ॥२०॥"))

# ---- 2d. zip -> extract -> OCR (भाषा आपोआप) ----
if pdf_ocr.check_setup()[0]:
    class _CP(zipfile.ZipInfo):                  # Windows Explorer सारखी zip (UTF-8 flag नाही)
        def _encodeFilenameFlags(self):
            return self.filename.encode("cp437"), self.flag_bits & ~0x800
    zt = tempfile.mkdtemp()
    gs.PDF_INBOX, gs.DOCS_DIR = os.path.join(zt, "pdf_inbox"), os.path.join(zt, "granth")
    gs.PDF_OUT = os.path.join(gs.DOCS_DIR, "pdf")
    os.makedirs(gs.PDF_INBOX)
    with zipfile.ZipFile(os.path.join(gs.PDF_INBOX, "आयुर्वेद संग्रह.zip"), "w") as z:
        z.writestr(_CP("ग्रंथ/चाचणी ग्रंथ.pdf".encode("utf-8").decode("cp437")),
                   open(os.path.join(ROOT, "tests", "data", "sample_scan.pdf"), "rb").read())
        z.writestr(_CP("टीप.txt".encode("utf-8").decode("cp437")), "हळद आणि दूध")
        z.writestr("../../evil.txt", "x")
    n_txt = gs.unpack_zips(lambda *_: None)
    pdfs = gs.pending_pdfs()
    check("zip: देवनागरी नावे + PDF सापडली", any(p.endswith("चाचणी ग्रंथ.pdf") for p in pdfs))
    check("zip: मजकूर-फाइल थेट granth/pdf मध्ये",
          n_txt >= 1 and os.path.exists(os.path.join(gs.PDF_OUT, "आयुर्वेद संग्रह", "टीप.txt")))
    check("zip: zip-slip बाहेर नाही", not os.path.exists(os.path.join(zt, "evil.txt"))
          and not os.path.exists(os.path.join(os.path.dirname(zt), "evil.txt")))
    check("zip: मूळ zip done मध्ये", os.path.exists(os.path.join(gs.PDF_INBOX, "done", "आयुर्वेद संग्रह.zip"))
          and not gs.pending_zips())
    pdf = next(p for p in pdfs if p.endswith(".pdf"))
    n, dest = pdf_ocr.process_pdf(pdf, "चाचणी ग्रंथ", gs.PDF_OUT, lang="auto", jobs=1, progress=lambda m: None)
    txt = open(os.path.join(dest, "part_01.txt"), encoding="utf-8").read()
    check("zip: OCR (भाषा आपोआप) + पान शीर्षक", n == 2 and "[चाचणी ग्रंथ पृ. 2]" in txt and "मिश्रणाने" in txt)
    try:
        pdf_ocr.ensure_langs(pdf_ocr.find_tesseract(), ["mar", "san"]); _have_mar = True
    except Exception:
        _have_mar = False
    if _have_mar:   # मराठी पुस्तक -> mar+san (हिंदी मॉडेल 'त्रिफव्ठा', 'सकाठ्ठी' असे वाचते)
        check("zip: मराठी ओळखली — ळ अचूक (त्रिफळा, सकाळी)", "त्रिफळा" in txt and "सकाळी" in txt)
    else:
        print("⏭  मराठी OCR test सोडला (mar भाषा-फाइल नाही)")
    shutil.rmtree(zt, ignore_errors=True)

# ---- 2e. Windows-सारख्या अडचणी ----
if pdf_ocr.check_setup()[0]:
    _wd = tempfile.mkdtemp()
    _src_dir = os.path.join(_wd, "माझे ग्रंथ"); os.makedirs(_src_dir)
    _pdf = os.path.join(_src_dir, "अग्नि पुराण.pdf")
    shutil.copy(os.path.join(ROOT, "tests", "data", "sample_scan.pdf"), _pdf)
    # (1) Tesseract ला फक्त ASCII जागा
    _calls, _orig_run = [], pdf_ocr.run
    def _rec(cmd, **kw):
        if "tesseract" in os.path.basename(str(cmd[0])).lower():
            _calls.append(cmd)
        return _orig_run(cmd, **kw)
    pdf_ocr.run = _rec
    try:
        pdf_ocr.process_pdf(_pdf, "अग्नि पुराण", os.path.join(_wd, "out"), lang="hin", jobs=2, progress=lambda m: None)
    finally:
        pdf_ocr.run = _orig_run
    _paths = [a for c in _calls for a in c[1:] if os.sep in str(a)]
    check("Windows: Tesseract ला दिलेल्या सर्व जागा इंग्रजी-अक्षरी (देवनागरी नाव असूनही)",
          bool(_paths) and all(str(a).isascii() for a in _paths))
    # (2)/(3) Tesseract अपयशी किंवा रिकामा — 'तयार' म्हणू नये
    _fake = os.path.join(_wd, "faketess.sh")
    for _mode, _label in (("fail", "Tesseract अपयशी -> स्पष्ट error, रिकामी पाने नाहीत"),
                          ("empty", "OCR रिकामा -> 'तयार' नाही, error")):
        with open(_fake, "w") as f:
            f.write("#!/bin/sh\ncase \"$*\" in *--list-langs*) echo 'x'; echo hin; echo san; exit 0;; esac\n" +
                    ("echo 'Error: cannot read input file' >&2; exit 1\n" if _mode == "fail" else "exit 0\n"))
        os.chmod(_fake, 0o755)
        _orig_find = pdf_ocr.find_tesseract
        pdf_ocr.find_tesseract = lambda: _fake
        _err = None
        try:
            pdf_ocr.process_pdf(_pdf, "रिकामा " + _mode, os.path.join(_wd, "out2"), lang="hin", jobs=1,
                                progress=lambda m: None, force_ocr=True)
        except pdf_ocr.OCRSetupError as e:
            _err = str(e)
        finally:
            pdf_ocr.find_tesseract = _orig_find
        _made = glob.glob(os.path.join(_wd, "out2", "*", "part_*.txt"))
        check(_label, _err is not None and not _made)
    # (4) zip हलवता आली नाही तरी पुन्हा extract नाही
    gs.PDF_INBOX, gs.DOCS_DIR = os.path.join(_wd, "pdf_inbox"), os.path.join(_wd, "granth")
    gs.PDF_OUT = os.path.join(gs.DOCS_DIR, "pdf"); os.makedirs(gs.PDF_INBOX)
    with zipfile.ZipFile(os.path.join(gs.PDF_INBOX, "संग्रह.zip"), "w") as z:
        z.write(_pdf, "अग्नि पुराण.pdf")
    _orig_move = shutil.move
    def _locked(src, dst, *a, **k):
        if src.endswith(".zip"):
            raise PermissionError(32, "The process cannot access the file")
        return _orig_move(src, dst, *a, **k)
    shutil.move = _locked
    try:
        gs.unpack_zips(lambda *_: None)
    finally:
        shutil.move = _orig_move
    check("Windows: zip हलवता आली नाही तरी crash नाही, पुन्हा extract नाही", not gs.pending_zips()
          and any(p.endswith("अग्नि पुराण.pdf") for p in gs.pending_pdfs()))
    # (5) जुन्या आवृत्तीत '0 पाने' झालेली PDF परत रांगेत
    os.makedirs(os.path.join(gs.PDF_INBOX, "done"), exist_ok=True)
    shutil.copy(_pdf, os.path.join(gs.PDF_INBOX, "done", "वायु पुराण.pdf"))
    os.makedirs(os.path.join(gs.PDF_OUT, pdf_ocr.slugify("वायु पुराण")))
    check("'0 पाने' झालेली PDF आपोआप पुन्हा रांगेत", gs.recover_empty_done() == 1
          and os.path.exists(os.path.join(gs.PDF_INBOX, "वायु पुराण.pdf")))
    shutil.rmtree(_wd, ignore_errors=True)

# ---- 2e2. पानाची रचना: अनुक्रमणिका आणि चित्रे ----
import page_layout as PL
def _w(t, x, y, b, l, conf=90):
    return {"b": b, "p": 1, "l": l, "x": x, "y": y, "w": 18 * len(t), "h": 30, "conf": conf, "text": t}
# Tesseract ने डावा स्तंभ (विषय) आणि उजवा स्तंभ (पान) वेगवेगळ्या block मध्ये वाचला
_idx = [_w("अनुक्रमणिका", 500, 50, 1, 1)]
for i, (t, n) in enumerate([("प्रथम अध्याय", 1), ("द्वितीय अध्याय", 9), ("तृतीय अध्याय", 17), ("चतुर्थ अध्याय", 28)]):
    _idx += [_w(t.split()[0], 100, 150 + 60 * i, 2, i), _w(t.split()[1], 260, 150 + 60 * i, 2, i),
             _w("..........", 450, 150 + 60 * i, 2, i)]
for i, n in enumerate(["]", "9", "[7", "28"]):
    _idx.append(_w(n, 1000, 152 + 60 * i, 3, i))
_lines = [t for _, t in PL.layout_lines(_idx)]
check("अनुक्रमणिका: विषय आणि पान क्रमांक एकाच ओळीत", _lines[1:] == ["प्रथम अध्याय … 1", "द्वितीय अध्याय … 9",
                                                                      "तृतीय अध्याय … 17", "चतुर्थ अध्याय … 28"])
_para = [_w("साधे", 100, 100, 1, 1), _w("वाक्य", 200, 100, 1, 1), _w("।", 300, 100, 1, 1)]
check("साध्या पानावर '।' व क्रम तसाच", [t for _, t in PL.layout_lines(_para)] == ["साधे वाक्य ।"])
check("'७ ७ ७' ठिपके -> …", PL.layout_lines([_w("अनुक्रमणिका", 0, 0, 1, 1)] + [_w(t, 100 + 40 * k, 100, 1, 2) for k, t in
      enumerate(["योग", "विचार", "७", "७", "७", "#+", "७", "41"])])[1][1] == "योग विचार … 41")
try:
    import numpy as _np
    _g = _np.full((1400, 1000), 255, _np.uint8)
    _g[100:130, 100:900] = 0                                     # मजकुराची ओळ (text box)
    _g[400:404, 300:700] = 0; _g[796:800, 300:700] = 0           # कुंडलीचा चौकोन + कर्ण
    _g[400:800, 300:304] = 0; _g[400:800, 696:700] = 0
    for _k in range(400):
        _g[400 + _k, 300 + _k] = 0; _g[400 + _k, 699 - _k] = 0
    _figs = PL.find_figures(_g, [(100, 100, 800, 30)])
    check("चित्र शोध: कुंडली सापडली, मजकूर नाही", len(_figs) == 1 and _figs[0][0] <= 310 and _figs[0][2] >= 690
          and _figs[0][1] >= 300)
    _g2 = _np.full((1400, 1000), 255, _np.uint8); _g2[20:24, 20:980] = 0; _g2[1376:1380, 20:980] = 0
    _g2[20:1380, 20:24] = 0; _g2[20:1380, 976:980] = 0
    check("चित्र शोध: पानाभोवतीची चौकट चित्र नाही", PL.find_figures(_g2, []) == [])
except ImportError:
    print("⏭  numpy नाही — चित्र-शोध test सोडला")
check("मजकूर-PDF पान थेट (OCR नको), scan/जुना font नाही",
      pdf_ocr.page_text_ok("हे पान मराठीत आहे आणि यात खरा मजकूर आहे. " * 5)
      and not pdf_ocr.page_text_ok("") and not pdf_ocr.page_text_ok("vk;qosZn ds vuqlkj " * 20))

if pdf_ocr.check_setup()[0]:
    _ld = tempfile.mkdtemp()
    _n, _dest = pdf_ocr.process_pdf(os.path.join(ROOT, "tests", "data", "layout_jyotish.pdf"), "नक्षत्र चाचणी", _ld,
                                    lang="hin", jobs=2, progress=lambda m: None)
    _t = open(os.path.join(_dest, "part_01.txt"), encoding="utf-8").read()
    _rows = re.findall(r"^.*अध्याय.*… [\d]+$", _t, flags=re.M)
    print("   अनुक्रमणिका:", _rows)
    check("OCR: अनुक्रमणिकेच्या ओळी पान-क्रमांकासह (≥6/8)", len(_rows) >= 6)
    check("OCR: कुंडली-चित्र जसेच्या तसे PNG + मजकुरात खूण",
          "🖼 चित्र 1: images/p00002_1.png" in _t and os.path.exists(os.path.join(_dest, "images", "p00002_1.png")))
    check("OCR: चित्राच्या आधी-नंतरचा मजकूर क्रमाने", _t.find("दाखवली आहे") < _t.find("🖼") < _t.find("वरील कुंडलीत"))
    _n, _dest = pdf_ocr.process_pdf(os.path.join(ROOT, "tests", "data", "mixed_digital_scan.pdf"), "मिश्र चाचणी", _ld,
                                    lang="hin", jobs=2, progress=lambda m: None)
    _t = open(os.path.join(_dest, "part_01.txt"), encoding="utf-8").read()
    check("मिश्र PDF: मजकूर-पान थेट (इंग्रजी जपले) + त्यातील आकृती, scan पान OCR",
          "The twelve houses of the horoscope" in _t and "images/p00001_1.png" in _t and "जन्मकुंडलीत" in _t)
    shutil.rmtree(_ld, ignore_errors=True)

# ---- 2f. विषयवार agents ----
import agents
_j, _s = agents.get("jyotish"), agents.get("sarva")
check("agents: ज्योतिष फाइल्स ओळखल्या (Windows \\ सह)", agents.owns(_j, "jyotish\\bphs\\part_01.txt")
      and agents.owns(_j, "pdf/ज्योतिष/सूर्यसिद्धांत/part_01.txt") and not agents.owns(_j, "sushruta/part_01.txt")
      and not agents.owns(_j, "jyotishX/a.txt") and agents.owns(_s, "sushruta/part_01.txt"))
check("agents: अज्ञात id -> सर्व ग्रंथ", agents.get("नाही")["id"] == "sarva")
_jp = agents.prompt(_j, gs.GRANTH_PROMPT)
check("agents: ज्योतिष prompt मध्ये सुरक्षा नियम", "मृत्यू" in _jp and "रत्न" in _jp and "ग्रंथानुसार" in _jp)
check("agents: आधुनिक/मूळ स्रोत", agents.is_modern("pdf\\x\\part_01.txt") and not agents.is_modern("charaka/a.txt"))
_saved = (gs.VECS, gs.MAT, gs.embed)
gs.VECS = [("charaka/a.txt", "अपचन आहार", None, 1.0), ("jyotish/bj/part_01.txt", "मेष लग्न फल", None, 1.0),
           ("pdf/ज्योतिष/x/part_01.txt", "गजकेसरी योग", None, 1.0)]
gs.MAT = None if gs.np is None else gs.np.array([[1, 0, 0], [0.9, 0.1, 0], [0.8, 0, 0.2]], dtype="float32")
if gs.MAT is not None:
    gs.MAT /= gs.np.linalg.norm(gs.MAT, axis=1, keepdims=True)
gs.VECS = [(n, t, [1, 0, 0] if gs.MAT is None else None, 1.0) for n, t, _, _ in gs.VECS]
gs.embed = lambda texts, progress=None: [[1.0, 0.0, 0.0] for _ in texts]
_h = gs.search("आहार", agents.get("jyotish"))
check("agents: ज्योतिष agent फक्त ज्योतिष ग्रंथांतून शोधतो", _h and all(n.replace("\\", "/").startswith(("jyotish/", "pdf/ज्योतिष/")) for _, n, _ in _h))
check("agents: सर्व ग्रंथ — पहिला तुकडा चरक", gs.search("आहार")[0][1] == "charaka/a.txt")
_m = gs.search_multi(["अ", "ब"], agents.get("jyotish"))
check("agents: अनेक प्रश्नांचा शोध, पुनरावृत्ती नाही", len(_m) == len({t for _, _, t in _m}) >= 2)
gs.VECS, gs.MAT, gs.embed = _saved
_old = (gs.PDF_INBOX, gs.PDF_OUT)
_sd = tempfile.mkdtemp()
gs.PDF_INBOX, gs.PDF_OUT = os.path.join(_sd, "pdf_inbox"), os.path.join(_sd, "granth", "pdf")
check("विषय-folder: pdf_inbox/ज्योतिष/… -> ज्योतिष", gs.subject_of(os.path.join(gs.PDF_INBOX, "ज्योतिष", "a", "b.pdf")) == "ज्योतिष"
      and gs.subject_of(os.path.join(gs.PDF_INBOX, "b.pdf")) == "" and gs.subject_of(os.path.join(gs.PDF_INBOX, "इतर", "b.pdf")) == "")
import io
_p = gs.save_upload(io.BytesIO(b"%PDF-1.4 x"), 10, "सूर्य.pdf", "सूर्यसिद्धांत", "auto", "ज्योतिष")
check("upload: विषय निवडल्यावर pdf_inbox/ज्योतिष मध्ये", os.path.dirname(_p) == os.path.join(gs.PDF_INBOX, "ज्योतिष"))
os.makedirs(os.path.join(gs.PDF_INBOX, "done"), exist_ok=True)
gs.move_aside(_p, "done")
check("done नंतरही pdf_inbox/ज्योतिष folder राहतो", os.path.isdir(os.path.join(gs.PDF_INBOX, "ज्योतिष")))
gs.PDF_INBOX, gs.PDF_OUT = _old
shutil.rmtree(_sd, ignore_errors=True)

# ---- 2g. व्याकरण: सूत्र-शोध आणि शब्दकोश ----
_saved = gs.VECS
gs.VECS = [("vyakarana/mahabhashya/part_01.txt", "[महाभाष्य 6.1.77]\nइकः यण् अचि इति …", None, 1.0),
           ("vyakarana/ashtadhyayi/part_01.txt", "[अष्टाध्यायी 6.1.76] छे च ।\n[अष्टाध्यायी 6.1.77] इको यणचि ।", None, 1.0),
           ("vyakarana/kashika/part_02.txt", "[काशिका 6.1.77]\nइको यणचि ।\nइकः स्थाने यणादेशो भवति अचि परतः । दध्यत्र\n"
            "[काशिका 6.1.78]\nएचोऽयवायावः ।", None, 1.0),
           ("vyakarana/laghusiddhantakaumudi/part_01.txt", "[लघुसिद्धान्तकौमुदी 15 = 6.1.77]\nइको यणचि ॥", None, 1.0)]
_r = gs.sutra_lookup("अष्टाध्यायी ६.१.७७ समजाव", agents.get("vyakarana"))
_lab = [re.search(r"\[(अष्टाध्यायी|काशिका|लघुसिद्धान्तकौमुदी|महाभाष्य)[^\]]*6\.1\.77\]", t).group(1) for _, _, t in _r]
check("सूत्र-शोध: ६.१.७७ -> सूत्र, काशिका, कौमुदी, महाभाष्य (क्रमाने)",
      _lab == ["अष्टाध्यायी", "काशिका", "लघुसिद्धान्तकौमुदी", "महाभाष्य"])
check("सूत्र-शोध: अष्टाध्यायीतून फक्त ते सूत्र (± एक), इतर ४० सूत्रे नाहीत",
      _r[0][2] == "[अष्टाध्यायी 6.1.76] छे च ।\n[अष्टाध्यायी 6.1.77] इको यणचि ।")
check("सूत्र-शोध: काशिकेतून पुढचे सूत्र (6.1.78) नाही", "एचोऽयवायावः" not in "".join(t for _, _, t in _r))
check("सूत्र-शोध: ज्योतिष प्रश्नात '1.1.1' -> नाही", gs.sutra_lookup("बृहज्जातक 1.1.1 चा अर्थ", agents.get("jyotish")) == [])
gs.VECS = _saved
import kosha
check("SLP1 -> देवनागरी", kosha.slp1_to_deva("praRavastu trayAtmaka sidDAntakOmudI go'SveByaH")
      == "प्रणवस्तु त्रयात्मक सिद्धान्तकौमुदी गोऽश्वेभ्यः")
_kd = tempfile.mkdtemp()
kosha.DB = os.path.join(_kd, "kosha.db"); kosha.KOSHA_DIR = _kd
_ks = os.path.join(ROOT, "tests", "data", "kosha_sample.txt")
kosha.build(lambda m: None, {"vcp": _ks, "skd": _ks})
_l = kosha.lookup("धर्माचा")
check("शब्दकोश: 'धर्माचा' -> धर्म (वाचस्पत्यम् + शब्दकल्पद्रुम), व्युत्पत्ती देवनागरीत",
      len(_l) == 2 and _l[0][1] == "धर्म" and "धृ—मन्" in _l[0][2] and "धर्मो रक्षति रक्षितः" in _l[0][2])
check("शब्दकोश: प्रश्नातील शब्द", kosha.words_in('"धर्म" शब्दाचा अर्थ वाचस्पत्यम् मध्ये काय आहे?') == ["धर्म"])

# ---- 2g2. chat मधून जन्म-माहिती ----
import jyotish as _J
check("जन्म-माहिती: '12 जुलै, 1977, रात्री 8:30 pm … अलिबाग'",
      _J.parse_birth("नाव - मंगेश, जन्माची वेळ (12 जुलै, 1977, रात्री 8:30 pm) ठिकाण- अलिबाग, जिल्हा- रायगड")
      == {"date": "1977-07-12", "time": "20:30", "place": "अलिबाग"})
check("जन्म-माहिती: १५/०८/१९९० सकाळी ६.३० पुणे; दुपारी 2:15 = 14:15; रात्री 1:10 = 01:10",
      _J.parse_birth("जन्म १५/०८/१९९० सकाळी ६.३० पुणे") == {"date": "1990-08-15", "time": "06:30", "place": "पुणे"}
      and _J.parse_birth("3 मार्च 2001 दुपारी 2:15")["time"] == "14:15"
      and _J.parse_birth("5 May 1990 रात्री 1:10")["time"] == "01:10")
check("जन्म-माहिती: साधा प्रश्न -> काहीच नाही", _J.parse_birth("मेष लग्नाचे फल काय? मे महिन्यात") == {})
check("रत्न-सल्ला ओळखणे", bool(gs.GEM_ADVICE.search("मंगळासाठी सोन्याच्या अंगठीत मूंगा जडवून घाला"))
      and not gs.GEM_ADVICE.search("ग्रंथात रत्नांचे वर्णन आहे"))

# ---- 2h. पदच्छेद (DCS) ----
import padaccheda
_pdir = tempfile.mkdtemp()
padaccheda.DB = os.path.join(_pdir, "p.db")
padaccheda.build(lambda m: None, os.path.join(ROOT, "tests", "data", "padaccheda"))
_pa = padaccheda.analyze_line("कर्मण्येवाधिकारस्ते मा फ़लेषु कदाचन । मा कर्मफलहेतुर्भूर्मा ते सङ्गोऽस्त्वकर्मणि ॥४७॥")
check("पदच्छेद: गीता 2.47 (OCR चुका असूनही) — दोन्ही श्लोकार्ध, क्रमाने",
      len(_pa) == 2 and _pa[0]["words"][0][:2] == ("कर्मणि", "कर्मन्") and _pa[1]["words"][-1][0] == "अकर्मणि")
check("पदच्छेद: व्याकरण मराठीत", "सप्तमी" in _pa[0]["words"][0][2] and "आज्ञार्थ" in _pa[1]["words"][8][2])
check("पदच्छेद: DCS मध्ये नसलेला श्लोक -> काहीच नाही (अंदाज नाही)",
      padaccheda.analyze_line("यस्योदये जगदिदं प्रतिबोधमेति मध्यस्थिते प्रसरति प्रकृतिक्रियासु") == [])
check("पदच्छेद: मराठी प्रश्नातून फक्त श्लोक-ओळी",
      padaccheda.sanskrit_lines("याचा अर्थ काय आहे?\nतपःस्वाध्यायनिरतं तपस्वी वाग्विदां वरम् ।") ==
      ["तपःस्वाध्यायनिरतं तपस्वी वाग्विदां वरम्"])

# ---- 3. App + बनावट Ollama ----
docs = os.path.join(tmp, "granth")
os.makedirs(docs)
shutil.copy(dst, os.path.join(docs, "av.txt"))
with zipfile.ZipFile(os.path.join(docs, "notes.docx"), "w") as z:
    z.writestr("word/document.xml", '<w:document xmlns:w="x"><w:body><w:p><w:r>'
               '<w:t>चरक संहितेनुसार अपचनात हलका आहार घ्यावा.</w:t></w:r></w:p></w:body></w:document>')

_bk = os.path.join(docs, "pdf", "ज्योतिष", "नक्षत्र_ग्रंथ")
os.makedirs(os.path.join(_bk, "images"))
shutil.copy(os.path.join(ROOT, "tests", "data", "sample_scan.pdf"), os.path.join(_bk, "images", "p00002_1.png"))
with open(os.path.join(_bk, "part_01.txt"), "w", encoding="utf-8") as f:
    f.write("[नक्षत्र ग्रंथ पृ. 2]\nरोहिणी नक्षत्राचे चक्र खालीलप्रमाणे आहे.\n\n🖼 चित्र 1: images/p00002_1.png\n")
env = dict(os.environ, GS_KOSHA_DIR=_kd, GS_PADA_DB=padaccheda.DB,
           GS_PADA_DATA=os.path.join(ROOT, "tests", "data", "padaccheda"), GS_DOCS=docs, GS_PORT="8799", OLLAMA_HOST="http://127.0.0.1:11499",
           MOCK_PORT="11499", PYTHONIOENCODING="utf-8")
mock = subprocess.Popen([sys.executable, os.path.join(ROOT, "tests", "mock_ollama.py")], env=env)
app = subprocess.Popen([sys.executable, os.path.join(ROOT, "granthsagar.py"), "--no-browser"],
                       env=env, cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
try:
    time.sleep(3)

    def ask(q):
        req = urllib.request.Request("http://127.0.0.1:8799/ask", data=json.dumps({"q": q}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return [json.loads(l) for l in r.read().decode().splitlines() if l]

    st = json.loads(urllib.request.urlopen("http://127.0.0.1:8799/status").read())
    check("status: 3 फाइल्स", st["ok"] and st["files"] == 3)
    ev = ask("अपचनात कोणता आहार घ्यावा?")
    types = [e["type"] for e in ev]
    check("उत्तर stream होते", "token" in types and types[-1] == "done")
    check("docx संदर्भ सापडला", any(e["type"] == "sources" and "notes.docx" in e["sources"] for e in ev))
    check("साध्या प्रश्नाला alert नाही", "alert" not in types)
    ev = ask("आईच्या छातीत दुखत आहे, काय करू?")
    check("आपत्कालीन: alert", any(e["type"] == "alert" for e in ev))
    check("आपत्कालीन: AI उपाय नाही, ठरलेले उत्तर", "".join(e.get("t", "") for e in ev) == gs.EMERGENCY_ANSWER)
    ev = ask("गरोदर स्त्रीने अपचनात काय आहार घ्यावा?")
    check("सावधगिरी: alert + उत्तर", any(e["type"] == "alert" for e in ev) and any(e["type"] == "token" for e in ev))
    ag = json.loads(urllib.request.urlopen("http://127.0.0.1:8799/agents").read())
    check("/agents: ज्योतिष agent + शहरे", any(a["id"] == "jyotish" and a["kundali"] for a in ag["agents"])
          and "पुणे" in ag["cities"])
    req = urllib.request.Request("http://127.0.0.1:8799/ask", data=json.dumps(
        {"q": "अपचनात कोणता आहार घ्यावा?", "agent": "jyotish"}).encode(), headers={"Content-Type": "application/json"})
    ev = [json.loads(l) for l in urllib.request.urlopen(req, timeout=20).read().decode().splitlines() if l]
    check("ज्योतिष agent ला आयुर्वेद फाइल्स दिसत नाहीत",
          any(e["type"] == "sources" for e in ev) and not any(e.get("sources") for e in ev))
    req = urllib.request.Request("http://127.0.0.1:8799/kundali", data=json.dumps(
        {"date": "1990-13-45", "time": "6:30", "place": "पुणे"}).encode(), headers={"Content-Type": "application/json"})
    kr = json.loads(urllib.request.urlopen(req, timeout=20).read())
    check("/kundali: चुकीची तारीख -> नम्र error, crash नाही", kr["ok"] is False and kr["msg"])
    _desc = os.path.join(_bk, "images", "p00002_1.png.desc")
    for _ in range(40):
        if os.path.exists(os.path.join(_bk, "चित्र_वर्णन_01.txt")):
            break
        time.sleep(0.5)
    check("चित्र: दृष्टी-मॉडेलने वर्णन लिहिले, शोधण्याजोगी फाइल बनली", os.path.exists(_desc)
          and "पृ. 2 — चित्र 1]" in open(os.path.join(_bk, "चित्र_वर्णन_01.txt"), encoding="utf-8").read())
    req = urllib.request.Request("http://127.0.0.1:8799/ask", data=json.dumps(
        {"q": "रोहिणी नक्षत्राचे चक्र", "agent": "jyotish"}).encode(), headers={"Content-Type": "application/json"})
    ev = [json.loads(l) for l in urllib.request.urlopen(req, timeout=20).read().decode().splitlines() if l]
    _imgs = next((e["images"] for e in ev if e["type"] == "images"), [])
    check("उत्तरासोबत ग्रंथातील चित्र", _imgs and _imgs[0].endswith("images/p00002_1.png"))
    if _imgs:
        _r = urllib.request.urlopen("http://127.0.0.1:8799/img?p=" + urllib.parse.quote(_imgs[0]))
        check("/img: चित्र मिळते", _r.status == 200 and len(_r.read()) > 1000)
    try:
        urllib.request.urlopen("http://127.0.0.1:8799/img?p=" + urllib.parse.quote("../../etc/passwd"))
        check("/img: granth बाहेरील फाइल नाही", False)
    except urllib.error.HTTPError:
        check("/img: granth बाहेरील फाइल नाही", True)
    req = urllib.request.Request("http://127.0.0.1:8799/ask", data=json.dumps(
        {"q": "धर्म शब्दाचा अर्थ सांगा", "agent": "vyakarana"}).encode(), headers={"Content-Type": "application/json"})
    ev = [json.loads(l) for l in urllib.request.urlopen(req, timeout=20).read().decode().splitlines() if l]
    _src = sum((e["sources"] for e in ev if e["type"] == "sources"), [])
    check("व्याकरण agent: शब्दकोशातील अर्थ उत्तराच्या संदर्भात", "वाचस्पत्यम्: धर्म" in _src
          and any("CC BY-SA" in x for x in _src))
    req = urllib.request.Request("http://127.0.0.1:8799/ask", data=json.dumps(
        {"q": "कर्मण्येवाधिकारस्ते मा फलेषु कदाचन । याचा अर्थ सांगा", "agent": "vyakarana"}).encode(),
        headers={"Content-Type": "application/json"})
    ev = [json.loads(l) for l in urllib.request.urlopen(req, timeout=20).read().decode().splitlines() if l]
    _pe = next((e for e in ev if e["type"] == "padaccheda"), None)
    check("उत्तरासोबत पदच्छेद-तक्ता", _pe and _pe["items"][0]["parts"][0]["words"][2][0] == "अधिकारः")
    req = urllib.request.Request("http://127.0.0.1:8799/ask", data=json.dumps(
        {"q": "माझा मृत्यू कधी होईल?", "agent": "jyotish"}).encode(), headers={"Content-Type": "application/json"})
    ev = [json.loads(l) for l in urllib.request.urlopen(req, timeout=20).read().decode().splitlines() if l]
    _t = "".join(e.get("t", "") for e in ev if e["type"] == "token")
    check("ज्योतिष: मृत्यूचे भाकीत -> ठरलेला नकार (AI ला विचारत नाही)", _t.startswith("मृत्यू, आयुष्याची मर्यादा"))
    req = urllib.request.Request("http://127.0.0.1:8799/ask", data=json.dumps(
        {"q": "माझा जन्म 12 जुलै 1977 रात्री 8:30, गाव - खेडेगाव", "agent": "jyotish"}).encode(),
        headers={"Content-Type": "application/json"})
    ev = [json.loads(l) for l in urllib.request.urlopen(req, timeout=20).read().decode().splitlines() if l]
    check("chat मधील जन्म-माहिती, ठिकाण अज्ञात -> अक्षांश-रेखांश मागतो",
          "अक्षांश-रेखांश" in "".join(e.get("t", "") for e in ev))
    page = urllib.request.urlopen("http://127.0.0.1:8799/").read().decode()
    check("chat पान", "ग्रंथसागर" in page)
finally:
    app.terminate(); mock.terminate()
    shutil.rmtree(tmp, ignore_errors=True)

print("\nसर्व tests पास ✅" if not failures else f"\n{failures} test(s) फेल ❌")
sys.exit(1 if failures else 0)
