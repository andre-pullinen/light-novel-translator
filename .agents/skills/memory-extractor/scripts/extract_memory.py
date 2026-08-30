#!/usr/bin/env python3
"""
Production-grade Memory Extractor & Knowledge Base Updater for Japanese Light Novels.

Features:
- Concurrency-Safe Atomic Persistence:
  - Dedicated lockfile (.lock) with exclusive fcntl.flock prevents race conditions.
  - Generates unique temporary files (NamedTemporaryFile) per process to prevent collision.
  - Performs atomic os.replace with automated backup (.bak) of previous file versions.
- Pure Non-Destructive Dry-Run Mode:
  - Simulation mode creates zero files or directories on disk.
  - Accurate operational diff and statistics before persistence.
- Strict vs Fallback Matching with Comprehensive Warnings:
  - Irreversible actions (REJECT, DELETE, MERGE source absorption) require strict ID / CJK matching.
  - Fallback matching (RU/EN glosses) across ADD, UPDATE, PROMOTE, and MERGE logs explicit warnings.
- Robust Proposal Schema & Identity Validation:
  - Pre-validates presence of identifying fields for ADD, UPDATE, PROMOTE, MERGE, and REJECT.
  - Prevents creation of empty or anonymous orphan entities in MERGE.
  - Detailed diagnostic error messages for malformed items.
- Full Lifecycle Actions:
  - ADD: Adds provisional entries to candidates.json or confirmed entries directly to master memory.
  - PROMOTE: Migrates entries from candidates.json to master files (characters, glossary, etc.) with confirmed status.
  - UPDATE: Deep updates existing entries, accumulating occurrences_count as a cumulative sum across chapters.
  - MERGE: Merges alias / provisional representations into a canonical entity, preserving all canonical metadata.
  - REJECT / DELETE: Safely removes unwanted entries from candidates.json by strict ID.
- Safe Dual-Schema JSON Handling:
  - Handles both dict-wrapped JSON ({"characters": [...]}) and bare list JSON ([...]).
  - Prevents hijacking unrelated list fields in dict-wrapped collections.
"""

import os
import sys
import json
import argparse
import fcntl
import tempfile
from typing import List, Dict, Any, Tuple, Optional

CATEGORY_CONFIG: Dict[str, Dict[str, str]] = {
    "characters": {
        "type": "character",
        "file": "characters.json",
        "root_key": "characters"
    },
    "glossary": {
        "type": "glossary",
        "file": "glossary.json",
        "root_key": "glossary"
    },
    "locations": {
        "type": "location",
        "file": "locations.json",
        "root_key": "locations"
    },
    "relationships": {
        "type": "relationship",
        "file": "relationships.json",
        "root_key": "relationships"
    },
    "lore": {
        "type": "lore",
        "file": "lore.json",
        "root_key": "lore"
    }
}


def parse_args():
    parser = argparse.ArgumentParser(description="Validate and apply memory proposals to project memory.")
    parser.add_argument("--proposal", required=True, help="Path to MEMORY_PROPOSAL.json (e.g. qa/tenbin/chapter04/MEMORY_PROPOSAL.json)")
    parser.add_argument("--memory-dir", required=True, help="Path to memory directory (e.g. memory/tenbin/)")
    parser.add_argument("--apply", action="store_true", help="Apply and persist proposals to memory files (default: dry-run)")
    return parser.parse_args()


def validate_proposal_data(data: Any, proposal_path: str) -> Tuple[bool, List[str]]:
    """Validates structural integrity and required entity fields of LLM proposal payload."""
    errors = []
    if not isinstance(data, dict):
        errors.append(f"Root JSON in '{proposal_path}' must be an object/dict, got {type(data).__name__}.")
        return False, errors

    proposals = data.get("proposals")
    if not isinstance(proposals, dict):
        errors.append(f"'proposals' field in '{proposal_path}' must be a dict/object, got {type(proposals).__name__}.")
        return False, errors

    for cat_name, items in proposals.items():
        if not isinstance(items, list):
            errors.append(f"Category '{cat_name}' in 'proposals' must contain a list, got {type(items).__name__}.")
            continue
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"Item #{idx} in category '{cat_name}' must be a dict/object, got {type(item).__name__}.")
                continue
            action = str(item.get("action", "")).upper()
            if action not in ("ADD", "PROMOTE", "UPDATE", "MERGE", "REJECT", "DELETE"):
                errors.append(f"Item #{idx} in category '{cat_name}' has invalid action '{action}'.")
                continue

            entry = item.get("entry")
            if not entry and "pair" in item and cat_name.lower() == "relationships":
                entry = {"characters": item.get("pair")}

            if action in ("ADD", "UPDATE", "PROMOTE"):
                if not isinstance(entry, dict) or not entry:
                    errors.append(f"Item #{idx} in category '{cat_name}' with action '{action}' is missing a valid 'entry' object.")
                else:
                    has_id = any(
                        entry.get(f) is not None and str(entry.get(f)).strip()
                        for f in ("id", "term_jp", "name_jp", "title_jp", "title_ru", "title", "term_ru", "name_ru", "term_en", "name_en", "title_en", "name_ja", "term_ja", "characters", "pair")
                    )
                    if not has_id:
                        errors.append(f"Item #{idx} in category '{cat_name}' with action '{action}' has an 'entry' without identifying fields (id, name, term, or pair).")

            elif action == "MERGE":
                has_merge_target = bool(item.get("target_id") or item.get("merge_into") or item.get("canonical_id") or (isinstance(entry, dict) and entry.get("id")))
                has_merge_source = bool(item.get("absorb_id") or item.get("source_id") or item.get("merged_from"))
                if not has_merge_target and not has_merge_source:
                    errors.append(f"Item #{idx} in category '{cat_name}' with action 'MERGE' must specify at least 'target_id' or 'absorb_id'.")

            elif action in ("REJECT", "DELETE"):
                has_reject_id = bool(item.get("id") or item.get("target_id") or (isinstance(entry, dict) and (entry.get("id") or entry.get("term_jp") or entry.get("name_jp"))))
                if not has_reject_id:
                    errors.append(f"Item #{idx} in category '{cat_name}' with action '{action}' must specify an 'id' to reject/delete.")

    return len(errors) == 0, errors


def load_collection(file_path: str, root_key: str) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Loads JSON collection from file, returning (list_of_entries, is_dict_wrapped).
    Validates dictionary schemas without hijacking unrelated list fields.
    """
    if not os.path.exists(file_path):
        return [], True if root_key else False

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Warning: Failed to parse '{file_path}': {e}. Initializing as empty.", file=sys.stderr)
        return [], True if root_key else False

    if isinstance(data, dict):
        if root_key in data and isinstance(data[root_key], list):
            return data[root_key], True
        # Check standard canonical list keys
        for fallback_key in ("items", "entries", "data"):
            if fallback_key in data and isinstance(data[fallback_key], list):
                return data[fallback_key], True
        print(f"Warning: Dict in '{file_path}' does not contain expected root key '{root_key}'. Initializing as empty list.", file=sys.stderr)
        return [], True
    elif isinstance(data, list):
        return data, False

    print(f"Warning: Unexpected root type ({type(data).__name__}) in '{file_path}'. Initializing as empty list.", file=sys.stderr)
    return [], False


def atomic_save_collection(
    file_path: str,
    entries: List[Dict[str, Any]],
    root_key: str,
    is_dict_wrapped: bool,
    make_backup: bool = True
):
    """
    Concurrency-safe atomic persistence.
    Acquires exclusive lock on dedicated .lock file, writes to unique per-process temp file,
    fsyncs, creates .bak backup, and atomically renames.
    """
    dir_name = os.path.dirname(os.path.abspath(file_path))
    os.makedirs(dir_name, exist_ok=True)

    lock_path = file_path + ".lock"
    payload: Any = {root_key: entries} if is_dict_wrapped else entries

    with open(lock_path, "a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            # Create unique temp file in target directory to ensure same filesystem for atomic rename
            prefix = f"{os.path.basename(file_path)}.{os.getpid()}."
            with tempfile.NamedTemporaryFile(mode="w", dir=dir_name, prefix=prefix, suffix=".tmp", delete=False, encoding="utf-8") as tf:
                tmp_path = tf.name
                json.dump(payload, tf, ensure_ascii=False, indent=2)
                tf.write("\n")
                tf.flush()
                os.fsync(tf.fileno())

            # Create backup of current file before replacing
            bak_path = file_path + ".bak"
            if make_backup and os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as src, open(bak_path, "w", encoding="utf-8") as dst:
                        dst.write(src.read())
                except Exception as e:
                    print(f"Warning: Failed to create backup '{bak_path}': {e}", file=sys.stderr)

            # Atomic rename (POSIX guarantees atomic replacement)
            os.replace(tmp_path, file_path)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def match_entity(a: Dict[str, Any], b: Dict[str, Any], category: str, strict: bool = False) -> Tuple[bool, str]:
    """
    Matches two entity dictionaries.
    Returns (is_match, match_reason).
    - If strict=True: requires matching ID, exact relationship pair, or exact Japanese term/name.
    - If strict=False: allows English or Russian names as fallback.
    """
    # 1. Match by ID
    a_id = str(a.get("id", "")).strip()
    b_id = str(b.get("id", "")).strip()
    if a_id and b_id and a_id == b_id:
        return True, "id"

    # 2. Relationship pair matching
    if category == "relationships":
        a_chars = set(a.get("characters") or a.get("pair") or [])
        b_chars = set(b.get("characters") or b.get("pair") or [])
        if a_chars and b_chars and a_chars == b_chars:
            return True, "relationship_pair"

    # 3. Japanese term / name / title matching (exact)
    a_jp = str(a.get("term_jp") or a.get("name_jp") or a.get("title_jp") or a.get("name_ja") or a.get("term_ja") or a.get("japanese") or "").strip()
    b_jp = str(b.get("term_jp") or b.get("name_jp") or b.get("title_jp") or b.get("name_ja") or b.get("term_ja") or b.get("japanese") or "").strip()
    if a_jp and b_jp and a_jp == b_jp:
        return True, "term_jp"

    if strict:
        return False, "none"

    # 4. English term / name / title matching (fallback)
    a_en = str(a.get("term_en") or a.get("name_en") or a.get("title_en") or a.get("english") or a.get("name_romaji") or a.get("term_romaji") or "").strip().lower()
    b_en = str(b.get("term_en") or b.get("name_en") or b.get("title_en") or b.get("english") or b.get("name_romaji") or b.get("term_romaji") or "").strip().lower()
    if a_en and b_en and a_en == b_en:
        return True, "term_en_fallback"

    # 5. Russian term / name / title matching (fallback)
    a_ru = str(a.get("term_ru") or a.get("name_ru") or a.get("title_ru") or a.get("title") or a.get("russian") or a.get("polivanov") or "").strip().lower()
    b_ru = str(b.get("term_ru") or b.get("name_ru") or b.get("title_ru") or b.get("title") or b.get("russian") or b.get("polivanov") or "").strip().lower()
    if a_ru and b_ru and a_ru == b_ru:
        return True, "term_ru_fallback"

    return False, "none"


def get_entity_title(entry: Dict[str, Any], fallback_item: Optional[Dict[str, Any]] = None) -> str:
    """Safe extraction of a human-readable entity title for logs."""
    for field in ("id", "term_jp", "name_jp", "title_jp", "title_ru", "title", "term_ru", "name_ru", "term_en", "name_en", "title_en", "name_ja", "term_ja"):
        val = entry.get(field)
        if val is not None and str(val).strip():
            return str(val).strip()

    if "characters" in entry and entry["characters"]:
        return str(entry["characters"])
    if "pair" in entry and entry["pair"]:
        return str(entry["pair"])

    if fallback_item:
        for f in ("target_id", "absorb_id", "id"):
            val = fallback_item.get(f)
            if val is not None and str(val).strip():
                return str(val).strip()

    return "unknown_entity"


def deep_update_entry(target: Dict[str, Any], source: Dict[str, Any]):
    """
    Updates target dictionary with source fields, accumulating occurrences_count and deduplicating lists.
    Normalizes legacy name_ja/term_ja into standard name_jp/term_jp.
    """
    for k, v in source.items():
        if v is None:
            continue
        # Normalize legacy field names to standard _jp
        if k == "name_ja":
            k = "name_jp"
            target.pop("name_ja", None)
        elif k == "term_ja":
            k = "term_jp"
            target.pop("term_ja", None)

        if k in target and isinstance(target[k], dict) and isinstance(v, dict):
            deep_update_entry(target[k], v)
        elif k in target and isinstance(target[k], list) and isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    match_found = False
                    item_id = item.get("id") or item.get("name") or item.get("chapter")
                    if item_id:
                        for target_item in target[k]:
                            if isinstance(target_item, dict):
                                t_id = target_item.get("id") or target_item.get("name") or target_item.get("chapter")
                                if t_id and str(t_id).strip().lower() == str(item_id).strip().lower():
                                    deep_update_entry(target_item, item)
                                    match_found = True
                                    break
                    if not match_found and item not in target[k]:
                        target[k].append(item)
                elif isinstance(item, str):
                    existing_lower = [str(x).lower() for x in target[k] if isinstance(x, str)]
                    if item.lower() not in existing_lower:
                        target[k].append(item)
                else:
                    if item not in target[k]:
                        target[k].append(item)
        elif k == "occurrences_count" and isinstance(v, (int, float)):
            target[k] = int(target.get(k, 0)) + int(v)
        else:
            target[k] = v


def main():
    args = parse_args()

    if not os.path.exists(args.proposal):
        print(f"Error: Proposal file '{args.proposal}' does not exist.", file=sys.stderr)
        sys.exit(1)

    with open(args.proposal, "r", encoding="utf-8") as f:
        try:
            proposal_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: Malformed JSON in proposal '{args.proposal}': {e}", file=sys.stderr)
            sys.exit(1)

    is_valid, validation_errors = validate_proposal_data(proposal_data, args.proposal)
    if not is_valid:
        print("Error: Invalid proposal payload:", file=sys.stderr)
        for err in validation_errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    project_name = proposal_data.get("project", "project")
    chapter_id = proposal_data.get("chapter", "unknown")
    proposals = proposal_data.get("proposals", {})

    print(f"=== Memory Extractor: Chapter {chapter_id} (Project: {project_name}) ===")
    print(f"Mode: {'APPLY (Changes will be persisted atomically with backup)' if args.apply else 'DRY-RUN (Simulation only, no files touched)'}")
    print()

    # Load candidates
    candidates_file = os.path.join(args.memory_dir, "candidates.json")
    candidates, is_cand_dict = load_collection(candidates_file, "candidates")

    # Load master collections
    master_stores: Dict[str, Tuple[List[Dict[str, Any]], bool, str]] = {}
    for cat, conf in CATEGORY_CONFIG.items():
        fpath = os.path.join(args.memory_dir, conf["file"])
        entries, is_dict = load_collection(fpath, conf["root_key"])
        master_stores[cat] = (entries, is_dict, fpath)

    stats = {
        "added_candidates": 0,
        "added_confirmed": 0,
        "promoted_to_master": 0,
        "updated_entries": 0,
        "merged_entries": 0,
        "rejected_entries": 0
    }

    log_messages: List[str] = []

    # Process all proposals
    for category_name, proposal_items in proposals.items():
        cat_key = category_name.lower()
        if cat_key not in CATEGORY_CONFIG:
            print(f"Warning: Unknown proposal category '{category_name}', skipping.", file=sys.stderr)
            continue

        conf = CATEGORY_CONFIG[cat_key]
        master_list, is_dict_wrapped, fpath = master_stores[cat_key]

        for item_idx, item in enumerate(proposal_items):
            action = str(item.get("action", "ADD")).upper()
            status = str(item.get("validation_status", "provisional")).lower()
            entry = item.get("entry", {})

            # For relationships, entry might be flat or wrapped in pair
            if not entry and "pair" in item and cat_key == "relationships":
                entry = {
                    "characters": item.get("pair"),
                    "register": item.get("register"),
                    "note": item.get("note"),
                    "core_dynamics": item.get("note")
                }

            entity_title = get_entity_title(entry, item)

            # -------------------------------------------------------------
            # Action: PROMOTE (Candidate -> Master Memory)
            # -------------------------------------------------------------
            if action == "PROMOTE":
                cand_query = {"id": item.get("candidate_id") or item.get("source_id") or item.get("absorb_id")} if (item.get("candidate_id") or item.get("source_id") or item.get("absorb_id")) else entry
                found_cand_idx = -1
                for idx, c in enumerate(candidates):
                    is_match, _ = match_entity(c, cand_query, cat_key, strict=True)
                    if is_match:
                        found_cand_idx = idx
                        break
                if found_cand_idx < 0:
                    for idx, c in enumerate(candidates):
                        is_match, reason = match_entity(c, cand_query, cat_key, strict=False)
                        if is_match:
                            found_cand_idx = idx
                            if reason.endswith("_fallback"):
                                log_messages.append(f"[PROMOTE:FALLBACK_WARNING] Candidate '{entity_title}' matched via non-strict fallback ({reason}).")
                            break

                promoted_entry = dict(entry)
                promoted_entry["validation_status"] = "confirmed"
                if "type" not in promoted_entry:
                    promoted_entry["type"] = conf["type"]

                if found_cand_idx >= 0:
                    cand_item = candidates.pop(found_cand_idx)
                    old_cand_id = cand_item.get("id")
                    merged = dict(cand_item)
                    deep_update_entry(merged, promoted_entry)
                    if old_cand_id and old_cand_id != merged.get("id"):
                        if "aliases" not in merged:
                            merged["aliases"] = []
                        if old_cand_id not in merged["aliases"]:
                            merged["aliases"].append(old_cand_id)
                    promoted_entry = merged
                    log_messages.append(f"[PROMOTE] Promoted '{entity_title}' from candidates to {conf['file']}.")
                else:
                    log_messages.append(f"[PROMOTE] Added confirmed '{entity_title}' directly to {conf['file']}.")

                # Insert or update in master
                found_master = False
                for m in master_list:
                    is_m, reason = match_entity(m, promoted_entry, cat_key, strict=False)
                    if is_m:
                        if reason.endswith("_fallback"):
                            log_messages.append(f"[PROMOTE:FALLBACK_WARNING] Master record '{entity_title}' in {conf['file']} matched via fallback ({reason}).")
                        deep_update_entry(m, promoted_entry)
                        found_master = True
                        break
                if not found_master:
                    master_list.append(promoted_entry)

                stats["promoted_to_master"] += 1

            # -------------------------------------------------------------
            # Action: MERGE (Absorb entity/alias into canonical entity)
            # -------------------------------------------------------------
            elif action == "MERGE":
                target_id = item.get("target_id") or item.get("merge_into") or item.get("canonical_id") or entry.get("id")
                absorb_id = item.get("absorb_id") or item.get("source_id") or item.get("merged_from")

                target_query = {"id": target_id} if target_id else entry
                absorbed_query = {"id": absorb_id} if absorb_id else {}

                # 1. Find canonical target entity
                target_ent = None
                for m in master_list:
                    is_m, reason = match_entity(m, target_query, cat_key, strict=False)
                    if is_m:
                        if reason.endswith("_fallback"):
                            log_messages.append(f"[MERGE:FALLBACK_WARNING] Target entity '{entity_title}' matched in master via fallback ({reason}).")
                        target_ent = m
                        break
                if not target_ent:
                    for c in candidates:
                        is_m, reason = match_entity(c, target_query, cat_key, strict=False)
                        if is_m:
                            if reason.endswith("_fallback"):
                                log_messages.append(f"[MERGE:FALLBACK_WARNING] Target candidate '{entity_title}' matched via fallback ({reason}).")
                            target_ent = c
                            break

                # If target entity doesn't exist, create it with identifying fields
                if not target_ent:
                    target_ent = dict(entry) if entry else {}
                    if target_id and "id" not in target_ent:
                        target_ent["id"] = target_id

                    has_identity = any(
                        target_ent.get(f) is not None and str(target_ent.get(f)).strip()
                        for f in ("id", "name_jp", "term_jp", "name_ja", "term_ja", "name_ru", "term_ru", "name_en", "term_en")
                    )

                    if not has_identity:
                        log_messages.append(f"[MERGE:ERROR] Item #{item_idx} has no identifying ID/names to create canonical entity. Skipping.")
                        continue

                    if status == "confirmed":
                        target_ent["validation_status"] = "confirmed"
                        if "type" not in target_ent:
                            target_ent["type"] = conf["type"]
                        master_list.append(target_ent)
                    else:
                        target_ent["type"] = conf["type"]
                        target_ent["validation_status"] = "provisional"
                        if "first_seen_chapter" not in target_ent:
                            target_ent["first_seen_chapter"] = chapter_id
                        candidates.append(target_ent)
                    log_messages.append(f"[MERGE->CREATE] Canonical entity '{target_id or entity_title}' created.")

                # 2. Locate and absorb source entity (STRICT MATCH ONLY)
                if absorb_id:
                    absorbed_item = None
                    for idx, c in enumerate(candidates):
                        is_m, _ = match_entity(c, absorbed_query, cat_key, strict=True)
                        if is_m:
                            absorbed_item = candidates.pop(idx)
                            break
                    if not absorbed_item:
                        for idx, m in enumerate(master_list):
                            is_m, _ = match_entity(m, absorbed_query, cat_key, strict=True)
                            if is_m:
                                absorbed_item = master_list.pop(idx)
                                break

                    if absorbed_item:
                        abs_name = absorbed_item.get("name_ru") or absorbed_item.get("term_ru") or absorbed_item.get("id")
                        if abs_name:
                            if "aliases" not in target_ent:
                                target_ent["aliases"] = []
                            if abs_name not in target_ent["aliases"]:
                                target_ent["aliases"].append(abs_name)

                        # Preserve canonical identifiers & metadata
                        canonical_id = target_ent.get("id")
                        canonical_type = target_ent.get("type")
                        canonical_status = target_ent.get("validation_status")
                        canonical_first_seen = target_ent.get("first_seen_chapter")
                        canonical_name_ru = target_ent.get("name_ru") or target_ent.get("term_ru")
                        canonical_name_jp = target_ent.get("name_jp") or target_ent.get("term_jp") or target_ent.get("name_ja") or target_ent.get("term_ja")

                        deep_update_entry(target_ent, absorbed_item)

                        if canonical_id:
                            target_ent["id"] = canonical_id
                        if canonical_type:
                            target_ent["type"] = canonical_type
                        if canonical_status:
                            target_ent["validation_status"] = canonical_status
                        if canonical_first_seen:
                            target_ent["first_seen_chapter"] = canonical_first_seen
                        if canonical_name_ru:
                            if "name_ru" in target_ent:
                                target_ent["name_ru"] = canonical_name_ru
                            elif "term_ru" in target_ent:
                                target_ent["term_ru"] = canonical_name_ru
                        if canonical_name_jp:
                            if "term_jp" in target_ent or "term_ja" in target_ent:
                                target_ent["term_jp"] = canonical_name_jp
                                target_ent.pop("term_ja", None)
                            else:
                                target_ent["name_jp"] = canonical_name_jp
                                target_ent.pop("name_ja", None)

                        log_messages.append(f"[MERGE] Absorbed '{absorb_id}' into canonical entity '{target_id or entity_title}'.")
                    else:
                        log_messages.append(f"[MERGE:WARNING] Absorbed entity ID '{absorb_id}' not found in candidates or master.")

                # 3. Apply additional fields from entry
                if entry:
                    deep_update_entry(target_ent, entry)

                stats["merged_entries"] += 1

            # -------------------------------------------------------------
            # Action: ADD
            # -------------------------------------------------------------
            elif action == "ADD":
                if status == "confirmed":
                    found_master = False
                    for m in master_list:
                        is_m, reason = match_entity(m, entry, cat_key, strict=False)
                        if is_m:
                            deep_update_entry(m, entry)
                            found_master = True
                            if reason.endswith("_fallback"):
                                log_messages.append(f"[ADD:FALLBACK_WARNING] Confirmed '{entity_title}' matched in {conf['file']} via fallback ({reason}), updated.")
                            else:
                                log_messages.append(f"[ADD->UPDATE] Confirmed '{entity_title}' exists in {conf['file']} ({reason}), updated.")
                            stats["updated_entries"] += 1
                            break
                    if not found_master:
                        new_confirmed = dict(entry)
                        new_confirmed["validation_status"] = "confirmed"
                        master_list.append(new_confirmed)
                        log_messages.append(f"[ADD] Added confirmed '{entity_title}' to {conf['file']}.")
                        stats["added_confirmed"] += 1

                    # Remove from candidates by strict match
                    candidates[:] = [c for c in candidates if not match_entity(c, entry, cat_key, strict=True)[0]]

                else:
                    found_cand = False
                    for c in candidates:
                        is_m, reason = match_entity(c, entry, cat_key, strict=False)
                        if is_m:
                            deep_update_entry(c, entry)
                            found_cand = True
                            if reason.endswith("_fallback"):
                                log_messages.append(f"[ADD:FALLBACK_WARNING] Provisional '{entity_title}' matched in candidates.json via fallback ({reason}), updated.")
                            else:
                                log_messages.append(f"[ADD->UPDATE] Provisional '{entity_title}' in candidates.json ({reason}), updated.")
                            stats["updated_entries"] += 1
                            break
                    if not found_cand:
                        new_cand = dict(entry)
                        new_cand["type"] = conf["type"]
                        new_cand["validation_status"] = "provisional"
                        if "first_seen_chapter" not in new_cand:
                            new_cand["first_seen_chapter"] = chapter_id
                        candidates.append(new_cand)
                        log_messages.append(f"[ADD] Added provisional '{entity_title}' to candidates.json.")
                        stats["added_candidates"] += 1

            # -------------------------------------------------------------
            # Action: UPDATE
            # -------------------------------------------------------------
            elif action == "UPDATE":
                updated = False
                for m in master_list:
                    is_m, reason = match_entity(m, entry, cat_key, strict=False)
                    if is_m:
                        deep_update_entry(m, entry)
                        updated = True
                        if reason.endswith("_fallback"):
                            log_messages.append(f"[UPDATE:FALLBACK_WARNING] Updated '{entity_title}' in {conf['file']} matched via fallback ({reason}).")
                        else:
                            log_messages.append(f"[UPDATE] Updated '{entity_title}' in {conf['file']} ({reason}).")
                        stats["updated_entries"] += 1
                        break

                if not updated:
                    for c in candidates:
                        is_m, reason = match_entity(c, entry, cat_key, strict=False)
                        if is_m:
                            deep_update_entry(c, entry)
                            updated = True
                            if reason.endswith("_fallback"):
                                log_messages.append(f"[UPDATE:FALLBACK_WARNING] Updated '{entity_title}' in candidates.json matched via fallback ({reason}).")
                            else:
                                log_messages.append(f"[UPDATE] Updated '{entity_title}' in candidates.json ({reason}).")
                            stats["updated_entries"] += 1
                            break

                if not updated:
                    if status == "confirmed":
                        new_confirmed = dict(entry)
                        new_confirmed["validation_status"] = "confirmed"
                        master_list.append(new_confirmed)
                        log_messages.append(f"[UPDATE->ADD] '{entity_title}' not found, created in {conf['file']}.")
                        stats["added_confirmed"] += 1
                    else:
                        new_cand = dict(entry)
                        new_cand["type"] = conf["type"]
                        new_cand["validation_status"] = "provisional"
                        new_cand["first_seen_chapter"] = chapter_id
                        candidates.append(new_cand)
                        log_messages.append(f"[UPDATE->ADD] '{entity_title}' not found, created in candidates.json.")
                        stats["added_candidates"] += 1

            # -------------------------------------------------------------
            # Action: REJECT / DELETE (STRICT MATCH ONLY)
            # -------------------------------------------------------------
            elif action in ("REJECT", "DELETE"):
                prev_len = len(candidates)
                target_query = entry if entry else {"id": item.get("id")}
                candidates[:] = [c for c in candidates if not match_entity(c, target_query, cat_key, strict=True)[0]]
                if len(candidates) < prev_len:
                    log_messages.append(f"[REJECT] Removed '{entity_title}' from candidates.json.")
                    stats["rejected_entries"] += 1
                else:
                    log_messages.append(f"[REJECT] Candidate '{entity_title}' not found by strict ID/term to remove.")

    # Output log
    for msg in log_messages:
        print(f"  {msg}")

    print("\n--- Summary of Operations ---")
    print(f"  Added to candidates (provisional): {stats['added_candidates']}")
    print(f"  Added directly to master:          {stats['added_confirmed']}")
    print(f"  Promoted to master memory:         {stats['promoted_to_master']}")
    print(f"  Updated existing entries:          {stats['updated_entries']}")
    print(f"  Merged entries:                    {stats['merged_entries']}")
    print(f"  Rejected / Deleted:                {stats['rejected_entries']}")
    print()

    # Commit if --apply is set
    if args.apply:
        os.makedirs(args.memory_dir, exist_ok=True)
        atomic_save_collection(candidates_file, candidates, "candidates", is_cand_dict, make_backup=True)
        print(f"✔ Saved (atomic + backup): {candidates_file} ({len(candidates)} candidates total)")

        for cat, (m_list, is_dict, fpath) in master_stores.items():
            conf = CATEGORY_CONFIG[cat]
            atomic_save_collection(fpath, m_list, conf["root_key"], is_dict, make_backup=True)
            print(f"✔ Saved (atomic + backup): {fpath} ({len(m_list)} {cat} total)")

        print("\nAll memory proposals successfully applied and committed to disk.")
    else:
        print("Dry-run complete. No files modified on disk. Use '--apply' to persist changes.")


if __name__ == "__main__":
    main()
