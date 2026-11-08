"""
छोटा GPT — फक्त NumPy वापरून शून्यापासून बनवलेला Transformer.
ChatGPT/Claude ज्या तत्त्वावर चालतात तेच इथे छोट्या प्रमाणात:
  token embedding + position embedding
  -> N वेळा [LayerNorm -> Multi-head Self-Attention -> Residual,
             LayerNorm -> MLP -> Residual]
  -> LayerNorm -> पुढच्या अक्षराचा अंदाज

चालवा:  python3 tiny_gpt.py            (training, default 3000 steps)
        python3 tiny_gpt.py 5000       (जास्त steps)
        python3 tiny_gpt.py check      (गणित बरोबर आहे का ते तपासणे)
"""
import numpy as np
import sys, time

# ---------------- Settings ----------------
C = 64          # embedding आकार (प्रत्येक अक्षराचे "vector")
NH = 4          # attention heads
NL = 2          # Transformer blocks (layers)
T = 32          # context: एका वेळी किती मागची अक्षरे पाहायची
B = 16          # batch size
LR = 3e-3       # learning rate (Adam)
HS = C // NH

rng = np.random.default_rng(0)

# ---------------- Data ----------------
text = open("data.txt", encoding="utf-8").read()
chars = sorted(set(text))
V = len(chars)
ch2i = {c: i for i, c in enumerate(chars)}
i2ch = {i: c for i, c in enumerate(chars)}
data = np.array([ch2i[c] for c in text])


def get_batch():
    ix = rng.integers(0, len(data) - T - 1, B)
    x = np.stack([data[i:i + T] for i in ix])
    y = np.stack([data[i + 1:i + T + 1] for i in ix])
    return x, y


# ---------------- Parameters ----------------
def init():
    s = 0.02
    P = {"wte": rng.normal(0, s, (V, C)), "wpe": rng.normal(0, s, (T, C))}
    for l in range(NL):
        P[f"g1{l}"] = np.ones(C); P[f"b1{l}"] = np.zeros(C)
        P[f"Wq{l}"] = rng.normal(0, s, (C, C))
        P[f"Wk{l}"] = rng.normal(0, s, (C, C))
        P[f"Wv{l}"] = rng.normal(0, s, (C, C))
        P[f"Wo{l}"] = rng.normal(0, s / np.sqrt(2 * NL), (C, C))
        P[f"g2{l}"] = np.ones(C); P[f"b2{l}"] = np.zeros(C)
        P[f"W1{l}"] = rng.normal(0, s, (C, 4 * C)); P[f"c1{l}"] = np.zeros(4 * C)
        P[f"W2{l}"] = rng.normal(0, s / np.sqrt(2 * NL), (4 * C, C)); P[f"c2{l}"] = np.zeros(C)
    P["gf"] = np.ones(C); P["bf"] = np.zeros(C)
    P["Wout"] = rng.normal(0, s, (C, V))
    return P


# ---------------- Building blocks ----------------
def ln_fwd(x, g, b, eps=1e-5):
    mu = x.mean(-1, keepdims=True)
    var = x.var(-1, keepdims=True)
    rstd = 1 / np.sqrt(var + eps)
    xh = (x - mu) * rstd
    return xh * g + b, (xh, rstd, g)


def ln_bwd(dout, cache):
    xh, rstd, g = cache
    dg = (dout * xh).reshape(-1, xh.shape[-1]).sum(0)
    db = dout.reshape(-1, xh.shape[-1]).sum(0)
    dxh = dout * g
    n = xh.shape[-1]
    dx = rstd / n * (n * dxh - dxh.sum(-1, keepdims=True)
                     - xh * (dxh * xh).sum(-1, keepdims=True))
    return dx, dg, db


K = np.sqrt(2 / np.pi)


def gelu(x):          # GPT मध्ये वापरले जाणारे smooth activation
    return 0.5 * x * (1 + np.tanh(K * (x + 0.044715 * x ** 3)))


def gelu_grad(x):
    th = np.tanh(K * (x + 0.044715 * x ** 3))
    return 0.5 * (1 + th) + 0.5 * x * (1 - th ** 2) * K * (1 + 3 * 0.044715 * x ** 2)


MASK = np.triu(np.ones((T, T), dtype=bool), 1)   # भविष्यातील अक्षरे दिसू नयेत


def split(x):   # (B,t,C) -> (B,NH,t,HS)
    b, t, _ = x.shape
    return x.reshape(b, t, NH, HS).transpose(0, 2, 1, 3)


def merge(x):   # (B,NH,t,HS) -> (B,t,C)
    b, _, t, _ = x.shape
    return x.transpose(0, 2, 1, 3).reshape(b, t, C)


def attn_fwd(h, Wq, Wk, Wv, Wo):
    t = h.shape[1]
    q, k, v = split(h @ Wq), split(h @ Wk), split(h @ Wv)
    att = q @ k.transpose(0, 1, 3, 2) / np.sqrt(HS)
    att = np.where(MASK[:t, :t], -1e9, att)
    att = np.exp(att - att.max(-1, keepdims=True))
    Pm = att / att.sum(-1, keepdims=True)          # attention weights
    y = merge(Pm @ v)
    return y @ Wo, (h, q, k, v, Pm, y)


def attn_bwd(dout, cache, Wq, Wk, Wv, Wo):
    h, q, k, v, Pm, y = cache
    dWo = y.reshape(-1, C).T @ dout.reshape(-1, C)
    dy = split(dout @ Wo.T)
    dP = dy @ v.transpose(0, 1, 3, 2)
    dv = Pm.transpose(0, 1, 3, 2) @ dy
    dA = Pm * (dP - (dP * Pm).sum(-1, keepdims=True)) / np.sqrt(HS)
    dq = dA @ k
    dk = dA.transpose(0, 1, 3, 2) @ q
    dq, dk, dv = merge(dq), merge(dk), merge(dv)
    hf = h.reshape(-1, C)
    dWq = hf.T @ dq.reshape(-1, C)
    dWk = hf.T @ dk.reshape(-1, C)
    dWv = hf.T @ dv.reshape(-1, C)
    dh = dq @ Wq.T + dk @ Wk.T + dv @ Wv.T
    return dh, dWq, dWk, dWv, dWo


# ---------------- Full model ----------------
def forward(P, idx, targets=None):
    t = idx.shape[1]
    x = P["wte"][idx] + P["wpe"][:t]
    caches = []
    for l in range(NL):
        h1, c_ln1 = ln_fwd(x, P[f"g1{l}"], P[f"b1{l}"])
        a, c_att = attn_fwd(h1, P[f"Wq{l}"], P[f"Wk{l}"], P[f"Wv{l}"], P[f"Wo{l}"])
        x = x + a
        h2, c_ln2 = ln_fwd(x, P[f"g2{l}"], P[f"b2{l}"])
        pre = h2 @ P[f"W1{l}"] + P[f"c1{l}"]
        r = gelu(pre)
        x = x + r @ P[f"W2{l}"] + P[f"c2{l}"]
        caches.append((c_ln1, c_att, c_ln2, h2, pre, r))
    hf, c_lnf = ln_fwd(x, P["gf"], P["bf"])
    logits = hf @ P["Wout"]
    if targets is None:
        return logits
    z = logits - logits.max(-1, keepdims=True)
    probs = np.exp(z); probs /= probs.sum(-1, keepdims=True)
    n = idx.size
    loss = -np.log(probs.reshape(-1, V)[np.arange(n), targets.ravel()] + 1e-12).mean()
    return loss, (idx, targets, probs, hf, c_lnf, caches)


def backward(P, cache):
    idx, targets, probs, hf, c_lnf, caches = cache
    G = {k: np.zeros_like(v) for k, v in P.items()}
    n = idx.size
    dlog = probs.copy().reshape(-1, V)
    dlog[np.arange(n), targets.ravel()] -= 1
    dlog = (dlog / n).reshape(probs.shape)
    G["Wout"] = hf.reshape(-1, C).T @ dlog.reshape(-1, V)
    dx, G["gf"], G["bf"] = ln_bwd(dlog @ P["Wout"].T, c_lnf)
    for l in reversed(range(NL)):
        c_ln1, c_att, c_ln2, h2, pre, r = caches[l]
        # MLP
        G[f"c2{l}"] = dx.reshape(-1, C).sum(0)
        G[f"W2{l}"] = r.reshape(-1, 4 * C).T @ dx.reshape(-1, C)
        dpre = (dx @ P[f"W2{l}"].T) * gelu_grad(pre)
        G[f"c1{l}"] = dpre.reshape(-1, 4 * C).sum(0)
        G[f"W1{l}"] = h2.reshape(-1, C).T @ dpre.reshape(-1, 4 * C)
        dh2, G[f"g2{l}"], G[f"b2{l}"] = ln_bwd(dpre @ P[f"W1{l}"].T, c_ln2)
        dx = dx + dh2
        # Attention
        dh1, G[f"Wq{l}"], G[f"Wk{l}"], G[f"Wv{l}"], G[f"Wo{l}"] = attn_bwd(
            dx, c_att, P[f"Wq{l}"], P[f"Wk{l}"], P[f"Wv{l}"], P[f"Wo{l}"])
        d1, G[f"g1{l}"], G[f"b1{l}"] = ln_bwd(dh1, c_ln1)
        dx = dx + d1
    np.add.at(G["wte"], idx, dx)
    G["wpe"][:idx.shape[1]] = dx.sum(0)
    return G


# ---------------- Text generation ----------------
def generate(P, start, n=150, temp=0.8):
    ids = [ch2i[c] for c in start]
    for _ in range(n):
        ctx = np.array([ids[-T:]])
        logits = forward(P, ctx)[0, -1] / temp
        p = np.exp(logits - logits.max()); p /= p.sum()
        ids.append(rng.choice(V, p=p))
    return "".join(i2ch[i] for i in ids)


# ---------------- Gradient check ----------------
def grad_check():
    P = init()
    x, y = get_batch()
    loss, cache = forward(P, x, y)
    G = backward(P, cache)
    worst = 0
    for name in ["Wq0", "Wk1", "Wv0", "Wo1", "W1{}".format(0), "g1{}".format(1), "wte", "wpe", "Wout"]:
        for _ in range(5):
            i = tuple(rng.integers(0, s) for s in P[name].shape)
            old = P[name][i]
            P[name][i] = old + 1e-5; lp, _ = forward(P, x, y)
            P[name][i] = old - 1e-5; lm, _ = forward(P, x, y)
            P[name][i] = old
            num = (lp - lm) / 2e-5
            rel = abs(num - G[name][i]) / max(1e-8, abs(num) + abs(G[name][i]))
            worst = max(worst, rel)
        print(f"{name:6s} ठीक")
    print(f"सर्वात जास्त relative error: {worst:.2e}  ({'बरोबर ✓' if worst < 1e-3 else 'चूक ✗'})")


# ---------------- Training (Adam) ----------------
def train(steps):
    P = init()
    print(f"vocabulary: {V} अक्षरे | parameters: {sum(v.size for v in P.values()):,}")
    m = {k: np.zeros_like(v) for k, v in P.items()}
    s = {k: np.zeros_like(v) for k, v in P.items()}
    t0 = time.time()
    for it in range(1, steps + 1):
        x, y = get_batch()
        loss, cache = forward(P, x, y)
        G = backward(P, cache)
        lr = LR * min(1.0, it / 100) * (0.1 + 0.9 * (1 - it / steps))   # warmup + decay
        for k in P:
            m[k] = 0.9 * m[k] + 0.1 * G[k]
            s[k] = 0.99 * s[k] + 0.01 * G[k] ** 2
            P[k] -= lr * (m[k] / (1 - 0.9 ** it)) / (np.sqrt(s[k] / (1 - 0.99 ** it)) + 1e-8)
        if it % 500 == 0 or it == 1:
            print(f"\n--- step {it}, loss {loss:.3f}, {time.time() - t0:.0f}s ---")
            print(generate(P, "शेतकरी", 100))
    np.savez("tiny_gpt_weights.npz", **P)
    print("\n===== पूर्ण train झालेला GPT काय लिहितो =====")
    for st in ["गावात", "संगणक", "पाऊस", "आज"]:
        print("\n» " + generate(P, st, 150))


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "3000"
    if arg == "check":
        grad_check()
    else:
        train(int(arg))
