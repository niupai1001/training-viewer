import json
import math
import statistics
import time
from pathlib import Path
from viewer_next.store import Store
from viewer_next.writer import RunWriter

root=Path('work/benchmark-v2')
source=root/'run'
if not (source/'run.json').exists():
    with RunWriter(source,experiment={'id':'bench','name':'性能样例'},variant={'id':'baseline','name':'基线','kind':'baseline'},metrics={'target':{'label':'目标','role':'loss','unit':'1','direction':'min'}}) as w:
        record={'session_id':w.session,'time':'2026-11-09T00:00:00Z'}
        with (source/'metrics.jsonl').open('w',encoding='utf-8') as f:
            for i in range(1000000):
                f.write(json.dumps({**record,'seq':i+2,'step':i,'values':{'target':.02+math.sin(i/30)*.001}})+'\n')
        w.seq=1000002
s=Store(root/'state')
t=time.perf_counter()
if s.db.execute('SELECT COUNT(*) FROM points').fetchone()[0] == 1000000:
    ingest=None
else:
    s.scan([source]);ingest=time.perf_counter()-t
rid=s.runs()[0]['meta']['run_id'];session=s.detail(rid)['sessions'][-1];times=[]
for i in range(20):
    t=time.perf_counter();result=s.curve(rid,'target',session=session,low=800000+i*17);times.append(time.perf_counter()-t)
with s.lock,s.db:
    for i in range(99):
        m=json.loads(s.db.execute('SELECT meta FROM runs WHERE id=?',(rid,)).fetchone()[0]);m['run_id']='bench'+str(i)
        s.db.execute('INSERT OR IGNORE INTO runs(id,path,meta) VALUES(?,?,?)',(m['run_id'],'synthetic',json.dumps(m)))
t=time.perf_counter();s.runs(100);listing=time.perf_counter()-t
print(json.dumps(dict(points=1000000,index_seconds=ingest,query_seconds=times,query_p95_seconds=sorted(times)[18],returned=len(result['points']),list_100_seconds=listing),indent=2))
s.close()
