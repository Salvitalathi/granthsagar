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
    check("गंभीर लक्षणाला alert", any(e["type"] == "alert" for e in ev))
    page = urllib.request.urlopen("http://127.0.0.1:8799/").read().decode()
    check("chat पान", "ग्रंथसागर" in page)
finally:
    app.terminate(); mock.terminate()
    shutil.rmtree(tmp, ignore_errors=True)

print("\nसर्व tests पास ✅" if not failures else f"\n{failures} test(s) फेल ❌")
sys.exit(1 if failures else 0)
