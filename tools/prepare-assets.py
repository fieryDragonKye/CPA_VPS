"""Stage locally built UI and checksum-verified CPA binaries, never upload data."""
from pathlib import Path
import argparse,hashlib,json,urllib.request,tarfile,shutil,tempfile
ROOT=Path(__file__).resolve().parent.parent
def fetch(url):
    with urllib.request.urlopen(url,timeout=60) as response:return response.read()
def main():
    p=argparse.ArgumentParser();p.add_argument('--arch',choices=['amd64','arm64'],required=True);a=p.parse_args()
    html=ROOT/'web/dist/index.html'
    if not html.is_file():raise SystemExit('Build web first: bun run build')
    target=ROOT/'deploy/vendor'/('linux-'+a.arch)/'cli-proxy-api'
    if target.exists():raise SystemExit('Refusing to overwrite existing staged backend; review/remove it explicitly')
    lock=json.loads((ROOT/'deploy/lock.json').read_text())
    version=lock['cpaVersion']
    asset='CLIProxyAPI_'+version+'_linux_'+('aarch64' if a.arch=='arm64' else 'amd64')+'.tar.gz'
    base='https://github.com/router-for-me/CLIProxyAPI/releases/download/v'+version+'/'
    sums=fetch(base+'checksums.txt').decode().splitlines()
    expected=next((l.split()[0] for l in sums if len(l.split())==2 and l.split()[1].lstrip('*')==asset),None)
    if not expected:raise SystemExit('No matching official checksum')
    data=fetch(base+asset)
    if hashlib.sha256(data).hexdigest()!=expected:raise SystemExit('Checksum mismatch; no binary staged')
    with tempfile.TemporaryFile() as f:
        f.write(data);f.seek(0)
        with tarfile.open(fileobj=f,mode='r:gz') as archive:
            members=[m for m in archive.getmembers() if m.isfile() and Path(m.name).name=='cli-proxy-api']
            if len(members)!=1:raise SystemExit('Unexpected archive layout')
            binary=archive.extractfile(members[0]).read()
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(binary);target.chmod(0o755)
    assets=ROOT/'deploy/assets';assets.mkdir(exist_ok=True);shutil.copyfile(html,assets/'management.html')
    print('Verified CPA '+version+' and built UI staged locally. No instance credentials imported.')
if __name__=='__main__':main()
