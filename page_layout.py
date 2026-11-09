"""
पानाची रचना जपणे (OCR नंतर):

  1. अनुक्रमणिका / तक्ते — Tesseract कधी कधी डावा स्तंभ (विषय) आणि उजवा स्तंभ (पान क्रमांक) वेगवेगळे वाचतो,
     त्यामुळे "विषय … पान" जोडी तुटते. इथे शब्दांच्या जागांवरून (x, y) ओळी पुन्हा जुळवल्या जातात:
         प्रथम अध्याय — राशी भेद …… 12      ->      प्रथम अध्याय — राशी भेद … 12
  2. चित्रे (कुंडली, नक्षत्र-चक्र, आकृत्या, फोटो) — मजकूर नसलेला पण शाई असलेला मोठा भाग = चित्र.
     ते जसेच्या तसे PNG म्हणून कापून ठेवले जाते; त्यातील अक्षरे मुख्य मजकुरात गोंधळ घालत नाहीत,
     आणि मजकुरात त्या जागी "🖼 चित्र …" अशी खूण राहते.

फक्त numpy + Pillow लागते.
"""
import re

FIG_MARK = "🖼"
NUM = re.compile(r"^[(\[]?[\d०-९]{1,4}[.)\]]?$")
LEADER = re.compile(r"^[.·•…_\-–—:,]{3,}$|^[.·…]{2,}[\d०-९]*$")
PUNCT_ONLY = re.compile(r"^[.·•…_\-–—:;,'`\"+#*~|]+$")
DOTJUNK = re.compile(r"^[.+#*७०,;:'`]{1,3}$")           # ठिपके कधी '७ ७ ७', '#+' असे वाचले जातात
INDEX_WORDS = ("अनुक्रम", "विषय-सूची", "विषयसूची", "विषयानुक्रम", "सूचीपत्र", "अनुक्रमणिका", "CONTENTS", "Contents")
LETTER = re.compile(r"[ऀ-ॣॱ-ॿA-Za-z]")


# ---------------------------------------------------------------- Tesseract TSV
def parse_tsv(tsv):
    """Tesseract TSV -> शब्दांची यादी {b, p, l, x, y, w, h, conf, text}"""
    words = []
    for row in tsv.splitlines()[1:]:
        c = row.split("\t")
        if len(c) != 12 or c[0] != "5" or not c[11].strip():
            continue
        try:
            words.append({"b": int(c[2]), "p": int(c[3]), "l": int(c[4]), "x": int(c[6]), "y": int(c[7]),
                          "w": int(c[8]), "h": int(c[9]), "conf": float(c[10]), "text": c[11].strip()})
        except ValueError:
            continue
    return words


def _median(xs, default=20):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else default


def is_table_page(words):
    """अनुक्रमणिका/तक्ता आहे का: 'अनुक्रमणिका' शब्द, किंवा भरपूर पान-क्रमांक/ठिपक्यांच्या रेषा"""
    if not words:
        return False
    if any(any(k in w["text"] for k in INDEX_WORDS) for w in words[:40]):
        return True
    n = len(words)
    special = sum(bool(NUM.match(w["text"]) or LEADER.match(w["text"])) for w in words)
    return n >= 15 and special / n >= 0.12


def fix_page_no(t):
    """अनुक्रमणिकेतील पान क्रमांकाच्या नेहमीच्या OCR चुका: ']' -> 1, '[7' -> 17, '4॥' -> 41"""
    if t in ("]", "[", "|", "l", "I"):
        return "1"
    t = re.sub(r"^[\[\]|lI](?=[\d०-९])", "1", t)
    t = re.sub(r"(?<=[\d०-९])[॥।|\]lI]$", "1", t)
    return t.strip(".,:;")


def _leader_runs(line):
    """ओळीतील '७ ७ ७ …' / '#+' अशा ठिपक्यांच्या धावा (≥3 शब्द) ओळखा"""
    flags = [bool(DOTJUNK.match(w["text"])) for w in line]
    out = [False] * len(line)
    i = 0
    while i < len(line):
        if flags[i]:
            j = i
            while j < len(line) and flags[j]:
                j += 1
            if j - i >= 3:
                for k in range(i, j):
                    out[k] = True
            i = j
        else:
            i += 1
    return out


def _join(line, mh, table):
    out, prev = "", None
    runs = _leader_runs(line) if table else [False] * len(line)
    if table and line:                            # शेवटचा शब्द पान क्रमांक असेल तर दुरुस्त करा
        last = line[-1]
        if not LETTER.search(last["text"]) or re.match(r"^[\[\]|lI]?[\d०-९]+[॥।|\]lI]?$", last["text"]):
            last["text"] = fix_page_no(last["text"]) or last["text"]
    for i, w in enumerate(line):
        t = w["text"]
        if re.fullmatch(r"[-–—]{1,3}", t):          # '--' = '—'
            t = "—"
        elif LEADER.match(t) or runs[i] or (table and PUNCT_ONLY.match(t)):   # ……… -> एक '…'
            if table and out and not out.endswith(" … "):
                out = out.rstrip() + " … "
            prev = w
            continue
        t = re.sub(r"^--+(?=\S)|(?<=\S)--+$", "—", t)
        if prev is not None and out and not out.endswith(" … "):
            gap = w["x"] - (prev["x"] + prev["w"])
            out += " … " if table and gap > 2.5 * mh else " "
        out += t
        prev = w
    return re.sub(r"\s+", " ", out).strip(" …") if out.strip(" …") else ""


def layout_lines(words, table=None):
    """शब्द -> [(y, ओळ)] ; तक्ता असेल तर जागेनुसार (y) ओळी, नाहीतर Tesseract चा क्रम (परिच्छेद जपून)"""
    if not words:
        return []
    if table is None:
        table = is_table_page(words)
    mh = _median([w["h"] for w in words])
    if table:
        rows = []
        for w in sorted(words, key=lambda w: w["y"] + w["h"] / 2):
            c = w["y"] + w["h"] / 2
            if rows and abs(c - rows[-1]["c"]) <= 0.6 * mh:
                r = rows[-1]; r["ws"].append(w); r["c"] = (r["c"] * (len(r["ws"]) - 1) + c) / len(r["ws"])
            else:
                rows.append({"c": c, "ws": [w]})
        out = []
        for r in rows:
            t = _join(sorted(r["ws"], key=lambda w: w["x"]), mh, True)
            if t:
                out.append((min(w["y"] for w in r["ws"]), t))
        return out
    groups, order = {}, []
    for w in words:
        k = (w["b"], w["p"], w["l"])
        if k not in groups:
            groups[k] = []; order.append(k)
        groups[k].append(w)
    out, last_par = [], None
    for k in order:
        t = _join(sorted(groups[k], key=lambda w: w["x"]), mh, False)
        if not t:
            continue
        if last_par is not None and k[:2] != last_par:
            out.append((min(w["y"] for w in groups[k]) - 0.1, ""))      # परिच्छेद
        out.append((min(w["y"] for w in groups[k]), t))
        last_par = k[:2]
    return out


# ---------------------------------------------------------------- चित्रे
def _otsu(a):
    import numpy as np
    hist = np.bincount(a.ravel(), minlength=256).astype(float)
    total = a.size
    sum_all = float((np.arange(256) * hist).sum())
    wb = sb = 0.0
    best, t_best = -1.0, 128
    for t in range(256):
        wb += hist[t]
        if wb == 0 or wb == total:
            continue
        sb += t * hist[t]
        mb, mf = sb / wb, (sum_all - sb) / (total - wb)
        between = wb * (total - wb) * (mb - mf) ** 2
        if between > best:
            best, t_best = between, t
    return t_best


def find_figures(gray, text_boxes, min_w=0.15, min_h=0.08):
    """gray: पानाचे greyscale चित्र (numpy uint8, H x W); text_boxes: [(x, y, w, h)] खऱ्या मजकुराचे.
    परत: चित्रांचे [(x0, y0, x1, y1)] (pixels)"""
    import numpy as np
    H, W = gray.shape
    s = max(1, round(max(H, W) / 1400))                 # विश्लेषणासाठी लहान प्रत (~1400 px)
    g = gray[::s, ::s]
    h, w = g.shape
    t = min(_otsu(g), 200)
    ink = g <= t
    if ink.mean() > 0.5:                                # उलटे (काळी पार्श्वभूमी) — सोडा
        return []
    pad = 2
    for (x, y, bw, bh) in text_boxes:                   # मजकूर काढून टाका
        ink[max(0, y // s - pad):(y + bh) // s + pad, max(0, x // s - pad):(x + bw) // s + pad] = False
    cell = 10
    gh, gw = h // cell, w // cell
    if gh < 3 or gw < 3:
        return []
    frac = ink[:gh * cell, :gw * cell].reshape(gh, cell, gw, cell).mean(axis=(1, 3))
    grid = frac > 0.025
    near = grid.copy()                                  # जवळचे भाग जोडा (रेषा, लहान फट)
    near[1:, :] |= grid[:-1, :]; near[:-1, :] |= grid[1:, :]
    near[:, 1:] |= grid[:, :-1]; near[:, :-1] |= grid[:, 1:]
    seen = np.zeros_like(near)
    figs = []
    for i in range(gh):
        for j in range(gw):
            if not near[i, j] or seen[i, j]:
                continue
            stack, cells = [(i, j)], []
            seen[i, j] = True
            while stack:
                a, b = stack.pop()
                cells.append((a, b))
                for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    na, nb = a + da, b + db
                    if 0 <= na < gh and 0 <= nb < gw and near[na, nb] and not seen[na, nb]:
                        seen[na, nb] = True
                        stack.append((na, nb))
            rows = [c[0] for c in cells]; cols = [c[1] for c in cells]
            r0, r1, c0, c1 = min(rows), max(rows) + 1, min(cols), max(cols) + 1
            fw, fh = (c1 - c0) / gw, (r1 - r0) / gh
            real = int(grid[r0:r1, c0:c1].sum())
            if fw < min_w or fh < min_h or real < 20:
                continue
            if fw > 0.85 and fh > 0.85 and real / ((r1 - r0) * (c1 - c0)) < 0.2:
                continue                                 # पानाभोवतीची चौकट
            if fh < 0.03 or fw < 0.03:
                continue                                 # नुसत्या रेषा
            figs.append((c0 * cell * s, r0 * cell * s, min(W, c1 * cell * s), min(H, r1 * cell * s)))
    # एकमेकांत घुसलेली चित्रे एक करा
    figs.sort()
    merged = []
    for f in figs:
        for k, m in enumerate(merged):
            if f[0] <= m[2] and m[0] <= f[2] and f[1] <= m[3] and m[1] <= f[3]:
                merged[k] = (min(f[0], m[0]), min(f[1], m[1]), max(f[2], m[2]), max(f[3], m[3]))
                break
        else:
            merged.append(f)
    return sorted(merged, key=lambda f: (f[1], f[0]))


def real_text_boxes(words, min_conf=50):
    """खात्रीचे शब्द (अक्षरे असलेले, confidence ≥ 50) — चित्र शोधताना हे वगळायचे"""
    return [(w["x"], w["y"], w["w"], w["h"]) for w in words
            if w["conf"] >= min_conf and len(LETTER.findall(w["text"])) >= 2]


def inside(w, box, margin=4):
    cx, cy = w["x"] + w["w"] / 2, w["y"] + w["h"] / 2
    return box[0] - margin <= cx <= box[2] + margin and box[1] - margin <= cy <= box[3] + margin


def save_crop(img, box, path, max_side=1400, pad=12):
    """PIL चित्रातून box कापून PNG (मोठे असेल तर लहान)"""
    W, H = img.size
    crop = img.crop((max(0, box[0] - pad), max(0, box[1] - pad), min(W, box[2] + pad), min(H, box[3] + pad)))
    if max(crop.size) > max_side:
        r = max_side / max(crop.size)
        crop = crop.resize((max(1, int(crop.size[0] * r)), max(1, int(crop.size[1] * r))))
    crop.save(path, optimize=True)
    return path


def figure_line(k, rel, labels):
    lab = " ".join(labels)[:200]
    return f"{FIG_MARK} चित्र {k}: {rel}" + (f" — चित्रातील अक्षरे: {lab}" if lab else "")


def ocr_page_layout(words, img, fig_dir, page, find=True, table=None, label_fn=None):
    """OCR शब्द + पानाचे चित्र -> (मजकूर, [चित्र-फाइल्स]). चित्रे fig_dir मध्ये p00012_1.png नावाने.
    label_fn(png) -> चित्रातील शब्द (उदा. कुंडलीतील ग्रह-अक्षरे) — Tesseract 'sparse' पद्धतीने"""
    import os
    import numpy as np
    figs = []
    if find and img is not None:
        try:
            figs = find_figures(np.asarray(img.convert("L")), real_text_boxes(words))
        except Exception:
            figs = []
    labels = [[] for _ in figs]
    body = []
    for w in words:
        k = next((i for i, f in enumerate(figs) if inside(w, f)), None)
        if k is None:
            body.append(w)
        elif w["conf"] >= 30 and LETTER.search(w["text"]) or NUM.match(w["text"]):
            labels[k].append(w["text"])
    lines = layout_lines(body, table)
    files, marks = [], []
    for k, f in enumerate(figs, 1):
        name = f"p{page:05d}_{k}.png"
        save_crop(img, f, os.path.join(fig_dir, name))
        files.append(name)
        if label_fn and not labels[k - 1]:
            try:
                got = [t for t in label_fn(os.path.join(fig_dir, name)) if LETTER.search(t) or NUM.match(t)]
                if sum(bool(LETTER.search(t)) for t in got) >= 3:      # नाहीतर नुसता गोंधळ
                    labels[k - 1] = got[:60]
            except Exception:
                pass
        marks.append((f[1], figure_line(k, "images/" + name, labels[k - 1])))
    out = []                         # ओळींचा क्रम तसाच (दोन स्तंभ असले तरी); चित्राची खूण त्याच्या उंचीवर
    for y, t in lines:
        while marks and marks[0][0] <= y:
            out += ["", marks.pop(0)[1], ""]
        out.append(t)
    for _, m in marks:
        out += ["", m]
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip(), files
