"""Ollama शिवाय चालणाऱ्या tests (बनावट Ollama server वापरून).  चालवा: python tests/test_offline.py"""
import os, sys, json, time, shutil, zipfile, tempfile, subprocess, urllib.request

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
        shutil.rmtree(_od, ignore_errors=True)
    else:
        print("⏭  hin+san OCR test सोडला (संस्कृत भाषा-फाइल नाही/उतरवता आली नाही)")

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

# ---- 3. App + बनावट Ollama ----
docs = os.path.join(tmp, "granth")
os.makedirs(docs)
shutil.copy(dst, os.path.join(docs, "av.txt"))
with zipfile.ZipFile(os.path.join(docs, "notes.docx"), "w") as z:
    z.writestr("word/document.xml", '<w:document xmlns:w="x"><w:body><w:p><w:r>'
               '<w:t>चरक संहितेनुसार अपचनात हलका आहार घ्यावा.</w:t></w:r></w:p></w:body></w:document>')

env = dict(os.environ, GS_DOCS=docs, GS_PORT="8799", OLLAMA_HOST="http://127.0.0.1:11499",
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
    check("status: 2 फाइल्स", st["ok"] and st["files"] == 2)
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
    page = urllib.request.urlopen("http://127.0.0.1:8799/").read().decode()
    check("chat पान", "ग्रंथसागर" in page)
finally:
    app.terminate(); mock.terminate()
    shutil.rmtree(tmp, ignore_errors=True)

print("\nसर्व tests पास ✅" if not failures else f"\n{failures} test(s) फेल ❌")
sys.exit(1 if failures else 0)
