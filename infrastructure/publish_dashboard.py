"""Atomically publish only a validated snapshot to the dedicated GitHub data branch."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from ingestion.batch.dashboard_contract import aggregate_digest, validate_snapshot

REPOSITORY = "quyenmcu/insightflow-ai-data-platform"
BRANCH = "codex/dashboard-data"


def api(method, path, payload=None, *, allow_missing=False):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("A short-lived GitHub job token is required")
    request = Request(f"https://api.github.com/repos/{REPOSITORY}/{path}",
        data=json.dumps(payload).encode() if payload is not None else None, method=method,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        if error.code == 404 and allow_missing:
            return None
        raise RuntimeError(f"GitHub snapshot publication failed (HTTP {error.code})") from None


def publish(path, baseline, source_fingerprint):
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY or os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise ValueError("Publication is restricted to this repository's trusted main workflow")
    content = Path(path).read_bytes()
    snapshot = json.loads(content)
    validate_snapshot(snapshot, baseline)
    if snapshot["source_fingerprint"] != source_fingerprint or snapshot["aggregate_sha256"] != aggregate_digest(snapshot["rows"]):
        raise ValueError("Snapshot source or aggregate checksum differs")
    current = api("GET", f"git/ref/heads/{BRANCH}", allow_missing=True)
    parent = current["object"]["sha"] if current else None
    tree = api("POST", "git/trees", {"tree": [{"path": "snapshot.json", "mode": "100644", "type": "blob", "content": content.decode("utf-8")}]})
    commit = api("POST", "git/commits", {"message": "Refresh verified dashboard aggregates", "tree": tree["sha"], "parents": [parent] if parent else []})
    if parent:
        api("PATCH", f"git/refs/heads/{BRANCH}", {"sha": commit["sha"], "force": False})
    else:
        api("POST", "git/refs", {"ref": f"refs/heads/{BRANCH}", "sha": commit["sha"]})
    restored = api("GET", f"contents/snapshot.json?ref={quote(commit['sha'], safe='')}")
    if restored.get("encoding") != "base64" or base64.b64decode(restored["content"]) != content:
        raise ValueError("Published snapshot readback differs")
    return {"branch": BRANCH, "commit": commit["sha"], "aggregateSha256": snapshot["aggregate_sha256"],
            "fileSha256": hashlib.sha256(content).hexdigest(), "readbackVerified": True,
            "url": f"https://raw.githubusercontent.com/{REPOSITORY}/refs/heads/{BRANCH}/snapshot.json"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("data/processed/dashboard/snapshot.json"))
    args = parser.parse_args()
    root = Path(__file__).parent
    result = publish(args.snapshot, json.loads((root / "postgres_baseline.json").read_text()),
                     json.loads((root / "bigquery_tables.json").read_text())["datasetSha256"])
    print(json.dumps(result, indent=2))
    args.snapshot.with_name("publication.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as stream:
            stream.write(f"\n## Dashboard refresh\nPublished verified aggregates to `{BRANCH}`.\nCommit: `{result['commit']}`. Readback matched.\n")


if __name__ == "__main__":
    main()
