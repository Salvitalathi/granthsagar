"""
पदच्छेद-माहिती: Digital Corpus of Sanskrit (DCS, Oliver Hellwig, CC BY 4.0) मधील विद्वानांनी तपासलेले
संधी-विग्रह + मूळ शब्द (lemma) + विभक्ती/वचन/लिंग/लकार -> data/padaccheda/<ग्रंथ>.jsonl.gz

  python scripts/build_padaccheda.py --list          (DCS मधील सर्व ग्रंथ + आकार)
  python scripts/build_padaccheda.py [नावे…]          (नावे नसल्यास: DEFAULT यादी)
(git लागते — हे CI मध्ये चालवले जाते; तयार फाइल्स repo मध्ये आहेत)
"""
import glob, gzip, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(HERE, ".cache", "dcs")
REPO = "https://github.com/OliverHellwig/sanskrit"
FILES = "dcs/data/conllu/files/"
OUT = os.path.join(HERE, "data", "padaccheda")
DEFAULT = ["Mahābhārata", "Rāmāyaṇa", "Harivaṃśa", "Atharvaveda (Śaunaka)", "Ṛgveda", "Carakasaṃhitā",
           "Suśrutasaṃhitā", "Aṣṭāṅgahṛdayasaṃhitā", "Bhāgavatapurāṇa", "Viṣṇupurāṇa", "Agnipurāṇa", "Garuḍapurāṇa",
           "Matsyapurāṇa", "Liṅgapurāṇa", "Kūrmapurāṇa", "Skandapurāṇa", "Manusmṛti", "Aṣṭādhyāyī", "Kāśikāvṛtti",
           "Nirukta", "Rājanighaṇṭu", "Chāndogyopaniṣad", "Bṛhadāraṇyakopaniṣad", "Taittirīyopaniṣad",
           "Muṇḍakopaniṣad", "Śvetāśvataropaniṣad", "Aitareyopaniṣad", "Yogasūtrabhāṣya", "Arthaśāstra",
           "Kauśikasūtra", "Bṛhatsaṃhitā", "Amarakośa", "Rasaratnasamuccaya", "Rasārṇava"]


def git(*args, cwd=None):
    subprocess.run(["git", "-c", "gc.auto=0", "-c", "core.quotepath=off", *args], cwd=cwd, check=True,
                   env=dict(os.environ, GIT_LFS_SKIP_SMUDGE="1"))


def ensure_repo():
    if not os.path.isdir(os.path.join(CACHE, ".git")):
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        git("clone", "-q", "--depth", "1", "--filter=blob:none", "--sparse", REPO, CACHE)


def all_texts():
    """{ग्रंथ: फाइल्सची संख्या} — (-l नको: blob:none clone मध्ये ते प्रत्येक फाइल उतरवते)"""
    out = subprocess.run(["git", "-c", "core.quotepath=off", "ls-tree", "-r", "--name-only", "HEAD", FILES],
                         cwd=CACHE, capture_output=True, text=True, check=True).stdout
    size = {}
    for path in out.splitlines():
        name = path[len(FILES):].split("/")[0]
        size[name] = size.get(name, 0) + 1
    return size


def sentences(folder):
    for f in sorted(glob.glob(os.path.join(folder, "**", "*.conllu"), recursive=True)):
        chap, text, words = None, None, []
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if line.startswith("## chapter:"):
                    chap = line.split(":", 1)[1].strip()
                elif line.startswith("# text ="):
                    text = line.split("=", 1)[1].strip()
                elif not line:
                    if text and words:
                        yield {"r": chap, "t": text, "w": words}
                    text, words = None, []
                elif line[0].isdigit():
                    c = line.split("\t")
                    if len(c) >= 6 and c[0].isdigit():
                        feats = "" if c[5] == "_" else c[5]
                        words.append([c[1], c[2], c[3], feats])
        if text and words:
            yield {"r": chap, "t": text, "w": words}


def main():
    ensure_repo()
    sizes = all_texts()
    if "--list" in sys.argv:
        for k, v in sorted(sizes.items(), key=lambda x: -x[1]):
            print(f"{v:6d} files  {k}")
        print(f"एकूण {sum(sizes.values())} files, {len(sizes)} ग्रंथ")
        return
    names = [a for a in sys.argv[1:] if not a.startswith("-") and a != "default"] or DEFAULT
    names = [n for n in names if n in sizes] + [n for n in names if n not in sizes and print("⚠️ नाही:", n)]
    git("sparse-checkout", "set", *[FILES + n for n in names], cwd=CACHE)
    os.makedirs(OUT, exist_ok=True)
    total = 0
    for n in names:
        slug = re.sub(r"[^a-z0-9]+", "_", n.lower().encode("ascii", "ignore").decode()).strip("_") or "x"
        path = os.path.join(OUT, slug + ".jsonl.gz")
        k = 0
        with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as f:
            for s in sentences(os.path.join(CACHE, FILES + n)):
                s["g"] = n
                f.write(json.dumps(s, ensure_ascii=False, separators=(",", ":")) + "\n"); k += 1
        total += os.path.getsize(path)
        print(f"✅ {n}: {k} वाक्ये -> {os.path.getsize(path) / 1e6:.1f} MB")
    print(f"एकूण {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
