"""
विषयवार agents — agents.json मधून.

प्रत्येक agent:
  folders  — granth/ मधील कोणते folders त्याचे (रिकामे = सर्व)
  inbox    — pdf_inbox/<inbox>/ मध्ये टाकलेल्या PDF चा मजकूर granth/pdf/<inbox>/ मध्ये जातो → आपोआप याच agent चा
  intro    — उत्तराची रचना (रिकामे = ग्रंथसागरची सर्वसाधारण रचना)
  rules    — या विषयाचे कडक नियम (सर्वसाधारण नियमांच्या जोडीला)
  kundali_intro — (ज्योतिष) जन्मकुंडली दिली असेल तेव्हाची उत्तर-रचना: फलादेश, फक्त संदर्भ नव्हे
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
AGENTS_FILE = os.path.join(HERE, "agents.json")
DEFAULT = "sarva"

# वापरकर्त्याच्या PDF (granth/pdf/) बहुतेक आधुनिक प्रकाशने/भाष्ये असतात — त्यांचा आशय सांगा, लांब उतारे नकोत.
MODERN_PREFIX = ("pdf/",)
SOURCE_TAG_FREE = "मूळ ग्रंथ — श्लोक जसाच्या तसा उद्धृत करू शकतोस"
SOURCE_TAG_MODERN = "आधुनिक प्रकाशन/भाष्य — मूळ श्लोक उद्धृत कर, पण भाष्य/अनुवादाचे लांब उतारे नकोत, आशय स्वतःच्या शब्दांत सांग"


def load():
    with open(AGENTS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    ids = set()
    for a in data:
        assert a["id"] not in ids, f"agents.json: '{a['id']}' दोनदा"
        ids.add(a["id"])
        a["folders"] = [x.strip("/\\").replace("\\", "/") for x in a.get("folders", [])]
        for k in ("intro", "rules", "examples"):
            a.setdefault(k, [])
    return data


AGENTS = load()
BY_ID = {a["id"]: a for a in AGENTS}


def get(agent_id):
    return BY_ID.get(agent_id or DEFAULT) or BY_ID[DEFAULT]


def norm(name):
    return name.replace("\\", "/")


def owns(agent, name):
    """granth/ मधील ही फाइल (relative नाव) या agent ची आहे का"""
    if not agent["folders"]:
        return True
    n = norm(name)
    return any(n == f or n.startswith(f + "/") for f in agent["folders"])


def is_modern(name):
    return norm(name).startswith(MODERN_PREFIX)


def source_tag(name):
    return SOURCE_TAG_MODERN if is_modern(name) else SOURCE_TAG_FREE


def inbox_subjects():
    """pdf_inbox मधील विषय-folders: {'ज्योतिष': 'jyotish', …}"""
    return {a["inbox"]: a["id"] for a in AGENTS if a.get("inbox")}


def prompt(agent, base_prompt, kundali=False):
    """agent चा system prompt. intro नसेल तर सर्वसाधारण prompt; rules नेहमी जोडले जातात.
    kundali=True आणि agent मध्ये kundali_intro असेल तर तो (फलादेशाची रचना) वापरला जातो."""
    intro = agent.get("kundali_intro") if kundali and agent.get("kundali_intro") else agent["intro"]
    p = "\n".join(intro) if intro else base_prompt
    if agent["rules"]:
        p += "\n\n" + agent["name"] + " — विशेष नियम:\n" + "\n".join("- " + r for r in agent["rules"])
    p += ("\n\nसंदर्भातील प्रत्येक तुकड्यासोबत त्याचा प्रकार दिला आहे: 'मूळ ग्रंथ' असेल तर श्लोक पूर्ण उद्धृत कर; "
          "'आधुनिक' असेल तर मूळ श्लोक उद्धृत कर पण भाष्य/अनुवादाचा आशय स्वतःच्या शब्दांत सांग.")
    return p


def public_list():
    return [{"id": a["id"], "name": a["name"], "icon": a.get("icon", ""), "about": a.get("about", ""),
             "inbox": a.get("inbox"), "kundali": bool(a.get("kundali")), "examples": a["examples"]}
            for a in AGENTS]
