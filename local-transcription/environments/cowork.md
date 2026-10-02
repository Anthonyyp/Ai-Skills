# Running in Claude Cowork

Cowork runs skills in a throwaway Linux VM (Ubuntu, 2 vCPU, no GPU). Its network goes through an
**allowlist**: package registries are open by default, but the hosts Whisper downloads its model
from are not. Verified working 2026-10-02 once the steps below are done.

## One-time setup (the account owner or org admin does this, not the agent)

Claude settings → **Capabilities** → *Allow network egress* on → **Additional allowed domains**:

```
huggingface.co
*.hf.co
```

Both are required. `huggingface.co` answers the request, then the model file streams from
`cas-server.xethub.hf.co` and `us.aws.cdn.hf.co`, which the wildcard covers. Allowing only the first
fails partway through the download. The change reaches an open session after its VM restarts;
a new session always picks it up.

## Checking it from inside the session

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://huggingface.co   # 200 = allowed
```

`000` with `CONNECT tunnel failed, response 403`, or `httpx.ProxyError: 403 Forbidden` from
faster-whisper, means the allowlist isn't in place. **Don't retry and don't try to route around
it.** Tell the user which two domains to add (above) and stop.

## Every session starts empty

Nothing persists between sessions, so each one repeats the install and the model download:

```bash
pip install --break-system-packages faster-whisper
```

| Model | Download | Notes |
|---|---|---|
| `tiny` | 75 MB, ~3 s | rough drafts |
| `base` | 142 MB, ~4 s | good default here |
| `large-v3` | 3.1 GB | best accuracy; CPU-only, so expect well under realtime on 2 vCPU |

Measure on the VM before quoting a time for a long recording. There is no GPU.

## The PyAV 19 trap (already handled)

A fresh `pip install` currently pulls PyAV 19, and faster-whisper 1.2.1 crashes when given a
**file path** (`TypeError: open() got an unexpected keyword argument 'metadata_errors'`).
`scripts/transcribe.py` avoids this by passing decoded samples instead of a path. If you write your
own call, do the same, or pin `av<19`.
