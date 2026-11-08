"""
छोटा AI — फक्त NumPy वापरून शून्यापासून बनवलेले character-level RNN.
हे मॉडेल data.txt मधील मराठी मजकूर वाचून, पुढचे अक्षर कोणते येईल ते शिकते,
आणि मग स्वतः नवीन मराठी वाक्ये लिहिते.

चालवा:  python3 tiny_ai.py
"""
import numpy as np
import sys

np.random.seed(42)

# ---------- १. Data वाचणे ----------
text = open("data.txt", encoding="utf-8").read()
chars = sorted(set(text))                  # सगळी वेगळी अक्षरे (vocabulary)
V = len(chars)
ch2i = {c: i for i, c in enumerate(chars)} # अक्षर -> क्रमांक
i2ch = {i: c for i, c in enumerate(chars)} # क्रमांक -> अक्षर
print(f"मजकूर: {len(text)} अक्षरे, vocabulary: {V} वेगळी अक्षरे")

# ---------- २. मॉडेलचा मेंदू (parameters) ----------
H = 128        # hidden layer चा आकार (मेंदूतील "न्यूरॉन्स")
T = 32         # एका वेळी किती अक्षरे पाहायची
lr = 0.1       # शिकण्याचा वेग (learning rate)

Wxh = np.random.randn(H, V) * 0.01   # input -> hidden
Whh = np.random.randn(H, H) * 0.01   # hidden -> hidden (आठवण)
Why = np.random.randn(V, H) * 0.01   # hidden -> output
bh = np.zeros((H, 1))
by = np.zeros((V, 1))
params = [Wxh, Whh, Why, bh, by]
print(f"एकूण parameters: {sum(p.size for p in params):,}")


# ---------- ३. Forward + Backward (शिकण्याचे गणित) ----------
def step(inputs, targets, hprev):
    xs, hs, ps = {}, {-1: hprev}, {}
    loss = 0.0
    # Forward: प्रत्येक अक्षरानंतर पुढच्या अक्षराचा अंदाज
    for t in range(len(inputs)):
        xs[t] = np.zeros((V, 1)); xs[t][inputs[t]] = 1
        hs[t] = np.tanh(Wxh @ xs[t] + Whh @ hs[t - 1] + bh)
        y = Why @ hs[t] + by
        e = np.exp(y - y.max()); ps[t] = e / e.sum()     # softmax
        loss -= np.log(ps[t][targets[t], 0])             # चूक किती?
    # Backward: चुकीवरून प्रत्येक weight किती बदलायचा ते काढणे
    grads = [np.zeros_like(p) for p in params]
    dWxh, dWhh, dWhy, dbh, dby = grads
    dhnext = np.zeros_like(hprev)
    for t in reversed(range(len(inputs))):
        dy = ps[t].copy(); dy[targets[t]] -= 1
        dWhy += dy @ hs[t].T; dby += dy
        dh = Why.T @ dy + dhnext
        dhraw = (1 - hs[t] ** 2) * dh
        dbh += dhraw
        dWxh += dhraw @ xs[t].T
        dWhh += dhraw @ hs[t - 1].T
        dhnext = Whh.T @ dhraw
    for g in grads:
        np.clip(g, -5, 5, out=g)
    return loss, grads, hs[len(inputs) - 1]


# ---------- ४. मॉडेलकडून नवीन मजकूर लिहून घेणे ----------
def generate(start, n=200, temp=0.7):
    h = np.zeros((H, 1))
    out = start
    for c in start[:-1]:
        x = np.zeros((V, 1)); x[ch2i[c]] = 1
        h = np.tanh(Wxh @ x + Whh @ h + bh)
    idx = ch2i[start[-1]]
    for _ in range(n):
        x = np.zeros((V, 1)); x[idx] = 1
        h = np.tanh(Wxh @ x + Whh @ h + bh)
        y = (Why @ h + by) / temp
        p = np.exp(y - y.max()); p /= p.sum()
        idx = np.random.choice(V, p=p.ravel())
        out += i2ch[idx]
    return out


# ---------- ५. Training (Adagrad) ----------
mem = [np.zeros_like(p) for p in params]
steps = int(sys.argv[1]) if len(sys.argv) > 1 else 15000
pos, h = 0, np.zeros((H, 1))
smooth = -np.log(1.0 / V) * T

for it in range(steps + 1):
    if pos + T + 1 >= len(text):
        pos, h = 0, np.zeros((H, 1))
    inp = [ch2i[c] for c in text[pos:pos + T]]
    tgt = [ch2i[c] for c in text[pos + 1:pos + T + 1]]
    loss, grads, h = step(inp, tgt, h)
    smooth = smooth * 0.999 + loss * 0.001
    for p, g, m in zip(params, grads, mem):
        m += g * g
        p -= lr * g / np.sqrt(m + 1e-8)
    if it % 3000 == 0:
        print(f"\n--- step {it}, loss {smooth / T:.3f} ---")
        print(generate("शेतकरी", 120))
    pos += T

print("\n===== पूर्ण train झालेला AI काय लिहितो =====")
for s in ["गावात", "संगणक", "पाऊस", "आज"]:
    print("\n» " + generate(s, 150))
