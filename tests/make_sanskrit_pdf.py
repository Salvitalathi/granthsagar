"""tests/data/sanskrit_hindi.pdf + .txt बनवतो: संस्कृत श्लोक + हिंदी अनुवाद (पान 1 स्वच्छ, पान 2 धूसर/blur scan सारखे).
श्लोक: भगवद्गीता 2.47, 2.20 आणि बृहत्पाराशर होराशास्त्र 1.4 (प्राचीन, मुक्त); हिंदी अनुवाद ग्रंथसागरसाठी नव्याने लिहिलेला."""
import os, random
from PIL import Image, ImageDraw, ImageFont, ImageFilter
F = "/usr/share/fonts/truetype/freefont/FreeSerif.ttf"
W, H = 1240, 1754
sk, hi = ImageFont.truetype(F, 40), ImageFont.truetype(F, 34)
BLOCKS = [
    ("sa", ["कर्मण्येवाधिकारस्ते मा फलेषु कदाचन ।", "मा कर्मफलहेतुर्भूर्मा ते सङ्गोऽस्त्वकर्मणि ॥४७॥"]),
    ("hi", ["तेरा अधिकार केवल कर्म करने में है, उसके फलों में कभी नहीं।",
            "इसलिए तू कर्मफल का कारण मत बन और कर्म न करने में भी",
            "तेरी आसक्ति न हो।"]),
    ("sa", ["न जायते म्रियते वा कदाचिन् नायं भूत्वा भविता वा न भूयः ।",
            "अजो नित्यः शाश्वतोऽयं पुराणो न हन्यते हन्यमाने शरीरे ॥२०॥"]),
    ("hi", ["यह आत्मा किसी काल में न जन्म लेता है और न मरता है।",
            "यह अजन्मा, नित्य, शाश्वत और पुरातन है; शरीर के मारे",
            "जाने पर भी यह नहीं मारा जाता।"]),
    ("sa", ["कथं सृष्टिरियं जाता जगतश्च लयः कथम् ।", "खस्थानां भूस्थितानां च सम्बन्धं वद विस्तरात् ॥४॥"]),
    ("hi", ["यह सृष्टि कैसे उत्पन्न हुई और जगत का लय कैसे होता है? आकाश में",
            "स्थित ग्रहों और पृथ्वी पर रहने वालों का संबंध विस्तार से कहिए।"]),
]
here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
img = Image.new("L", (W, H), 255); d = ImageDraw.Draw(img)
y, truth = 140, []
for kind, lines in BLOCKS:
    for t in lines:
        font = sk if kind == "sa" else hi
        x = (W - d.textlength(t, font=font)) / 2 if kind == "sa" else 110
        d.text((x, y), t, font=font, fill=0, anchor="ls")
        y += 62 if kind == "sa" else 54
        truth.append(t)
    y += 40
    truth.append("")
random.seed(1)
scan = img.filter(ImageFilter.GaussianBlur(1.6)).point(lambda v: min(255, max(0, v + random.randint(-12, 12)) if v > 200 else v))
scan = scan.point(lambda v: 225 if v > 225 else v)                  # पिवळसर/धूसर कागद
noise = Image.effect_noise((W, H), 18)
scan = Image.blend(scan, noise.point(lambda v: v), 0.08).rotate(0.6, fillcolor=225)
img.save(os.path.join(here, "sanskrit_hindi.pdf"), save_all=True, append_images=[scan], resolution=150)
open(os.path.join(here, "sanskrit_hindi.txt"), "w", encoding="utf-8").write("\n".join(truth).strip() + "\n")
print("ok")
