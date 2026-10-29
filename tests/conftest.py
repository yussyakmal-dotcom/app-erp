import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from manufacturing import Workflow, execute

ADMIN = {"id": 1, "username": "admin", "role": "admin", "warehouseId": None}
NOW = 1793401500000


@pytest.fixture
def state():
    s = {"v": 3, "seq": {}, "products": [], "warehouses": [], "kitchens": [], "boms": [],
         "batches": [], "movements": [], "reservations": [], "transfers": [], "productions": [],
         "scraps": [], "audit": []}
    for i, name in enumerate(["Central", "Dapur A", "Dapur B", "Dapur C", "Packing", "Toko A", "Toko B"], 1):
        s["warehouses"].append({"id": i, "name": name, "code": str(i), "isCentral": i == 1, "isActive": True})
    for i in range(1, 4):
        s["kitchens"].append({"id": i, "name": f"Dapur {i}", "code": f"K{i}", "warehouseId": i+1, "isActive": True})
    for i, (name, unit) in enumerate([("Tepung","kg"),("Gula","kg"),("A","pcs"),("B","pcs"),("C","pcs"),("D supplier","pcs"),("Paket P","paket"),("Adonan","kg")], 1):
        s["products"].append({"id":i,"name":name,"code":f"P{i}","baseUom":unit,"uoms":[{"name":"sak","factor":25}] if i==1 else [],"isActive":True,"minCentral":0,"minBranch":0})
    for i, pid in enumerate([3,4,5,8], 1):
        s["boms"].append({"id":i,"productId":pid,"code":f"B{i}","name":f"BOM {pid}","yieldQty":100,"yieldUom":s['products'][pid-1]['baseUom'],"kitchenId":min(i,3),"isActive":True,"lines":[{"productId":1,"qty":10,"uom":"kg"},{"productId":2,"qty":2,"uom":"kg"}]})
    s["boms"].append({"id":5,"code":"BP","productId":7,"yieldQty":1,"yieldUom":"paket","kitchenId":None,"isActive":True,"lines":[{"productId":i,"qty":1,"uom":"pcs"} for i in (3,4,5,6)]})
    w = Workflow(s, ADMIN, NOW)
    w.save_settings({"packingWarehouseId":5,"timezone":"Asia/Jakarta"})
    for pid,bid,kid,kind in [(3,1,1,"kitchen"),(4,2,2,"kitchen"),(5,3,3,"kitchen"),(8,4,3,"semi"),(7,5,None,"package")]:
        w.configure_product({"productId":pid,"bomId":bid,"kitchenId":kid,"kind":kind,"allocationStep":1})
    for wid in [1,2,3,4]:
        w.credit(1,wid,100,10000,"OPEN","IN")
        w.credit(2,wid,20,12000,"OPEN","IN")
    w.credit(6,5,100,5000,"PO-D","IN")
    return s


def action(s, name, data, actor=ADMIN):
    return execute(s, actor, name, data, NOW)[0]


def order(s, kind, pid, qty, store=6):
    o = action(s,"save_order",{"kind":kind,"customer":"Customer" if kind=="SO" else "","storeId":store,"orderDate":"2026-10-29","deliveryDate":"2026-10-31","lines":[{"productId":pid,"qty":qty,"price":50000}]})
    action(s,"confirm_order",{"id":o["id"]})
    return o


def complete(s, mo, qty, start="2026-10-30T20:00", finish="2026-10-31T09:55"):
    return action(s,"complete_mo",{"id":mo["id"],"actualQty":qty,"physicalStartedAt":start,"physicalFinishedAt":finish})
