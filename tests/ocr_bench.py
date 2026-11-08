"""OCR मॉडेल्सची तुलना: python tests/ocr_bench.py <tessdata-dir> <lang> ... (ground truth: tests/data/om_mantra.txt)"""
import sys, os, re, difflib, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pdf_ocr as p
ROOT = os.path.dirname(os.path.abspath(__file__))
truth = open(os.path.join(ROOT, "data", "om_mantra.txt"), encoding="utf-8").read()
png = "/tmp/om_page.png"
p.render_page(os.path.join(ROOT, "data", "om_mantra.pdf"), 1, png, 300)
norm = lambda t: re.sub(r"\s+", " ", t.replace("ः:", "ः")).strip()
td = sys.argv[1]
for lang in sys.argv[2:]:
    for psm in ("3", "6"):
        cmd = ["tesseract", png, "stdout", "-l", lang, "--psm", psm] + (["--tessdata-dir", td] if td != "-" else [])
        raw = subprocess.run(cmd, capture_output=True).stdout.decode("utf-8", "replace")
        for stage, txt in (("raw", raw), ("fixed", p.clean(raw))):
            acc = difflib.SequenceMatcher(None, norm(truth), norm(txt)).ratio()
            print(f"| {os.path.basename(td.rstrip('/')) or 'apt'} | {lang} | psm{psm} | {stage} | ॐ {txt.count('ॐ')}/11 | {acc*100:.1f}% |")
        if psm == "3":
            print("```\n" + raw.strip()[:600] + "\n```")
