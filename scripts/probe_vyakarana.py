"""व्याकरण-ग्रंथांचे digital स्रोत तपासणे (आकार, परवाना, नमुना). CI मध्ये चालते."""
import json, re, urllib.request
UA = {"User-Agent": "granthsagar-research/1.0 (study project)"}
def get(url, n=None):
    req = urllib.request.Request(url, headers=dict(UA, **({"Range": f"bytes=0-{n}"} if n else {})))
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read(), r.headers
def head(url):
    try:
        b, h = get(url, 1500)
        print(f"\n### {url}\n  size={h.get('Content-Range') or h.get('Content-Length')}\n" +
              "\n".join("  | " + l for l in b.decode('utf-8', 'replace').splitlines()[:25]))
    except Exception as e:
        print(f"\n### {url}\n  ERR {e}")
R = "https://raw.githubusercontent.com/sanskrit-lexicon/csl-orig/master/"
for p in ["README.md", "LICENSE", "v02/vcp/vcp.txt", "v02/skd/skd.txt", "v02/vcp/vcpheader.xml", "v02/skd/skdheader.xml"]:
    head(R + p)
api = "https://api.github.com/repos/sanskrit-lexicon/csl-orig"
try:
    d = json.loads(get(api)[0]); print("\nrepo license:", d.get("license"), "size KB:", d.get("size"))
except Exception as e:
    print("api ERR", e)
for repo in ["ashtadhyayi-com/data", "sanskrit/ashtadhyayi", "drdhaval2785/SanskritVerb"]:
    try:
        d = json.loads(get("https://api.github.com/repos/" + repo)[0])
        print(f"\nrepo {repo}: license={d.get('license')} size={d.get('size')} desc={d.get('description')}")
        t = json.loads(get(f"https://api.github.com/repos/{repo}/contents")[0])
        print("  files:", [x["name"] for x in t][:40])
    except Exception as e:
        print("repo ERR", repo, e)
# GRETIL: व्याकरण फाइल्स
try:
    idx = get("https://gretil.sub.uni-goettingen.de/gretil/corpustei/transformations/plaintext/")[0].decode("utf-8", "replace")
    names = sorted(set(re.findall(r'href="([^"]+\.txt)"', idx)))
    for n in names:
        if re.search(r"kAzik|mahAbhA|aSTAdhy|pANin|patJjal|vyAkar|dhAtup|siddhAntakaum|amara", n, re.I):
            head("https://gretil.sub.uni-goettingen.de/gretil/corpustei/transformations/plaintext/" + n)
except Exception as e:
    print("gretil ERR", e)
