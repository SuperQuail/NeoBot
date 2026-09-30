import pathlib, re, json
root = pathlib.Path('.').resolve()
anchor = re.compile(r'([A-Za-z0-9_./\\-]+\.py):(\d+)')
full = re.compile(r'([A-Za-z0-9_/\\-]+/[A-Za-z0-9_.\\-]+\.py)')

files = [p for p in list((root/'app').rglob('*.py')) + list((root/'packages').rglob('*.py'))
         if '__pycache__' not in p.parts]
by_rel = {p.relative_to(root).as_posix(): p for p in files}

def cands(ref):
    ref = ref.replace('\\', '')
    parts = pathlib.PurePosixPath(ref).parts
    out = []
    for p in files:
        rel = p.relative_to(root).as_posix().split('/')
        if len(parts) <= len(rel) and rel[-len(parts):] == list(parts):
            out.append(p)
    return out

def lines(p):
    return len(p.read_text(encoding='utf-8', errors='replace').splitlines())

stats = {'total': 0, 'unique_ok': 0, 'context_ok': 0, 'context_bad': 0, 'range_only': 0, 'unresolved': 0}
bad_samples, unresolved_samples = [], []
for p in sorted((root/'docs/flow').glob('*.md')):
    if not re.match(r'^\d{2}[a-z]?-', p.stem):
        continue
    src = p.read_text(encoding='utf-8').splitlines()
    for n, line in enumerate(src, 1):
        for m in anchor.finditer(line):
            ref, ln = m.group(1), int(m.group(2))
            stats['total'] += 1
            cs = cands(ref)
            if not cs:
                stats['unresolved'] += 1
                if len(unresolved_samples) < 8:
                    unresolved_samples.append(f"{p.stem}: {ref}:{ln}")
                continue
            if len(cs) == 1:
                stats['unique_ok' if ln <= lines(cs[0]) else 'unresolved'] += 1
                continue
            # 多候选：先看上文里的完整路径
            ctx = ' '.join(src[max(0, n - 6):n])
            ctx_refs = [r.replace('\\', '') for r in full.findall(ctx)]
            hit = None
            for cr in ctx_refs:
                exact = [c for c in cs if c.relative_to(root).as_posix() == cr]
                if exact:
                    hit = exact[0]
                    break
            if hit is None:
                inr = [c for c in cs if ln <= lines(c)]
                if len(inr) == 1:
                    hit = inr[0]
                    stats['range_only'] += 1
                elif inr:
                    hit = inr[0]
                    stats['range_only'] += 1
            if hit is None:
                stats['context_bad'] += 1
                if len(bad_samples) < 6:
                    bad_samples.append(f"{p.stem} {ref}:{ln}")
            else:
                stats['context_ok'] += 1

stats['pass_rate_%'] = round((stats['total'] - stats['unresolved'] - stats['context_bad']) / stats['total'] * 100, 2)
stats['bad_samples'] = bad_samples
stats['unresolved_samples'] = unresolved_samples
print(json.dumps(stats, ensure_ascii=False, indent=1))
