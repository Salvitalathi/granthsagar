"""copyright-मुक्त ज्योतिष ग्रंथ शोधणे: archive.org (1929 पूर्वी) आणि sa.wikisource"""
import json, sys, urllib.request, urllib.parse
UA = {"User-Agent": "granthsagar-research/1.0 (study project)"}
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()
queries = sys.argv[1:] or ["brihat jataka", "brihat samhita", "parasara hora", "saravali", "phaladeepika",
                           "jataka parijata", "surya siddhanta", "hora sara", "laghu jataka", "jyotisha"]
for q in queries:
    u = ("https://archive.org/advancedsearch.php?q=" + urllib.parse.quote(f'title:({q}) AND date:[1700-01-01 TO 1928-12-31] AND mediatype:texts')
         + "&fl[]=identifier&fl[]=title&fl[]=date&fl[]=language&rows=12&output=json")
    try:
        docs = json.loads(get(u))["response"]["docs"]
    except Exception as e:
        print("ERR", q, e); continue
    print(f"\n## archive.org: {q} ({len(docs)})")
    for d in docs:
        print(f"  {d.get('date','')[:4]} | {d['identifier']} | {str(d.get('title',''))[:90]} | {d.get('language','')}")
for t in ["बृहत्पाराशरहोराशास्त्रम्", "बृहज्जातकम्", "सारावली", "फलदीपिका", "जातकपारिजातः", "होरासारः"]:
    u = "https://sa.wikisource.org/w/api.php?action=query&list=search&format=json&srlimit=5&srsearch=" + urllib.parse.quote(t)
    try:
        res = json.loads(get(u))["query"]["search"]
        print(f"\n## wikisource: {t}: " + " | ".join(f"{r['title']} ({r['size']}B)" for r in res))
    except Exception as e:
        print("ERR wikisource", t, e)
