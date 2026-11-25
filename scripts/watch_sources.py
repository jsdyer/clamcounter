#!/usr/bin/env python3
"""Check reviewed menu evidence without automatically changing editorial prices."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AGENT = "ClamCounter-SourceWatch/1.0 (+https://coolcode.ca/clamcounter/)"
IDENTIFIER = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def normalized(value):
    return " ".join(value.casefold().split())


class VisibleParts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text, self.assets = [], []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"head", "script", "style", "svg", "noscript"}:
            self.hidden += 1
        if tag == "img":
            values = dict(attrs)
            if values.get("src"):
                self.assets.append(values["src"])

    def handle_endtag(self, tag):
        if tag in {"head", "script", "style", "svg", "noscript"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, value):
        if not self.hidden:
            self.text.append(value)


def read_json(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=path.name + ".", delete=False) as output:
        temporary = Path(output.name)
        json.dump(data, output, ensure_ascii=False, indent=2)
        output.write("\n")
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_config(config):
    if config.get("schema_version") != 1 or not isinstance(config.get("sources"), list) or not config["sources"]:
        raise ValueError("Expected a version-1 nonempty source list")
    if not 1 <= config.get("timeout_seconds", 0) <= 60 or not 1024 <= config.get("maximum_download_bytes", 0) <= 20_000_000:
        raise ValueError("Invalid download limits")
    seen = set()
    for source in config["sources"]:
        identity = source.get("id", "")
        if not IDENTIFIER.fullmatch(identity) or identity in seen:
            raise ValueError("Source IDs must be unique lowercase slugs")
        seen.add(identity)
        if not source.get("name") or not source.get("resources"):
            raise ValueError(f"{identity}: name and resources required")
        resources = set()
        for resource in source["resources"]:
            key = resource.get("id", "")
            if not IDENTIFIER.fullmatch(key) or key in resources:
                raise ValueError(f"{identity}: invalid or duplicate resource ID")
            resources.add(key)
            url = urlsplit(resource.get("url", ""))
            if url.scheme != "https" or not url.hostname or url.username or url.password or url.fragment:
                raise ValueError(f"{identity}/{key}: HTTPS source without credentials/fragment required")
            if resource.get("kind") not in {"html", "png"}:
                raise ValueError(f"{identity}/{key}: unsupported source kind")
            if resource["kind"] == "html" and not resource.get("required_text"):
                raise ValueError(f"{identity}/{key}: expected page text is required")
            for section in resource.get("sections", []):
                if not section.get("start") or not section.get("end"):
                    raise ValueError(f"{identity}/{key}: explicit section boundaries required")
    return config


def fetch(resource, config):
    # Some restaurant hosts reject custom crawler agents. A null override uses
    # urllib's ordinary truthful default; no browser/session impersonation.
    agent = resource.get("user_agent", DEFAULT_AGENT)
    request = Request(resource["url"], headers={"User-Agent": agent} if agent else {})
    with urlopen(request, timeout=config["timeout_seconds"]) as response:
        raw = response.read(config["maximum_download_bytes"] + 1)
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}")
    if not raw or len(raw) > config["maximum_download_bytes"]:
        raise ValueError("Empty or oversized source response")
    return raw


def fingerprint(resource, raw):
    if resource["kind"] == "png":
        if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Expected PNG menu image, not an error page")
        return sha256(raw).hexdigest()
    page = VisibleParts()
    page.feed(raw.decode("utf-8"))
    text = normalized(" ".join(page.text))
    for required in resource["required_text"]:
        if normalized(required) not in text:
            raise ValueError(f"Expected menu/contact text missing: {required}")
    material = []
    for section in resource.get("sections", []):
        start, end = normalized(section["start"]), normalized(section["end"])
        try:
            begin = text.index(start)
            finish = text.index(end, begin + len(start))
        except ValueError as error:
            raise ValueError("Reviewed section boundaries changed; manual review needed") from error
        material.append(text[begin:finish])
    if not material:
        material.append(text)
    if resource.get("asset_path_contains"):
        links = sorted({urljoin(resource["url"], value) for value in page.assets
                        if resource["asset_path_contains"] in value})
        if not links:
            raise ValueError("Expected linked menu images missing")
        material.extend(links)
    return sha256("\n".join(material).encode("utf-8")).hexdigest()


def oldest(values):
    return min(values) if values and all(values) else None


def watch(root=ROOT, *, accept_reviewed=False, reviewed_at=None, fetcher=fetch, now=None):
    config = validate_config(read_json(root / "config/sources.json"))
    baseline_path = root / "config/source-fingerprints.json"
    baseline = read_json(baseline_path, {"schema_version": 1, "sources": {}})
    previous = read_json(root / "web/data/status.json", {})
    now = now or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if accept_reviewed:
        if not reviewed_at:
            raise ValueError("--accept-reviewed requires --reviewed-at YYYY-MM-DD after manual review")
        if date.fromisoformat(reviewed_at).isoformat() != reviewed_at or reviewed_at > now[:10]:
            raise ValueError("Review date must be an ISO date no later than the check date")
    prior = {source["id"]: source for source in previous.get("sources", [])}
    results, failed = [], False
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {(source["id"], resource["id"]): pool.submit(fetcher, resource, config)
                   for source in config["sources"] for resource in source["resources"]}
        for source in config["sources"]:
            identity = source["id"]
            accepted = baseline.get("sources", {}).get(identity, {})
            old_source = prior.get(identity, {})
            old_resources = {item["id"]: item for item in old_source.get("resources", [])}
            resources = []
            for resource in source["resources"]:
                item = {"id": resource["id"], "url": resource["url"], "attempted_at": now}
                old = old_resources.get(resource["id"], {})
                try:
                    digest = fingerprint(resource, pending[identity, resource["id"]].result())
                    reference = accepted.get("resources", {}).get(resource["id"])
                    # Baselines include URLs and selectors so config edits require
                    # review even if the returned bytes happen to be identical.
                    definition = sha256(json.dumps(resource, sort_keys=True).encode()).hexdigest()
                    matches = reference and reference.get("sha256") == digest and reference.get("definition_sha256") == definition
                    item.update(status="ok" if matches else "needs_review", checked_at=now,
                                sha256=digest, definition_sha256=definition)
                except Exception as error:
                    failed = True
                    item.update(status="error", checked_at=old.get("checked_at"),
                                sha256=old.get("sha256"), error=f"{type(error).__name__}: {error}"[:400])
                resources.append(item)
            state = "error" if any(item["status"] == "error" for item in resources) else (
                "needs_review" if any(item["status"] == "needs_review" for item in resources) else "ok")
            results.append({"id": identity, "name": source["name"], "reviewed_at": accepted.get("reviewed_at"),
                            "attempted_at": now, "checked_at": now if state != "error" else old_source.get("checked_at"),
                            "status": state, "resources": resources})
    if accept_reviewed and not failed:
        new_baseline = {"schema_version": 1, "sources": {}}
        for source in results:
            source.update(reviewed_at=reviewed_at, status="ok")
            for resource in source["resources"]:
                resource["status"] = "ok"
            new_baseline["sources"][source["id"]] = {
                "reviewed_at": reviewed_at,
                "resources": {item["id"]: {key: item[key] for key in ("sha256", "definition_sha256")}
                              for item in source["resources"]}}
        atomic_json(baseline_path, new_baseline)
    status = {"schema_version": 1, "source_count": len(results), "attempted_at": now,
              # This is the last complete successful run, not the minimum of
              # independently successful sources from different failed runs.
              "checked_at": previous.get("checked_at") if failed else now,
              "reviewed_at": oldest([item["reviewed_at"] for item in results]),
              "status": "error" if failed else ("needs_review" if any(item["status"] == "needs_review" for item in results) else "ok"),
              "sources": results}
    atomic_json(root / "web/data/status.json", status)
    return status, 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accept-reviewed", action="store_true", help="Accept current fingerprints only after manually reviewing menus and catalogue")
    parser.add_argument("--reviewed-at", help="Actual manual review date, YYYY-MM-DD; required with --accept-reviewed")
    parser.add_argument("--validate", action="store_true", help="Validate configured sources without using the network")
    args = parser.parse_args()
    if args.validate:
        config = validate_config(read_json(ROOT / "config/sources.json"))
        print(f"Validated {len(config['sources'])} configured restaurant sources")
        return 0
    if args.reviewed_at and not args.accept_reviewed:
        parser.error("--reviewed-at requires --accept-reviewed")
    try:
        status, code = watch(accept_reviewed=args.accept_reviewed, reviewed_at=args.reviewed_at)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    for source in status["sources"]:
        print(f"{source['id']}: {source['status']} (checked {source['checked_at']}, reviewed {source['reviewed_at']})")
        for resource in source["resources"]:
            if resource.get("error"):
                print(f"  {resource['id']}: {resource['error']}")
    print("Menu checks do not update prices or confirm today's availability.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
