"""खरे वाचस्पत्यम्/शब्दकल्पद्रुम उतरवून शब्दकोश बनतो का आणि शब्द सापडतात का (CI)"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GS_KOSHA_DIR", "/tmp/kosha")
import kosha
t0 = time.time()
n = kosha.build(print)
print(f"⏱ {time.time() - t0:.0f} से., db {os.path.getsize(kosha.DB) / 1e6:.0f} MB, {n} शब्द")
for w in ["धर्म", "धर्मः", "रामः", "अग्निः", "ज्योतिषम्", "ग्रह", "नक्षत्रम्", "व्याकरणम्", "गुण", "आयुर्वेद", "ॐ"]:
    r = kosha.lookup(w, 400)
    print(f"\n## {w}: {len(r)}")
    for name, k, t in r[:2]:
        print(f"  [{name} — {k}] {t[:400]}")
print("\nप्रश्न:", kosha.words_in("\"नक्षत्र\" शब्दाची व्युत्पत्ती शब्दकल्पद्रुम मध्ये काय आहे?"))
