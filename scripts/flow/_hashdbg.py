import pathlib
import sys
sys.path.insert(0, r'D:\Code\Python\NeoBot\scripts\flow')
import check_flow_diagrams as c
root = pathlib.Path('.').resolve()
diagrams = c.load_diagrams(root / 'docs' / 'flow')
d = [x for x in diagrams if x.path.stem == '23-billing-stats'][0]
print('covers:', d.covers)
h, manifest = c.compute_verified_hash(d.covers, root)
print('computed:', h, 'files:', len(manifest))
print('recorded:', d.front.get('verified_hash'))
for item in manifest[:20]:
    print('  ', item)