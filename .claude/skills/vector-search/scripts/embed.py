"""The embedder: text in, one unit vector out. Nothing here knows about rules.

WHY THIS FILE IS SEPARATE
-------------------------
Everything else in this skill is arithmetic over vectors and would keep working if the model were
swapped. Isolating the model means the swap is one file, and it means the pinning rules live in one
place: which graph, which prompt prefixes, which pooling, which dimension. Get any of those four
wrong and the vectors are still numbers, still comparable, and quietly worse - which is this repo's
signature failure mode, so they are asserted rather than assumed.

THE FOUR THINGS THAT MUST MATCH THE MODEL CARD
  prompts   voyage-4 wants a task prefix. A query and a document are embedded DIFFERENTLY.
  pooling   mean over the unmasked tokens, not the pooler_output head.
  norm      L2, so a dot product IS cosine similarity.
  dim       Matryoshka: truncate THEN re-normalise. 512 is the default here.

Model weights live outside the repo, on the Desktop, because a 431 MB binary is build input rather
than source and this repo has no version control. Override with RULE_SEARCH_MODEL.
"""

import hashlib
import json
import os
import pathlib

DEFAULT_MODEL = pathlib.Path(
    os.environ.get("RULE_SEARCH_MODEL",
                   r"C:\Users\ljcg3\OneDrive\Desktop\models\voyage-4-nano-onnx"))
GRAPH = "onnx/model_quantized.onnx"
DIM = 512                     # 2048 native, truncatable to 1024, 512, 256
MAX_TOKENS = 1024             # a rule is ~250; this is headroom for a whole file as a query

QUERY_PREFIX = "Represent the query for retrieving supporting documents: "
DOC_PREFIX = "Represent the document for retrieval: "


class Embedder:
    def __init__(self, model_dir: pathlib.Path = DEFAULT_MODEL, dim: int = DIM):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.np = np
        self.dir = pathlib.Path(model_dir)
        graph = self.dir / GRAPH
        tok = self.dir / "tokenizer.json"
        for p in (graph, tok):
            if not p.is_file():
                raise SystemExit(
                    "missing %s\nSet RULE_SEARCH_MODEL to the model folder, or fetch the model: "
                    "see SKILL.md" % p)
        self.dim = dim
        # Default ORT settings left one core busy and the other seven idle: a single short query took
        # 383 ms. This machine has eight, and nothing else wants them while the game is not running.
        so = ort.SessionOptions()
        so.intra_op_num_threads = int(os.environ.get("RULE_SEARCH_THREADS", "8"))
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(graph), sess_options=so,
                                            providers=["CPUExecutionProvider"])
        self.tok = Tokenizer.from_file(str(tok))
        self.inputs = [i.name for i in self.session.get_inputs()]

    # -- identity, so an index can refuse to serve vectors from a different model ----------------
    def fingerprint(self) -> dict:
        return fingerprint_for(self.dir, self.dim)

    def _run(self, texts, prefix):
        np = self.np
        encs = [self.tok.encode(prefix + t) for t in texts]
        ids = [e.ids[:MAX_TOKENS] for e in encs]
        n = max(len(i) for i in ids)
        arr = np.array([i + [0] * (n - len(i)) for i in ids], dtype=np.int64)
        mask = np.array([[1] * len(i) + [0] * (n - len(i)) for i in ids], dtype=np.int64)
        feed = {}
        for nm in self.inputs:
            if "ids" in nm:
                feed[nm] = arr
            elif "mask" in nm:
                feed[nm] = mask
            elif "type" in nm:
                feed[nm] = np.zeros_like(arr)
        out = self.session.run(None, feed)
        hidden = next(a for a in out if a.ndim == 3)                  # last_hidden_state
        m = mask[:, :hidden.shape[1], None].astype(np.float32)
        pooled = (hidden * m).sum(1) / np.maximum(m.sum(1), 1e-9)     # MEAN pooling
        pooled = pooled[:, :self.dim]                                 # Matryoshka truncation
        norm = np.linalg.norm(pooled, axis=1, keepdims=True)
        return (pooled / np.maximum(norm, 1e-9)).astype(np.float32)   # THEN re-normalise

    def documents(self, texts, batch: int = 16):
        return self._stack(texts, DOC_PREFIX, batch)

    def queries(self, texts, batch: int = 16):
        return self._stack(texts, QUERY_PREFIX, batch)

    def _stack(self, texts, prefix, batch):
        np = self.np
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        chunks = [self._run(texts[i:i + batch], prefix) for i in range(0, len(texts), batch)]
        return np.vstack(chunks)


def fingerprint_for(model_dir: pathlib.Path = DEFAULT_MODEL, dim: int = DIM):
    """The model's identity without loading the runtime, or None when its graph file is missing.

    `index.py --status` uses this to notice a model swap: an index built by another model is stale even
    when every document hash still matches (review finding 2026-09-13). Hashing the 431 MB graph takes
    about a second, so the hash is kept beside the graph's size and modification time and reused while
    those are unchanged.
    """
    graph = pathlib.Path(model_dir) / GRAPH
    try:
        st = graph.stat()
    except OSError:
        return None
    seen = "%s|%d|%d" % (graph.as_posix(), st.st_size, st.st_mtime_ns)
    memo = pathlib.Path(__file__).resolve().parent.parent / "data" / "model-hash.json"
    cached = load_manifest(memo)
    if cached.get("seen") == seen:
        digest = cached["sha256_16"]
    else:
        h = hashlib.sha256()
        with open(graph, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        digest = h.hexdigest()[:16]
        try:
            memo.parent.mkdir(parents=True, exist_ok=True)
            memo.write_text(json.dumps({"seen": seen, "sha256_16": digest}), encoding="utf-8")
        except OSError:
            pass
    return {"model_dir": pathlib.Path(model_dir).as_posix(), "graph": GRAPH, "dim": dim,
            "graph_sha256_16": digest, "max_tokens": MAX_TOKENS,
            "query_prefix": QUERY_PREFIX, "doc_prefix": DOC_PREFIX}


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def load_manifest(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
