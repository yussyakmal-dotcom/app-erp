from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from conftest import action

os.environ.setdefault('DATABASE_URL','sqlite://')
os.environ.setdefault('SEED_DEMO_USERS','false')
os.environ.setdefault('ADMIN_PASSWORD','OnlyForTests123')
import main


@pytest.fixture
def client(tmp_path,monkeypatch,state):
    engine=create_engine('sqlite:///'+str(tmp_path/'test.db'),connect_args={'check_same_thread':False})
    monkeypatch.setattr(main,'engine',engine)
    monkeypatch.setattr(main,'SessionLocal',sessionmaker(bind=engine))
    monkeypatch.setattr(main,'AUDIT_LOG_PATH',str(tmp_path/'audit.jsonl'))
    with TestClient(main.app) as c:
        with main.SessionLocal() as db:
            u=db.query(main.User).first();u.must_change_password=False
            db.add(main.AppState(id=1,version=1,data=json.dumps(state)))
            db.commit()
        assert c.post('/api/auth/login',json={'username':'admin','password':'OnlyForTests123'}).status_code==200
        yield c
    engine.dispose()


def command(c,act,data,version=None,key=None):
    if version is None:version=c.get('/api/state').json()['version']
    return c.post('/api/manufacturing/commands',json={'version':version,'requestId':key or str(uuid.uuid4()),'action':act,'data':data})


def new_mo(c):
    r=command(c,'create_mo',{'productId':3,'qty':100,'productionDate':'2026-10-30'})
    assert r.status_code==200,r.text
    return r.json()['result']


def completion(m):
    return {'id':m['id'],'actualQty':95,'physicalStartedAt':'2026-10-30T20:00','physicalFinishedAt':'2026-10-31T09:55'}


def test_replay_same_request_is_exactly_once(client):
    m=new_mo(client);key=str(uuid.uuid4());v=client.get('/api/state').json()['version'];data=completion(m)
    a=command(client,'complete_mo',data,v,key);b=command(client,'complete_mo',data,v,key)
    assert a.status_code==b.status_code==200
    assert a.json()['version']==b.json()['version'] and b.json()['replayed']
    assert a.json()['data']['batches']==b.json()['data']['batches']
    assert command(client,'complete_mo',{**data,'actualQty':1},v,key).status_code==409


def test_concurrent_same_version_commits_once(client):
    m=new_mo(client);v=client.get('/api/state').json()['version']
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes=list(pool.map(lambda _:command(client,'complete_mo',completion(m),v).status_code,range(2)))
    assert sorted(codes)==[200,409]
    s=client.get('/api/state').json()['data']
    assert sum(b['qty'] for b in s['batches'] if b['productId']==3)==95


def test_second_short_ingredient_rolls_back_first_and_output(client):
    with main.SessionLocal() as db:
        row=db.get(main.AppState,1);s=json.loads(row.data)
        next(b for b in s['batches'] if b['productId']==2 and b['warehouseId']==2)['qty']=0
        row.data=json.dumps(s);db.commit()
    m=new_mo(client);before=client.get('/api/state').json()
    r=command(client,'complete_mo',completion(m))
    assert r.status_code==400
    after=client.get('/api/state').json()
    assert before==after


def test_raw_negative_and_production_bypass_are_rejected(client):
    before=client.get('/api/state').json();data=deepcopy(before['data']);data['batches'][0]['qty']=-1
    assert client.put('/api/state',json={'version':before['version'],'data':data}).status_code==400
    data=deepcopy(before['data']);data['productions'].append({'id':1,'status':'selesai'})
    assert client.put('/api/state',json={'version':before['version'],'data':data}).status_code==400
    assert client.get('/api/state').json()==before


def test_rejected_assembly_has_no_partial_consumption(client):
    with main.SessionLocal() as db:
        row=db.get(main.AppState,1);s=json.loads(row.data)
        from manufacturing import Workflow
        from conftest import ADMIN,order
        w=Workflow(s,ADMIN)
        for pid in (3,4,5):w.credit(pid,5,100,1,'OUTPUT','IN')
        order(s,'SO',3,100)
        row.data=json.dumps(s);db.commit()
    r=command(client,'create_mo',{'productId':7,'qty':100,'productionDate':'2026-10-31'})
    m=r.json()['result'];before=client.get('/api/state').json()
    data={'id':m['id'],'actualQty':100,'physicalStartedAt':'2026-10-31T12:00','physicalFinishedAt':'2026-10-31T12:10'}
    assert command(client,'complete_mo',data).status_code==400
    assert client.get('/api/state').json()==before


def test_preview_does_not_write_or_increment_version(client):
    before=client.get('/api/state').json()
    r=client.post('/api/manufacturing/preview',json={'action':'material_preview','data':{'kitchenId':1,'productIds':[1]}})
    assert r.status_code==200
    assert client.get('/api/state').json()==before


def test_ui_and_module_served(client):
    r=client.get('/');assert r.status_code==200
    assert '/static/manufacturing.js' in r.text
    assert client.get('/static/manufacturing.js').status_code==200


def test_two_different_mos_cannot_overdraw_shared_materials(client):
    with main.SessionLocal() as db:
        row=db.get(main.AppState,1);s=json.loads(row.data)
        next(b for b in s['batches'] if b['productId']==1 and b['warehouseId']==2)['qty']=15
        row.data=json.dumps(s);db.commit()
    first=new_mo(client);second=new_mo(client);v=client.get('/api/state').json()['version']
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda m:command(client,'complete_mo',completion(m),v),[first,second]))
    assert sorted(r.status_code for r in responses)==[200,409]
    loser=[first,second][next(i for i,r in enumerate(responses) if r.status_code==409)]
    assert command(client,'complete_mo',completion(loser)).status_code==400
    s=client.get('/api/state').json()['data']
    assert next(b for b in s['batches'] if b['productId']==1 and b['warehouseId']==2)['qty']==5
