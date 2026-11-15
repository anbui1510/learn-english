from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Default Nelson-oriented specialty tree (US-G2-060).
DEFAULT_TREE: list[dict[str, Any]] = [
    {
        "slug": "peds-foundations",
        "title": "Nhi đại cương",
        "parent_slug": None,
        "children": [
            {"slug": "peds-fever", "title": "Sốt", "parent_slug": "peds-foundations"},
            {
                "slug": "peds-diarrhea",
                "title": "Tiêu chảy",
                "parent_slug": "peds-foundations",
            },
            {
                "slug": "peds-respiratory",
                "title": "Hô hấp",
                "parent_slug": "peds-foundations",
            },
        ],
    },
    {
        "slug": "peds-cardiology",
        "title": "Tim mạch nhi",
        "parent_slug": "peds-foundations",
        "children": [],
    },
]


@dataclass(frozen=True)
class TreeNodeView:
    slug: str
    title: str
    parent_slug: str | None
    unlocked: bool
    completed: bool
    unlock_reason: str | None
    case_ids: list[int]
    children: list["TreeNodeView"]


def _flatten(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in nodes:
        out.append(node)
        kids = node.get("children") or []
        if kids:
            out.extend(_flatten(kids))
    return out


def module_complete(
    *,
    module_slug: str,
    cases_by_module: dict[str, list[int]],
    completed_case_ids: set[int],
    certified_modules: set[str],
) -> bool:
    if module_slug in certified_modules:
        return True
    case_ids = cases_by_module.get(module_slug) or []
    if not case_ids:
        # No published cases yet — treat incomplete (cannot auto-unlock children).
        return False
    return all(case_id in completed_case_ids for case_id in case_ids)


def build_skill_tree(
    *,
    cases_by_module: dict[str, list[int]],
    completed_case_ids: set[int],
    certified_modules: set[str],
    tree: list[dict[str, Any]] | None = None,
) -> list[TreeNodeView]:
    catalog = tree if tree is not None else DEFAULT_TREE
    flat = _flatten(catalog)
    parents = {n["slug"]: n.get("parent_slug") for n in flat}

    def node_unlocked(slug: str) -> tuple[bool, str | None]:
        parent = parents.get(slug)
        if not parent:
            return True, None
        if module_complete(
            module_slug=parent,
            cases_by_module=cases_by_module,
            completed_case_ids=completed_case_ids,
            certified_modules=certified_modules,
        ):
            return True, None
        return False, f"Complete module '{parent}' first"

    def render(node: dict[str, Any]) -> TreeNodeView:
        slug = str(node["slug"])
        unlocked, reason = node_unlocked(slug)
        completed = module_complete(
            module_slug=slug,
            cases_by_module=cases_by_module,
            completed_case_ids=completed_case_ids,
            certified_modules=certified_modules,
        )
        children = [render(child) for child in (node.get("children") or [])]
        return TreeNodeView(
            slug=slug,
            title=str(node["title"]),
            parent_slug=node.get("parent_slug"),
            unlocked=unlocked,
            completed=completed,
            unlock_reason=None if unlocked else reason,
            case_ids=list(cases_by_module.get(slug) or []),
            children=children,
        )

    return [render(node) for node in catalog]


def tree_to_dict(nodes: list[TreeNodeView]) -> list[dict[str, Any]]:
    def one(node: TreeNodeView) -> dict[str, Any]:
        return {
            "slug": node.slug,
            "title": node.title,
            "parent_slug": node.parent_slug,
            "unlocked": node.unlocked,
            "completed": node.completed,
            "unlock_reason": node.unlock_reason,
            "case_ids": node.case_ids,
            "children": [one(child) for child in node.children],
        }

    return [one(node) for node in nodes]
