import os, sys, re
from pathlib import Path
from collections import defaultdict

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]

def collapse_names(names):
    # Разделяет имя на: Префикс (без цифр на конце) + Цифры + Окончание/Расширение
    pat = re.compile(r"^(.*?)(\d+)(.*)$")
    groups = defaultdict(list)
    others = []

    for name in names:
        m = pat.match(name)
        if m:
            pfx, num_str, rest = m.groups()
            groups[(pfx, rest)].append((int(num_str), len(num_str), name))
        else:
            others.append(name)

    collapsed = []
    for (pfx, rest), items in groups.items():
        if len(items) >= 3:  # Схлопывать от 3 файлов и больше
            items.sort(key=lambda x: x[0])
            s_num, pad, _ = items[0]
            e_num, _, _ = items[-1]
            collapsed.append(f"{pfx}{str(s_num).zfill(pad)}..{str(e_num).zfill(pad)}{rest} ({len(items)} files)")
        else:
            collapsed.extend([name for _, _, name in items])

    return sorted(others + collapsed, key=natural_sort_key)

def print_tree(dir_path, prefix=""):
    try:
        entries = sorted(list(dir_path.iterdir()), key=lambda e: (not e.is_dir(), natural_sort_key(e.name)))
    except PermissionError:
        return

    dirs = [e for e in entries if e.is_dir()]
    files = [e.name for e in entries if not e.is_dir()]

    collapsed_files = collapse_names(files)
    items_to_show = [(d, True) for d in dirs] + [(f, False) for f in collapsed_files]
    total = len(items_to_show)

    for i, (item, is_dir) in enumerate(items_to_show):
        is_last = (i == total - 1)
        branch = "└── " if is_last else "├── "
        next_prefix = prefix + ("    " if is_last else "│   ")

        if is_dir:
            print(f"{prefix}{branch}{item.name}/")
            print_tree(item, next_prefix)
        else:
            print(f"{prefix}{branch}{item}")

target = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
print(f"{target}/")
print_tree(target)