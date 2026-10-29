"""Create a NEW private instance with new local keys, never import live auth/config."""
from pathlib import Path
import argparse
import json
import os
import re
import secrets

ROOT=Path(__file__).resolve().parent.parent


def block_yaml(value, indent=0):
    """Serialize the initializer's JSON-shaped data as block YAML without dependencies."""
    prefix=' '*indent
    def scalar(item):
        if item is None or isinstance(item,(str,bool,int,float)):
            return json.dumps(item,ensure_ascii=False,allow_nan=False)
        raise TypeError('Unsupported initializer scalar')
    def nested(item):
        return isinstance(item,(dict,list)) and bool(item)
    lines=[]
    if not value and isinstance(value,(dict,list)):
        return prefix+('{}' if isinstance(value,dict) else '[]')+'\n'
    if isinstance(value,dict):
        for key,item in value.items():
            if not isinstance(key,str):raise TypeError('Initializer keys must be strings')
            plain=re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*',key) and key.lower() not in {'true','false','null','yes','no','on','off','y','n'}
            head=prefix+(key if plain else json.dumps(key,ensure_ascii=False))+':'
            if nested(item):lines.extend([head,block_yaml(item,indent+2).rstrip('\n')])
            else:lines.append(head+' '+('[]' if isinstance(item,list) else '{}' if isinstance(item,dict) else scalar(item)))
    elif isinstance(value,list):
        for item in value:
            if nested(item):lines.extend([prefix+'-',block_yaml(item,indent+2).rstrip('\n')])
            else:lines.append(prefix+'- '+('[]' if isinstance(item,list) else '{}' if isinstance(item,dict) else scalar(item)))
    else:raise TypeError('Expected initializer mapping or list')
    return '\n'.join(lines)+'\n'


def prepare(destination, mode, port=8317):
    if os.name=='posix' and os.geteuid()==0:
        import pwd
        try:
            account=pwd.getpwuid(10001)
        except KeyError:
            account=None
        if account and account.pw_name not in ('cpa','cpa-personal'):
            raise ValueError('UID10001 belongs to another account; review ownership before preparing data')
    destination=destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Instance directory must be empty; refusing to overwrite')
    destination.mkdir(parents=True,exist_ok=True)
    if os.name=='posix':
        destination.chmod(0o750)
        if os.geteuid()==0:os.chown(destination,0,10001)
    for name in ['config','auths','logs','insights','plugins','secrets','caddy-data','caddy-config']:
        (destination/name).mkdir(mode=0o700)
    admin=secrets.token_urlsafe(48);client=secrets.token_urlsafe(48)
    auth_path='/var/lib/cpa/auths' if mode=='private-pod' else str(destination/'auths')
    config={'config-version':8,'server':{'host':'127.0.0.1','port':port,'trusted-proxies':[], 'discovery':{'enabled':False}},
        'management':{'allow-remote':False,'secret-key':admin,'disable-control-panel':False,'disable-auto-update-panel':True},
        'access':{'api-keys':[client]},'oauth':{'auth-dir':auth_path},'requests':{'proxy-url':''},
        'routing':{'retry':{'request-retry':1}},
        'observability':{'logs':{'logging-to-file':True,'request-log':False,'logs-max-total-size-mb':20,'error-logs-max-files':3},'usage':{'usage-statistics-enabled':True},'pprof':{'enable':False}}}
    # Block mappings also work with plugins that do not traverse YAML flow nodes.
    (destination/'config/config.yaml').write_text(block_yaml(config),encoding='utf-8')
    for name,value in [('management.key',admin),('client.key',client)]:
        (destination/'secrets'/name).write_text(value+'\n',encoding='utf-8')
    version=json.loads((ROOT/'lock.json').read_text())['bundleVersion']
    (destination/'instance.json').write_text(json.dumps({'mode':mode,'createdBy':version,'port':port}),encoding='utf-8')
    if os.name=='posix':
        for p in destination.rglob('*'):
            p.chmod(0o700 if p.is_dir() else 0o600)
            if os.geteuid()==0 and p.parts[-2:]!=('secrets','client.key'):
                # The unprivileged application user reads config/auth/data and its secret.
                os.chown(p,10001,10001)
        if mode=='private-pod' and os.geteuid()!=0:
            print('NOTICE: before Docker start, root must chown app data and management.key to UID/GID 10001; see README')
    return destination


def main():
    if os.name!='posix':raise ValueError('Prepare runtime data on Linux, not in the Windows production workspace')
    p=argparse.ArgumentParser();p.add_argument('--instance',type=Path,required=True)
    p.add_argument('--mode',choices=['private-pod'],default='private-pod');p.add_argument('--env-file',type=Path,required=True)
    a=p.parse_args()
    if a.env_file.exists():raise ValueError('Refusing to overwrite env file')
    dest=prepare(a.instance,a.mode)
    lock=json.loads((ROOT/'lock.json').read_text())
    a.env_file.write_text('\n'.join(['PERSONAL_RELEASE='+lock['bundleVersion'],'INSTANCE_ROOT='+str(dest),
        'PYTHON_IMAGE='+lock['images']['python']['reference'],'CADDY_IMAGE='+lock['images']['caddy']['reference'],
        'ADMIN_ORIGINS=http://127.0.0.1:18317','']),encoding='utf-8')
    print('New private instance prepared. Keys are stored in restricted files, not printed. No upstream credentials imported.')


if __name__=='__main__':main()
