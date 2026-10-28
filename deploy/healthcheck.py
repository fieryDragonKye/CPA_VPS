import os
import json
from pathlib import Path
import sys
import urllib.request

kind = sys.argv[1]
if kind=='cpa':
    url='http://127.0.0.1:8317/'
    headers={}
else:
    url='http://127.0.0.1:8320/v8/management/extensions/insights/status'
    headers={'Authorization':'Bearer '+Path(os.environ['MANAGEMENT_KEY_FILE']).read_text().strip()}
try:
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(urllib.request.Request(url,headers=headers),timeout=4) as r:
        if r.status!=200:raise ValueError('unhealthy')
        if kind!='cpa' and json.load(r).get('state') not in ('running','disabled'):
            raise ValueError('collector not ready')
except Exception:
    sys.exit(1)
