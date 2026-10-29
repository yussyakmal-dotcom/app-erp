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


def select_product(page, path, product_id):
    code = page.evaluate('(id) => P(id).code', product_id)
    page.locator(f'[data-product-search="{path}"]').fill(code)
    page.locator(f'#product-picker-popup [role=option][data-value="{product_id}"]').click()
    assert page.locator(f'[data-bind="{path}"]').input_value() == str(product_id)


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
    select_product(page, 'mfMo.productId', recipe['productId'])
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
    select_product(page, 'mfDirect.lines.0.productId', recipe['productId'])
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
        select_product(page, 'mfOrder.lines.0.productId', info['pid'])
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
    select_product(page, 'po.lines.0.productId', 1)
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


def test_product_search_5000_skus_paging_keyboard_and_no_free_text(browser_app):
    from playwright.sync_api import expect
    page = browser_app
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    last = page.evaluate('''() => {
      const template = S.products[0], count = S.products.length;
      for (let i=count+1; i<=5000; i++) S.products.push({...clone(template),
        id:10000+i, code:`TEST-${String(i).padStart(5,'0')}`,
        name:i===5000?'Coklat Paling Akhir':i%25===0?`Coklat Bubuk ${i}`:`Bahan ${i}`,
        isActive:true, manufacturing:undefined});
      S.ui.page='po'; render();
      return S.products[S.products.length-1];
    }''')
    page.locator('[data-act=newPO]').click()
    field = page.locator('[data-product-search="po.lines.0.productId"]')
    field.click()
    options = page.locator('#product-picker-popup [role=option]')
    assert options.count() == 50
    assert page.locator('#modal select option').count() < 100
    field.fill('CoKLaT')
    assert options.count() == 50
    assert all('coklat' in text.lower() for text in options.all_text_contents())
    first = options.first.inner_text()
    page.get_by_role('button', name='Berikutnya', exact=True).click()
    assert options.first.inner_text() != first
    assert options.count() == 50
    page.get_by_role('button', name='Sebelumnya', exact=True).click()
    assert options.first.inner_text() == first
    # A query from the end of the full catalogue is found immediately.
    field.fill(last['code'].lower())
    assert options.count() == 1
    field.press('ArrowDown')
    expect(field).to_have_attribute('aria-activedescendant', 'product-picker-option-0')
    field.press('Enter')
    expect(page.locator('[data-bind="po.lines.0.productId"]')).to_have_value(str(last['id']))
    assert last['name'] in field.input_value()
    expect(page.locator('[data-bind="po.lines.0.uom"]')).to_have_value(last['poUom'])
    assert page.locator('#product-picker-popup').count() == 0
    # Typing is a search, never a replacement product ID; blur restores selection.
    field.fill('produk tidak pernah ada xyz')
    expect(page.locator('#product-picker-count')).to_have_text('Tidak ada produk yang cocok.')
    field.press('Enter')
    assert page.locator('[data-bind="po.lines.0.productId"]').input_value() == str(last['id'])
    field.press('Tab')
    assert last['name'] in field.input_value()
    field.click()
    page.get_by_role('button', name='Kosongkan pilihan', exact=True).click()
    assert page.locator('[data-bind="po.lines.0.productId"]').input_value() == ''
    assert field.input_value() == ''
    # An unrelated form redraw preserves the active query and search results.
    field.fill('akhir coklat')
    field.press('Home')
    page.evaluate('refresh()')
    expect(field).to_have_value('akhir coklat')
    assert field.evaluate('(el)=>el.selectionStart') == 0
    assert options.count() == 1
    field.press('Escape')
    assert page.locator('#product-picker-popup').count() == 0
    assert page.locator('#modal').is_visible()
    assert errors == []


def test_product_search_legacy_forms_filters_and_change_hooks(browser_app):
    page = browser_app
    products = page.evaluate('''() => {
      const p=S.products.find(p=>availQ(p.id,central().id)>0);
      const other=S.products.find(x=>x.id!==p.id && x.isActive);
      return {p,other};
    }''')
    p, other = products['p'], products['other']
    page.locator('[data-act=go][data-page=inbound]').click()
    select_product(page, 'inb.lines.0.productId', p['id'])
    assert page.locator('[data-bind="inb.lines.0.uom"]').input_value() == p['baseUom']
    assert float(page.locator('[data-bind="inb.lines.0.cost"]').input_value()) == p['refPrice']
    page.locator('[data-act=go][data-page=transfer]').click()
    page.locator('[data-act=newTransfer]').click()
    field = page.locator('[data-product-search="trf.lines.0.productId"]')
    field.click()
    eligible = page.evaluate('actP().filter(p=>availQ(p.id,+F.trf.srcId)>1e-9).map(p=>String(p.id))')
    assert page.locator('#product-picker-popup [role=option]').evaluate_all('(els)=>els.map(e=>e.dataset.value)') == eligible
    select_product(page, 'trf.lines.0.productId', p['id'])
    assert page.locator('[data-bind="trf.lines.0.uom"]').input_value() == p['baseUom']
    page.locator('#modal .mhead [data-act=closeModal]').click()
    page.locator('[data-act=go][data-page=usage]').click()
    select_product(page, 'use.productId', p['id'])
    assert page.locator('[data-bind="use.uom"]').input_value() == p['baseUom']
    page.locator('[data-act=go][data-page=boms]').click()
    page.locator('[data-act=editBom]:not([data-id])').click()
    select_product(page, 'bomForm.productId', other['id'])
    ingredient = page.locator('[data-product-search="bomForm.lines.0.productId"]')
    ingredient.fill(other['code'])
    assert page.locator(f'#product-picker-popup [data-value="{other["id"]}"]').count() == 0
    select_product(page, 'bomForm.lines.0.productId', p['id'])
    assert page.locator('[data-bind="bomForm.lines.0.uom"]').input_value() == p['baseUom']
    page.locator('[data-act=bomAddLine]').click()
    select_product(page, 'bomForm.lines.1.productId', p['id'])
    page.locator('[data-act=bomDelLine][data-i="0"]').click()
    assert page.locator('[data-bind="bomForm.lines.0.productId"]').input_value() == str(p['id'])
    assert page.locator('[data-product-search="bomForm.lines.1.productId"]').count() == 0
    page.locator('#modal .mhead [data-act=closeModal]').click()
    page.locator('[data-act=go][data-page=scrap]').click()
    page.locator('[data-act=newScrap]').click()
    field = page.locator('[data-product-search="scr.batchId"]')
    field.fill(p['code'])
    option = page.locator('#product-picker-popup [role=option]').first
    batch_id = option.get_attribute('data-value')
    option.click()
    assert page.locator('[data-bind="scr.batchId"]').input_value() == batch_id
    page.locator('#modal .mhead [data-act=closeModal]').click()
    page.locator('[data-act=go][data-page=reports]').click()
    page.locator('[data-act=setF][data-path="rep.tab"][data-val=kartu]').click()
    select_product(page, 'rep.pid', p['id'])
    page.locator('[data-product-search="rep.pid"]').click()
    page.get_by_role('button', name='Semua produk', exact=True).click()
    assert page.locator('[data-bind="rep.pid"]').input_value() == ''


def test_product_search_manufacturing_rows_duplicate_names_and_mobile(browser_app):
    from playwright.sync_api import expect
    page = browser_app
    ids = page.evaluate('''() => {
      const template=S.products[0];
      for (const [id,code,active] of [[8001,'COC-A',true],[8002,'COC-B',true],[8003,'COC-OFF',false]])
        S.products.push({...clone(template),id,code,name:'Coklat Sama',isActive:active,manufacturing:undefined});
      S.ui.page='manufacturing';render();
      return [8001,8002];
    }''')
    page.locator('[data-act=mfNewOrder][data-kind=RO]').click()
    select_product(page, 'mfOrder.lines.0.productId', ids[0])
    page.locator('[data-act=mfLineAdd]').click()
    field = page.locator('[data-product-search="mfOrder.lines.1.productId"]')
    field.fill('coklat sama')
    expect(page.locator('#product-picker-popup [role=option]')).to_have_count(2)
    page.locator('#product-picker-popup [data-value="8002"]').click()
    assert page.evaluate('F.mfOrder.lines.map(l=>l.productId)') == ['8001', '8002']
    page.locator('[data-act=mfLineRemove][data-i="0"]').click()
    assert page.locator('[data-bind="mfOrder.lines.0.productId"]').input_value() == '8002'
    page.set_viewport_size({'width':390, 'height':844})
    page.wait_for_function('document.querySelector("#side").getBoundingClientRect().right <= 0')
    field = page.locator('[data-product-search="mfOrder.lines.0.productId"]')
    field.fill('coklat')
    bounds = page.locator('#product-picker-popup').bounding_box()
    assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= 390
    assert bounds['y'] >= 0 and bounds['y'] + bounds['height'] <= 844
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    output = Path('test-results'); output.mkdir(exist_ok=True)
    page.screenshot(path=str(output/'product-search-mobile.png'), full_page=True)
    # Escape closes the list first, preserving the order dialog.
    field.press('Escape')
    assert page.locator('#modal').is_visible()
    page.locator('#modal .mhead [data-act=closeModal]').click()
    page.set_viewport_size({'width':1440, 'height':1000})
    page.locator('[data-path=mfTab][data-val=materials]').click()
    page.locator('[data-act=mfNewRequest]').click()
    select_product(page, 'mfRequest.productId', ids[0])
    page.locator('#modal .mhead [data-act=closeModal]').click()
    page.locator('[data-path=mfTab][data-val=mos]').click()
    page.locator('[data-act=mfNewMo]').click()
    field = page.locator('[data-product-search="mfMo.productId"]')
    field.fill('COC-A')
    assert page.locator('#product-picker-popup [role=option]').count() == 0
    page.locator('#modal .mhead [data-act=closeModal]').click()
    page.locator('[data-act=go][data-page=mfgconfig]').first.click()
    page.locator('[data-act=mfMinimum]').click()
    select_product(page, 'mfMinimum.productId', ids[1])
    page.locator('[data-bind="mfMinimum.warehouseId"]').select_option('1')
    assert float(page.locator('[data-bind="mfMinimum.qty"]').input_value()) >= 0
    field = page.locator('[data-product-search="mfMinimum.productId"]')
    field.fill('coklat')
    page.screenshot(path=str(output/'product-search-desktop.png'), full_page=True)
    page.locator('#modal .mhead [data-act=closeModal]').click()
    assert page.locator('#product-picker-popup').count() == 0
