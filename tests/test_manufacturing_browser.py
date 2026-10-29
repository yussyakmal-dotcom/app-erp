"""Browser coverage against an isolated, disposable local inventory database.

Install Chromium with `python -m playwright install chromium` before running.
No requests are made to a deployed inventory installation.
"""
import json
import os
import socket
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uvicorn

os.environ.setdefault('DATABASE_URL','sqlite://')
os.environ.setdefault('SEED_DEMO_USERS','false')
os.environ.setdefault('ADMIN_PASSWORD','OnlyForTests123')
import main


@pytest.fixture
def browser_app(tmp_path,monkeypatch):
    from playwright.sync_api import sync_playwright
    engine=create_engine('sqlite:///'+str(tmp_path/'browser.db'),connect_args={'check_same_thread':False})
    monkeypatch.setattr(main,'engine',engine)
    monkeypatch.setattr(main,'SessionLocal',sessionmaker(bind=engine))
    monkeypatch.setattr(main,'AUDIT_LOG_PATH',str(tmp_path/'audit.jsonl'))
    monkeypatch.setattr(main,'DEMO_DATA',True)
    main.init_db()
    with main.SessionLocal() as db:
        u=db.query(main.User).first();u.must_change_password=False;db.commit()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(main.app,host='127.0.0.1',port=port,lifespan='off',log_level='warning'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.05)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1440,'height':1000})
            page.goto(f'http://127.0.0.1:{port}')
            page.locator('[name=username]').fill('admin')
            page.locator('[name=password]').fill('OnlyForTests123')
            page.locator('#loginForm button').click()
            page.wait_for_function('ME && S && !dirty && !saving && document.getElementById("login").hidden')
            yield page
            browser.close()
    finally:
        server.should_exit=True;thread.join(10);engine.dispose()


def test_browser_forms_master_mo_results_and_all_tabs(browser_app):
    page=browser_app;errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    data=page.evaluate('({kitchens:S.kitchens,boms:S.boms,warehouses:S.warehouses})')
    packing=next(w for w in data['warehouses'] if w['code']=='GD-PCK')
    recipe=data['boms'][0]
    page.locator('[data-act=go][data-page=mfgconfig]').click()
    page.locator('[data-act=mfSettings]').click()
    page.locator('[data-bind="mfSettings.packingWarehouseId"]').select_option(str(packing['id']))
    page.locator('[data-act=mfSettingsSave]').click()
    page.wait_for_function('S.manufacturing?.settings.packingWarehouseId && !mfBusy')
    page.locator(f'[data-act=mfProduct][data-id="{recipe["productId"]}"]').click()
    page.locator('[data-bind="mfProduct.kind"]').select_option('kitchen')
    page.locator('[data-bind="mfProduct.kitchenId"]').select_option(str(recipe['kitchenId']))
    page.locator('[data-bind="mfProduct.bomId"]').select_option(str(recipe['id']))
    page.locator('[data-act=mfProductSave]').click()
    page.wait_for_function('!mfBusy && !M')
    page.locator('[data-act=go][data-page=manufacturing]').click()
    page.locator('[data-path=mfTab][data-val=mos]').click()
    page.locator('[data-act=mfNewMo]').click()
    page.locator('[data-bind="mfMo.productId"]').select_option(str(recipe['productId']))
    assert page.locator('[data-bind="mfMo.bomId"]').count()==0
    page.locator('[data-bind="mfMo.qty"]').fill('10')
    page.locator('[data-bind="mfMo.productionDate"]').fill('2026-10-30')
    page.locator('[data-act=mfCreateMo]').click()
    page.wait_for_function('!mfBusy && !M && S.productions.some(p=>p.manufacturingVersion===1)')
    mo=page.evaluate('S.productions.find(p=>p.manufacturingVersion===1)')
    # Supply only this disposable test database; real receipts remain unchanged.
    page.evaluate('''async mo => {
      await mfFlush();
      for(const l of mo.bomSnapshot.lines){
        const q=l.qty*mo.planQty/mo.bomSnapshot.yieldQty;
        const b={id:nid('batches'),productId:l.productId,warehouseId:mo.sourceWarehouseId,qty:q+100,cost:1000,batchNo:'UI-TEST',expDate:null,inboundAt:Date.now(),createdAt:Date.now(),rack:''};
        S.batches.push(b);mv('IN',b,b.qty,'UI-TEST','');
      }
      save();await mfFlush();
    }''',mo)
    page.locator(f'[data-act=mfFinish][data-id="{mo["id"]}"]').click()
    page.locator('[data-bind="mfFinish.physicalStartedAt"]').fill('2026-10-30T20:00')
    page.locator('[data-bind="mfFinish.physicalFinishedAt"]').fill('2026-10-31T09:55')
    page.locator('[data-bind="mfFinish.actualQty"]').fill('9')
    page.locator('[data-act=mfFinishSave]').click()
    page.wait_for_function('!mfBusy && !M && S.productions.some(p=>p.manufacturingVersion===1 && p.status==="selesai")')
    result=page.evaluate('S.productions.find(p=>p.manufacturingVersion===1)')
    assert result['actualQty']==9 and result['shortageQty']==1
    assert result['ingredientsUsed'][0]['qtyUsed']==recipe['lines'][0]['qty']*10/recipe['yieldQty']
    page.locator('[data-path=mfTab][data-val=packing]').click()
    page.locator('[data-act=mfDirect]').click()
    page.locator('[data-bind="mfDirect.kitchenId"]').select_option(str(recipe['kitchenId']))
    page.locator('[data-bind="mfDirect.lines.0.productId"]').select_option(str(recipe['productId']))
    page.locator('[data-bind="mfDirect.lines.0.qty"]').fill('9')
    page.locator('[data-act=mfDirectSave]').click()
    page.wait_for_function('!mfBusy && !M && S.transfers.some(t=>t.direct)')
    assert page.evaluate('S.transfers.find(t=>t.direct).status')=='diterima'
    for tab in ['orders','plans','mos','materials','packing','schedule','history']:
        page.locator(f'[data-path=mfTab][data-val="{tab}"]').click()
        assert page.locator('#view table').count()>0
    # The central inventory pages continue to render on the extended state.
    for name in ['dashboard','stock','inbound','transfer','products','kitchens','boms','reports']:
        page.locator(f'[data-act=go][data-page="{name}"]').first.click()
        assert page.locator('#view').inner_text().strip()
    page.locator('[data-act=go][data-page=manufacturing]').click()
    page.locator('[data-path=mfTab][data-val=mos]').click()
    output=Path('test-results');output.mkdir(exist_ok=True)
    page.screenshot(path=str(output/'manufacturing-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_function('document.querySelector("#side").getBoundingClientRect().right <= 0')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(output/'manufacturing-mobile.png'),full_page=True)
    assert errors==[]


def configure_packing(page):
    return page.evaluate('''async()=>{
      const packing=S.warehouses.find(w=>w.code==='GD-PCK');
      await mfCommand('save_settings',{packingWarehouseId:packing.id,timezone:'Asia/Jakarta'});
      return packing.id;
    }''')


def test_browser_orders_consolidation_allocation_and_delivery(browser_app):
    page=browser_app;packing=configure_packing(page)
    info=page.evaluate('''async wid=>{
      const p=S.products.find(p=>p.code==='P-011');
      const b={id:nid('batches'),productId:p.id,warehouseId:wid,qty:150,cost:1000,batchNo:'SO-RO-TEST',expDate:null,inboundAt:Date.now(),createdAt:Date.now(),rack:''};
      S.batches.push(b);mv('IN',b,150,'UI-TEST','');
      save();await mfFlush();return {pid:p.id,store:mfStores()[0].id};
    }''',packing)
    page.locator('[data-act=go][data-page=manufacturing]').click()
    for kind in ['SO','RO']:
        page.locator(f'[data-act=mfNewOrder][data-kind="{kind}"]').click()
        if kind=='SO':page.locator('[data-bind="mfOrder.customer"]').fill('Customer Test')
        else:page.locator('[data-bind="mfOrder.storeId"]').select_option(str(info['store']))
        page.locator('[data-bind="mfOrder.orderDate"]').fill('2026-10-29')
        page.locator('[data-bind="mfOrder.deliveryDate"]').fill('2026-10-31')
        page.locator('[data-bind="mfOrder.lines.0.productId"]').select_option(str(info['pid']))
        page.locator('[data-bind="mfOrder.lines.0.qty"]').fill('100')
        page.locator('[data-act=mfSaveOrder]').click();page.wait_for_function('!mfBusy && !M')
        page.locator('[data-act=mfConfirmOrder]').click();page.wait_for_function('!mfBusy && !M')
    page.locator('[data-path=mfTab][data-val=plans]').click()
    page.locator('[data-act=mfNewPlan]').click()
    page.locator('[data-bind="mfPlan.deliveryDate"]').fill('2026-10-31')
    page.locator('[data-bind="mfPlan.productionDate"]').fill('2026-10-30')
    for el in page.locator('#modal input[type=checkbox]').all():el.check()
    page.locator('[data-act=mfSavePlan]').click();page.wait_for_function('!mfBusy && !M')
    plan_id=page.evaluate('S.manufacturing.plans[0].id')
    page.locator('[data-path=mfTab][data-val=packing]').click()
    page.locator('[data-act=mfAllocation]').click()
    page.locator('[data-bind="mfAllocation.planId"]').select_option(str(plan_id))
    page.locator('[data-act=mfAllocationPreview]').click()
    page.locator('[data-bind="mfAllocation.lines.0.qty"]').wait_for()
    assert page.locator('[data-bind="mfAllocation.lines.0.qty"]').input_value()=='50'
    page.locator('[data-act=mfAllocationSave]').click();page.wait_for_function('!mfBusy && !M')
    page.locator('[data-act=mfStoreDos]').click();page.wait_for_function('!mfBusy && !M')
    deliveries=page.evaluate('S.manufacturing.deliveries')
    assert [(d['kind'],d['lines'][0]['qty']) for d in deliveries]==[('SO',100),('RO',50)]
    page.evaluate('window.print=()=>{}')
    version=page.evaluate('VER')
    page.locator('[data-act=mfPrint][data-kind=delivery]').first.click()
    assert page.evaluate('VER')==version
    for d in deliveries:
        page.locator(f'[data-act=mfShipDelivery][data-id="{d["id"]}"]').click()
        page.locator('[data-act=modalOk]').click();page.wait_for_function('!mfBusy && !M')
    assert page.evaluate('(pid)=>stockQ(pid,mfState().settings.packingWarehouseId)',info['pid'])==0
    page.locator('[data-act=mfReceive]').click()
    page.locator('[data-act=mfReceiveSave]').click();page.wait_for_function('!mfBusy && !M')
    assert page.evaluate('S.manufacturing.deliveries.find(d=>d.kind==="RO").status')=='diterima'


def test_browser_purchase_order_receives_directly_in_packing(browser_app):
    page=browser_app;packing=configure_packing(page)
    page.locator('[data-act=go][data-page=po]').click()
    page.locator('[data-act=newPO]').click()
    page.locator('[data-bind="po.warehouseId"]').select_option(str(packing))
    page.locator('[data-bind="po.supplierId"]').select_option('1')
    page.locator('[data-bind="po.lines.0.productId"]').select_option('1')
    page.locator('[data-bind="po.lines.0.uom"]').select_option('kg')
    page.locator('[data-bind="po.lines.0.qty"]').fill('2')
    page.locator('[data-bind="po.lines.0.price"]').fill('12000')
    page.locator('[data-act=poSave]').click()
    page.wait_for_function('!dirty && !saving && !M')
    po=page.evaluate('S.pos[S.pos.length-1]')
    assert po['warehouseId']==packing
    assert page.evaluate('(id)=>docHtml("po",byId(S.pos,id),1)',po['id']).find('Gudang Packing')>=0
    page.locator(f'[data-act=openPO][data-id="{po["id"]}"]').click()
    page.locator('[data-act=poOrder]').click();page.wait_for_function('!dirty && !saving')
    page.locator('[data-act=inbFromPO]').click()
    assert page.locator('[data-bind="inb.warehouseId"]').input_value()==str(packing)
    before=page.evaluate('(wid)=>stockQ(1,wid)',packing)
    page.locator('[data-bind="inb.lines.0.batchNo"]').fill('SUPPLIER-PACKING-TEST')
    page.locator('[data-bind="inb.lines.0.exp"]').fill('2030-01-01')
    page.locator('[data-act=inbSubmit]').click()
    page.locator('[data-act=modalOk]').click();page.wait_for_function('!dirty && !saving && !M')
    assert page.evaluate('(wid)=>stockQ(1,wid)',packing)==before+2
    assert page.evaluate('S.inbounds[0].warehouseId')==packing
