"""agent-evolve CLI.

Commands:
  evolve init [--root DIR]            scaffold the workspace layout
  evolve scan [--history DIR]         scan conversations, print signal stats
  evolve propose [--min-score N]      create proposals for topics above threshold
  evolve list [--status S]            list proposals
  evolve approve <id> [--approver A]  human approval (writes ledger)
  evolve reject <id> [--reason R]     reject a proposal
  evolve apply <id>                   apply an approved proposal (backup + merge)
  evolve rollback <id>                restore from the pre-apply backup

Discovery is automatic; nothing is ever written to protected files
without an explicit human `approve` step.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import core


def _paths(root: Path) -> dict:
    return {
        "root": root,
        "history": root / "history",
        "rules": root / "rules" / "config.json",
        "proposals": root / "proposals",
        "pending": root / "proposals" / "pending",
        "approved": root / "proposals" / "approved",
        "rejected": root / "proposals" / "rejected",
        "backups": root / "backups",
        "ledger": root / "ledger" / "approval.jsonl",
        "templates": root / "templates" / "proposal.md",
        "memory": root / "memory",
    }


def cmd_init(args) -> int:
    root = Path(args.root)
    p = _paths(root)
    for d in (p["history"], p["rules"], p["pending"], p["approved"], p["rejected"], p["backups"], p["ledger"].parent, p["templates"].parent, p["memory"]):
        d.mkdir(parents=True, exist_ok=True)
    cfg = p["rules"]
    if not cfg.exists():
        cfg.write_text(json.dumps(core.DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
    tpl = p["templates"]
    if not tpl.exists():
        tpl.write_text(core.PROPOSAL_TEMPLATE, encoding="utf-8")
    (root / "ledger" / "approval.jsonl").touch()
    print(f"initialized evolution workspace at {root}")
    print(f"  history/      put conversation logs here (.md/.txt/.jsonl)")
    print(f"  rules/config.json  topics, thresholds, profile, protected files")
    return 0


def cmd_scan(args) -> int:
    root = Path(args.root)
    p = _paths(root)
    config = core.load_config(p["rules"])
    signals = core.scan_history(Path(args.history), config)
    stats = core.aggregate(signals)
    print(f"scanned {len(signals)} signals across {len(stats)} topics\n")
    if not stats:
        print("no signals found. add conversation logs under history/ and tune rules/config.json topics.")
        return 0
    for st in stats:
        print(f"  {st['topic']:<16} score={st['score']:<5} total={st['count']:<3} {st['breakdown']}")
    return 0


def cmd_propose(args) -> int:
    root = Path(args.root)
    p = _paths(root)
    config = core.load_config(p["rules"])
    signals = core.scan_history(p["history"], config)
    stats = core.aggregate(signals)
    created = core.build_proposals(stats, config, p["pending"], args.min_score)
    if created:
        for f in created:
            print(f"created {f.name}")
    else:
        print("no proposals created (below threshold or already proposed)")
    return 0


def cmd_list(args) -> int:
    root = Path(args.root)
    p = _paths(root)
    for sub in ("pending", "approved", "rejected", "applied"):
        d = p["proposals"] / sub
        if not d.exists():
            continue
        for f in sorted(d.glob("*.md")):
            meta, _ = core.parse_proposal(f.read_text(encoding="utf-8"))
            if args.status and meta.get("status") != args.status:
                continue
            print(f"[{meta.get('status','?'):>8}] {f.stem}  {meta.get('topic','?')}")
    return 0


def cmd_approve(args) -> int:
    root = Path(args.root)
    p = _paths(root)
    f = core.find_proposal(p["pending"], args.id)
    core.set_status(f, "approved")
    core.ledger_append(p["ledger"], {"action": "approve", "proposal_id": args.id, "approver": args.approver})
    print(f"approved {args.id} by {args.approver}")
    return 0


def cmd_reject(args) -> int:
    root = Path(args.root)
    p = _paths(root)
    f = core.find_proposal(p["pending"], args.id)
    core.set_status(f, "rejected", extra=args.reason)
    core.ledger_append(p["ledger"], {"action": "reject", "proposal_id": args.id, "reason": args.reason})
    print(f"rejected {args.id}")
    return 0


def cmd_apply(args) -> int:
    root = Path(args.root)
    p = _paths(root)
    target = core.apply_proposal(p["pending"], p["backups"], p["ledger"], args.id, root)
    print(f"applied {args.id} -> {target}")
    return 0


def cmd_rollback(args) -> int:
    root = Path(args.root)
    p = _paths(root)
    target = core.rollback_proposal(p["pending"], p["backups"], p["ledger"], args.id)
    print(f"rolled back {args.id} -> restored {target}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="evolve", description="Universal Agent Evolution Protocol CLI")
    ap.add_argument("--root", default=".", help="evolution workspace root (default: .)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="scaffold workspace")
    sp = sub.add_parser("scan", help="scan conversations and print signal stats")
    sp.add_argument("--history", default=None, help="history dir (default: <root>/history)")
    sp = sub.add_parser("propose", help="create proposals for topics above threshold")
    sp.add_argument("--min-score", type=float, default=None, help="minimum aggregated score")
    sp = sub.add_parser("list", help="list proposals")
    sp.add_argument("--status", choices=["pending", "approved", "rejected", "applied"], default=None)
    sp = sub.add_parser("approve", help="approve a pending proposal (HUMAN ONLY)")
    sp.add_argument("id")
    sp.add_argument("--approver", default="human")
    sp = sub.add_parser("reject", help="reject a pending proposal")
    sp.add_argument("id")
    sp.add_argument("--reason", default="")
    sp = sub.add_parser("apply", help="apply an approved proposal")
    sp.add_argument("id")
    sp = sub.add_parser("rollback", help="restore pre-apply backup")
    sp.add_argument("id")

    args = ap.parse_args(argv)
    if args.cmd == "scan" and args.history is None:
        args.history = str(_paths(Path(args.root))["history"])

    handlers = {
        "init": cmd_init,
        "scan": cmd_scan,
        "propose": cmd_propose,
        "list": cmd_list,
        "approve": cmd_approve,
        "reject": cmd_reject,
        "apply": cmd_apply,
        "rollback": cmd_rollback,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
