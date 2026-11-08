"""पूर्ण प्रवाह (भाषा ओळख + OCR) एका PDF वर: python tests/ocr_debug.py sample_scan.pdf"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pdf_ocr as p
ROOT = os.path.dirname(os.path.abspath(__file__))
for name in sys.argv[1:]:
    out = tempfile.mkdtemp()
    n, d = p.process_pdf(os.path.join(ROOT, "data", name), name, out, lang="auto", jobs=1, progress=print)
    print(open(os.path.join(d, "part_01.txt"), encoding="utf-8").read()[:500], "\n")
