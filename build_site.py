#!/usr/bin/env python3
"""Build index.html with embedded DATA blob and push (git or Contents API).
Idempotent: skips push when data unchanged."""
import json, os, re, sys, base64, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "template.html")
OUT = os.path.join(HERE, "index.html")
DATA_RE = re.compile(r"const DATA = \{.*?\};", re.S)


def build(state):
    tpl = open(TEMPLATE, encoding="utf-8").read()
    blob = "const DATA = " + json.dumps(state, separators=(",", ":")) + ";"
    if DATA_RE.search(tpl):
        html = DATA_RE.sub(lambda m: blob, tpl, count=1)
    else:
        raise RuntimeError("DATA marker not found in template")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    return html


def current_remote_hash(token, repo):
    url = f"https://api.github.com/repos/{repo}/contents/index.html"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r).get("sha")
    except Exception:
        return None


def push_api(token, repo, html, message):
    url = f"https://api.github.com/repos/{repo}/contents/index.html"
    payload = {
        "message": message,
        "content": base64.b64encode(html.encode("utf-8")).decode(),
        "branch": "main",
    }
    sha = current_remote_hash(token, repo)
    if sha:
        payload["sha"] = sha
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="PUT", headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    state_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "state.json")
    state = json.load(open(state_path))
    html = build(state)
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("SIGNAL_REPO", "CR1983gh/trading-signal")
    if token:
        # Actions path: Contents API
        old = current_remote_hash(token, repo)
        # change detection: compare with committed blob via raw fetch
        try:
            raw = urllib.request.urlopen(
                f"https://raw.githubusercontent.com/{repo}/main/index.html?cb={os.getpid()}",
                timeout=20).read().decode("utf-8")
            m = DATA_RE.search(raw)
            if m:
                same = json.dumps(json.loads(m.group(0)[len("const DATA = "):-1]),
                                 sort_keys=True) == json.dumps(state, sort_keys=True)
                if same:
                    print("No changes today — skip push.")
                    return
        except Exception:
            pass
        res = push_api(token, repo, html, f"Signal update {state['generated_utc'][:16]}")
        print("Pushed via Contents API:", res.get("commit", {}).get("sha", "?")[:8])
    else:
        print("Built index.html locally (no GITHUB_TOKEN — git push manually).")


if __name__ == "__main__":
    main()
