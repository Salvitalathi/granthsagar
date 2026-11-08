"""
ग्रंथ तयार करा — internet वरून उतरवलेले संस्कृत ग्रंथ "ग्रंथसागर" साठी तयार करणे.

काय करतो:
  * GRETIL सारख्या sites चे romanized (IAST) मजकूर देवनागरीत रूपांतरित करतो
      ye triṣaptāḥ pariyanti  ->  ये त्रिषप्ताः परियन्ति
  * ओळीच्या सुरुवातीचा संदर्भ (उदा. AVŚ_1,1.1a) ठेवून [अथर्ववेद 1.1.1a] असा करतो,
    म्हणजे AI उत्तरात नेमका श्लोक सांगू शकतो
  * आधीच देवनागरीत असलेल्या किंवा इंग्रजी भाषांतराच्या फाइल्स तशाच ठेवतो
  * तयार फाइल्स "granth" folder मध्ये टाकतो

वापर:
  1. उतरवलेल्या .txt फाइल्स "granth_raw" folder मध्ये ठेवा
  2. python granth_tayar.py
  3. मग python granthsagar.py  (किंवा chat मध्ये "फाइल्स पुन्हा वाचा")

स्वतःचे नाव द्यायचे असल्यास (उदा. AVŚ -> अथर्ववेद) खालील NAMES मध्ये जोडा.
"""
import os, re, sys, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "granth_raw")
OUT = os.path.join(HERE, "granth", "sanskrit")

# संक्षेप -> पूर्ण नाव (हवे तसे वाढवा)
NAMES = {
    "AVŚ": "अथर्ववेद (शौनक)", "AVS": "अथर्ववेद (शौनक)", "AV": "अथर्ववेद",
    "AVP": "अथर्ववेद (पैप्पलाद)", "PS": "अथर्ववेद (पैप्पलाद)",
    "Car": "चरक संहिता", "CS": "चरक संहिता", "Ca": "चरक संहिता",
    "Su": "सुश्रुत संहिता", "SS": "सुश्रुत संहिता",
    "AHS": "अष्टांगहृदय", "AH": "अष्टांगहृदय",
}

# ---------------- IAST -> देवनागरी ----------------
VOWELS = {"a": "अ", "ā": "आ", "i": "इ", "ī": "ई", "u": "उ", "ū": "ऊ", "ṛ": "ऋ", "ṝ": "ॠ",
          "ḷ": "ऌ", "e": "ए", "ai": "ऐ", "o": "ओ", "au": "औ"}
MATRAS = {"a": "", "ā": "ा", "i": "ि", "ī": "ी", "u": "ु", "ū": "ू", "ṛ": "ृ", "ṝ": "ॄ",
          "ḷ": "ॢ", "e": "े", "ai": "ै", "o": "ो", "au": "ौ"}
CONS = {"kh": "ख", "gh": "घ", "ch": "छ", "jh": "झ", "ṭh": "ठ", "ḍh": "ढ", "th": "थ", "dh": "ध",
        "ph": "फ", "bh": "भ", "k": "क", "g": "ग", "ṅ": "ङ", "c": "च", "j": "ज", "ñ": "ञ",
        "ṭ": "ट", "ḍ": "ड", "ṇ": "ण", "t": "त", "d": "द", "n": "न", "p": "प", "b": "ब",
        "m": "म", "y": "य", "r": "र", "l": "ल", "v": "व", "ś": "श", "ṣ": "ष", "s": "स",
        "h": "ह", "ḻ": "ळ", "ḻh": "ळ्ह"}
OTHER = {"ṃ": "ं", "ṁ": "ं", "ḥ": "ः", "m̐": "ँ", "'": "ऽ", "’": "ऽ", "||": "॥", "|": "।",
         "//": "॥", "/": "।"}
DIGITS = str.maketrans("0123456789", "०१२३४५६७८९")
VIRAMA = "्"
IAST_MARK = re.compile(r"[āīūṛṝḷṅñṭḍṇśṣṃṁḥ]")


def _match(s, i, table):
    for L in (3, 2, 1):
        if s[i:i + L] in table:
            return s[i:i + L]
    return None


def iast_to_deva(text, digits=False):
    s = unicodedata.normalize("NFC", text).lower()
    s = s.replace("ṁ", "ṃ").replace("ṟ", "r")
    out, i = [], 0
    while i < len(s):
        c = _match(s, i, CONS)
        if c:
            out.append(CONS[c]); i += len(c)
            v = _match(s, i, MATRAS)
            if v:
                # "a" + "i"/"u" वेगळे अक्षर असण्याची शक्यता सोडून नेहमी ai/au घेतो
                out.append(MATRAS[v]); i += len(v)
            else:
                out.append(VIRAMA)
            continue
        v = _match(s, i, VOWELS)
        if v:
            out.append(VOWELS[v]); i += len(v); continue
        o = _match(s, i, OTHER)
        if o:
            out.append(OTHER[o]); i += len(o); continue
        out.append(s[i]); i += 1
    res = "".join(out)
    return res.translate(DIGITS) if digits else res


# ---------------- GRETIL फाइल स्वच्छ करणे ----------------
REF = re.compile(r"^\s*([A-ZĀŚṢ][A-Za-zĀŚṢ]{0,5})[_\s.]?([\d][\d.,:]*[a-f]?)\s*[:.]?\s+(.*)$")
TRAIL_REF = re.compile(r"\s*//\s*([A-ZĀŚṢ][A-Za-zĀŚṢ]{0,5})[_\s.]?([\d][\d.,:]*[a-f]?)\s*//\s*$")


EN_WORDS = re.compile(r"\b(the|and|of|is|to|with|in|for|that|which|by)\b", re.I)


def looks_english(line):
    """IAST फाइलमध्ये इंग्रजी भाषांतराच्या ओळी असतील तर त्या रूपांतरित करू नका."""
    return len(EN_WORDS.findall(line)) >= 2 and not IAST_MARK.search(line)


def pretty_ref(abbr, num):
    name = NAMES.get(abbr, NAMES.get(abbr.rstrip("_"), abbr))
    return f"[{name} {num.replace(',', '.').strip('.')}]"


def strip_header(lines):
    """GRETIL फाइल्समध्ये वर license/माहिती असते; '# Text' नंतरचा भाग घ्या."""
    for k, ln in enumerate(lines):
        if re.match(r"^\s*#\s*text\s*$", ln, flags=re.I):
            return lines[k + 1:]
    return lines


def convert_file(src, dst):
    with open(src, encoding="utf-8-sig", errors="replace") as f:
        lines = strip_header(f.read().splitlines())
    roman = sum(bool(IAST_MARK.search(l)) for l in lines)
    deva = sum(bool(re.search(r"[ऀ-ॿ]", l)) for l in lines)
    nonempty = sum(bool(l.strip()) for l in lines) or 1
    is_iast = roman > deva and roman >= 0.1 * nonempty
    out = []
    for ln in lines:
        ln = ln.rstrip()
        if not ln.strip():
            out.append(""); continue
        ref = ""
        m = TRAIL_REF.search(ln)
        if m:
            ref = pretty_ref(m.group(1), m.group(2)); ln = ln[:m.start()]
        else:
            m = REF.match(ln)
            if m and is_iast:
                ref = pretty_ref(m.group(1), m.group(2)); ln = m.group(3)
        body = iast_to_deva(ln) if is_iast and not looks_english(ln) else ln
        out.append(f"{ref} {body}".strip())
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(out).strip() + "\n")
    return is_iast, len(out)


def main():
    for st in (sys.stdout, sys.stderr):
        try: st.reconfigure(encoding="utf-8")
        except Exception: pass
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print(iast_to_deva("ye triṣaptāḥ pariyanti viśvā rūpāṇi bibhrataḥ |"))
        return
    os.makedirs(RAW, exist_ok=True)
    files = [f for f in sorted(os.listdir(RAW)) if f.lower().endswith((".txt", ".md"))]
    if not files:
        print(f"'{RAW}' मध्ये .txt फाइल्स टाका आणि पुन्हा चालवा.")
        return
    for fn in files:
        dst = os.path.join(OUT, os.path.splitext(fn)[0] + ".txt")
        is_iast, n = convert_file(os.path.join(RAW, fn), dst)
        print(f"✅ {fn}: {n} ओळी {'(देवनागरीत रूपांतरित)' if is_iast else '(जशी आहे तशी)'}")
    print(f"\nतयार फाइल्स: {OUT}\nआता 'ग्रंथसागर' मध्ये '📂 फाइल्स पुन्हा वाचा' दाबा.")


if __name__ == "__main__":
    main()
