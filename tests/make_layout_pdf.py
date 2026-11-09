"""tests/data/layout_jyotish.pdf बनवतो: अनुक्रमणिका (ठिपक्यांच्या रेषा + उजवीकडे पान क्रमांक) आणि कुंडली-चित्र असलेले पान.
(Pillow + raqm + FreeSerif लागते; तयार PDF repo मध्ये आहे — CI मध्ये पुन्हा बनवत नाही)"""
import os
from PIL import Image, ImageDraw, ImageFont
F = "/usr/share/fonts/truetype/freefont/FreeSerif.ttf"
W, H = 1240, 1754
big, mid, small = (ImageFont.truetype(F, s) for s in (52, 36, 30))
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "layout_jyotish.pdf")

p1 = Image.new("L", (W, H), 255); d = ImageDraw.Draw(p1)
d.text((W // 2, 140), "अनुक्रमणिका", font=big, fill=0, anchor="mm")
rows = [("प्रथम अध्याय — राशी भेद", 1), ("द्वितीय अध्याय — ग्रह स्वरूप", 9), ("तृतीय अध्याय — नक्षत्र विचार", 17),
        ("चतुर्थ अध्याय — भाव फल", 28), ("पंचम अध्याय — योग विचार", 41), ("षष्ठ अध्याय — दशा फल", 56),
        ("सप्तम अध्याय — कुंडली मिलान", 70), ("अष्टम अध्याय — मुहूर्त", 88)]
for i, (t, n) in enumerate(rows):
    y = 300 + i * 95
    d.text((140, y), t, font=mid, fill=0, anchor="ls")
    x = 140 + d.textlength(t, font=mid) + 20
    while x < 1010:
        d.text((x, y), ".", font=mid, fill=0, anchor="ls"); x += 22
    d.text((1100, y), str(n), font=mid, fill=0, anchor="rs")

p2 = Image.new("L", (W, H), 255); d = ImageDraw.Draw(p2)
para = ["जन्मकुंडलीत बारा भाव असतात. पहिल्या भावाला लग्न म्हणतात आणि",
        "तेथून घड्याळाच्या उलट दिशेने भाव मोजले जातात. खालील आकृतीत",
        "उत्तर भारतीय पद्धतीची कुंडली दाखवली आहे."]
for i, t in enumerate(para):
    d.text((120, 150 + i * 60), t, font=mid, fill=0, anchor="ls")
x0, y0, s = 320, 400, 600                      # कुंडली
d.rectangle((x0, y0, x0 + s, y0 + s), outline=0, width=4)
d.line((x0, y0, x0 + s, y0 + s), fill=0, width=3); d.line((x0 + s, y0, x0, y0 + s), fill=0, width=3)
d.polygon([(x0 + s / 2, y0), (x0 + s, y0 + s / 2), (x0 + s / 2, y0 + s), (x0, y0 + s / 2)], outline=0, width=3)
for (fx, fy, t) in [(.5, .25, "सू चं"), (.25, .12, "२"), (.12, .25, "३ मं"), (.27, .5, "४"), (.5, .73, "७ गु"),
                    (.73, .5, "१० श"), (.75, .88, "८"), (.88, .75, "९ रा"), (.5, .44, "१")]:
    d.text((x0 + fx * s, y0 + fy * s), t, font=small, fill=0, anchor="mm")
para2 = ["वरील कुंडलीत सूर्य आणि चंद्र लग्नात आहेत. ग्रंथानुसार अशा योगाचे",
         "फल सांगताना इतर ग्रहांची दृष्टीही पाहावी, असे आचार्य सांगतात."]
for i, t in enumerate(para2):
    d.text((120, 1130 + i * 60), t, font=mid, fill=0, anchor="ls")
p1.save(out, save_all=True, append_images=[p2], resolution=150)
print(out)

# मिश्र PDF: पान 1 खरा मजकूर (digital) + आकृती, पान 2 scan (वरील कुंडलीचे पान)
from reportlab.pdfgen import canvas
import pypdfium2 as pdfium
tmp = out.replace(".pdf", "_tmp.pdf")
c = canvas.Canvas(tmp, pagesize=(595, 842))
y = 780
for line in ["The twelve houses of the horoscope are counted from the ascendant. In the north",
             "Indian style the first house is the upper central diamond and the houses are",
             "counted anti-clockwise. The figure below shows the arrangement of the houses",
             "and the signs that is used in this book for all the examples of the chapter."]:
    c.drawString(60, y, line); y -= 18
c.rect(170, 330, 250, 250, stroke=1, fill=0)
c.line(170, 330, 420, 580); c.line(170, 580, 420, 330)
c.line(295, 580, 420, 455); c.line(420, 455, 295, 330); c.line(295, 330, 170, 455); c.line(170, 455, 295, 580)
y = 290
for line in ["After the figure the text of the chapter continues with the rules for the lords",
             "of the houses and the aspects of the planets, as taught by the old teachers."]:
    c.drawString(60, y, line); y -= 18
c.showPage(); c.save()
dst = pdfium.PdfDocument(tmp)
src = pdfium.PdfDocument(out)
dst.import_pages(src, [1])
mixed = os.path.join(os.path.dirname(out), "mixed_digital_scan.pdf")
dst.save(mixed)
os.remove(tmp)
print(mixed)
