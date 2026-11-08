"""एका lang/psm चे raw आणि clean() नंतरचे output शेजारी: python tests/ocr_debug.py mar+san 6"""
import sys, os, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pdf_ocr as p
ROOT = os.path.dirname(os.path.abspath(__file__))
pdf = os.path.join(ROOT, "data", sys.argv[3] if len(sys.argv) > 3 else "om_mantra.pdf")
p.render_page(pdf, 1, "/tmp/dbg.png", 300)
raw = subprocess.run(["tesseract", "/tmp/dbg.png", "stdout", "-l", sys.argv[1], "--psm", sys.argv[2]],
                     capture_output=True).stdout.decode("utf-8", "replace")
print(f"### {sys.argv[1]} psm{sys.argv[2]} {os.path.basename(pdf)}\n--- RAW ---\n{raw}\n--- CLEAN ---\n{p.clean(raw)}\n")
