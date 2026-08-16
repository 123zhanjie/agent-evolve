"""Core logic for agent-evolve.

Zero third-party dependencies. Everything is files:
  - history/         raw conversation logs (md / txt / jsonl)
  - rules/config.json  topics, thresholds, profiles, protected files
  - proposals/pending|approved|rejected|applied/
  - ledger/approval.jsonl   append-only audit trail
  - backups/{proposal_id}/  pre-apply snapshots

Pipeline: scan -> aggregate -> propose -> approve -> apply -> rollback.
Discovery is automatic; writing to protected files only ever happens
after a human approval, recorded in the ledger.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

VERSION = "0.1.0"

SIGNAL_WEIGHTS = {
    "correction": 1.0,   # user actively corrected this topic
    "explicit": 1.0,     # user said "remember / always do this"
    "repeat": 0.7,       # same preference mentioned across sessions
    "acceptance": 0.3,   # weak signal: style used and never corrected
}

TRIGGER_PATTERNS = {
    "correction": re.compile(r"(别用|不要|别再|说了别|又用|又犯|应该用|改回|不能用|禁止|总是用|老是)"),
    "explicit": re.compile(r"(记住|写进记忆|记下来|以后都这样|以后都用)"),
    "repeat": re.compile(r"(以后|每次都|都用|一律|统一|默认|仍然|还是要)"),
}

DEFAULT_CONFIG = {
    "profile": "active",
    "thresholds": {"correction": 2, "repeat": 3, "explicit": 1},
    "min_score": 2.0,
    "decay_days": 30,
    "topics": {
        "中文标点规则": ["冒号", "破折号"],
        "配图风格": ["配图", "白底", "麦肯锡", "500dpi", "遮挡"],
        "输出格式": ["表格", "列表", "bullet"],
    },
    "protected_files": ["MEMORY.md", "AGENTS.md"],
}

PROPOSAL_TEMPLATE = """---
id: {id}
status: pending
profile: {profile}
topic: {topic}
target: {target}
created: {created}
---
## 建议改动
{content}

## 理由
该主题在对话历史中出现 {count} 次（{breakdown}），达到触发阈值。

## 候选依据
{evidence}
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_config(path: Path) -> dict:
    if path.exists():
        cfg = json.loads(path.read_text(encoding="utf-8"))
        merged = dict(DEFAULT_CONFIG)
        merged.update(cfg)
        return merged
    return dict(DEFAULT_CONFIG)


# ---------------------------------------------------------------- scan

def _decay(days: int, decay_days: int) -> float:
    if days <= decay_days:
        return 1.0
    return max(0.2, 1.0 - (days - decay_days) / (decay_days * 2))


def extract_signals(text: str, topics: dict, source: str, mtime_days: int, decay_days: int) -> list[dict]:
    """Scan one paragraph/line: a signal is a topic keyword hit plus a trigger phrase."""
    signals = []
    for topic, keywords in topics.items():
        for kw in keywords:
            if kw not in text:
                continue
            stype = "acceptance"
            for t, pat in TRIGGER_PATTERNS.items():
                if pat.search(text):
                    stype = t
                    break
            signals.append({
                "topic": topic,
                "type": stype,
                "quote": text.strip()[:200],
                "source": source,
                "decay": _decay(mtime_days, decay_days),
            })
            break  # one signal per topic per paragraph
    return signals


def scan_history(history_dir: Path, config: dict) -> list[dict]:
    signals: list[dict] = []
    if not history_dir.exists():
        return signals
    now = datetime.now(timezone.utc)
    for f in sorted(history_dir.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in (".md", ".txt", ".jsonl"):
            continue
        days = max(0, (now - datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)).days)
        raw = f.read_text(encoding="utf-8", errors="ignore")
        if f.suffix.lower() == ".jsonl":
            for line in raw.splitlines():
                if not line.strip():
                    continue
                try:
                    text = json.loads(line).get("text") or json.loads(line).get("content") or line
                except json.JSONDecodeError:
                    text = line
                signals.extend(extract_signals(text, config["topics"], f"{f}", days, config["decay_days"]))
        else:
            for para in re.split(r"\n\s*\n", raw):
                if para.strip():
                    signals.extend(extract_signals(para, config["topics"], f"{f}", days, config["decay_days"]))
    return signals


def aggregate(signals: list[dict]) -> list[dict]:
    stats: dict[str, dict] = {}
    for s in signals:
        st = stats.setdefault(s["topic"], {"topic": s["topic"], "counts": {}, "score": 0.0, "samples": []})
        st["counts"][s["type"]] = st["counts"].get(s["type"], 0) + 1
        st["score"] += SIGNAL_WEIGHTS.get(s["type"], 0.3) * s.get("decay", 1.0)
        if len(st["samples"]) < 5:
            st["samples"].append({"type": s["type"], "quote": s["quote"], "source": s["source"]})
    for st in stats.values():
        st["score"] = round(st["score"], 2)
        st["breakdown"] = ", ".join(f"{k}={v}" for k, v in sorted(st["counts"].items()))
        st["count"] = sum(st["counts"].values())
    return sorted(stats.values(), key=lambda x: -x["score"])


# ---------------------------------------------------------------- proposals

def _next_id(proposals_dir: Path, topic: str) -> str:
    existing = len(list(proposals_dir.glob("*.md"))) if proposals_dir.exists() else 0
    return f"evo-{datetime.now().strftime('%Y%m%d')}-{existing + 1:03d}"


def proposal_exists(proposals_dir: Path, topic: str) -> bool:
    for f in proposals_dir.glob("*.md"):
        meta, _ = parse_proposal(f.read_text(encoding="utf-8"))
        if meta.get("topic") == topic and meta.get("status") in ("pending", "approved", "applied"):
            return True
    return False


def build_proposals(stats: list[dict], config: dict, proposals_dir: Path, min_score: float) -> list[Path]:
    proposals_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    th = config["thresholds"]
    for st in stats:
        if st["score"] < min_score:
            continue
        counts = st["counts"]
        if counts.get("correction", 0) < th["correction"] and counts.get("repeat", 0) < th["repeat"] and counts.get("explicit", 0) < th["explicit"]:
            continue
        if proposal_exists(proposals_dir, st["topic"]):
            continue
        pid = _next_id(proposals_dir, st["topic"])
        evidence = "\n".join(f"- [{s['type']}] {s['quote']}  ({s['source']})" for s in st["samples"])
        body = PROPOSAL_TEMPLATE.format(
            id=pid, profile=config["profile"], topic=st["topic"],
            target=config["protected_files"][0], created=now_iso(),
            content=f"（待填写：关于「{st['topic']}」的具体规则文本）",
            count=st["count"], breakdown=st["breakdown"], evidence=evidence,
        )
        p = proposals_dir / f"{pid}.md"
        p.write_text(body, encoding="utf-8")
        created.append(p)
    return created


def parse_proposal(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return {}, text
    meta = dict(re.findall(r"^(\w+):\s*(.*)$", m.group(1), re.M))
    return meta, m.group(2)


def find_proposal(proposals_dir: Path, pid: str) -> Path:
    candidates = list(proposals_dir.glob(f"{pid}.md"))
    if not candidates:
        raise FileNotFoundError(f"proposal {pid} not found under {proposals_dir}")
    return candidates[0]


def set_status(p: Path, status: str, extra: str = "") -> None:
    meta, body = parse_proposal(p.read_text(encoding="utf-8"))
    meta["status"] = status
    if extra:
        meta["note"] = extra
    head = "\n".join(f"{k}: {v}" for k, v in meta.items())
    p.write_text(f"---\n{head}\n---\n{body}", encoding="utf-8")


# ---------------------------------------------------------------- ledger

def ledger_append(ledger_path: Path, entry: dict) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": now_iso(), **entry}, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- apply / rollback

def apply_proposal(proposals_dir: Path, backups_dir: Path, ledger_path: Path, pid: str, root: Path) -> str:
    p = find_proposal(proposals_dir, pid)
    meta, body = parse_proposal(p.read_text(encoding="utf-8"))
    if meta.get("status") != "approved":
        raise RuntimeError(f"proposal {pid} is {meta.get('status')}, need approved first")
    target = (root / meta["target"]).resolve()
    if not target.exists():
        target = (root / "memory" / meta["target"]).resolve()
    snap = backups_dir / pid
    snap.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
    shutil.copy2(target, snap / target.name)
    kind = meta.get("kind", "new")
    if kind == "refine":
        _apply_refine(target, body, pid)
    else:
        addition = f"\n\n<!-- applied from {pid} on {now_iso()} -->\n{body.split('## 理由', 1)[0].replace('## 建议改动', '## 规则').strip()}\n"
        with target.open("a", encoding="utf-8") as fh:
            fh.write(addition)
    set_status(p, "applied")
    ledger_append(ledger_path, {"action": "apply", "proposal_id": pid, "target": str(target), "kind": kind})
    return str(target)


def _section(body: str, title: str) -> str:
    m = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", body, re.S | re.M)
    return m.group(1).strip() if m else ""


def _apply_refine(target: Path, body: str, pid: str) -> None:
    """Replace the original rule entry with the refined one (versioned)."""
    old_block = _section(body, "原条目")
    new_block = _section(body, "建议改动")
    if not old_block or not new_block:
        raise RuntimeError(f"refine proposal {pid} is missing 原条目/建议改动 sections")
    text = target.read_text(encoding="utf-8")
    if old_block not in text:
        raise RuntimeError(f"original entry not found in {target}; refusing to apply")
    text = text.replace(old_block, new_block, 1)
    target.write_text(text, encoding="utf-8")


def rollback_proposal(proposals_dir: Path, backups_dir: Path, ledger_path: Path, pid: str) -> str:
    p = find_proposal(proposals_dir, pid)
    meta, _ = parse_proposal(p.read_text(encoding="utf-8"))
    snap = backups_dir / pid
    if not snap.exists() or not any(snap.iterdir()):
        raise FileNotFoundError(f"no backup for {pid}, nothing to roll back")
    backup_file = next(snap.iterdir())
    if not backup_file.is_file():
        raise FileNotFoundError(f"unexpected backup layout for {pid}")
    target = backup_file.parent  # snap dir itself; restore path recorded in ledger
    # restore: copy back to the original location recorded in the proposal's applied target
    ledger_entries = [json.loads(l) for l in ledger_path.read_text(encoding="utf-8").splitlines() if l.strip()] if ledger_path.exists() else []
    applied = [e for e in ledger_entries if e.get("proposal_id") == pid and e.get("action") == "apply"]
    if not applied:
        raise RuntimeError(f"no apply record for {pid} in ledger")
    orig = Path(applied[-1]["target"])
    shutil.copy2(backup_file, orig)
    set_status(p, "approved")
    ledger_append(ledger_path, {"action": "rollback", "proposal_id": pid, "target": str(orig)})
    return str(orig)


# ---------------------------------------------------------------- v0.2 refinement

REFINE_TRIGGER_WORDS = [
    "还要注意", "另外", "补充", "具体来说", "还有", "以及",
    "细化", "调整", "改成", "更新", "记得加", "加上", "注意一下",
]

REFINE_PROPOSAL_TEMPLATE = """---
id: {id}
status: pending
profile: {profile}
kind: refine
topic: {topic}
target: {target}
created: {created}
---
## 原条目
{old_entry}

## 建议改动
{new_entry}

## 理由
对话中出现针对已有规则「{topic}」的更细要求，匹配相似度 {score:.2f}，建议细化该条目。

## 候选依据
{evidence}
"""


def parse_rules_entries(text: str) -> list[dict]:
    """Extract rule entries: '- item' bullets and '### title' lines grouped by '## section'."""
    entries: list[dict] = []
    section = "通用"
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("## "):
            section = line[3:].strip()
        elif line.startswith("- ") or line.startswith("* "):
            entries.append({"section": section, "text": line[2:].strip()})
        elif line.startswith("### "):
            entries.append({"section": section, "text": line[4:].strip()})
    return entries


def entry_head(entry_text: str, max_len: int = 12) -> str:
    """Leading fragment of an entry used for keyword matching."""
    head = entry_text.split("：")[0].split(":")[0].strip()
    return head[:max_len]


def semantic_similarity(query: str, text: str, provider: str = "local") -> float:
    """Similarity backend. 'local' is the zero-dependency difflib scorer.

    Optional providers (openai / sentence-transformers) can be plugged in
    behind this function without touching the rest of the pipeline.
    """
    if provider in ("none", "local"):
        return SequenceMatcher(None, query, text).ratio()
    raise NotImplementedError(
        f"embedding provider '{provider}' requires optional dependencies; see docs/embedding.md"
    )


def detect_refinement_signals(text: str, entries: list[dict], trigger_words: list[str]) -> list[dict]:
    """A refinement signal = the head of an existing rule entry appears in the
    conversation together with a refinement trigger phrase."""
    signals = []
    for e in entries:
        head = entry_head(e["text"])
        if not head or len(head) < 2:
            continue
        if head in text:
            trig = [t for t in trigger_words if t in text]
            if trig:
                signals.append({"entry": e, "head": head, "triggers": trig, "quote": text.strip()[:200]})
    return signals


def build_refinement_proposals(signals: list[dict], config: dict, proposals_dir: Path) -> list[Path]:
    """For each refinement signal, propose merging the new detail into the matched entry.
    Proposals are diff-style (原条目 -> 建议改动); human approval required before apply."""
    proposals_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    provider = config.get("embedding", {}).get("provider", "local")
    seen: set[str] = set()
    for s in signals:
        entry = s["entry"]
        key = entry["text"][:20]
        if key in seen:
            continue
        seen.add(key)
        pid = _next_id(proposals_dir, entry["text"][:12])
        merged = f"{entry['text']}；{s['quote']}" if entry["text"] else s["quote"]
        evidence = "\n".join(f"- [{t}] {s['quote']}" for t in s["triggers"])
        body = REFINE_PROPOSAL_TEMPLATE.format(
            id=pid,
            profile=config["profile"],
            topic=entry["text"][:20],
            target=config.get("rules_file", "memory/MEMORY.md"),
            created=now_iso(),
            old_entry=entry["text"],
            new_entry=merged,
            score=semantic_similarity(entry["text"], s["quote"], provider),
            evidence=evidence,
        )
        p = proposals_dir / f"{pid}.md"
        p.write_text(body, encoding="utf-8")
        created.append(p)
    return created
