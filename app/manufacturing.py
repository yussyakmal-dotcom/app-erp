"""Manufacturing commands over the existing inventory document.

Quantities use product base units. Callers apply a command to a private copy and
commit the complete document using the existing database version compare/swap.
No command writes a database or changes a caller's persistent state by itself.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
from zoneinfo import ZoneInfo
import hashlib
import json
import os
import uuid


class ManufacturingError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def require(condition, message, status=400):
    if not condition:
        raise ManufacturingError(message, status)


def quantity(value, positive=False):
    try:
        require(not isinstance(value, bool), "Jumlah harus berupa angka.")
        n = Decimal(str(value))
        require(n.is_finite() and n >= 0 and n <= Decimal("1000000000000"), "Jumlah harus angka terbatas dan tidak negatif.")
        n = n.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        require(not positive or n > 0, "Jumlah harus lebih dari nol.")
        return n
    except (InvalidOperation, TypeError, ValueError) as exc:
        if isinstance(exc, ManufacturingError):
            raise
        raise ManufacturingError("Jumlah tidak valid.") from exc


def number(value):
    return float(quantity(value))


def ident(value):
    try:
        require(not isinstance(value, bool) and str(int(value)) == str(value), "ID tidak valid.")
        return int(value)
    except (ValueError, TypeError) as exc:
        raise ManufacturingError("ID tidak valid.") from exc


def lookup(rows, key, label="Data", active=False):
    key = ident(key)
    result = next((r for r in rows if r.get("id") == key), None)
    require(result is not None, f"{label} tidak ditemukan.", 404)
    require(not active or result.get("isActive", True), f"{label} tidak aktif.")
    return result


def date_value(value):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date().isoformat()
    except (ValueError, TypeError) as exc:
        raise ManufacturingError("Tanggal harus YYYY-MM-DD.") from exc


def state_section(state):
    return state.setdefault("manufacturing", {
        "schemaVersion": 1, "settings": {"packingWarehouseId": None,
            "timezone": os.getenv("TZ", "Asia/Jakarta"),
            "sessions": [{"id": 1, "time": "08:00"}, {"id": 2, "time": "11:00"}, {"id": 3, "time": "14:00"}]},
        "orders": [], "plans": [], "requests": [], "allocations": [],
        "deliveries": [], "schedules": [], "commands": {},
    })


def next_id(state, key):
    seq = state.setdefault("seq", {})
    records = state.get("movements" if key == "mv" else key, [])
    seq[key] = max(int(seq.get(key, 0)), max((int(x["id"]) for x in records), default=0)) + 1
    return seq[key]


def make_record(state, key, prefix, now, actor):
    i = next_id(state, "mfg_" + key)
    return {"id": i, "no": f"{prefix}-{i:06d}", "createdAt": now,
            "createdBy": actor["username"]}


def allowed(actor, roles, warehouse=None):
    require(actor["role"] == "admin" or actor["role"] in roles, "Tidak memiliki akses untuk tindakan ini.", 403)
    require(actor["role"] == "admin" or not actor.get("warehouseId") or warehouse is None
            or actor["warehouseId"] == warehouse, "Gudang di luar lingkup akun Anda.", 403)


PLAN_ROLES = {"produksi", "purchasing", "approver", "gudang"}
EXEC_ROLES = {"produksi", "approver", "gudang", "packing"}
PACK_ROLES = {"packing", "gudang"}


class Workflow:
    def __init__(self, state, actor, now=None):
        self.s, self.actor = state, actor
        self.now = int(now if now is not None else datetime.now(timezone.utc).timestamp() * 1000)
        self.m = state_section(state)
        for key in ("productions", "batches", "movements", "reservations", "transfers", "scraps"):
            state.setdefault(key, [])

    def product(self, pid, active=True):
        return lookup(self.s.get("products", []), pid, "Produk", active)

    def warehouse(self, wid):
        return lookup(self.s.get("warehouses", []), wid, "Gudang", True)

    def kitchen(self, kid):
        k = lookup(self.s.get("kitchens", []), kid, "Dapur", True)
        warehouse = self.warehouse(k["warehouseId"])
        require(not warehouse.get("isCentral") and warehouse["id"] != self.m["settings"].get("packingWarehouseId"),
                "Gudang dapur harus terpisah dari Central dan Packing.")
        return k

    def packing(self):
        wid = self.m["settings"].get("packingWarehouseId")
        require(wid, "Tentukan Gudang Packing pada Pengaturan manufaktur.")
        return self.warehouse(wid)["id"]

    def zone(self):
        return ZoneInfo(self.m["settings"]["timezone"])

    def local_date(self):
        return datetime.fromtimestamp(self.now / 1000, self.zone()).date().isoformat()

    def scope(self, roles, warehouse=None):
        allowed(self.actor, roles, warehouse)

    def factor(self, p, unit):
        if unit == p["baseUom"]:
            return Decimal(1)
        item = next((x for x in p.get("uoms", []) if x["name"] == unit), None)
        require(item, f"Satuan {unit} tidak terdaftar pada {p['name']}.")
        return quantity(item["factor"], True)

    def recipe(self, p):
        config = p.get("manufacturing", {})
        require(config.get("kind") in {"kitchen", "semi", "package"}, f"Atur produksi untuk {p['name']} pada master produk.")
        candidates = [b for b in self.s.get("boms", []) if b.get("isActive", True) and b["productId"] == p["id"]]
        if config.get("bomId"):
            candidates = [b for b in candidates if b["id"] == config["bomId"]]
        require(len(candidates) == 1, f"Tentukan satu BOM utama untuk {p['name']} pada master produk.")
        bom = candidates[0]
        total = quantity(bom["yieldQty"], True) * self.factor(p, bom["yieldUom"])
        lines, seen = [], set()
        for line in bom.get("lines", []):
            cp = self.product(line["productId"])
            require(cp["id"] != p["id"] and cp["id"] not in seen, "BOM memuat bahan ganda atau produk itu sendiri.")
            seen.add(cp["id"])
            lines.append({"productId": cp["id"], "qty": float(quantity(line["qty"], True) * self.factor(cp, line["uom"])), "uom": cp["baseUom"]})
        require(lines, "BOM belum berisi bahan.")
        return {"id": bom["id"], "code": bom["code"], "yieldQty": float(total), "yieldUom": p["baseUom"], "lines": lines}

    def requirements(self, snapshot, qty):
        return [{"productId": l["productId"], "qty": number(quantity(l["qty"]) * quantity(qty) / quantity(snapshot["yieldQty"], True))} for l in snapshot["lines"]]

    def stock(self, pid, wid, free=True):
        total = Decimal(0)
        for b in self.s["batches"]:
            if b["productId"] == pid and b["warehouseId"] == wid:
                total += quantity(b["qty"]) - (self.reserved(b["id"]) if free else 0)
        return max(Decimal(0), total)

    def reserved(self, bid):
        return sum((quantity(r["qty"]) for r in self.s["reservations"]
                    if r["batchId"] == bid and r.get("expiresAt", self.now + 1) > self.now), Decimal(0))

    def picks(self, pid, wid, qty):
        remaining, picks = quantity(qty), []
        batches = sorted((b for b in self.s["batches"] if b["productId"] == pid and b["warehouseId"] == wid),
                         key=lambda b: (b.get("inboundAt", 0), b["id"]))
        for b in batches:
            take = min(remaining, max(Decimal(0), quantity(b["qty"]) - self.reserved(b["id"])))
            if take:
                picks.append({"batchId": b["id"], "batchNo": b.get("batchNo", ""), "qty": float(take),
                              "cost": b.get("cost", 0), "expDate": b.get("expDate"), "rack": b.get("rack", ""),
                              "inboundAt": b.get("inboundAt", self.now), "received": None})
                remaining -= take
            if not remaining:
                break
        require(not remaining, f"Stok {self.product(pid, False)['name']} di {self.warehouse(wid)['name']} kurang {remaining}. Stok tidak boleh minus.")
        return picks

    def movement(self, batch, qty, kind, ref):
        self.s["movements"].append({"id": next_id(self.s, "mv"), "ts": self.now, "type": kind,
            "productId": batch["productId"], "warehouseId": batch["warehouseId"], "batchId": batch["id"],
            "batchNo": batch.get("batchNo", ""), "qty": float(qty), "cost": batch.get("cost", 0),
            "ref": ref, "note": "", "user": self.actor["username"], "manufacturingVersion": 1})

    def consume(self, picks, kind, ref):
        cost = Decimal(0)
        for pk in picks:
            b = lookup(self.s["batches"], pk["batchId"], "Batch")
            q = quantity(pk["qty"])
            require(quantity(b["qty"]) - self.reserved(b["id"]) >= q, "Stok berubah atau telah direservasi. Muat ulang perhitungan.")
            b["qty"] = float(quantity(b["qty"]) - q)
            self.movement(b, -q, kind, ref)
            cost += q * quantity(b.get("cost", 0))
        return float(cost)

    def credit(self, pid, wid, qty, cost, ref, kind, batch_no="", exp=None, rack="", inbound_at=None):
        q = quantity(qty)
        if not q:
            return None
        b = {"id": next_id(self.s, "batches"), "productId": pid, "warehouseId": wid,
             "qty": float(q), "cost": number(cost), "batchNo": batch_no or ref,
             "expDate": exp, "rack": rack, "inboundAt": inbound_at or self.now, "createdAt": self.now}
        self.s["batches"].append(b)
        self.movement(b, q, kind, ref)
        return b

    def minimum(self, pid, wid):
        p, w = self.product(pid), self.warehouse(wid)
        return quantity(p.get("minimumByWarehouse", {}).get(str(wid), p.get("minCentral" if w.get("isCentral") else "minBranch", 0)))

    def save_settings(self, data):
        self.scope(set())
        wid = self.warehouse(data["packingWarehouseId"])["id"]
        require(not self.warehouse(wid).get("isCentral") and not any(k["warehouseId"] == wid and k.get("isActive", True) for k in self.s.get("kitchens", [])), "Packing harus berbeda dari Central dan dapur.")
        zone = str(data.get("timezone", "Asia/Jakarta"))
        try:
            ZoneInfo(zone)
        except (ValueError, KeyError) as exc:
            raise ManufacturingError("Zona waktu tidak dikenali.") from exc
        sessions = self.clean_sessions(data.get("sessions", self.m["settings"]["sessions"]))
        old = self.m["settings"].get("packingWarehouseId")
        require(not old or old == wid or not any(d["status"] == "siap" for d in self.m["deliveries"]), "Selesaikan DO aktif sebelum mengganti gudang Packing.")
        self.m["settings"] = {"packingWarehouseId": wid, "timezone": zone, "sessions": sessions}
        return self.m["settings"]

    def clean_sessions(self, sessions):
        require(isinstance(sessions, list) and len(sessions) == 3, "Isi tiga sesi pengiriman.")
        result = []
        for i, item in enumerate(sessions, 1):
            try:
                t = datetime.strptime(item["time"], "%H:%M").strftime("%H:%M")
            except (ValueError, KeyError, TypeError) as exc:
                raise ManufacturingError("Jam sesi harus HH:MM.") from exc
            result.append({"id": i, "time": t})
        return result

    def configure_product(self, data):
        self.scope(set())
        p = self.product(data["productId"])
        kind = data.get("kind")
        require(kind in {"purchased", "kitchen", "semi", "package"}, "Jenis produksi tidak valid.")
        config = {"kind": kind, "kitchenId": None, "bomId": None,
                  "allocationStep": number(quantity(data.get("allocationStep", 1), True))}
        if kind in {"kitchen", "semi"}:
            config["kitchenId"] = self.kitchen(data["kitchenId"])["id"]
        if kind != "purchased":
            bom = lookup(self.s.get("boms", []), data["bomId"], "BOM", True)
            require(bom["productId"] == p["id"], "BOM tidak sesuai dengan produk.")
            require(not bom.get("kitchenId") or bom["kitchenId"] == config["kitchenId"], "Dapur BOM berbeda dengan master produk.")
            config["bomId"] = bom["id"]
        p["manufacturing"] = config
        if kind != "purchased":
            self.recipe(p)
        return p

    def set_minimum(self, data):
        wid = self.warehouse(data["warehouseId"])["id"]
        self.scope({"produksi", "gudang", "packing"}, wid)
        p = self.product(data["productId"])
        p.setdefault("minimumByWarehouse", {})[str(wid)] = number(data["qty"])
        return p

    def order_lines(self, lines):
        require(isinstance(lines, list) and lines, "Tambahkan minimal satu SKU.")
        result, seen = [], set()
        for line in lines:
            p = self.product(line["productId"])
            require(p["id"] not in seen, "Gabungkan SKU yang sama dalam satu baris.")
            seen.add(p["id"])
            result.append({"id": len(result) + 1, "productId": p["id"], "qty": number(quantity(line["qty"], True)),
                           "uom": p["baseUom"], "price": number(line.get("price", 0))})
        return result

    def save_order(self, data):
        kind = data.get("kind")
        require(kind in {"RO", "SO"}, "Pilih RO atau SO.")
        wid = None
        if kind == "RO":
            wid = self.warehouse(data["storeId"])["id"]
            require(wid in self.stores(), "Tujuan RO harus gudang toko.")
            self.scope({"toko", "gudang", "produksi", "packing"}, wid if self.actor["role"] in {"toko", "gudang"} else None)
        else:
            self.scope({"sales"})
            require(str(data.get("customer", "")).strip(), "Nama customer wajib diisi.")
        packing = self.packing()
        if data.get("id"):
            order = lookup(self.m["orders"], data["id"], "Order")
            require(order["status"] == "draft" and order["kind"] == kind, "Hanya draft dengan jenis yang sama dapat diubah.")
            if kind == "RO" and self.actor.get("warehouseId"):
                self.scope({"toko", "gudang", "produksi", "packing"}, order["storeId"])
        else:
            order = make_record(self.s, "orders", kind, self.now, self.actor)
            self.m["orders"].append(order)
        order.update({"kind": kind, "status": "draft", "packingWarehouseId": packing, "storeId": wid,
                      "customer": str(data.get("customer", "")).strip()[:200], "sourceRef": str(data.get("sourceRef", ""))[:100],
                      "orderDate": date_value(data["orderDate"]), "deliveryDate": date_value(data["deliveryDate"]),
                      "lines": self.order_lines(data["lines"]), "note": str(data.get("note", ""))[:2000]})
        return order

    def confirm_order(self, data):
        o = lookup(self.m["orders"], data["id"], "Order")
        self.scope({"sales"} if o["kind"] == "SO" else {"toko", "gudang", "produksi", "packing"},
                   o["storeId"] if o["kind"] == "RO" and self.actor["role"] in {"toko", "gudang"} else None)
        require(o["status"] == "draft", "Order sudah dikonfirmasi atau dibatalkan.")
        for line in o["lines"]:
            p = self.product(line["productId"])
            if p.get("manufacturing", {}).get("kind") == "package":
                line["packageBom"] = self.recipe(p)
                require(not any(self.product(c["productId"]).get("manufacturing", {}).get("kind") == "package" for c in line["packageBom"]["lines"]), "Paket bertingkat belum didukung pada versi ini.")
        o.update(status="dikonfirmasi", confirmedAt=self.now)
        if o["kind"] == "SO":
            do = self.make_delivery(o, o["lines"])
            o["deliveryId"] = do["id"]
        return o

    def cancel_order(self, data):
        o = lookup(self.m["orders"], data["id"], "Order")
        self.scope({"sales"} if o["kind"] == "SO" else {"toko", "produksi", "gudang", "packing"},
                   o.get("storeId") if self.actor["role"] in {"toko", "gudang"} else None)
        require(not o.get("planId"), "Order sudah masuk rekap; selesaikan penyesuaian rencana dahulu.")
        for d in self.m["deliveries"]:
            if d["orderId"] == o["id"]:
                require(d["status"] == "siap", "DO sudah dikirim.")
                d["status"] = "batal"
        o["status"] = "batal"
        return o

    def create_plan(self, data):
        self.scope(PLAN_ROLES | {"packing"})
        ids = [ident(x) for x in data.get("orderIds", [])]
        require(ids and len(ids) == len(set(ids)), "Pilih order untuk direkap satu kali.")
        orders = [lookup(self.m["orders"], i, "Order") for i in ids]
        require(all(o["status"] == "dikonfirmasi" and not o.get("planId") for o in orders), "Order harus dikonfirmasi dan belum direkap.")
        day = date_value(data["deliveryDate"])
        require(all(o["deliveryDate"] == day for o in orders), "Gabungkan order dengan tanggal kirim yang sama.")
        plan = make_record(self.s, "plans", "REKAP", self.now, self.actor)
        plan.update({"deliveryDate": day, "productionDate": date_value(data["productionDate"]), "status": "direkap", "orderIds": ids, "requirements": []})
        for o in orders:
            o["planId"] = plan["id"]
            for line in o["lines"]:
                source = {"orderId": o["id"], "orderLineId": line["id"], "sourceKind": o["kind"]}
                if line.get("packageBom"):
                    plan["requirements"].append({**source, "productId": line["productId"], "qty": line["qty"], "kind": "package", "packageBom": deepcopy(line["packageBom"])})
                    for c in self.requirements(line["packageBom"], line["qty"]):
                        plan["requirements"].append({**source, **c, "kind": self.product(c["productId"]).get("manufacturing", {}).get("kind", "purchased"), "packageProductId": line["productId"]})
                else:
                    p = self.product(line["productId"])
                    plan["requirements"].append({**source, "productId": p["id"], "qty": line["qty"], "kind": p.get("manufacturing", {}).get("kind", "purchased")})
        self.m["plans"].append(plan)
        return plan

    def create_mo(self, data):
        p = self.product(data["productId"])
        cfg = p.get("manufacturing", {})
        kind = cfg.get("kind")
        require(kind in {"kitchen", "semi", "package"}, "Produk belum ditetapkan sebagai produksi/perakitan.")
        kitchen = self.kitchen(cfg["kitchenId"]) if kind != "package" else None
        wid = kitchen["warehouseId"] if kitchen else self.packing()
        self.scope(PLAN_ROLES if kitchen else PACK_ROLES, wid)
        q = number(quantity(data["qty"], True))
        snapshot = self.recipe(p)
        plan_id, source_links = None, []
        if data.get("planId"):
            plan = lookup(self.m["plans"], data["planId"], "Rekap")
            plan_id = plan["id"]
            require(not any(m.get("planId") == plan_id and m["productId"] == p["id"] for m in self.s["productions"] if m.get("manufacturingVersion")), "Satu rekap hanya memiliki satu MO per SKU; tidak membuat MO susulan.")
            source_links = [deepcopy(r) for r in plan["requirements"] if r["productId"] == p["id"]]
            require(source_links, "Produk tidak ada pada rekap.")
            require(quantity(q) == sum((quantity(r["qty"]) for r in source_links), Decimal(0)), "Jumlah MO harus sesuai total SKU dalam rekap.")
            if kind == "package":
                snapshots = [r["packageBom"] for r in source_links if r.get("packageBom")]
                require(snapshots and all(b == snapshots[0] for b in snapshots), "BOM paket pada sumber berbeda; selaraskan sebelum produksi.")
                snapshot = deepcopy(snapshots[0])
        mo = make_record(self.s, "mo", "MO", self.now, self.actor)
        mo["id"] = next_id(self.s, "productions")
        mo.update({"manufacturingVersion": 1, "kind": "dapur" if kitchen else "packing", "productId": p["id"],
            "kitchenId": kitchen["id"] if kitchen else None, "bomId": snapshot["id"], "bomSnapshot": snapshot,
            "sourceWarehouseId": wid, "targetWarehouseId": wid, "planId": plan_id, "sources": source_links,
            "scheduledDate": date_value(data["productionDate"]), "deliveryDate": date_value(data.get("deliveryDate", data["productionDate"])),
            "planQty": q, "planUom": p["baseUom"], "actualQty": None, "status": "terjadwal", "ingredientsUsed": [],
            "cogs": 0, "unitCost": 0, "note": str(data.get("note", ""))[:2000], "workOrder": None})
        if kitchen:
            wo = make_record(self.s, "wo", "WO", self.now, self.actor)
            wo.update(moId=mo["id"], qty=q, status="terjadwal")
            mo["workOrder"] = wo
        self.s["productions"].append(mo)
        return mo

    def create_plan_mos(self, data):
        self.scope(PLAN_ROLES | PACK_ROLES)
        plan = lookup(self.m["plans"], data["id"], "Rekap")
        mode = data.get("kind", "kitchen")
        require(mode in {"kitchen", "package"}, "Jenis MO tidak valid.")
        totals = defaultdict(Decimal)
        for r in plan["requirements"]:
            if (r["kind"] == "package") == (mode == "package") and r["kind"] in {"kitchen", "package"}:
                totals[r["productId"]] += quantity(r["qty"])
        made = []
        for pid, qty in totals.items():
            if any(m.get("planId") == plan["id"] and m["productId"] == pid for m in self.s["productions"] if m.get("manufacturingVersion")):
                continue
            made.append(self.create_mo({"productId": pid, "qty": str(qty), "planId": plan["id"], "productionDate": plan["productionDate"], "deliveryDate": plan["deliveryDate"]}))
        require(made, "Tidak ada SKU baru untuk dibuatkan MO. Bahan setengah jadi dibuat manual sesuai buffer.")
        return made

    def mo(self, key):
        mo = lookup(self.s["productions"], key, "MO")
        require(mo.get("manufacturingVersion") == 1, "Ini riwayat produksi lama. Adopsi jadwal lama sebelum memprosesnya.")
        return mo

    def physical_time(self, value):
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return dt.replace(tzinfo=self.zone()) if dt.tzinfo is None else dt.astimezone(self.zone())
        except (ValueError, TypeError) as exc:
            raise ManufacturingError("Isi tanggal dan jam pelaksanaan fisik.") from exc

    def check_shift(self, start, finish=None):
        t = start.time().replace(tzinfo=None)
        require(t >= time(20) or t <= time(10), "Produksi fisik dapur berlangsung pukul 20.00–10.00.")
        last_day = start.date() + timedelta(days=1) if t >= time(20) else start.date()
        end = datetime.combine(last_day, time(10), self.zone())
        if finish is not None:
            require(start <= finish <= end, "Waktu mulai dan selesai harus dalam satu shift 20.00–10.00.")

    def start_mo(self, data):
        mo = self.mo(data["id"])
        self.scope(EXEC_ROLES, mo["sourceWarehouseId"])
        require(mo["status"] == "terjadwal", "MO tidak dalam status terjadwal.")
        start = self.physical_time(data["physicalStartedAt"])
        if mo["kind"] == "dapur":
            self.check_shift(start)
            mo["workOrder"].update(status="diproses", physicalStartedAt=start.isoformat())
        mo.update(status="diproses", physicalStartedAt=start.isoformat(), startedAt=self.now, startedBy=self.actor["username"])
        return mo

    def cancel_mo(self, data):
        mo = self.mo(data["id"])
        self.scope(PLAN_ROLES | PACK_ROLES, mo["sourceWarehouseId"])
        require(mo["status"] == "terjadwal", "Hanya MO yang belum dilaksanakan dapat dibatalkan.")
        mo["status"] = "batal"
        if mo["workOrder"]:
            mo["workOrder"]["status"] = "batal"
        return mo

    def complete_mo(self, data):
        mo = self.mo(data["id"])
        self.scope(EXEC_ROLES, mo["sourceWarehouseId"])
        require(mo["status"] in {"terjadwal", "diproses"}, "MO sudah selesai atau dibatalkan.")
        start = self.physical_time(mo.get("physicalStartedAt") or data["physicalStartedAt"])
        finish = self.physical_time(data["physicalFinishedAt"])
        require(finish >= start, "Waktu selesai lebih awal dari mulai.")
        if mo["kind"] == "dapur":
            self.check_shift(start, finish)
        actual = quantity(data["actualQty"])
        planned = quantity(mo["workOrder"]["qty"] if mo["workOrder"] else mo["planQty"])
        # Assembly consumes the components actually assembled; kitchen WO is fixed.
        usage_qty = planned if mo["workOrder"] else actual
        require(mo["kind"] == "dapur" or actual > 0, "Jumlah paket harus lebih dari nol.")
        commitments = self.free_for_stores(include_negative=True) if mo["kind"] == "packing" else None
        inputs, cost = [], Decimal(0)
        for req in self.requirements(mo["bomSnapshot"], usage_qty):
            picks = self.picks(req["productId"], mo["sourceWarehouseId"], req["qty"])
            used_cost = self.consume(picks, "PROD_USAGE", mo["no"])
            cost += Decimal(str(used_cost))
            inputs.append({"productId": req["productId"], "qtyUsed": req["qty"], "uom": self.product(req["productId"], False)["baseUom"], "cogs": used_cost, "picks": picks})
        exp = data.get("expDate")
        exp = int(datetime.combine(datetime.strptime(date_value(exp), "%Y-%m-%d").date(), time(), self.zone()).timestamp() * 1000) if exp else None
        unit_cost = cost / actual if actual else Decimal(0)
        batch = self.credit(mo["productId"], mo["targetWarehouseId"], actual, unit_cost, mo["no"], "PROD_OUTPUT",
                            str(data.get("batchNo", ""))[:50], exp, str(data.get("rack", ""))[:50])
        if commitments is not None:
            after = self.free_for_stores(include_negative=True)
            require(all(q >= min(Decimal(0), commitments.get(pid, Decimal(0))) for pid, q in after.items()),
                    "Perakitan ini memakai komponen yang diprioritaskan untuk SO/DO lain.")
        mo.update(status="selesai", actualQty=float(actual), shortageQty=float(max(Decimal(0), planned-actual)),
            excessQty=float(max(Decimal(0), actual-planned)), cogs=float(cost), unitCost=float(unit_cost), ingredientsUsed=inputs,
            outputBatchId=batch["id"] if batch else None, batchNo=batch["batchNo"] if batch else "", expDate=exp,
            physicalStartedAt=start.isoformat(), physicalFinishedAt=finish.isoformat(), completedAt=self.now,
            completedBy=self.actor["username"], completionNote=str(data.get("note", ""))[:2000])
        if mo["workOrder"]:
            mo["workOrder"].update(status="selesai", physicalStartedAt=start.isoformat(), physicalFinishedAt=finish.isoformat())
        return mo

    def adopt_legacy(self, data):
        old = lookup(self.s["productions"], data["id"], "Jadwal lama")
        require(not old.get("manufacturingVersion") and old["status"] in {"terjadwal", "diproses"}, "Hanya jadwal lama yang belum selesai dapat diadopsi.")
        require(not old.get("ingredientsUsed"), "Jadwal lama sudah mencatat konsumsi; cocokkan histori sebelum adopsi.")
        p = self.product(old["productId"])
        bom = lookup(self.s.get("boms", []), old["bomId"], "BOM lama")
        mo = self.create_mo({"productId": p["id"], "qty": str(quantity(old["planQty"]) * self.factor(p, bom["yieldUom"])),
                             "productionDate": old["scheduledDate"], "note": "Adopsi " + old["no"]})
        old.update(status="batal", adoptedMoId=mo["id"], closedAt=self.now, closedBy=self.actor["username"])
        mo["legacyProductionId"] = old["id"]
        return mo

    def material_preview(self, data):
        k = self.kitchen(data["kitchenId"])
        self.scope(PLAN_ROLES, k["warehouseId"])
        plan_id = ident(data["planId"]) if data.get("planId") else None
        needs = defaultdict(Decimal)
        if plan_id:
            lookup(self.m["plans"], plan_id, "Rekap")
            for mo in self.s["productions"]:
                if mo.get("manufacturingVersion") and mo.get("planId") == plan_id and mo["kitchenId"] == k["id"] and mo["status"] in {"terjadwal", "diproses"}:
                    for line in self.requirements(mo["bomSnapshot"], mo["workOrder"]["qty"]):
                        needs[line["productId"]] += quantity(line["qty"])
        ids = set(needs) | {p["id"] for p in self.s.get("products", []) if p.get("isActive", True) and self.minimum(p["id"], k["warehouseId"]) > 0}
        ids |= {ident(x) for x in data.get("productIds", [])}
        lines = []
        for pid in sorted(ids):
            physical, free = self.stock(pid, k["warehouseId"], False), self.stock(pid, k["warehouseId"])
            minimum = self.minimum(pid, k["warehouseId"])
            incoming = sum((quantity(l["qty"]) for t in self.s["transfers"] if t["dstId"] == k["warehouseId"] and t["status"] == "dikirim" for l in t["lines"] if l["productId"] == pid), Decimal(0))
            lines.append({"productId": pid, "needQty": float(needs[pid]), "physicalQty": float(physical), "reservedQty": float(physical-free),
                          "availableQty": float(free), "incomingQty": float(incoming), "minimumQty": float(minimum),
                          "suggestedQty": float(max(Decimal(0), needs[pid] + minimum - free))})
        return {"kitchenId": k["id"], "warehouseId": k["warehouseId"], "planId": plan_id, "lines": lines}

    def save_request(self, data):
        preview = self.material_preview({**data, "productIds": [l["productId"] for l in data["lines"]]})
        lines = []
        requested = self.order_lines(data["lines"])
        for l in requested:
            row = next(x for x in preview["lines"] if x["productId"] == l["productId"])
            lines.append({**row, "qty": l["qty"], "uom": l["uom"]})
        if data.get("id"):
            r = lookup(self.m["requests"], data["id"], "Permintaan bahan")
            require(not r.get("transferId") and r["kitchenId"] == preview["kitchenId"] and r.get("planId") == preview["planId"], "Permintaan sudah diproses atau kelompoknya berubah.")
        else:
            require(not preview["planId"] or not any(r["kitchenId"] == preview["kitchenId"] and r.get("planId") == preview["planId"] for r in self.m["requests"]), "Rekap ini sudah mempunyai permintaan untuk dapur tersebut; ubah permintaan yang ada.")
            r = make_record(self.s, "requests", "BAHAN", self.now, self.actor)
            self.m["requests"].append(r)
        centrals = [w for w in self.s.get("warehouses", []) if w.get("isCentral") and w.get("isActive", True)]
        require(len(centrals) == 1, "Tentukan satu Gudang Central aktif.")
        r.update(kitchenId=preview["kitchenId"], warehouseId=preview["warehouseId"], planId=preview["planId"],
                 sourceWarehouseId=centrals[0]["id"], status="diminta", lines=lines, note=str(data.get("note", ""))[:2000])
        return r

    def new_transfer(self, source, dest, lines, ref):
        record = {"id": next_id(self.s, "transfers"), "no": f"TR-MFG-{uuid.uuid4().hex[:10].upper()}",
                  "transactionDate": self.local_date(), "srcId": source, "dstId": dest, "status": "draft",
                  "createdAt": self.now, "createdBy": self.actor["username"], "expiresAt": self.now + 24*3600000,
                  "ttlHours": 24, "shippedAt": None, "receivedAt": None, "printCount": 0, "fifoOverride": False,
                  "note": ref, "lines": [], "manufacturingVersion": 1}
        for line in lines:
            pid, q = line["productId"], number(line["qty"])
            record["lines"].append({"productId": pid, "qty": q, "uom": self.product(pid, False)["baseUom"], "uomQty": q,
                                    "picks": self.picks(pid, source, q)})
        self.s["transfers"].append(record)
        return record

    def prepare_request(self, data):
        r = lookup(self.m["requests"], data["id"], "Permintaan bahan")
        self.scope({"gudang"}, r["sourceWarehouseId"])
        require(not r.get("transferId"), "Picking/transfer sudah dibuat untuk permintaan ini.")
        t = self.new_transfer(r["sourceWarehouseId"], r["warehouseId"], r["lines"], r["no"])
        t["materialRequestId"] = r["id"]
        for l in t["lines"]:
            for pk in l["picks"]:
                self.s["reservations"].append({"id": next_id(self.s, "reservations"), "transferId": t["id"],
                    "batchId": pk["batchId"], "qty": pk["qty"], "expiresAt": t["expiresAt"]})
        r.update(transferId=t["id"], status="dipicking")
        return t

    def ship_transfer(self, data):
        t = lookup(self.s["transfers"], data["id"], "Transfer")
        require(t.get("manufacturingVersion") and t.get("materialRequestId"), "Bukan transfer permintaan manufaktur.")
        self.scope({"gudang"}, t["srcId"])
        require(t["status"] == "draft", "Transfer tidak dalam status draft.")
        # Re-pick at shipment, including when a previous draft reservation expired.
        self.s["reservations"] = [r for r in self.s["reservations"] if r.get("transferId") != t["id"]]
        for l in t["lines"]:
            l["picks"] = self.picks(l["productId"], t["srcId"], l["qty"])
            self.consume(l["picks"], "TRF_OUT", t["no"])
        t.update(status="dikirim", shippedAt=self.now, shippedBy=self.actor["username"])
        lookup(self.m["requests"], t["materialRequestId"])["status"] = "dikirim"
        return t

    def cancel_transfer(self, data):
        t = lookup(self.s["transfers"], data["id"], "Transfer")
        require(t.get("manufacturingVersion") and t.get("materialRequestId") and t["status"] == "draft", "Hanya draft picking bahan yang dapat dibatalkan.")
        self.scope({"gudang"}, t["srcId"])
        self.s["reservations"] = [r for r in self.s["reservations"] if r.get("transferId") != t["id"]]
        t.update(status="batal", closedAt=self.now)
        r = lookup(self.m["requests"], t["materialRequestId"])
        r.setdefault("previousTransferIds", []).append(t["id"])
        r.pop("transferId", None)
        r["status"] = "diminta"
        return t

    def receive_transfer(self, data):
        t = lookup(self.s["transfers"], data["id"], "Transfer")
        require(t.get("manufacturingVersion") and t["status"] == "dikirim", "Transfer tidak sedang dikirim.")
        self.scope({"gudang", "produksi", "toko", "packing"}, t["dstId"])
        rec = data.get("received")
        short = []
        for i, l in enumerate(t["lines"]):
            for j, pk in enumerate(l["picks"]):
                q = quantity(rec[i][j] if rec is not None else pk["qty"])
                pk["received"] = float(q)
                self.credit(l["productId"], t["dstId"], q, pk["cost"], t["no"], "TRF_IN", pk["batchNo"], pk["expDate"], inbound_at=pk["inboundAt"])
                if q < quantity(pk["qty"]):
                    short.append({"productId": l["productId"], "batchId": None, "batchNo": pk["batchNo"], "qty": float(quantity(pk["qty"])-q), "cost": pk["cost"]})
        t.update(status="diterima", receivedAt=self.now, receivedBy=self.actor["username"])
        if short:
            sc = {"id": next_id(self.s, "scraps"), "no": "BS-" + t["no"], "transactionDate": self.local_date(),
                  "warehouseId": t["dstId"], "status": "draft", "source": "transit", "reason": "Selisih kurang transit " + t["no"],
                  "deductOnApprove": False, "ref": t["no"], "createdAt": self.now, "createdBy": self.actor["username"],
                  "approvedBy": None, "approvedAt": None, "lines": short}
            self.s["scraps"].append(sc)
            t["scrapNo"] = sc["no"]
        if t.get("materialRequestId"):
            lookup(self.m["requests"], t["materialRequestId"])["status"] = "diterima"
        if t.get("deliveryId"):
            lookup(self.m["deliveries"], t["deliveryId"])["status"] = "diterima"
        return t

    def direct_to_packing(self, data):
        k = self.kitchen(data["kitchenId"])
        self.scope(EXEC_ROLES, k["warehouseId"])
        t = self.new_transfer(k["warehouseId"], self.packing(), self.order_lines(data["lines"]), "Dapur → Packing satu langkah")
        for l in t["lines"]:
            self.consume(l["picks"], "TRF_OUT", t["no"])
            for pk in l["picks"]:
                self.credit(l["productId"], t["dstId"], pk["qty"], pk["cost"], t["no"], "TRF_IN", pk["batchNo"], pk["expDate"], inbound_at=pk["inboundAt"])
                pk["received"] = pk["qty"]
        t.update(status="diterima", shippedAt=self.now, receivedAt=self.now, shippedBy=self.actor["username"], receivedBy=self.actor["username"], direct=True)
        return t

    def stores(self):
        excluded = {k["warehouseId"] for k in self.s.get("kitchens", [])}
        excluded.add(self.m["settings"].get("packingWarehouseId"))
        return [w["id"] for w in self.s.get("warehouses", []) if w.get("isActive", True) and not w.get("isCentral") and w["id"] not in excluded]

    def save_schedule(self, data):
        self.scope(PACK_ROLES, self.packing())
        day = date_value(data["date"])
        sessions = self.clean_sessions(data["sessions"])
        stores = self.stores()
        rows = [{"storeId": ident(r["storeId"]), "sessionId": ident(r["sessionId"])} for r in data["stores"]]
        require(sorted(r["storeId"] for r in rows) == sorted(stores) and all(r["sessionId"] in {1, 2, 3} for r in rows), "Jadwalkan setiap toko sekali pada salah satu dari tiga sesi.")
        schedule = {"date": day, "sessions": sessions, "stores": rows}
        self.m["schedules"] = [s for s in self.m["schedules"] if s["date"] != day] + [schedule]
        for d in self.m["deliveries"]:
            if d["status"] == "siap" and d["deliveryDate"] == day and d["kind"] == "RO":
                d["sessionId"] = next(r["sessionId"] for r in rows if r["storeId"] == d["storeId"])
        return schedule

    def make_delivery(self, order, lines):
        d = make_record(self.s, "deliveries", "DO", self.now, self.actor)
        schedule = next((s for s in self.m["schedules"] if s["date"] == order["deliveryDate"]), None)
        session = next((r["sessionId"] for r in schedule["stores"] if r["storeId"] == order["storeId"]), 1) if schedule else 1
        d.update({"orderId": order["id"], "kind": order["kind"], "storeId": order["storeId"], "customer": order["customer"],
                  "warehouseId": order["packingWarehouseId"], "deliveryDate": order["deliveryDate"], "sessionId": session,
                  "status": "siap", "lines": [deepcopy(l) for l in lines], "printCount": 0})
        self.m["deliveries"].append(d)
        return d

    def free_for_stores(self, exclude_plan=None, exclude_delivery=None, include_negative=False):
        wid = self.packing()
        pool = {p["id"]: self.stock(p["id"], wid) for p in self.s.get("products", [])}
        # First protect full SO demand. For unassembled packs, hold their components.
        for d in sorted(self.m["deliveries"], key=lambda x: (x["deliveryDate"], x["id"])):
            if d["status"] != "siap" or d["kind"] != "SO" or d["warehouseId"] != wid:
                continue
            for l in d["lines"]:
                pid, q = l["productId"], quantity(l["qty"])
                if l.get("packageBom"):
                    stocked = min(max(Decimal(0), pool.get(pid, Decimal(0))), q)
                    pool[pid] = pool.get(pid, Decimal(0)) - stocked
                    for c in self.requirements(l["packageBom"], q-stocked):
                        pool[c["productId"]] = pool.get(c["productId"], Decimal(0)) - quantity(c["qty"])
                else:
                    pool[pid] = pool.get(pid, Decimal(0)) - q
        for d in self.m["deliveries"]:
            if d["status"] != "siap" or d["kind"] != "RO" or d["id"] == exclude_delivery:
                continue
            order = lookup(self.m["orders"], d["orderId"])
            if exclude_plan and order.get("planId") == exclude_plan:
                continue
            for l in d["lines"]:
                pool[l["productId"]] = pool.get(l["productId"], Decimal(0)) - quantity(l["qty"])
        return pool if include_negative else {pid: max(Decimal(0), q) for pid, q in pool.items()}

    def allocation_preview(self, data):
        self.scope(PACK_ROLES, self.packing())
        plan = lookup(self.m["plans"], data["planId"], "Rekap")
        pool = self.free_for_stores(exclude_plan=plan["id"])
        grouped = defaultdict(list)
        for o in self.m["orders"]:
            if o.get("planId") == plan["id"] and o["kind"] == "RO" and o["status"] == "dikonfirmasi":
                for l in o["lines"]:
                    grouped[l["productId"]].append({"orderId": o["id"], "orderLineId": l["id"], "storeId": o["storeId"], "productId": l["productId"], "requestedQty": l["qty"]})
        lines = []
        for pid, rows in grouped.items():
            step = quantity(self.product(pid, False).get("manufacturing", {}).get("allocationStep", 1), True)
            total = sum((quantity(r["requestedQty"]) for r in rows), Decimal(0))
            distributable = min(pool.get(pid, Decimal(0)), total)
            units = (distributable / step).to_integral_value(rounding=ROUND_DOWN)
            assigned, parts = Decimal(0), []
            for row in rows:
                exact = units * quantity(row["requestedQty"]) / total
                whole = exact.to_integral_value(rounding=ROUND_DOWN)
                assigned += whole
                parts.append([row, whole, exact-whole])
            for entry in sorted(parts, key=lambda x: (-x[2], x[0]["orderId"], x[0]["orderLineId"]))[:int(units-assigned)]:
                entry[1] += 1
            for row, whole, _ in parts:
                lines.append({**row, "suggestedQty": float(whole*step), "qty": float(whole*step), "availableForStores": float(pool.get(pid, 0)), "step": float(step)})
        return {"planId": plan["id"], "lines": lines}

    def validate_allocation(self, plan_id, lines):
        preview = self.allocation_preview({"planId": plan_id})
        expected = {(x["orderId"], x["orderLineId"]): x for x in preview["lines"]}
        require(len(lines) == len(expected), "Isi alokasi setiap baris RO pada rekap.")
        seen, totals, cleaned = set(), defaultdict(Decimal), []
        for row in lines:
            key = (ident(row["orderId"]), ident(row["orderLineId"]))
            require(key in expected and key not in seen, "Baris alokasi tidak valid atau ganda.")
            seen.add(key)
            original = expected[key]
            q = quantity(row["qty"])
            totals[original["productId"]] += q
            cleaned.append({**original, "qty": float(q)})
        free = self.free_for_stores(exclude_plan=plan_id)
        for pid, qty in totals.items():
            require(qty <= free.get(pid, 0), f"Alokasi {self.product(pid, False)['name']} melebihi sisa setelah prioritas SO.")
        return cleaned

    def save_allocation(self, data):
        pid = ident(data["planId"])
        old = next((a for a in self.m["allocations"] if a["planId"] == pid), None)
        require(not old or not old.get("deliveryIds"), "DO toko sudah dibuat; alokasi tidak dapat diubah lagi.")
        lines = self.validate_allocation(pid, data["lines"])
        a = old or make_record(self.s, "allocations", "ALOKASI", self.now, self.actor)
        if not old:
            self.m["allocations"].append(a)
        a.update(planId=pid, lines=lines, updatedAt=self.now, updatedBy=self.actor["username"])
        return a

    def create_store_deliveries(self, data):
        self.scope(PACK_ROLES, self.packing())
        a = lookup(self.m["allocations"], data["id"], "Alokasi")
        require(not a.get("deliveryIds"), "DO toko untuk alokasi ini sudah dibuat.")
        a["lines"] = self.validate_allocation(a["planId"], a["lines"])
        result = []
        orders = [o for o in self.m["orders"] if o.get("planId") == a["planId"]]
        require(all(o.get("deliveryId") for o in orders if o["kind"] == "SO"), "Siapkan DO SO terlebih dahulu.")
        for o in orders:
            if o["kind"] != "RO":
                continue
            lines = []
            for l in o["lines"]:
                row = next(x for x in a["lines"] if x["orderId"] == o["id"] and x["orderLineId"] == l["id"])
                if quantity(row["qty"]):
                    lines.append({**l, "qty": row["qty"]})
            if lines:
                result.append(self.make_delivery(o, lines))
        require(result, "Tidak ada alokasi positif untuk dikirim.")
        a["deliveryIds"] = [d["id"] for d in result]
        return result

    def assign_delivery(self, data):
        d = lookup(self.m["deliveries"], data["id"], "DO")
        self.scope(PACK_ROLES, d["warehouseId"])
        require(d["status"] == "siap", "DO sudah dikirim.")
        session = ident(data["sessionId"])
        require(session in {1, 2, 3}, "Pilih sesi 1–3.")
        d["sessionId"] = session
        return d

    def ship_delivery(self, data):
        d = lookup(self.m["deliveries"], data["id"], "DO")
        self.scope(PACK_ROLES, d["warehouseId"])
        require(d["status"] == "siap", "DO sudah dikirim atau dibatalkan.")
        order = lookup(self.m["orders"], d["orderId"])
        if d["kind"] == "SO":
            require([(l["productId"], l["qty"]) for l in d["lines"]] == [(l["productId"], l["qty"]) for l in order["lines"]], "DO SO harus sama dengan SO.")
        else:
            free = self.free_for_stores(exclude_delivery=d["id"])
            require(all(quantity(l["qty"]) <= free.get(l["productId"], 0) for l in d["lines"]), "Stok sisa setelah prioritas SO tidak cukup untuk DO toko.")
        if d["kind"] == "RO":
            t = self.new_transfer(d["warehouseId"], d["storeId"], d["lines"], d["no"])
            t.update(deliveryId=d["id"], status="dikirim", shippedAt=self.now, shippedBy=self.actor["username"])
            d["transferId"] = t["id"]
            for l in t["lines"]:
                self.consume(l["picks"], "TRF_OUT", t["no"])
        else:
            for l in d["lines"]:
                self.consume(self.picks(l["productId"], d["warehouseId"], l["qty"]), "DELIVERY_OUT", d["no"])
        d.update(status="dikirim", shippedAt=self.now, shippedBy=self.actor["username"])
        if d["kind"] == "SO":
            order["status"] = "dipenuhi"
        return d


COMMANDS = {name for name in (
    "save_settings", "configure_product", "set_minimum", "save_order", "confirm_order", "cancel_order",
    "create_plan", "create_mo", "create_plan_mos", "start_mo", "complete_mo", "cancel_mo", "adopt_legacy",
    "save_request", "prepare_request", "ship_transfer", "cancel_transfer", "receive_transfer", "direct_to_packing",
    "save_schedule", "save_allocation", "create_store_deliveries", "assign_delivery", "ship_delivery")}


def execute(state, actor, action, data, now=None):
    require(action in COMMANDS, "Tindakan manufaktur tidak dikenal.")
    require(isinstance(data, dict), "Payload harus berupa objek.")
    w = Workflow(state, actor, now)
    try:
        result = getattr(w, action)(data)
    except (KeyError, IndexError, TypeError) as exc:
        raise ManufacturingError("Isian tindakan belum lengkap atau formatnya salah.") from exc
    event = {"timestamp": datetime.fromtimestamp(w.now/1000, timezone.utc).isoformat(), "user_id": actor["username"],
             "role": actor["role"], "action": "MFG_" + action.upper(), "endpoint": "/api/manufacturing/commands",
             "payload_before": None, "payload_after": deepcopy(result), "source": "server"}
    state.setdefault("audit", []).insert(0, event)
    state["audit"] = state["audit"][:3000]
    validate_stock(state, w.now)
    return result, event


def preview(state, actor, action, data):
    require(action in {"material_preview", "allocation_preview"}, "Pratinjau tidak dikenal.")
    try:
        return getattr(Workflow(state, actor), action)(data)
    except (KeyError, IndexError, TypeError) as exc:
        raise ManufacturingError("Isian pratinjau belum lengkap.") from exc


def validate_stock(state, now=None):
    require(isinstance(state, dict), "State harus berupa objek.")
    now = now if now is not None else datetime.now(timezone.utc).timestamp()*1000
    batches = state.get("batches", [])
    require(isinstance(batches, list), "Daftar stok tidak valid.")
    seen = set()
    for b in batches:
        require(isinstance(b, dict) and "id" in b and "qty" in b, "Batch tidak valid.")
        require(b["id"] not in seen, "ID batch ganda.")
        seen.add(b["id"])
        quantity(b["qty"])
        quantity(b.get("cost", 0))
    reserved = defaultdict(Decimal)
    for r in state.get("reservations", []):
        q = quantity(r["qty"])
        if r.get("expiresAt", now+1) > now:
            reserved[r["batchId"]] += q
    for b in batches:
        require(reserved[b["id"]] <= quantity(b["qty"]), "Stok tersisa lebih kecil dari reservasi aktif.")
    require(all(not q or bid in seen for bid, q in reserved.items()), "Reservasi menunjuk batch yang tidak ada.")


def validate_legacy_write(before, after, actor):
    """Keep old inventory writes compatible without bypassing server commands."""
    validate_stock(after)
    if before is None:
        allowed(actor, set())
        require(not after.get("manufacturing"), "Inisialisasi manufaktur melalui API perintah.")
        return
    validate_stock_delta(before, after)
    require(before.get("manufacturing") == after.get("manufacturing"), "Gunakan tindakan manufaktur untuk mengubah dokumennya.")
    require(before.get("productions", []) == after.get("productions", []), "Produksi harus dicatat melalui API manufaktur.")
    for old in before.get("transfers", []):
        if old.get("manufacturingVersion"):
            new = next((x for x in after.get("transfers", []) if x.get("id") == old["id"]), None)
            # Printing does not change business state. Draft reservation expiry
            # is handled by the command path, not by the old browser sweep.
            require(new is not None and {k:v for k,v in new.items() if k != "printCount"} == {k:v for k,v in old.items() if k != "printCount"}, "Transfer manufaktur harus diproses melalui server.")
    old_transfers = {t["id"]: t for t in before.get("transfers", [])}
    packing = before.get("manufacturing", {}).get("settings", {}).get("packingWarehouseId")
    kitchen_warehouses = {k["warehouseId"] for k in before.get("kitchens", [])}
    for new in after.get("transfers", []):
        old = old_transfers.get(new["id"])
        require(not new.get("manufacturingVersion") or old is not None, "Transfer manufaktur baru dibuat melalui server.")
        if old != new and not new.get("manufacturingVersion") and packing:
            require(not (new["dstId"] == packing and new["srcId"] in kitchen_warehouses), "Gunakan transfer Dapur → Packing satu langkah pada Manufaktur.")
            require(not (new["srcId"] == packing and new["status"] == "dikirim"), "Pengiriman dari Packing harus melalui DO pada Manufaktur.")
    before_products = {p["id"]: p for p in before.get("products", [])}
    after_products = {p["id"]: p for p in after.get("products", [])}
    for pid in set(before_products) | set(after_products):
        a, b = before_products.get(pid, {}), after_products.get(pid, {})
        require(a.get("manufacturing") == b.get("manufacturing") and a.get("minimumByWarehouse") == b.get("minimumByWarehouse"), "Konfigurasi produksi/minimum diubah melalui tindakan manufaktur.")
    if actor["role"] == "admin":
        return
    permissions = {
        "purchasing": {"pos", "suppliers", "audit", "seq", "leadHistory"},
        "gudang": {"batches", "reservations", "transfers", "scraps", "movements", "inbounds", "usages", "opnames", "pos", "leadHistory", "audit", "seq"},
        "approver": {"batches", "scraps", "movements", "opnames", "audit", "seq"},
        "packing": {"batches", "reservations", "transfers", "movements", "inbounds", "pos", "leadHistory", "audit", "seq"},
    }
    for key in set(before) | set(after):
        if before.get(key) != after.get(key):
            require(key in permissions.get(actor["role"], set()), "Peran tidak boleh mengubah " + key + ".", 403)
    if actor.get("warehouseId"):
        previous = {b["id"]: b for b in before.get("batches", [])}
        current = {b["id"]: b for b in after.get("batches", [])}
        for bid in set(previous) | set(current):
            old, new = previous.get(bid), current.get(bid)
            if old != new:
                require(all(b is None or b["warehouseId"] == actor["warehouseId"] for b in (old, new)), "Stok di luar lingkup gudang akun.", 403)


def command_digest(action, data):
    return hashlib.sha256(json.dumps([action, data], sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate_stock_delta(before, after):
    """Reconcile legacy writes at product/warehouse level, including rack moves.

    Historical movements can contain opening balances and imported usage. They
    remain unchanged; only the proposed delta is reconciled against new entries.
    """
    old = before.get("movements", [])
    new = after.get("movements", [])
    require(isinstance(new, list) and new[:len(old)] == old, "Riwayat pergerakan stok tidak boleh diubah atau dihapus.")
    ids = {m["id"] for m in old}
    changes, booked = defaultdict(Decimal), defaultdict(Decimal)
    for sign, state in [(-1, before), (1, after)]:
        for b in state.get("batches", []):
            changes[(b["productId"], b["warehouseId"])] += sign * quantity(b["qty"])
    for m in new[len(old):]:
        require(isinstance(m, dict) and {"id", "productId", "warehouseId", "qty"}.issubset(m), "Catatan pergerakan stok tidak lengkap.")
        require(m["id"] not in ids, "ID pergerakan stok ganda.")
        ids.add(m["id"])
        try:
            q = Decimal(str(m["qty"]))
            require(q.is_finite(), "Jumlah pergerakan tidak valid.")
            q = q.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        except InvalidOperation as exc:
            raise ManufacturingError("Jumlah pergerakan tidak valid.") from exc
        booked[(m["productId"], m["warehouseId"])] += q
    require(all(changes[k] == booked[k] for k in set(changes) | set(booked)),
            "Perubahan stok tidak sesuai catatan pergerakan. Muat ulang dan ulangi transaksi.")
