"""Build a curated source zip without credentials, local DB, or other projects."""
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DIRECTORIES=('backend','web','tests','eval','docs','scripts')
FILES=('README.md','README.zh-CN.md','package.json','server.py','.gitignore','.env.example')
SUFFIXES={'.py','.js','.html','.css','.json','.md','.png'}


def build():
    paths=[ROOT/name for name in FILES]
    for name in DIRECTORIES:
        paths.extend(p for p in (ROOT/name).rglob('*') if p.is_file() and p.suffix in SUFFIXES and '__pycache__' not in p.parts)
    paths=sorted(set(paths))
    inventory=[]
    for path in paths:
        data=path.read_bytes()
        if path.suffix != '.png' and re.search(rb'\bsk-[A-Za-z0-9_-]{20,}',data):
            raise SystemExit('Potential API credential found in '+str(path.relative_to(ROOT)))
        inventory.append({'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(data).hexdigest()})
    out=ROOT/'artifacts'/'release'; out.mkdir(parents=True,exist_ok=True)
    archive=out/'tracenote-source.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for path in paths: z.write(path,'trace-note/'+str(path.relative_to(ROOT)))
        z.writestr('trace-note/SOURCE-MANIFEST.json',json.dumps(inventory,indent=2))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert all('/data/' not in n and not n.endswith('/.env') and '/.git/' not in n for n in z.namelist())
    print(json.dumps({'archive':str(archive),'files':len(paths),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}))


if __name__=='__main__': build()
