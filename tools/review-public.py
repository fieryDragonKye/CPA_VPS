"""Heuristic public-source review. Print paths/line numbers, never secret values."""
from pathlib import Path
import re,json,sys,os,hashlib
ROOT=Path(__file__).resolve().parent.parent
SELF=Path(__file__).resolve()
KNOWN=json.loads((SELF.parent/'review-fixtures.json').read_text()).get('api-token',{})
SKIP={'.git','node_modules','dist','__pycache__','vendor','artifacts'}
patterns={
 'private-key':r'-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----',
 'credential-in-url':r'https?://[^\s/<>"\x27]{1,128}:[^\s/@<>"\x27]{1,128}@',
 'jwt-like-token':r'eyJ[A-Za-z0-9_-]{12,2048}\.[A-Za-z0-9_-]{12,2048}\.[A-Za-z0-9_-]{12,2048}',
 'personal-account':r'[A-Za-z0-9._%+\-]{1,128}@icloud\.com',
 'api-token':r'\bsk-[A-Za-z0-9_-]{24,}',
 'personal-path':r'[A-Z]:[\\/]Users[\\/](?!Public\b|Default\b|example\b|test\b)[^\\/\s]+',
}
hits=[];files=0;large=[];fixtures=[]
def candidates():
 for base,dirs,names in os.walk(ROOT,followlinks=False):
  dirs[:]=[d for d in dirs if d not in SKIP and not (Path(base)/d).is_symlink() and not (Path(base)/d).is_junction()]
  for name in names:yield Path(base)/name
for p in candidates():
 if not p.is_file() or any(x in SKIP for x in p.relative_to(ROOT).parts):continue
 files+=1
 if p==SELF:continue
 if p.stat().st_size>5*1024*1024:large.append(p.relative_to(ROOT).as_posix())
 try:text=p.read_text(encoding='utf-8-sig')
 except (UnicodeError,OSError):continue
 for number,line in enumerate(text.splitlines(),1):
  for name,pat in patterns.items():
   literal={'private-key':'PRIVATE KEY','credential-in-url':'@','jwt-like-token':'eyJ','personal-account':'@icloud.com','personal-path':'Users','api-token':'sk-'}[name]
   if literal not in line:continue
   if re.search(pat,line):
    item={'file':p.relative_to(ROOT).as_posix(),'line':number,'rule':name}
    known_api=name=='api-token' and all(hashlib.sha256(m[0].encode()).hexdigest() in KNOWN.get(item['file'],[]) for m in re.finditer(pat,line))
    if known_api or (item['file']=='insights/test_server.py' and ((name=='credential-in-url' and 'example.test' in line) or (name=='api-token' and ('THISISATEST' in line or 'ANOTHERTEST' in line)))):fixtures.append(item)
    else:hits.append(item)
print(json.dumps({'files_reviewed':files,'findings':hits,'recognized_test_fixtures':fixtures,'files_over_5MiB':large,'note':'Heuristic only. Inspect staged Git diff and use secret scanning before publishing.'},ensure_ascii=False,indent=2))
sys.exit(1 if hits else 0)
