import json, re, urllib.request, urllib.parse
UA = {"User-Agent": "granthsagar-research/1.0 (study project)"}
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read().decode("utf-8", "replace")
G = "https://gretil.sub.uni-goettingen.de/gretil/corpustei/transformations/plaintext/"
mb = get(G + "sa_pataJjali-vyAkaraNamahAbhASya.txt")
i = mb.find("# Text"); print("MB header:\n", mb[:i][-1500:])
body = mb[i:]
for pos in (5000, 200000, 2000000):
    print(f"\n--- MB @{pos}\n", body[pos:pos + 900])
print("\nMB marker kinds:", sorted(set(re.findall(r"\((\w+?)_?\d", body)))[:30])
print("P-refs sample:", re.findall(r"\(P_[^)]{1,20}\)|p_\d,\d\.\d+", body)[:20])
a = get(G + "sa_pANini-aSTAdhyAyI.txt"); i = a.find("# Text"); print("\nASHT header tail:\n", a[:i][-600:])
l = get(G + "sa_varadarAja-laghusiddhAntakaumudI.txt"); i = l.find("# Text"); print("\nLSK @10000:\n", l[i + 10000:i + 11200])
W = "https://sa.wikisource.org/w/index.php?"
t = get(W + urllib.parse.urlencode({"title": "काशिका/प्रथमोऽध्यायः/प्रथमः पादः", "action": "raw"}))
print("\nKASHIKA 1.1 size", len(t), "\n", t[:2500])
t = get(W + urllib.parse.urlencode({"title": "अष्टाध्यायी/प्रथमः अध्यायः", "action": "raw"}))
print("\nWIKI ASHT size", len(t), "\n", t[:800])
