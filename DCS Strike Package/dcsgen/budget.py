"""Unit budget: keep the total unit count under a limit to protect performance.

The flights themselves are never trimmed. Groups are trimmed least-important
first (highest priority number), largest first, shrinking each group down to its
floor and then dropping it entirely if it is optional.
"""


def _next_victim(groups):
    candidates = [g for g in groups if g.count > g.floor or g.optional]
    if not candidates:
        return None
    return max(candidates, key=lambda g: (g.priority, g.count))


def apply_budget(plan, max_units):
    fixed = sum(f.size for f in plan.flights) + (1 if plan.carrier else 0)
    if fixed > max_units:
        raise ValueError(
            f"The flights alone need {fixed} units, more than the limit of {max_units}. "
            "Raise --max-units or use fewer flights or smaller flights.")

    plan.units_before_budget = plan.total_units
    dropped = []
    while plan.total_units > max_units:
        victim = _next_victim(plan.groups)
        if victim is None:
            raise ValueError(
                f"Cannot fit the mission into {max_units} units; the minimum is {plan.total_units}.")
        if victim.count > victim.floor:
            core = max(victim.units, key=lambda u: u[1])
            core[1] -= 1
        else:
            plan.groups.remove(victim)
            dropped.append(victim.name)

    removed = plan.units_before_budget - plan.total_units
    if removed:
        msg = f"Unit budget: trimmed {removed} units ({plan.units_before_budget} -> {plan.total_units})."
        if dropped:
            msg += f" Dropped groups: {', '.join(dropped)}."
        plan.notes.append(msg)
