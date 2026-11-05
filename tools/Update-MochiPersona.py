"""Apply the reviewed shared persona, backing up identity and preserving memory."""
import argparse,json
from pathlib import Path
from nas import NAS
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--settings',type=Path,default=ROOT/'.runtime/nas.json');a=p.parse_args()
    settings=json.loads(a.settings.read_text());nas=NAS(settings)
    files={name:(ROOT/'profiles/mochi'/name).read_text(encoding='utf-8') for name in ('SOUL.md','SOUL-VOICE.md')}
    try:
        print(nas.container('hermes-agent','hermes-agent',"python - <<'PY'\n"+'FILES='+repr(files)+'\n'+'''
from pathlib import Path
import os,shutil,hashlib,json,time
root=Path('/opt/data/profiles/mochi');owner=root.stat()
os.setgroups([owner.st_gid]);os.setgid(owner.st_gid);os.setuid(owner.st_uid)
memory={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'memories/MEMORY.md',root/'memories/USER.md') if p.is_file()}
backup=root/'backups'/('persona-'+str(int(time.time())));backup.mkdir(parents=True,mode=0o700)
for name,content in FILES.items():
    path=root/name
    if path.exists():shutil.copy2(path,backup/name)
    temporary=path.with_suffix('.persona-partial');temporary.write_text(content);temporary.replace(path)
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==digest for p,digest in memory.items())
print(json.dumps({'persona_updated':True,'profile':'mochi','native_memories_preserved':True,'previous_identity_backed_up':True}))
PY'''))
        for name,target in (('SOUL.md','identity-original.md'),('SOUL-VOICE.md','identity-voice.md')):
            nas.upload(ROOT/'profiles/mochi'/name,settings['model_remote']+'/code/'+target)
    finally:nas.close()


if __name__=='__main__':main()
