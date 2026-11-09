import json, urllib.request, urllib.parse
UA = {"User-Agent": "granthsagar-research/1.0 (study project)"}
def get(url, n=None):
    req = urllib.request.Request(url, headers=dict(UA, **({"Range": f"bytes=0-{n}"} if n else {})))
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read(), r.headers
G = "https://gretil.sub.uni-goettingen.de/gretil/corpustei/transformations/plaintext/"
for n in ["sa_pANini-aSTAdhyAyI", "sa_pANini-aSTAdhyAyI-sUtrapATha", "sa_aSTAdhyAyI", "sa_vAmana-jayAditya-kAzikAvRtti",
          "sa_jayAditya-vAmana-kAzikAvRtti", "sa_kAzikAvRtti", "sa_vAmana-jayAditya-kAzikA",
          "sa_pataJjali-vyAkaraNamahAbhASya", "sa_pataJjali-mahAbhASya", "sa_patJjali-vyAkaraNamahAbhASya",
          "sa_vyAkaraNamahAbhASya", "sa_pANini-dhAtupATha", "sa_amarasiMha-nAmaliGgAnuzAsana", "sa_bhaTTojidIkSita-siddhAntakaumudI",
          "sa_varadarAja-laghusiddhAntakaumudI"]:
    try:
        b, h = get(G + n + ".txt", 3000)
        t = b.decode("utf-8", "replace")
        body = t.split("# Text")[-1] if "# Text" in t else t[-900:]
        print(f"\n### FOUND {n}  size={h.get('Content-Range')}\n" + "\n".join("  | " + l for l in body.strip().splitlines()[:12]))
    except Exception as e:
        print(f"--- {n}: {e}")
W = "https://sa.wikisource.org/w/api.php?"
for q in ["अष्टाध्यायी", "काशिका", "महाभाष्यम्", "व्याकरणमहाभाष्यम्", "सिद्धान्तकौमुदी", "धातुपाठः"]:
    try:
        r = json.loads(get(W + urllib.parse.urlencode({"action": "query", "list": "search", "format": "json",
                                                        "srlimit": 6, "srsearch": q}))[0])["query"]["search"]
        print(f"\n## wiki {q}: " + " | ".join(f"{x['title']} ({x['size']}B)" for x in r))
        r = json.loads(get(W + urllib.parse.urlencode({"action": "query", "list": "allpages", "format": "json",
                                                        "aplimit": 8, "apprefix": q}))[0])["query"]["allpages"]
        print("   prefix: " + " | ".join(x["title"] for x in r))
    except Exception as e:
        print("wiki ERR", q, e)
