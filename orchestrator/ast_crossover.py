"""AST-guided crossover utilities for combining parent candidates."""
from __future__ import annotations

import ast
import copy
import difflib
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .models import BehaviorFeatures, ProgramCandidate

EVOLVE_PATTERN = re.compile(
    r"(# EVOLVE-BLOCK-START.*?\n)(.*?)(\n# EVOLVE-BLOCK-END)",
    flags=re.DOTALL,
)


@dataclass
class CrossoverPlan:
    """Metadata describing how crossover combined parent fragments."""

    parents: Tuple[str, str]
    strategy: str
    description: str
    fragments: int


@dataclass
class CrossoverResult:
    """Result of applying crossover, including source and metadata."""

    merged_source: str
    merged_block: str
    plan: CrossoverPlan
    behavior: Optional[BehaviorFeatures]
    patch_payload: Dict[str, object]


def _extract_block(source_text: str) -> str:
    match = EVOLVE_PATTERN.search(source_text)
    if not match:
        raise ValueError("Expected EVOLVE-BLOCK markers in parent source")
    return match.group(2)


def _apply_block(base_source: str, new_block: str) -> str:
    match = EVOLVE_PATTERN.search(base_source)
    if not match:
        raise ValueError("Base source missing EVOLVE-BLOCK markers")
    prefix, _, suffix = match.groups()
    start = base_source[: match.start()]
    end = base_source[match.end() :]
    block = textwrap.dedent(new_block).strip()
    return f"{start}{prefix}{block}\n{suffix}{end}"


def _merge_functions(functions_a: Dict[str, ast.FunctionDef], functions_b: Dict[str, ast.FunctionDef]) -> Tuple[List[ast.stmt], List[str]]:
    merged: List[ast.stmt] = []
    notes: List[str] = []
    for name in sorted(set(functions_a) | set(functions_b)):
        func_a = functions_a.get(name)
        func_b = functions_b.get(name)
        if func_a and func_b:
            merged_func, note = _blend_function(func_a, func_b)
            merged.append(merged_func)
            notes.append(note)
        elif func_a:
            merged.append(copy.deepcopy(func_a))
            notes.append(f"Inherited {name} from parent A")
        elif func_b:
            merged.append(copy.deepcopy(func_b))
            notes.append(f"Inherited {name} from parent B")
    return merged, notes


def _blend_function(func_a: ast.FunctionDef, func_b: ast.FunctionDef) -> Tuple[ast.FunctionDef, str]:
    body_a = copy.deepcopy(func_a.body)
    body_b = copy.deepcopy(func_b.body)
    pivot_a = max(1, len(body_a)) // 2
    pivot_b = max(1, len(body_b)) // 2
    blended_body = body_a[:pivot_a] + body_b[pivot_b:]
    if not blended_body:
        blended_body = [ast.Pass()]
    decorator_list = copy.deepcopy(
        func_a.decorator_list or func_b.decorator_list or []
    )
    blended = ast.FunctionDef(
        name=func_a.name,
        args=copy.deepcopy(func_a.args),
        body=blended_body,
        decorator_list=decorator_list,
        returns=func_a.returns or func_b.returns,
        type_comment=func_a.type_comment or func_b.type_comment,
        type_params=[],
    )
    ast.copy_location(blended, func_a)
    ast.fix_missing_locations(blended)
    note = (
        f"Merged {func_a.name} using {pivot_a} statements from parent A and "
        f"{len(body_b) - pivot_b} from parent B"
    )
    return blended, note


def _parse_block(block: str) -> Dict[str, ast.FunctionDef]:
    module = ast.parse(textwrap.dedent(block))
    return {
        node.name: node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
    }


def perform_ast_crossover(
    parent_a: ProgramCandidate,
    parent_b: ProgramCandidate,
    *,
    base_source: Optional[str] = None,
) -> CrossoverResult:
    """Produces a child program by combining the EVOLVE blocks of two parents."""

    source_a = Path(parent_a.source_path).read_text(encoding="utf-8")
    source_b = Path(parent_b.source_path).read_text(encoding="utf-8")
    block_a = _extract_block(source_a)
    block_b = _extract_block(source_b)
    functions_a = _parse_block(block_a)
    functions_b = _parse_block(block_b)
    merged_functions, notes = _merge_functions(functions_a, functions_b)
    module = ast.Module(body=merged_functions, type_ignores=[])
    ast.fix_missing_locations(module)
    merged_block = textwrap.dedent(ast.unparse(module)).strip()

    base = base_source or source_a
    merged_source = _apply_block(base, merged_block)

    diff = "".join(
        difflib.unified_diff(
            source_a.splitlines(keepends=True),
            merged_source.splitlines(keepends=True),
            fromfile=f"{parent_a.id}.py",
            tofile="crossover.py",
            n=3,
        )
    )
    patch_payload: Dict[str, object]
    if diff.strip():
        patch_payload = {"diff_type": "unified", "payload": diff}
    else:
        patch_payload = {"diff_type": "sr", "payload": merged_block}
    patch_payload["metadata"] = {
        "strategy": "ast_mix",
        "notes": notes,
    }

    behavior = BehaviorFeatures(
        coverage_bits=(len(merged_block.splitlines()),),
        hotspots={"blend_ratio": len(notes)},
        output_signature=f"{parent_a.id[:6]}|{parent_b.id[:6]}",
    )

    plan = CrossoverPlan(
        parents=(parent_a.id, parent_b.id),
        strategy="ast_mix",
        description="; ".join(notes) if notes else "Inherited blocks",
        fragments=len(merged_functions),
    )

    return CrossoverResult(
        merged_source=merged_source,
        merged_block=merged_block,
        plan=plan,
        behavior=behavior,
        patch_payload=patch_payload,
    )

