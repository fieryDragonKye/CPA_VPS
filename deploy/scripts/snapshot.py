"""Offline private data backup/restore; no deletion and no overwrite of a nonempty destination."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import sqlite3

DIRECTORIES=['config','auths','logs','insights','plugins','secrets','caddy-data','caddy-config']


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def snapshot(source,target):
    source=source.resolve();target=target.resolve()
    if target==source or target.is_relative_to(source):raise ValueError('Backup must be outside instance')
    if target.exists():raise ValueError('Backup destination already exists')
    assert source.is_dir()
    for directory in DIRECTORIES:
        base=source/directory
        assert base.is_dir() and not base.is_symlink()
        assert not any(p.is_symlink() for p in base.rglob('*')),'Symlink in private data; refuse backup'
    target.mkdir(parents=True,mode=0o700)
    for directory in DIRECTORIES:
        shutil.copytree(source/directory,target/directory,ignore=shutil.ignore_patterns('*.sqlite','*.sqlite-wal','*.sqlite-shm'))
    database=source/'insights/usage.sqlite'
    if database.exists():
        src=sqlite3.connect(f'{database.as_uri()}?mode=ro',uri=True)
        dst=sqlite3.connect(target/'insights/usage.sqlite')
        try:
            src.backup(dst)
            assert dst.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        finally:
            dst.close()
            src.close()
    manifest={p.relative_to(target).as_posix():sha(p) for p in target.rglob('*') if p.is_file()}
    (target/'snapshot-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    if os.name=='posix':
        for p in target.rglob('*'):p.chmod(0o700 if p.is_dir() else 0o600)
    return len(manifest)


def restore(source,target):
    source=source.resolve();target=target.resolve()
    assert target!=source and not target.is_relative_to(source)
    assert not target.exists(),'Restore only to a new directory; never overwrite existing data'
    manifest=json.loads((source/'snapshot-manifest.json').read_text())
    for rel,digest in manifest.items():
        file=(source/rel).resolve()
        assert file.is_relative_to(source) and not (source/rel).is_symlink() and sha(file)==digest
    target.mkdir(parents=True,mode=0o750)
    for directory in DIRECTORIES:
        (target/directory).mkdir(mode=0o700)
    for rel in manifest:
        assert Path(rel).parts[0] in DIRECTORIES
        dst=target/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/rel,dst)
    if os.name=='posix' and os.geteuid()==0:
        os.chown(target,0,10001)
        for p in target.rglob('*'):
            p.chmod(0o700 if p.is_dir() else 0o600)
            if p.parts[-2:]!=('secrets','client.key'):os.chown(p,10001,10001)
    return len(manifest)


def main():
    p=argparse.ArgumentParser();p.add_argument('operation',choices=['backup','restore']);p.add_argument('--source',type=Path,required=True);p.add_argument('--to',type=Path,required=True);p.add_argument('--offline-confirmed',action='store_true');a=p.parse_args()
    if not a.offline_confirmed:raise ValueError('Stop and verify writers first, then provide --offline-confirmed')
    count=(snapshot if a.operation=='backup' else restore)(a.source,a.to)
    print(json.dumps({'operation':a.operation,'files':count,'path':str(a.to),'containsSensitiveData':True}))


if __name__=='__main__':main()
