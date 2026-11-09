import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from viewer_next.writer import RunWriter
from viewer_next.store import Store
from viewer_next.server import create_app


def writer(path, **extra):
    return RunWriter(path, experiment={'id':'e','name':'自定义实验'},
      variant={'id':'v','name':'基线','kind':'baseline'},
      metrics={'objective':{'label':'目标','unit':'1','direction':'min','role':'loss'}}, **extra)


def test_writer_resume_and_lock(tmp_path):
    with writer(tmp_path) as w:
        w.log(10,{'objective':1})
        with pytest.raises(OSError):
            writer(tmp_path)
        with pytest.raises(ValueError):
            w.log(9,{'objective':2})
        with pytest.raises(ValueError):
            w.log(11,{'objective':float('nan')})
    with RunWriter(tmp_path,resume=True) as resumed:
        resumed.log(3,{'objective':.5})
    s=Store(tmp_path/'state');s.scan([tmp_path])
    run=s.runs()[0]
    assert len(run['sessions'])==2 and run['status']=='completed'
    assert s.summary(run['meta']['run_id'])['objective']['latest']['step']==3
    s.close()


def test_partial_bad_duplicate_and_reset(tmp_path):
    source=tmp_path/'中文 路径'
    with writer(source) as w:
        w.log(1,{'objective':2})
        w.log(1,{'objective':1})
    s=Store(tmp_path/'state');s.scan([source]);rid=s.runs()[0]['meta']['run_id']
    assert s.curve(rid,'objective')['count']==1
    assert s.summary(rid)['objective']['best']['value']==1
    p=source/'metrics.jsonl'
    data=json.loads(p.read_text().splitlines()[-1]);data.update(seq=100,step=2,values={'objective':.5})
    with p.open('ab') as f:f.write(b'bad\n'+json.dumps(data).encode())
    s.scan([source]);assert s.curve(rid,'objective')['count']==1
    with p.open('ab') as f:f.write(b'\n')
    s.scan([source]);assert s.curve(rid,'objective')['count']==2
    p.write_text('')
    s.scan([source]);assert s.curve(rid,'objective')['count']==0
    s.close()


def test_sampling_and_conflict(tmp_path):
    import shutil
    a=tmp_path/'a'
    with writer(a) as w:
        for step in range(1000):w.log(step,{'objective':100 if step==500 else .02+step*.00001})
    b=tmp_path/'b';shutil.copytree(a,b)
    s=Store(tmp_path/'state');s.scan([a,b]);assert len(s.runs())==1
    rid=s.runs()[0]['meta']['run_id'];curve=s.curve(rid,'objective',budget=100)
    assert len(curve['points'])<=100 and max(p['value'] for p in curve['points'])==100
    assert s.curve(rid,'objective',low=800)['y_max']<.04
    with (b/'metrics.jsonl').open('a') as f:f.write('{}\n')
    s.scan([b]);assert s.db.execute('SELECT COUNT(*) FROM issues').fetchone()[0]>0
    s.close()


def test_api_security_and_state(tmp_path):
    app=create_app(tmp_path/'state','secret')
    with TestClient(app,base_url='http://127.0.0.1') as c:
        assert c.get('/api/v2/roots').status_code==403
        headers={'x-viewer-token':'secret'}
        assert c.get('/api/v2/roots',headers={**headers,'origin':'https://evil.example'}).status_code==403
        assert c.get('/api/v2/roots',headers={**headers,'host':'evil.example'}).status_code==403
        assert c.put('/api/v2/settings/workspace',headers=headers,json={'value':'test'}).status_code==200
        assert c.get('/api/v2/settings/workspace',headers=headers).json()=='test'
        assert c.put('/api/v2/settings/chart.train%2Floss',headers=headers,json={'value':{'mode':'late'}}).status_code==200
        assert c.get('/api/v2/settings/chart.train%2Floss',headers=headers).json()=={'mode':'late'}
        assert c.post('/api/v2/roots',headers=headers,json={'path':str(tmp_path/'absent')}).status_code==400


def test_reopen_and_constant_series(tmp_path):
    source=tmp_path/'run'
    with writer(source) as w:
        for step in range(100):
            w.log(step,{'objective':0})
    state=tmp_path/'state'
    s=Store(state);s.add(source);s.setting('workspace','saved',True);s.scan()
    rid=s.runs()[0]['meta']['run_id'];s.close()
    s=Store(state)
    assert s.roots()==[str(source.resolve())]
    assert s.setting('workspace')=='saved'
    curve=s.curve(rid,'objective',budget=20)
    assert curve['y_min']==curve['y_max']==0
    assert 1<=len(curve['points'])<=20
    s.close()
