"""sanskrit_parser Python 3.12 वर चालतो का, वेग आणि गुणवत्ता (CI)"""
import time, sys, subprocess
t0 = time.time()
from sanskrit_parser import Parser
p = Parser(output_encoding="devanagari", input_encoding="devanagari", lexical_lookup="combined")
print("load", round(time.time() - t0, 1), "s")
TESTS = ["कर्मण्येवाधिकारस्ते", "मा कर्मफलहेतुर्भूर्मा ते सङ्गोऽस्त्वकर्मणि", "अजो नित्यः शाश्वतोऽयं पुराणो",
         "कथं सृष्टिरियं जाता जगतश्च लयः कथम्", "रामो लङ्कां याति", "पप्रच्छोपेत्य मैत्रेयः प्रणिपत्य कृताञ्जलिः",
         "मूर्तित्वे परिकल्पितः शशभृतो वर्त्मापुनर्जन्मनाम्"]
for s in TESTS:
    t0 = time.time()
    try:
        splits = p.split(s, limit=3)
        print(f"\n## {s}  ({time.time() - t0:.1f}s)")
        for sp in (splits or [])[:3]:
            print("  ", sp)
        if splits:
            try:
                parses = list(splits[0].parse(limit=1))
                for pr in parses[:1]:
                    print("   parse:", pr)
            except Exception as e:
                print("   parse ERR", e)
    except Exception as e:
        print(f"\n## {s}: ERR {type(e).__name__} {e}")
