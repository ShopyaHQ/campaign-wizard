#!/usr/bin/env python3
"""validate_state.py — the external transition validator.

    python3 scripts/validate_state.py --state campaigns/<run_id>/state.yaml
    python3 scripts/validate_state.py --state campaigns/<run_id>/state.yaml --to VALIDATED

The model is NEVER the authority on whether a stage is complete. This script is. It reads
schemas/workflow_state.schema.yaml (the declarative transition table) and
SHOPYA_CAMPAIGN_CHARTER.yaml (the pinned governing contract), evaluates prerequisites against
artifacts ON DISK and recorded owner decisions, and exits non-zero naming every failure.

It re-implements nothing from the schema: states, transitions, predicates, item predicates,
path resolution and refusal messages all come from that file. Changing the process means
editing the schema, not this script.
"""
import argparse, hashlib, json, os, sys
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEF_SCHEMA  = os.path.join(ROOT, "schemas", "workflow_state.schema.yaml")
DEF_CHARTER = os.path.join(ROOT, "SHOPYA_CAMPAIGN_CHARTER.yaml")
DEF_RUNS    = os.path.join(ROOT, "campaigns")

MISSING = object()


class Failure:
    def __init__(self, refusal, detail, path=None, expected=None, actual=None):
        self.refusal, self.detail = refusal, detail
        self.path, self.expected, self.actual = path, expected, actual

    def render(self, refusals):
        msg = refusals.get(self.refusal, {}).get("message", "").strip()
        ref = refusals.get(self.refusal, {}).get("charter_ref")
        out = ["  [%s] %s" % (self.refusal, self.detail)]
        if self.path is not None:
            out.append("      path:     %s" % self.path)
        if self.expected is not None:
            out.append("      expected: %r" % (self.expected,))
        if self.actual is not MISSING and self.actual is not None:
            out.append("      actual:   %r" % (self.actual,))
        elif self.actual is MISSING:
            out.append("      actual:   <absent>")
        if msg:
            out.append("      rule:     %s" % " ".join(msg.split()))
        if ref:
            out.append("      charter:  %s" % ref)
        return "\n".join(out)

    def as_dict(self):
        return {"refusal": self.refusal, "detail": self.detail, "path": self.path,
                "expected": self.expected,
                "actual": None if self.actual is MISSING else self.actual}


class Validator:
    def __init__(self, state_path, schema_path, charter_path, runs_dir, run_dir=None):
        self.state_path = os.path.abspath(state_path)
        # The LOGICAL run directory. When validating a proposed state held outside the repo
        # (atomic transition), this is supplied so the run is not mistaken for its own sibling.
        self.run_dir = os.path.abspath(run_dir) if run_dir else os.path.dirname(self.state_path)
        self.runs_dir = runs_dir
        self.schema = self._load(schema_path, "schema")
        self.charter = self._load(charter_path, "charter")
        self.state = self._load(state_path, "state")
        self.refusals = self.schema.get("refusals", {})
        self.states = {s["name"]: s for s in self.schema["states"]}
        self.failures = []
        self.warnings = []
        self._artifact_cache = {}

    # ---------- io ----------
    @staticmethod
    def _load(path, what):
        if not os.path.exists(path):
            sys.exit("FATAL: %s not found: %s" % (what, path))
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def fail(self, refusal, detail, path=None, expected=None, actual=MISSING):
        self.failures.append(Failure(refusal, detail, path, expected, actual))

    # ---------- artifacts ----------
    def artifact_record(self, key):
        return (self.state.get("artifacts") or {}).get(key)

    def _artifact_path(self, p):
        """Resolve a registered artifact path. Absolute: as-is. Relative: run-root first
        (current convention, NAMING_CONVENTIONS.md), repo-root second (legacy layout)."""
        if os.path.isabs(p):
            return p
        rr = os.path.join(self.run_dir, p)
        if os.path.exists(rr):
            return rr
        return os.path.join(ROOT, p)

    def artifact_doc(self, key):
        """Load an artifact's YAML. Returns MISSING if absent, superseded or unreadable."""
        if key in self._artifact_cache:
            return self._artifact_cache[key]
        rec = self.artifact_record(key)
        doc = MISSING
        if rec:
            if rec.get("status", "current") != "current":
                doc = MISSING
            else:
                p = self._artifact_path(rec.get("path", ""))
                if os.path.exists(p) and p.endswith((".yaml", ".yml")):
                    try:
                        with open(p, encoding="utf-8") as f:
                            doc = yaml.safe_load(f)
                    except Exception:
                        doc = MISSING
        self._artifact_cache[key] = doc
        return doc

    # ---------- path resolution ----------
    def _root_doc(self, root):
        pr = (self.schema.get("path_resolution") or {}).get(root)
        if not pr:
            return self.state, False
        doc = self.artifact_doc(pr["artifact"])
        if doc is MISSING:
            return MISSING, True
        if pr.get("key"):
            return (doc.get(pr["key"], MISSING) if isinstance(doc, dict) else MISSING), True
        return doc, True

    def resolve_all(self, dotted):
        """Return [(concrete_path, value)]. Expands when a segment addresses into a list."""
        segs = dotted.split(".")
        base, mapped = self._root_doc(segs[0])
        if base is MISSING:
            return [(dotted, MISSING)]
        if mapped and (self.schema["path_resolution"].get(segs[0]) or {}).get("key"):
            cur = [(segs[0], base)]          # root already IS the value
            rest = segs[1:]
        elif mapped:
            cur = [(segs[0], base)]
            rest = segs[1:]
        else:
            cur = [("", base)]
            rest = segs
        for seg in rest:
            nxt = []
            for pfx, val in cur:
                if isinstance(val, list):
                    for i, item in enumerate(val):
                        v = item.get(seg, MISSING) if isinstance(item, dict) else MISSING
                        nxt.append(("%s[%d].%s" % (pfx, i, seg), v))
                elif isinstance(val, dict):
                    nxt.append((("%s.%s" % (pfx, seg)).lstrip("."), val.get(seg, MISSING)))
                else:
                    nxt.append((("%s.%s" % (pfx, seg)).lstrip("."), MISSING))
            cur = nxt
        return [(p or dotted, v) for p, v in cur]

    def resolve(self, dotted):
        r = self.resolve_all(dotted)
        return r[0][1] if len(r) == 1 else [v for _, v in r]

    # ---------- predicates ----------
    def check(self, p, args, ctx):
        fn = getattr(self, "p_" + p, None)
        if fn is None:
            self.fail("prerequisites_unmet",
                      "%s: predicate '%s' is not in the schema vocabulary" % (ctx, p))
            return False
        return fn(args, ctx)

    def p_charter_approved(self, a, ctx):
        st = (self.charter.get("charter") or {}).get("status")
        if st != "approved":
            self.fail("charter_not_approved", "%s: pinned charter is %r" % (ctx, st),
                      "charter.status", "approved", st)
            return False
        return True

    def p_versions_pinned(self, a, ctx):
        ok = True
        for f in ("spec_version", "charter_version"):
            v = (self.state.get("run") or {}).get(f)
            if not v:
                self.fail("prerequisites_unmet", "%s: run.%s is not pinned" % (ctx, f),
                          "run." + f, "<non-null>", v)
                ok = False
        return ok

    def p_versions_unchanged(self, a, ctx):
        """run.spec_version / charter_version may only change through a recorded migration.
        The current value must equal EITHER the value pinned at NEW, OR the `to_*` of the
        latest run.migration record. Any other change is a silent drift and is refused."""
        run = self.state.get("run") or {}
        hist = self.state.get("workflow", {}).get("history") or []
        pinned = next((h for h in hist if h.get("to") == "NEW"), None)
        migs = run.get("migration") or []
        latest = migs[-1] if migs else None
        ok = True
        for f, refusal in (("spec_version", "spec_version_changed_mid_run"),
                           ("charter_version", "charter_version_changed_without_migration")):
            was = (pinned or {}).get("pinned_" + f)
            allowed = {was}
            if latest is not None:
                allowed.add(latest.get("to_" + f))
            if was and run.get(f) not in allowed:
                self.fail(refusal, "%s: %s is %r — neither the value pinned at NEW (%r) nor a "
                          "recorded migration target" % (ctx, f, run.get(f), was),
                          "run." + f, "pinned value or a migrated target", run.get(f))
                ok = False
        return ok

    def p_canon_matches_or_migrated(self, a, ctx):
        """Model B (current-canon): the validator ALWAYS evaluates rules against the on-disk
        canon. A run whose pinned versions differ from the loaded canon is stale and MUST be
        migrated (run.py migrate) before it can transition — otherwise it would be silently
        judged under rules it never adopted. Provenance (creating versions) stays in history."""
        run = self.state.get("run") or {}
        loaded = {"spec_version": (self.schema.get("schema") or {}).get("version"),
                  "charter_version": (self.charter.get("charter") or {}).get("version")}
        ok = True
        for f in ("spec_version", "charter_version"):
            if run.get(f) and loaded[f] and run.get(f) != loaded[f]:
                self.fail("run_canon_version_mismatch",
                          "%s: run.%s is %r but the loaded canon is %r — this run predates the "
                          "current rules and must be migrated (run.py migrate) before it can "
                          "transition; the validator evaluates current canon, so an un-migrated "
                          "run would be judged under rules it never adopted"
                          % (ctx, f, run.get(f), loaded[f]),
                          "run." + f, loaded[f], run.get(f))
                ok = False
        return ok

    def p_version_not_withdrawn(self, a, ctx):
        ch = self.charter.get("charter") or {}
        if "withdrawn_versions" not in ch:
            # RESERVED, v1. Say so out loud rather than passing silently.
            w = ((self.schema.get("reserved_not_implemented") or {})
                 .get("charter.withdrawn_versions") or {}).get("warning")
            if w and w not in self.warnings:
                self.warnings.append("WARNING: " + w)
            return True
        wd = ch.get("withdrawn_versions") or []
        v = (self.state.get("run") or {}).get("charter_version")
        if v in wd:
            self.fail("withdrawn_version_loaded", "%s: charter_version %r is withdrawn" % (ctx, v),
                      "run.charter_version", "not withdrawn", v)
            return False
        return True

    def p_artifact_exists(self, a, ctx):
        key = a[0]
        rec = self.artifact_record(key)
        if not rec:
            self.fail("prerequisites_unmet", "%s: artifact %r is not registered" % (ctx, key),
                      "artifacts.%s" % key, "<registered>", MISSING)
            return False
        if rec.get("status", "current") != "current":
            self.fail("stale_artifact_treated_as_current",
                      "%s: artifact %r is superseded" % (ctx, key),
                      "artifacts.%s.status" % key, "current", rec.get("status"))
            return False
        p = rec.get("path", "")
        full = self._artifact_path(p)
        if not os.path.exists(full):
            self.fail("artifact_deleted", "%s: artifact %r missing on disk (%s)" % (ctx, key, p),
                      "artifacts.%s.path" % key, "<exists>", p)
            return False
        want = rec.get("sha256")
        if want and os.path.isfile(full):
            got = hashlib.sha256(open(full, "rb").read()).hexdigest()
            if got != want:
                self.fail("prerequisites_unmet",
                          "%s: artifact %r hash mismatch" % (ctx, key),
                          "artifacts.%s.sha256" % key, want, got)
                return False
        return True

    def p_artifact_current(self, a, ctx):
        rec = self.artifact_record(a[0]) or {}
        if rec.get("status", "current") != "current":
            self.fail("stale_artifact_treated_as_current",
                      "%s: artifact %r is superseded" % (ctx, a[0]),
                      "artifacts.%s.status" % a[0], "current", rec.get("status"))
            return False
        return True

    def p_field_present(self, a, ctx):
        ok = True
        for p, v in self.resolve_all(a[0]):
            if v is MISSING:
                self.fail("prerequisites_unmet", "%s: %s is absent" % (ctx, p), p, "<present>", MISSING)
                ok = False
        return ok

    def p_field_non_empty(self, a, ctx):
        ok = True
        for p, v in self.resolve_all(a[0]):
            if v is MISSING or v is None or v == "" or v == [] or v == {}:
                self.fail("prerequisites_unmet", "%s: %s is empty" % (ctx, p), p, "<non-empty>",
                          MISSING if v is MISSING else v)
                ok = False
        return ok

    def p_field_equals(self, a, ctx):
        path, want = a[0], a[1]
        ok = True
        for p, v in self.resolve_all(path):
            if v != want:
                self.fail("prerequisites_unmet", "%s: %s != %r" % (ctx, p, want), p, want, v)
                ok = False
        return ok

    def p_field_in(self, a, ctx):
        path, allowed = a[0], a[1]
        ok = True
        for p, v in self.resolve_all(path):
            if v is MISSING or v not in allowed:
                self.fail("prerequisites_unmet", "%s: %s not in closed set" % (ctx, p),
                          p, allowed, v)
                ok = False
        return ok

    def p_count_between(self, a, ctx):
        path, lo, hi = a[0], a[1], a[2]
        v = self.resolve(path)
        n = len(v) if isinstance(v, (list, dict)) else 0
        if not (lo <= n <= hi):
            self.fail("prerequisites_unmet", "%s: %s has %d items" % (ctx, path, n),
                      path, "%d..%d" % (lo, hi), n)
            return False
        return True

    def p_count_max(self, a, ctx):
        path, n_max = a[0], a[1]
        v = self.resolve(path)
        n = len(v) if isinstance(v, (list, dict)) else 0
        if n > n_max:
            self.fail("prerequisites_unmet", "%s: %s has %d items" % (ctx, path, n),
                      path, "<= %d" % n_max, n)
            return False
        return True

    def p_sum_max(self, a, ctx):
        """Sum numeric values at the path. Missing or non-numeric fails loudly.
        A null cap (A4, 2026-08-10) means NO ceiling: the declaration and numericity
        requirements still apply in full, but no maximum is enforced — used where an owner
        ruling removed an obsolete cap without inventing a replacement number."""
        path, cap = a[0], a[1]
        pairs = self.resolve_all(path)
        if not pairs or all(v is MISSING for _, v in pairs):
            self.fail("prerequisites_unmet", "%s: %s resolved to nothing" % (ctx, path),
                      path, "numeric values", MISSING)
            return False
        total, ok = 0, True
        for p, val in pairs:
            if val is MISSING or val is None:
                self.fail("prerequisites_unmet",
                          "%s: %s is undeclared — a cap cannot skip undeclared values" % (ctx, p),
                          p, "a number (0 if none)", MISSING)
                ok = False
            elif isinstance(val, bool) or not isinstance(val, (int, float)):
                self.fail("prerequisites_unmet", "%s: %s is not numeric" % (ctx, p),
                          p, "a number", val)
                ok = False
            else:
                total += val
        if ok and cap is not None and total > cap:
            self.fail("prerequisites_unmet",
                      "%s: %s sums to %s, over the cap" % (ctx, path, total),
                      path, "<= %s" % cap, total)
            return False
        return ok

    def p_each_has_keys(self, a, ctx):
        """Key PRESENCE only. A null value passes — the stage schema decides nullability."""
        return self._each_has(a, ctx, require_non_null=False)

    def p_each_has_non_null(self, a, ctx):
        return self._each_has(a, ctx, require_non_null=True)

    def p_each_has(self, a, ctx):
        # DEPRECATED alias, retained so an older pinned spec still resolves.
        return self._each_has(a, ctx, require_non_null=True)

    def _each_has(self, a, ctx, require_non_null=True):
        path, fields = a[0], a[1]
        val = self.resolve(path)
        if val is MISSING:
            self.fail("prerequisites_unmet", "%s: %s is absent" % (ctx, path), path, fields, MISSING)
            return False
        items = val if isinstance(val, list) else [val]
        ok = True
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                self.fail("prerequisites_unmet", "%s: %s[%d] is not a record" % (ctx, path, i),
                          "%s[%d]" % (path, i), "mapping", type(item).__name__)
                ok = False
                continue
            for f in fields:
                if f not in item:
                    self.fail("prerequisites_unmet",
                              "%s: %s[%d] missing required key %r" % (ctx, path, i, f),
                              "%s[%d].%s" % (path, i, f), "<key present>", MISSING)
                    ok = False
                elif require_non_null and item.get(f) in (None, "", [], {}):
                    self.fail("prerequisites_unmet",
                              "%s: %s[%d] required field %r is null or empty" % (ctx, path, i, f),
                              "%s[%d].%s" % (path, i, f), "<non-null>", item.get(f))
                    ok = False
        return ok

    def p_each_satisfies(self, a, ctx):
        path, ipred = a[0], a[1]
        spec = (self.schema.get("item_predicates") or {}).get(ipred)
        if not spec:
            self.fail("prerequisites_unmet", "%s: unknown item predicate %r" % (ctx, ipred))
            return False
        val = self.resolve(path)
        items = val if isinstance(val, list) else ([] if val is MISSING else [val])
        ok = True
        for i, item in enumerate(items):
            if not self._item_ok(ipred, spec, item):
                self.fail("prerequisites_unmet",
                          "%s: %s" % (ctx, spec.get("failure_message", ipred)),
                          "%s[%d]" % (path, i), ipred, item if isinstance(item, dict) else item)
                ok = False
        return ok

    def _item_ok(self, name, spec, item):
        if not isinstance(item, dict):
            return False
        if name == "exactly_one_collection":
            c = item.get("collection_id")
            return c is not None and not isinstance(c, (list, dict)) and c != ""
        if name == "has_rail_position":
            rp = item.get("rail_position")
            return isinstance(rp, int) and rp >= 0
        if name == "meets_technical_minimum":
            return isinstance(item.get("eligible_count"), int) and item["eligible_count"] >= 1
        if name == "meets_quality_minimum_or_has_exception":
            mins = spec.get("quality_minimums", {})
            need = mins.get(item.get("entity_type"))
            n = item.get("eligible_count")
            if isinstance(n, int) and need is not None and n >= need:
                return True
            exc = item.get("quality_exception") or {}
            if exc.get("approved") is True and exc.get("approved_by") and exc.get("rationale"):
                self.warnings.append(
                    "WARNING: %s below quality minimum (%s < %s) — approved exception by %s"
                    % (item.get("entity_id", "?"), n, need, exc.get("approved_by")))
                return True
            return False
        return False

    def p_owner_decision_recorded(self, a, ctx):
        did = a[0]
        d = (self.state.get("owner_decisions") or {}).get(did)
        if not d or d.get("decided") is not True or not d.get("decided_by") or not d.get("decided_at"):
            self.fail("closing_sentence_is_not_proof",
                      "%s: owner decision %r is not recorded" % (ctx, did),
                      "owner_decisions.%s" % did,
                      "{status: owner_confirmed, decided: true, decided_by, decided_at}",
                      d if d else MISSING)
            return False
        # governance_003: only an owner_confirmed entry gates a transition. A provisional
        # recommendation, engine fulfillment, validator pass or exception never satisfies it.
        if d.get("status") != "owner_confirmed":
            self.fail("closing_sentence_is_not_proof",
                      "%s: owner decision %r has status %r, not owner_confirmed — an agent "
                      "recommendation or engine fulfillment cannot gate this transition"
                      % (ctx, did, d.get("status")),
                      "owner_decisions.%s.status" % did, "owner_confirmed", d.get("status"))
            return False
        # A1 (2026-08-10): a decision invalidated by a reopen is not a live approval. It gates
        # again only after the owner genuinely re-records it (record-decision clears the entry
        # from state.invalidated on an owner_confirmed re-record).
        if did in (self.state.get("invalidated") or []):
            self.fail("stale_decision_after_reopen",
                      "%s: owner decision %r was invalidated by a reopen and cannot gate a "
                      "transition until re-recorded by the owner" % (ctx, did),
                      "invalidated", "does not include %r" % did, did)
            return False
        return True

    def p_pending_validation_passed(self, a, ctx):
        vid = a[0]
        pv = next((p for p in (self.charter.get("charter") or {}).get("pending_validations", [])
                   if p.get("id") == vid), None)
        if not pv or pv.get("passed") is not True:
            self.fail("capability_claimed_while_pending",
                      "%s: charter pending_validation %r has not passed" % (ctx, vid),
                      "charter.pending_validations.%s.passed" % vid, True,
                      (pv or {}).get("passed", MISSING))
            return False
        return True

    def p_capability_permitted(self, a, ctx):
        cap = a[0]
        claimed = [c.get("capability") for c in (self.state.get("capability_claims") or [])]
        if cap not in claimed:
            return True                       # not claimed -> nothing to permit
        for pv in (self.charter.get("charter") or {}).get("pending_validations", []):
            if cap in (pv.get("blocking_for") or []) and pv.get("passed") is not True:
                self.fail("capability_claimed_while_pending",
                          "%s: run claims %r, blocked by unpassed validation %r"
                          % (ctx, cap, pv.get("id")),
                          "capability_claims", "not claimed, or validation passed", cap)
                return False
        return True

    def p_campaign_id_unique(self, a, ctx):
        cid = ((self.state.get("identity") or {}).get("campaign_id") or {}).get("value")
        if not cid:
            return True
        mine = (self.state.get("run") or {}).get("run_id")
        for other, doc in self._sibling_states():
            if doc.get("run", {}).get("run_id") == mine:
                continue
            o = (doc.get("identity") or {}).get("campaign_id") or {}
            if o.get("value") != cid:
                continue
            live = doc.get("workflow", {}).get("state") not in ("ABANDONED", "REVIEWED")
            if live or o.get("externally_referenced") is True:
                self.fail("campaign_id_collision",
                          "%s: campaign_id %r already owned by %s" % (ctx, cid, other),
                          "identity.campaign_id.value", "unique", cid)
                return False
        return True

    def p_last_validation_passed(self, a, ctx):
        att = self.state.get("validation_attempts") or []
        if not att:
            self.fail("validation_failure_treated_as_transition",
                      "%s: no validation has been attempted" % ctx,
                      "validation_attempts", "at least one passing attempt", [])
            return False
        last = att[-1]
        if last.get("result") != "passed":
            self.fail("validation_failure_treated_as_transition",
                      "%s: last validation attempt failed (%d failure(s))"
                      % (ctx, len(last.get("failures") or [])),
                      "validation_attempts[-1].result", "passed", last.get("result"))
            return False
        if last.get("invalidated_at"):
            self.fail("prerequisites_unmet",
                      "%s: last passing validation was invalidated by %r — revalidate"
                      % (ctx, last.get("invalidated_by_decision")),
                      "validation_attempts[-1].invalidated_at", None, last.get("invalidated_at"))
            return False
        return True

    def p_validation_binds_products_csv(self, a, ctx):
        """The passing attempt must be bound to the registered products_csv by hash.
        A validation attempt is written ONLY by run.py validate-execution, which stamps
        output_sha256 = sha256(built CSV) and registers that same file as products_csv.
        Requiring equality here means an agent cannot hand-author a CSV, register it, and
        separately fabricate a 'passed' attempt — the two are no longer settable, and their
        hashes must agree."""
        att = self.state.get("validation_attempts") or []
        if not att:
            self.fail("validation_failure_treated_as_transition",
                      "%s: no validation attempt to bind" % ctx, "validation_attempts",
                      "a passing attempt bound to products_csv", [])
            return False
        last = att[-1]
        stamped = last.get("output_sha256")
        rec = self.artifact_record("products_csv") or {}
        # A1 (2026-08-10): a superseded products_csv can never anchor a live binding — the
        # schema rule "a superseded artifact can never satisfy a gate" applies to hash
        # anchors too, not only to artifact_exists.
        if rec and rec.get("status", "current") != "current":
            self.fail("stale_artifact_treated_as_current",
                      "%s: products_csv is superseded — a superseded build cannot anchor a "
                      "validation binding; regenerate via validate-execution" % ctx,
                      "artifacts.products_csv.status", "current", rec.get("status"))
            return False
        registered = rec.get("sha256")
        if not stamped or not registered or stamped != registered:
            self.fail("validation_failure_treated_as_transition",
                      "%s: passing attempt is not bound to the registered products_csv "
                      "(attempt output_sha256=%r, products_csv sha256=%r) — run "
                      "validate-execution so the pass is computed from the built file"
                      % (ctx, stamped, registered),
                      "validation_attempts[-1].output_sha256", registered, stamped)
            return False
        # A stale-truth (--allow-stale) or legacy-replay build is diagnostic, never launch-ready.
        # validate-execution never produces such an attempt; a hand-forged one is refused here.
        if last.get("production") is not True or last.get("allow_stale_used") or last.get("legacy_replay_used"):
            self.fail("validation_failure_treated_as_transition",
                      "%s: the bound validation attempt is not a production build "
                      "(production=%r, allow_stale_used=%r, legacy_replay_used=%r) — stale or "
                      "legacy builds cannot satisfy VALIDATED"
                      % (ctx, last.get("production"), last.get("allow_stale_used"),
                         last.get("legacy_replay_used")),
                      "validation_attempts[-1].production", True, last.get("production"))
            return False
        return True

    def p_verification_bound_to_executed_build(self, a, ctx):
        """LIVE consumes a COMPUTED verification record (run.py verify-live), not an asserted
        boolean. The record must report a pass, be bound by build_sha256 to the registered
        products_csv, and — for a human-observed result — name who observed it."""
        v = self.state.get("verification") or {}
        # A1 (2026-08-10): a verification invalidated by a reopen is history, not proof.
        if v.get("invalidated_at"):
            self.fail("prerequisites_unmet",
                      "%s: verification was invalidated by %r — a pre-reopen probe cannot "
                      "satisfy LIVE; re-run verify-live against the regenerated build"
                      % (ctx, v.get("invalidated_by_decision")),
                      "verification.invalidated_at", None, v.get("invalidated_at"))
            return False
        vrec = self.artifact_record("products_csv") or {}
        if vrec and vrec.get("status", "current") != "current":
            self.fail("stale_artifact_treated_as_current",
                      "%s: products_csv is superseded — verification cannot bind to a "
                      "superseded build" % ctx,
                      "artifacts.products_csv.status", "current", vrec.get("status"))
            return False
        if v.get("result") != "pass" or v.get("post_cache_verified") is not True:
            self.fail("prerequisites_unmet",
                      "%s: verification is not a recorded pass (result=%r, post_cache_verified=%r)"
                      % (ctx, v.get("result"), v.get("post_cache_verified")),
                      "verification.result", "pass", v.get("result"))
            return False
        vsha = v.get("build_sha256")
        registered = (self.artifact_record("products_csv") or {}).get("sha256")
        if not vsha or not registered or vsha != registered:
            self.fail("prerequisites_unmet",
                      "%s: verification.build_sha256 (%r) does not match the registered "
                      "products_csv (%r) — verify the build that was actually executed"
                      % (ctx, vsha, registered),
                      "verification.build_sha256", registered, vsha)
            return False
        if v.get("method") == "human_observation" and not v.get("observed_by"):
            self.fail("prerequisites_unmet",
                      "%s: human-observed verification must record observed_by" % ctx,
                      "verification.observed_by", "<non-empty>", MISSING)
            return False
        if v.get("method") not in ("automated_probe", "human_observation"):
            self.fail("prerequisites_unmet",
                      "%s: verification.method must be automated_probe or human_observation (got %r)"
                      % (ctx, v.get("method")), "verification.method",
                      "automated_probe|human_observation", v.get("method"))
            return False
        return True

    # (F5, 2026-08-09) removed p_downstream_superseded: it was a `return True` stub referenced
    # by no prerequisite. Reopen supersession is enforced concretely in check_reopen against the
    # transition's supersedes_artifacts list, not via this predicate.

    # ---------- sibling runs ----------
    def _sibling_states(self):
        out = []
        if not os.path.isdir(self.runs_dir):
            return out
        cand = []
        for d in sorted(os.listdir(self.runs_dir)):
            if d == "_to_delete":
                continue
            base = os.path.join(self.runs_dir, d)
            if not os.path.isdir(base):
                continue
            if d == "_drafts":
                cand += [(x, os.path.join(base, x)) for x in sorted(os.listdir(base))]
            elif os.path.isdir(os.path.join(base, "runs")):
                rb = os.path.join(base, "runs")
                cand += [(x, os.path.join(rb, x)) for x in sorted(os.listdir(rb))]
            else:
                cand.append((d, base))
        for d, dirp in cand:
            p = os.path.join(dirp, "state.yaml")
            # A run is never its own sibling. Compare DIRECTORIES, not file paths — during an
            # atomic transition the file under validation is <run_dir>/.state.proposed.yaml,
            # which would otherwise match its own canonical state.yaml as a different run.
            if os.path.dirname(os.path.abspath(p)) == self.run_dir or not os.path.exists(p):
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    out.append((d, yaml.safe_load(f) or {}))
            except Exception:
                pass
        return out

    # ---------- always-on invariants ----------
    def invariants(self):
        ctx = "invariant"
        self.p_versions_pinned([], ctx)
        self.p_versions_unchanged([], ctx)
        self.p_canon_matches_or_migrated([], ctx)
        self.p_version_not_withdrawn([], ctx)

        run_id = (self.state.get("run") or {}).get("run_id")
        for other, doc in self._sibling_states():
            if doc.get("run", {}).get("run_id") == run_id:
                self.fail("run_id_reused", "run_id %r also used by %s" % (run_id, other),
                          "run.run_id", "globally unique", run_id)

        ident = (self.state.get("identity") or {}).get("campaign_id") or {}
        if ident.get("externally_referenced") is True:
            hist_ids = {h.get("campaign_id_at_transition")
                        for h in (self.state.get("workflow", {}).get("history") or [])
                        if h.get("campaign_id_at_transition")}
            stale = {h for h in hist_ids if h != ident.get("value")}
            fer = ident.get("first_external_reference") or {}
            if stale:
                self.fail("campaign_id_mutated_after_external_reference",
                          "campaign_id changed after external reference: %s -> %r"
                          % (sorted(stale), ident.get("value")),
                          "identity.campaign_id.value", sorted(stale), ident.get("value"))
            if not all(fer.get(k) for k in ("system", "artifact", "timestamp")):
                self.fail("prerequisites_unmet",
                          "externally_referenced is true but first_external_reference is incomplete",
                          "identity.campaign_id.first_external_reference",
                          "{system, artifact, timestamp}", fer)

        et = self.state.get("execution_tracking") or {}
        if et.get("external_handoffs_implemented") in ("partial", "complete") \
                and not (self.state.get("owner_decisions") or {}).get("handoffs_implemented_reported"):
            self.fail("handoff_reported_as_implemented",
                      "external_handoffs_implemented is %r with no owner report"
                      % et.get("external_handoffs_implemented"),
                      "execution_tracking.external_handoffs_implemented", "unknown",
                      et.get("external_handoffs_implemented"))

        # NOTE (F5, 2026-08-09): the former frozen_collection_modified check iterated
        # collection_freeze.modified_since_freeze — a field no command ever writes and that is
        # not settable. It could never fire in normal operation (fake enforcement) and was
        # removed rather than left as a phantom guard. Detecting a REAL post-LIVE modification
        # needs the engine to diff live collection contents against the freeze snapshot's
        # per-collection hashes and report drift; that collection-diff writer is a NEXT_PASS
        # item. The refusal string frozen_collection_modified is retained in the schema for
        # when that writer lands. Until then, freeze integrity is not machine-enforced here.

        # governance_003: decision-ledger status integrity. product_owner and decided:true are
        # valid ONLY on an owner_confirmed entry; agent recommendations and engine fulfillment
        # must never be stamped as owner decisions.
        for did, d in (self.state.get("owner_decisions") or {}).items():
            if not isinstance(d, dict):
                continue
            st = d.get("status")
            if d.get("decided_by") == "product_owner" and st != "owner_confirmed":
                self.fail("decision_status_misstamped",
                          "owner_decisions.%s is decided_by product_owner but status is %r "
                          "(only owner_confirmed may carry product_owner)" % (did, st),
                          "owner_decisions.%s.status" % did, "owner_confirmed", st)
            if d.get("decided") is True and st != "owner_confirmed":
                self.fail("decision_status_misstamped",
                          "owner_decisions.%s sets decided: true but status is %r "
                          "(decided is true only when owner_confirmed)" % (did, st),
                          "owner_decisions.%s.status" % did, "owner_confirmed", st)

        for key, rec in (self.state.get("artifacts") or {}).items():
            p = rec.get("path", "")
            full = self._artifact_path(p)
            if not os.path.exists(full):
                self.fail("artifact_deleted",
                          "artifact %r is registered but missing on disk" % key,
                          "artifacts.%s.path" % key, "<exists>", p)

        # A2 (2026-08-10): status/proof coherence. 'validated' is a machine-checkable claim:
        # it holds ONLY while the last non-invalidated passing validation attempt is a
        # production build hash-bound to the CURRENT products_csv. A migrated run whose
        # traversed proof fails the current canon may not remain semantically post-VALIDATED
        # on it (run.py migrate stamps such proof invalid and downgrades this status; this
        # invariant catches any state that dodged the writer).
        if et.get("seam6_execution_status") == "validated":
            live = [x for x in (self.state.get("validation_attempts") or [])
                    if x.get("result") == "passed" and not x.get("invalidated_at")]
            csv_rec = self.artifact_record("products_csv") or {}
            lastp = live[-1] if live else None
            bound = (lastp is not None
                     and lastp.get("production") is True
                     and lastp.get("output_sha256")
                     and lastp.get("output_sha256") == csv_rec.get("sha256")
                     and csv_rec.get("status", "current") == "current"
                     and not lastp.get("allow_stale_used")
                     and not lastp.get("legacy_replay_used"))
            if not bound:
                self.fail("stale_execution_proof",
                          "seam6_execution_status is 'validated' but the last non-invalidated "
                          "passing validation attempt is not a production build hash-bound to "
                          "the current products_csv — regenerate via validate-execution "
                          "(canon migration stamps such stale proof invalid)",
                          "execution_tracking.seam6_execution_status",
                          "a live hash-bound production pass",
                          "unbound or invalidated proof")

    # ---------- artifact structural validation (separate phase) ----------
    def check_artifacts(self):
        reg = self.schema.get("artifact_schemas") or {}
        for key, meta in reg.items():
            rec = self.artifact_record(key)
            if not rec or rec.get("status", "current") != "current":
                continue
            doc = self.artifact_doc(key)
            if doc is MISSING or not isinstance(doc, dict):
                self.fail("artifact_structure_invalid",
                          "artifact %r is registered but unreadable or not a mapping" % key,
                          "artifacts.%s.path" % key, "readable YAML mapping", rec.get("path"))
                continue
            sp = os.path.join(ROOT, meta["schema"])
            if not os.path.exists(sp):
                self.fail("artifact_structure_invalid",
                          "stage schema missing for %r: %s" % (key, meta["schema"]))
                continue
            spec = self._load(sp, "stage schema")
            getattr(self, "_struct_" + meta["validator"])(key, doc, spec)

    def _bad(self, key, path, expected, actual, detail):
        self.fail("artifact_structure_invalid", "%s: %s" % (key, detail), path, expected, actual)

    def _struct_frame(self, key, doc, spec):
        for name, f in (spec.get("fields") or {}).items():
            present = name in doc
            val = doc.get(name, MISSING)
            if f.get("required") and not present:
                self._bad(key, name, "<present>", MISSING, "required field %r absent" % name)
                continue
            if not present:
                continue
            if f.get("type") == "list":
                if not isinstance(val, list):
                    self._bad(key, name, "list", type(val).__name__, "%r must be a list" % name)
                    continue
                if not val and not f.get("allows_empty") and f.get("required"):
                    self._bad(key, name, "non-empty list", val, "%r may not be empty" % name)
                for i, item in enumerate(val):
                    if f.get("item_enum") and item not in f["item_enum"]:
                        self._bad(key, "%s[%d]" % (name, i), f["item_enum"], item,
                                  "value not in the closed set")
            elif f.get("type") == "mapping":
                if not isinstance(val, dict):
                    self._bad(key, name, "mapping", type(val).__name__, "%r must be a mapping" % name)
                else:
                    for sub, sf in (f.get("fields") or {}).items():
                        if sub not in val:
                            self._bad(key, "%s.%s" % (name, sub), "<present>", MISSING,
                                      "required subfield absent")
            else:
                if f.get("required") and not f.get("nullable") and val in (None, "", [], {}):
                    self._bad(key, name, "<non-empty>", val, "required field %r is empty" % name)

    def _struct_signals(self, key, doc, spec):
        sd = spec.get("signals_document") or {}
        for name, f in (sd.get("top_level") or {}).items():
            if not f.get("required"):
                continue
            if name not in doc:
                self._bad(key, name, "<present>", MISSING, "required top-level field absent")
            elif doc.get(name) in (None, "") and not f.get("allows_empty"):
                self._bad(key, name, "<non-empty>", doc.get(name), "required field is empty")
        fams = ((spec.get("evidence_families") or {}).get("values")) or []
        if (spec.get("evidence_families") or {}).get("required_coverage") == "all":
            got = set(doc.get("evidence_families_covered") or [])
            missing = [f for f in fams if f not in got]
            if missing:
                self._bad(key, "evidence_families_covered", fams, sorted(got),
                          "scan must cover all six families; missing %s" % missing)
        rec = sd.get("signal_record") or {}
        req = [n for n, f in rec.items() if isinstance(f, dict) and f.get("required")]
        seen = set()
        for i, sig in enumerate(doc.get("signals") or []):
            p = "signals[%d]" % i
            if not isinstance(sig, dict):
                self._bad(key, p, "mapping", type(sig).__name__, "signal is not a record"); continue
            for n in req:
                nullable = (rec[n] or {}).get("nullable")
                if n not in sig:
                    self._bad(key, "%s.%s" % (p, n), "<present>", MISSING, "required field absent")
                elif sig.get(n) in (None, "", [], {}) and not nullable:
                    self._bad(key, "%s.%s" % (p, n), "<non-empty>", sig.get(n), "required field empty")
            if sig.get("evidence_type") and sig["evidence_type"] not in fams:
                self._bad(key, "%s.evidence_type" % p, fams, sig["evidence_type"], "not a valid family")
            conf = (rec.get("confidence") or {}).get("values") or []
            if sig.get("confidence") and sig["confidence"] not in conf:
                self._bad(key, "%s.confidence" % p, conf, sig["confidence"], "not a valid grade")
            if isinstance(sig.get("limitations"), str) and sig["limitations"].strip().lower() in \
                    ("none", "n/a", "na", "-"):
                self._bad(key, "%s.limitations" % p, "a real limitation", sig["limitations"],
                          "'none' is not an acceptable limitations value")
            do, it = sig.get("direct_observation"), sig.get("interpretation")
            if isinstance(do, str) and isinstance(it, str) and do.strip() and do.strip() == it.strip():
                self._bad(key, "%s.interpretation" % p, "distinct from direct_observation", it,
                          "observation and interpretation must not restate each other")
            sid = sig.get("signal_id")
            if sid in seen:
                self._bad(key, "%s.signal_id" % p, "unique", sid, "duplicate signal_id")
            seen.add(sid)

    # ---------- state / transition ----------
    def check_state_prereqs(self, name):
        st = self.states.get(name)
        if not st:
            self.fail("illegal_transition", "unknown state %r" % name)
            return
        for pr in st.get("entry_prerequisites") or []:
            self.check(pr["p"], pr.get("args") or [], "%s.entry" % name)

    def find_transition(self, frm, to):
        for t in self.schema["transitions"]:
            if t.get("to") != to:
                continue
            if t.get("from") == frm:
                return t
            if t.get("from") == "ANY_PRE_LIVE" and frm in (t.get("expands_to") or []):
                return t
        return None

    def check_transition(self, to):
        frm = self.state.get("workflow", {}).get("state")
        if frm is None:
            self.fail("illegal_transition", "state file has no workflow.state")
            return
        if frm in ("ABANDONED",):
            self.fail("illegal_transition", "ABANDONED is terminal and has no outbound transitions",
                      "workflow.state", "<non-terminal>", frm)
            return
        t = self.find_transition(frm, to)
        if not t:
            if to == "ABANDONED" and frm in ("LIVE", "REVIEWED"):
                self.fail("abandon_after_live",
                          "ABANDONED is not reachable from %s" % frm, "workflow.state",
                          "pre-LIVE state", frm)
            else:
                self.fail("illegal_transition", "no transition %s -> %s" % (frm, to),
                          "workflow.state", "a declared edge", "%s -> %s" % (frm, to))
            return
        ttype = t.get("transition_type")
        if t.get("owner_decision"):
            self.p_owner_decision_recorded([t["owner_decision"]], "%s->%s" % (frm, to))
        if ttype == "reopen":
            self.check_reopen(t, frm, to)
        self.check_state_prereqs(to)
        if to == "ABANDONED":
            self.check_abandonment()

    def check_reopen(self, t, frm, to):
        ctx = "%s->%s(reopen)" % (frm, to)
        did = t.get("owner_decision")
        d = (self.state.get("owner_decisions") or {}).get(did) or {}
        for f in t.get("decision_value_required_fields") or []:
            if not (d.get("value") or {}).get(f):
                self.fail("reopen_without_decision",
                          "%s: decision %r missing value.%s" % (ctx, did, f),
                          "owner_decisions.%s.value.%s" % (did, f), "<non-empty>", MISSING)
        if not d.get("value", {}).get("reason") and "reason" not in (t.get("decision_value_required_fields") or []):
            if not d.get("note"):
                self.fail("reopen_without_decision",
                          "%s: a reopen must record a reason" % ctx,
                          "owner_decisions.%s" % did, "value.reason or note", MISSING)
        arts = self.state.get("artifacts") or {}
        for key in t.get("supersedes_artifacts") or []:
            rec = arts.get(key)
            if rec and rec.get("status", "current") == "current":
                self.fail("reopen_without_decision",
                          "%s: artifact %r must be marked superseded before reopening" % (ctx, key),
                          "artifacts.%s.status" % key, "superseded", rec.get("status", "current"))
            if rec and rec.get("status") == "superseded" and not rec.get("supersession_reason"):
                self.fail("reopen_without_decision",
                          "%s: artifact %r superseded without a reason" % (ctx, key),
                          "artifacts.%s.supersession_reason" % key, "<non-empty>", MISSING)
        inval = self.state.get("invalidated") or []
        for target in t.get("invalidates") or []:
            if target not in inval:
                self.fail("reopen_without_decision",
                          "%s: dependent approval %r must be invalidated" % (ctx, target),
                          "invalidated", "includes %r" % target, inval)

    def check_abandonment(self):
        ab = self.state.get("abandonment") or {}
        ident = (self.state.get("identity") or {}).get("campaign_id") or {}
        if ab.get("run_id_status") != "retained":
            self.fail("run_id_reused", "abandonment.run_id_status must be 'retained'",
                      "abandonment.run_id_status", "retained", ab.get("run_id_status", MISSING))
        if not ident.get("value"):
            want = "never_minted"
        elif ident.get("externally_referenced") is True:
            want = "retired"
        else:
            want = "released"
        if ab.get("campaign_id_status") != want:
            self.fail("prerequisites_unmet",
                      "abandonment.campaign_id_status must be %r for this id state" % want,
                      "abandonment.campaign_id_status", want, ab.get("campaign_id_status", MISSING))


def main():
    ap = argparse.ArgumentParser(description="Validate a campaign run's workflow state.")
    ap.add_argument("--state", required=True)
    ap.add_argument("--to", help="target state for a transition check")
    ap.add_argument("--schema", default=DEF_SCHEMA)
    ap.add_argument("--charter", default=DEF_CHARTER)
    ap.add_argument("--runs-dir", default=DEF_RUNS)
    ap.add_argument("--run-dir", help="logical run directory, when --state is a proposal held "
                                      "elsewhere. Defaults to the state file's directory.")
    ap.add_argument("--phase", default="all", choices=["all", "state", "artifacts", "transition"],
                    help="validation phase. Content QUALITY is never validated here.")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    v = Validator(a.state, a.schema, a.charter, a.runs_dir, a.run_dir)
    cur = v.state.get("workflow", {}).get("state")
    if a.phase in ("all", "state"):
        v.invariants()
    if a.phase in ("all", "artifacts"):
        v.check_artifacts()
    if a.phase in ("all", "transition"):
        if a.to:
            v.check_transition(a.to)
        elif a.phase == "transition":
            sys.exit("FATAL: --phase transition requires --to")
        else:
            v.check_state_prereqs(cur)

    ok = not v.failures
    if a.json:
        print(json.dumps({"ok": ok, "current_state": cur, "target_state": a.to,
                          "spec_version": v.schema["schema"]["version"],
                          "charter_version": (v.charter.get("charter") or {}).get("version"),
                          "failures": [f.as_dict() for f in v.failures],
                          "warnings": v.warnings}, indent=2))
        sys.exit(0 if ok else 1)

    head = "%s%s" % (cur, " -> %s" % a.to if a.to else " (current-state check)")
    print("=== validate_state %s ===" % head)
    print("    schema  %s   charter %s (%s)" % (
        v.schema["schema"]["version"],
        (v.charter.get("charter") or {}).get("version"),
        (v.charter.get("charter") or {}).get("status")))
    for w in v.warnings:
        print("  " + w)
    if ok:
        print("\nPASS — every prerequisite satisfied.")
        sys.exit(0)
    print("\nREFUSED — %d failure(s):\n" % len(v.failures))
    for f in v.failures:
        print(f.render(v.refusals))
        print()
    sys.exit(1)


if __name__ == "__main__":
    main()
