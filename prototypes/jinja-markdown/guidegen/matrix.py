"""Dimension matrix: ordered dimensions + rules -> the enumerated supported
set, plus the ci: job list. This model is the irreducibly custom part of
the problem in ANY host syntax."""

import itertools


def short(cell):
    return " ".join(f"{k}={v}" for k, v in cell.items())


def variant_slug(cell, order):
    return "-".join(cell[d].replace("/", "").replace(".", "") for d in order)


class Matrix:
    def __init__(self, meta, errors):
        self.dims = meta.get("dimensions") or {}
        self.order = list(self.dims)
        self.values = {d: [str(v) for v in (s.get("values") or [])]
                       for d, s in self.dims.items()}
        self.defaults = {}
        for d, s in self.dims.items():
            if not self.values[d]:
                errors.append(f"dimension {d}: needs a non-empty values list")
                continue
            default = str(s.get("default", self.values[d][0]))
            if default not in self.values[d]:
                errors.append(f"dimension {d}: default {default!r} not in values")
            self.defaults[d] = default

        def aslist(v):
            return [str(x) for x in v] if isinstance(v, list) else [str(v)]

        self.rules = [{"when": {k: aslist(v) for k, v in (r.get("when") or {}).items()},
                       "allow": {k: aslist(v) for k, v in (r.get("allow") or {}).items()}}
                      for r in meta.get("rules") or []]
        idx = {d: i for i, d in enumerate(self.order)}
        for n, rule in enumerate(self.rules, 1):
            for part, name in ((rule["when"], "when"), (rule["allow"], "allow")):
                for k, vals in part.items():
                    if k not in self.dims:
                        errors.append(f"rule {n}: {name} references unknown dimension {k!r}")
                    elif not set(vals) <= set(self.values[k]):
                        errors.append(f"rule {n}: {name} {k} has undeclared values")
            if rule["when"] and rule["allow"]:
                if max(idx.get(k, 0) for k in rule["when"]) >= \
                   min(idx.get(k, 0) for k in rule["allow"]):
                    errors.append(f"rule {n}: `when` dimensions must all come before "
                                  "`allow` dimensions in declaration order")

        self.supported = self._enumerate() if not errors else []
        for d in self.order:
            used = {c[d] for c in self.supported}
            for v in self.values.get(d, []):
                if self.supported and v not in used:
                    errors.append(f"dimension {d}: value {v!r} is not reachable "
                                  "under the rules (dead value)")

        self.ci = []
        for n, row in enumerate(meta.get("ci") or [], 1):
            cell = {k: str(v) for k, v in (row or {}).items()}
            if set(cell) != set(self.dims):
                missing = set(self.dims) - set(cell)
                extra = set(cell) - set(self.dims)
                errors.append(f"ci[{n}]: each row must be a complete flattened "
                              f"assignment of ALL dimensions"
                              + (f" — missing {sorted(missing)}" if missing else "")
                              + (f" — unknown {sorted(extra)}" if extra else ""))
            elif cell not in self.supported:
                errors.append(f"ci[{n}]: {cell} is not a supported combination")
            else:
                self.ci.append(cell)

    def _enumerate(self):
        out = []
        for combo in itertools.product(*(self.values[d] for d in self.order)):
            cell = dict(zip(self.order, combo))
            ok = True
            for rule in self.rules:
                if all(cell[k] in v for k, v in rule["when"].items()):
                    if not all(cell[k] in v for k, v in rule["allow"].items()):
                        ok = False
                        break
            if ok:
                out.append(cell)
        return out

    def default_cell(self):
        if dict(self.defaults) in self.supported:
            return dict(self.defaults)
        return dict(self.supported[0]) if self.supported else dict(self.defaults)
