from copy import deepcopy
from decimal import Decimal
import pytest
from manufacturing import Workflow, ManufacturingError, execute, validate_legacy_write, validate_stock
from conftest import ADMIN, NOW, action, order, complete


def mo(s, pid=3, qty=100):
    return action(s,"create_mo",{"productId":pid,"qty":qty,"productionDate":"2026-10-30"})


@pytest.mark.parametrize("output,short,extra",[(95,5,0),(105,0,5),(0,100,0)])
def test_wo_fixed_consumption_with_short_excess_and_total_loss(state,output,short,extra):
    m=mo(state);complete(state,m,output)
    w=Workflow(state,ADMIN,NOW)
    assert w.stock(1,2)==90 and w.stock(2,2)==18
    assert w.stock(3,2)==output
    assert (m['shortageQty'],m['excessQty'])==(short,extra)
    assert len(state['productions'])==1 and m['workOrder']['status']=='selesai'
    with pytest.raises(ManufacturingError): complete(state,m,output)


def test_recipe_snapshot_and_product_master_choose_bom(state):
    m=mo(state)
    state['boms'][0]['lines'][0]['qty']=99
    complete(state,m,100)
    assert m['bomId']==1 and m['kitchenId']==1
    assert m['ingredientsUsed'][0]['qtyUsed']==10


@pytest.mark.parametrize('start,end', [('2026-10-30T19:59','2026-10-31T01:00'),('2026-10-31T09:00','2026-10-31T20:00'),('2026-10-30T20:00','2026-10-31T10:01')])
def test_physical_shift_cannot_cross_daytime(state,start,end):
    m=mo(state)
    with pytest.raises(ManufacturingError,match='20.00'):complete(state,m,100,start,end)


def test_late_posting_uses_physical_times_not_clock(state):
    m=mo(state)
    complete(state,m,100)
    assert m['physicalFinishedAt'].startswith('2026-10-31T09:55')
    assert m['completedAt']==NOW


def test_buffer_minimum_can_be_consumed_to_zero(state):
    action(state,'set_minimum',{'productId':1,'warehouseId':2,'qty':5})
    action(state,'set_minimum',{'productId':1,'warehouseId':3,'qty':9})
    b=next(b for b in state['batches'] if b['productId']==1 and b['warehouseId']==2);b['qty']=10
    m=mo(state);complete(state,m,100)
    w=Workflow(state,ADMIN,NOW)
    assert w.stock(1,2)==0 and w.minimum(1,2)==5 and w.minimum(1,3)==9


def test_material_suggestion_thirteen_edit_and_one_multi_sku_transfer(state):
    state['boms'][1]['kitchenId']=1
    action(state,'configure_product',{'productId':4,'bomId':2,'kitchenId':1,'kind':'kitchen','allocationStep':1})
    o=action(state,'save_order',{'kind':'RO','storeId':6,'orderDate':'2026-10-29','deliveryDate':'2026-10-31','lines':[{'productId':3,'qty':100},{'productId':4,'qty':50}]})
    action(state,'confirm_order',{'id':o['id']})
    p=action(state,'create_plan',{'orderIds':[o['id']],'productionDate':'2026-10-30','deliveryDate':'2026-10-31'})
    action(state,'create_plan_mos',{'id':p['id']})
    assert len(state['productions'])==2
    next(b for b in state['batches'] if b['productId']==1 and b['warehouseId']==2)['qty']=7
    action(state,'set_minimum',{'productId':1,'warehouseId':2,'qty':5})
    w=Workflow(state,ADMIN,NOW)
    preview=w.material_preview({'kitchenId':1,'planId':p['id']})
    assert next(l for l in preview['lines'] if l['productId']==1)['suggestedQty']==13
    r=action(state,'save_request',{'kitchenId':1,'planId':p['id'],'lines':[{'productId':1,'qty':8},{'productId':2,'qty':2}]})
    t=action(state,'prepare_request',{'id':r['id']})
    assert len(t['lines'])==2 and t['lines'][0]['qty']==8
    action(state,'ship_transfer',{'id':t['id']})
    assert w.stock(1,2)==7
    action(state,'receive_transfer',{'id':t['id']})
    assert w.stock(1,2)==15
    with pytest.raises(ManufacturingError): action(state,'prepare_request',{'id':r['id']})


def test_buffer_request_without_work_order_and_expired_reservation(state):
    r=action(state,'save_request',{'kitchenId':1,'lines':[{'productId':1,'qty':5},{'productId':2,'qty':1}]})
    t=action(state,'prepare_request',{'id':r['id']})
    for reservation in state['reservations']: reservation['expiresAt']=0
    action(state,'ship_transfer',{'id':t['id']})
    assert t['status']=='dikirim' and len(state['productions'])==0


def test_semifinished_is_not_automatically_manufactured(state):
    state['boms'][0]['lines'].append({'productId':8,'qty':5,'uom':'kg'})
    m=mo(state)
    assert len(state['productions'])==1 and m['workOrder']
    assert m['bomSnapshot']['lines'][-1]['productId']==8


def test_bom_unit_conversion_to_base(state):
    state['boms'][0]['lines'][0].update(qty=0.4,uom='sak')
    m=mo(state);complete(state,m,100)
    assert m['ingredientsUsed'][0]['qtyUsed']==10


def test_direct_transfer_has_equal_immediate_receipt(state):
    m=mo(state);complete(state,m,95)
    t=action(state,'direct_to_packing',{'kitchenId':1,'lines':[{'productId':3,'qty':95}]})
    w=Workflow(state,ADMIN,NOW)
    assert t['status']=='diterima' and t['receivedAt']==t['shippedAt']
    assert w.stock(3,2)==0 and w.stock(3,5)==95
    assert not state['reservations']


def test_full_package_so_priority_and_store_allocation(state):
    so=order(state,'SO',7,100)
    ro1=order(state,'RO',3,40,6);ro2=order(state,'RO',3,60,7)
    plan=action(state,'create_plan',{'orderIds':[so['id'],ro1['id'],ro2['id']],'productionDate':'2026-10-30','deliveryDate':'2026-10-31'})
    mos=action(state,'create_plan_mos',{'id':plan['id']})
    assert {m['productId']:m['planQty'] for m in mos}=={3:200,4:100,5:100}
    for m in mos:
        qty=150 if m['productId']==3 else 100
        complete(state,m,qty)
        action(state,'direct_to_packing',{'kitchenId':m['kitchenId'],'lines':[{'productId':m['productId'],'qty':qty}]})
    w=Workflow(state,ADMIN,NOW)
    before=w.allocation_preview({'planId':plan['id']})
    assert [l['qty'] for l in before['lines']]==[20,30]  # Protect components before assembly.
    packs=action(state,'create_plan_mos',{'id':plan['id'],'kind':'package'})
    assert len(packs)==1 and packs[0]['workOrder'] is None
    complete(state,packs[0],100,'2026-10-31T12:00','2026-10-31T12:10')
    assert w.stock(7,5)==100 and w.stock(3,5)==50 and w.stock(6,5)==0
    al=w.allocation_preview({'planId':plan['id']})
    assert [l['qty'] for l in al['lines']]==[20,30]
    al['lines'][0]['qty']=35;al['lines'][1]['qty']=15
    saved=action(state,'save_allocation',al)
    store_dos=action(state,'create_store_deliveries',{'id':saved['id']})
    so_do=next(d for d in state['manufacturing']['deliveries'] if d['kind']=='SO')
    assert so_do['lines'][0]['productId']==7 and so_do['lines'][0]['qty']==100
    action(state,'ship_delivery',{'id':so_do['id']})
    for d in store_dos:
        action(state,'ship_delivery',{'id':d['id']})
        action(state,'receive_transfer',{'id':d['transferId']})
    assert w.stock(3,5)==0 and w.stock(7,5)==0
    assert w.stock(3,6)==35 and w.stock(3,7)==15
    assert len(state['productions'])==4  # No shortage backorder.


def test_allocation_rejects_double_use_and_stock_change(state):
    w=Workflow(state,ADMIN,NOW);w.credit(3,5,150,1,'OUTPUT','IN')
    so=order(state,'SO',3,100);ro=order(state,'RO',3,100)
    p=action(state,'create_plan',{'orderIds':[so['id'],ro['id']],'productionDate':'2026-10-30','deliveryDate':'2026-10-31'})
    a=w.allocation_preview({'planId':p['id']});a['lines'][0]['qty']=51
    with pytest.raises(ManufacturingError):action(state,'save_allocation',a)
    a['lines'][0]['qty']=50; a=action(state,'save_allocation',a)
    next(b for b in state['batches'] if b['productId']==3 and b['warehouseId']==5)['qty']=140
    with pytest.raises(ManufacturingError):action(state,'create_store_deliveries',{'id':a['id']})


def test_store_only_assembly_cannot_take_other_so_components(state):
    w=Workflow(state,ADMIN,NOW)
    for pid in (3,4,5):w.credit(pid,5,100,1,'OUTPUT','IN')
    order(state,'SO',3,100)
    pack=mo(state,7,100)
    with pytest.raises(ManufacturingError,match='diprioritaskan'):
        complete(state,pack,100,'2026-10-31T12:00','2026-10-31T12:01')


def test_same_date_consolidation_one_mo_per_sku_no_backorder(state):
    a=order(state,'RO',3,100);b=order(state,'SO',3,100)
    p=action(state,'create_plan',{'orderIds':[a['id'],b['id']],'productionDate':'2026-10-30','deliveryDate':'2026-10-31'})
    made=action(state,'create_plan_mos',{'id':p['id']})
    assert len(made)==1 and made[0]['planQty']==200 and len(made[0]['sources'])==2
    with pytest.raises(ManufacturingError):action(state,'create_plan_mos',{'id':p['id']})
    with pytest.raises(ManufacturingError):action(state,'create_plan',{'orderIds':[a['id']],'productionDate':'2026-10-30','deliveryDate':'2026-10-31'})


def test_largest_remainder_rounds_without_losing_or_exceeding_stock(state):
    w=Workflow(state,ADMIN,NOW);w.credit(3,5,5,1,'OUT','IN')
    a=order(state,'RO',3,4,6);b=order(state,'RO',3,6,7)
    p=action(state,'create_plan',{'orderIds':[a['id'],b['id']],'productionDate':'2026-10-30','deliveryDate':'2026-10-31'})
    r=w.allocation_preview({'planId':p['id']})
    assert [x['qty'] for x in r['lines']]==[2,3]


def test_roles_and_kitchen_scope(state):
    staff={'id':2,'username':'cook','role':'produksi','warehouseId':2}
    m=execute(state,staff,'create_mo',{'productId':3,'qty':100,'productionDate':'2026-10-30'},NOW)[0]
    assert m['sourceWarehouseId']==2
    with pytest.raises(ManufacturingError):execute(state,staff,'create_mo',{'productId':4,'qty':100,'productionDate':'2026-10-30'},NOW)
    r=execute(state,staff,'save_request',{'kitchenId':1,'lines':[{'productId':1,'qty':1}]},NOW)[0]
    with pytest.raises(ManufacturingError):execute(state,staff,'prepare_request',{'id':r['id']},NOW)


@pytest.mark.parametrize('bad',[-1,-0.00001,float('nan'),float('inf'),'x',True])
def test_all_writes_reject_negative_or_nonfinite_stock(state,bad):
    state['batches'][0]['qty']=bad
    with pytest.raises(ManufacturingError):validate_stock(state)


def test_raw_state_cannot_change_manufacturing_and_other_warehouse(state):
    m=mo(state);new=deepcopy(state);new['productions'][0]['planQty']=1
    with pytest.raises(ManufacturingError):validate_legacy_write(state,new,ADMIN)
    new=deepcopy(state);new['manufacturing']['deliveries'].append({'id':99})
    with pytest.raises(ManufacturingError):validate_legacy_write(state,new,ADMIN)
    new=deepcopy(state);new['batches'][0]['qty']=1
    with pytest.raises(ManufacturingError):validate_legacy_write(state,new,{'role':'gudang','warehouseId':2})


def test_schedule_all_stores_one_date_three_editable_sessions(state):
    s=action(state,'save_schedule',{'date':'2026-10-31','sessions':[{'time':'09:30'},{'time':'12:10'},{'time':'16:00'}],'stores':[{'storeId':6,'sessionId':1},{'storeId':7,'sessionId':3}]})
    assert len(s['sessions'])==3 and len(s['stores'])==2
    assert s['date']=='2026-10-31'


def test_legacy_stock_write_must_match_new_movements(state):
    new=deepcopy(state);new['batches'][0]['qty']-=1
    with pytest.raises(ManufacturingError,match='pergerakan'):validate_legacy_write(state,new,ADMIN)
    b=new['batches'][0]
    new['movements'].append({'id':max(m['id'] for m in new['movements'])+1,'productId':b['productId'],'warehouseId':b['warehouseId'],'batchId':b['id'],'qty':-1})
    validate_legacy_write(state,new,ADMIN)
    new['movements'][0]['qty']-=1
    with pytest.raises(ManufacturingError,match='Riwayat'):validate_legacy_write(state,new,ADMIN)


def test_legacy_rack_split_keeps_product_warehouse_balance(state):
    new=deepcopy(state);b=new['batches'][0];b['qty']-=5
    new['batches'].append({**b,'id':999,'qty':5,'rack':'B'})
    validate_legacy_write(state,new,ADMIN)
