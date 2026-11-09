"""संस्कृत + हिंदी OCR तुलना: python tests/sanskrit_bench.py <tessdata-dir|-> <lang> ...
ground truth: tests/data/sanskrit_hindi.txt; पान 1 स्वच्छ, पान 2 धूसर/blur. संस्कृत ओळी आणि हिंदी ओळी वेगवेगळी अचूकता."""
import sys, os, re, difflib, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pdf_ocr as p
import page_layout as L
ROOT = os.path.dirname(os.path.abspath(__file__))
truth = [l for l in open(os.path.join(ROOT, "data", "sanskrit_hindi.txt"), encoding="utf-8").read().splitlines() if l]
SA = {l for l in truth if "॥" in l or "।" in l and p.is_sanskrit_line(l)}
norm = lambda t: re.sub(r"\s+", " ", t).strip()


def score(text):
    got = [l for l in text.splitlines() if l.strip()]
    res = {"sa": [], "hi": []}
    for t in truth:
        best = max((difflib.SequenceMatcher(None, norm(t), norm(g)).ratio() for g in got), default=0)
        res["sa" if t in SA else "hi"].append(best)
    return {k: sum(v) / len(v) * 100 for k, v in res.items()}


def tsv_lines(png, lang, psm, td):
    cmd = ["tesseract", png, "stdout", "-l", lang, "--psm", psm, "-c", "tessedit_create_tsv=1"] + \
          (["--tessdata-dir", td] if td != "-" else [])
    words = L.parse_tsv(subprocess.run(cmd, capture_output=True).stdout.decode("utf-8", "replace"))
    lines = {}
    for w in words:
        lines.setdefault((w["b"], w["p"], w["l"]), []).append(w)
    out = []
    for ws in lines.values():
        ws.sort(key=lambda w: w["x"])
        out.append({"y0": min(w["y"] for w in ws), "y1": max(w["y"] + w["h"] for w in ws),
                    "conf": sum(w["conf"] for w in ws) / len(ws), "text": " ".join(w["text"] for w in ws)})
    return sorted(out, key=lambda l: l["y0"])


def dual(png, td, psm):
    """प्रत्येक ओळ: hin+san आणि san+hin पैकी जास्त confidence ची"""
    a, b = tsv_lines(png, "hin+san", psm, td), tsv_lines(png, "san+hin", psm, td)
    out = []
    for la in a:
        lb = max(b, key=lambda x: min(la["y1"], x["y1"]) - max(la["y0"], x["y0"]), default=None)
        out.append(lb["text"] if lb and lb["conf"] > la["conf"] + 2 else la["text"])
    return "\n".join(out)


td = sys.argv[1]
pngs = []
for pg in (1, 2):
    png = f"/tmp/sk_page{pg}.png"
    p.render_page(os.path.join(ROOT, "data", "sanskrit_hindi.pdf"), pg, png, 300)
    pngs.append(png)
name = "apt" if td == "-" else os.path.basename(td.rstrip("/"))
for lang in sys.argv[2:]:
    for psm in ("3", "6"):
        for pg, png in enumerate(pngs, 1):
            if lang == "dual":
                raw = dual(png, td, psm)
            else:
                cmd = ["tesseract", png, "stdout", "-l", lang, "--psm", psm] + (["--tessdata-dir", td] if td != "-" else [])
                raw = subprocess.run(cmd, capture_output=True).stdout.decode("utf-8", "replace")
            r, f = score(raw), score(p.clean(raw))
            print(f"| {name} | {lang} | psm{psm} | {'स्वच्छ' if pg == 1 else 'धूसर'} | {r['sa']:.1f} → {f['sa']:.1f} | "
                  f"{r['hi']:.1f} → {f['hi']:.1f} |")
            if lang in ("hin+san", "san+hin") and psm == "3" and name in ("tessdata_best", "apt"):
                print("\n```\n" + p.clean(raw)[:700] + "\n```\n")
