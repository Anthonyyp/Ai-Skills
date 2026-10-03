# Running in Claude Cowork

Cowork runs skills in a throwaway Linux VM (Ubuntu, 2 vCPU, no GPU). Its network goes through an
**allowlist**: package registries (PyPI, npm, GitHub) are open by default, but the hosts Kokoro
needs for its model and its CPU engine are not.

## One-time setup (the account owner or org admin does this, not the agent)

Claude settings → **Capabilities** → *Allow network egress* on → **Additional allowed domains**:

```
huggingface.co
*.hf.co
download.pytorch.org
download-r2.pytorch.org
```

| Domain | Why it's needed |
|---|---|
| `huggingface.co`, `*.hf.co` | The Kokoro model (~313 MB) and voice files. `huggingface.co` answers, then the file streams from `cas-server.xethub.hf.co` / `us.aws.cdn.hf.co`. |
| `download.pytorch.org` | PyTorch's package index for the **CPU-only** build. |
| `download-r2.pytorch.org` | Where that index actually serves the PyTorch file from (PyTorch's Cloudflare storage). |

Everything else the setup uses is already reachable: PyPI (`pypi.org`, `files.pythonhosted.org`)
for Kokoro and its Python packages, and GitHub for spaCy's English model.

### Why exactly two PyTorch hosts, and not `*.pytorch.org`

A wildcard would cover both download hosts and survive PyTorch moving its storage again, but it also
opens everything else under `pytorch.org`, including **`discuss.pytorch.org`, a public forum where
anyone can post and upload files**. That's a place a misled agent could read planted instructions
from, or post data to, and the skill never needs it. Listing the two download hosts is least
privilege. If PyTorch moves storage, the install fails **loudly** on the new host (see below) and
you add that one domain.

## ⛔ Never install PyTorch from PyPI here

If `download.pytorch.org` or `download-r2.pytorch.org` is refused (`CONNECT tunnel failed,
response 403`, or uv's `tunnel error: unsuccessful`), **stop and tell the user which host to
allowlist.** Do **not** fall back to plain `pip install torch` / `uv pip install torch` from PyPI.
On Linux that's the GPU build: **3.2 GB** of downloads (2.5 GB of NVIDIA libraries the VM can't use)
and a 5.7 GB environment, measured 2026-10-02. It works, but it's ~6× the size for nothing.

## Every session starts empty

Nothing persists between sessions, so each one repeats the setup in SKILL.md. Cowork already has
Python 3.12 and uv, so `uv venv --python 3.12` costs nothing.

### Install, with the PyTorch file pinned by fingerprint

Same three steps as SKILL.md, except PyTorch is pinned to the exact file verified for Cowork
(Linux x86_64, Python 3.12). If anything other than that file arrives, even from the real site,
uv refuses it with `Hash mismatch` and installs nothing:

```bash
uv venv --python 3.12 ~/.venvs/kokoro
echo "torch==2.14.1+cpu --hash=sha256:5a6363570c753812540a05eb82380e329469cbe668643e88111414c12627711f" > /tmp/torch.txt
uv pip install --python ~/.venvs/kokoro --index-url https://download.pytorch.org/whl/cpu     --require-hashes --no-deps -r /tmp/torch.txt
uv pip install --python ~/.venvs/kokoro kokoro soundfile "transformers>=4.45" pip
```

The fingerprint is the one `download.pytorch.org` publishes for
`torch-2.14.1+cpu-cp312-cp312-manylinux_2_28_x86_64.whl` (196 MB). `--no-deps` is deliberate: torch's
helper packages (sympy, networkx and so on) then come from PyPI in the next step. **Skip apt**:
system espeak-ng isn't needed, because Kokoro bundles its own.

### What it costs (measured 2026-10-02, fresh session)

| | |
|---|---|
| Setup (venv + both installs) | ~13 s, ~340 MB downloaded |
| First render | ~28 s, plus ~310 MB of downloads (Kokoro model 313 MB, spaCy English model 13 MB) |
| **Total per fresh session** | **~650 MB, under a minute** |
| Environment on disk | 1.2 GB |
| Render speed on 2 vCPU | 2.1× realtime cold, 2.4× warm |
| No NVIDIA packages | confirmed |
| Offline once cached | confirmed |

For comparison, the PyPI fallback this guide forbids measured 3.6 GB and a 5.7 GB environment.

## Checking it from inside the session

```bash
for h in huggingface.co download.pytorch.org download-r2.pytorch.org; do
  printf "%s " $h; curl -sS -o /dev/null -w "%{http_code}\n" -m 15 https://$h/
done
```

`000` with `CONNECT tunnel failed, response 403` means that host isn't allowlisted. Don't retry and
don't route around it; tell the user which domain to add, and stop.
