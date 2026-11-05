from pathlib import Path
import paramiko

root=Path(__file__).resolve().parents[1]
destination=root/'.runtime/nas-voice-benchmark';destination.mkdir(exist_ok=True)
remote='/home/truenas_admin/mochi-voice-benchmark/results'
client=paramiko.SSHClient();client.load_host_keys(str(Path.home()/'.ssh/known_hosts'))
client.set_missing_host_key_policy(paramiko.RejectPolicy())
client.connect('192.168.8.245',username='truenas_admin',key_filename=str(Path.home()/'.ssh/truenas_audit_ed25519'),
 timeout=10,look_for_keys=False,allow_agent=False)
sftp=client.open_sftp()
for name in ('benchmark.log','int8/benchmark.json','int8/sample.wav','cpu-sweep/summary.json','cpu-eight/summary.json',
             'fp32-compile-v2/report.json','fp32-compile-v2/baseline.wav',
             'fp32-compile-v2/compile_cold.wav','fp32-compile-v2/compile_warm.wav',
             *(f'{run}/{precision}-{threads}/{filename}' for run in ('cpu-sweep','cpu-eight') for precision in ('fp32','int8')
               for threads in (1,2,4,8) for filename in ('benchmark.json','sample.wav'))):
    target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
    try:sftp.get(remote+'/'+name,str(target))
    except IOError:continue
sftp.close();client.close()
if (destination/'fp32-compile-v2/report.json').exists():print((destination/'fp32-compile-v2/report.json').read_text())
elif (destination/'cpu-eight/summary.json').exists():print((destination/'cpu-eight/summary.json').read_text())
elif (destination/'cpu-sweep/summary.json').exists():print((destination/'cpu-sweep/summary.json').read_text())
elif (destination/'int8/benchmark.json').exists():print((destination/'int8/benchmark.json').read_text())
elif (destination/'benchmark.log').exists():print((destination/'benchmark.log').read_text(errors='replace')[-1800:])
else:print('Benchmark still preparing or paused for an active conversation.')
