'use strict';
/* Manufacturing UI uses the same products, stock and session as inventory. */
let mfBusy = false;
const mfState = () => S.manufacturing || {settings: {packingWarehouseId: null, timezone: 'Asia/Jakarta', sessions: [{id:1,time:'08:00'},{id:2,time:'11:00'},{id:3,time:'14:00'}]}, orders: [], plans: [], requests: [], allocations: [], deliveries: [], schedules: []};
const mfConfig = p => p?.manufacturing || {kind:'purchased', kitchenId:null, bomId:null, allocationStep:1};
const mfKinds = {purchased:'Beli / bahan', kitchen:'Produk dapur', semi:'Setengah jadi', package:'Paket Packing'};
const mfCan = (roles, wid) => ME?.role === 'admin' || roles.includes(ME?.role) && (!wid || !ME.warehouseId || ME.warehouseId === +wid);
const mfPlanRoles = ['produksi','purchasing','approver','gudang'];
const mfPackRoles = ['packing','gudang'];
const mfExecRoles = ['produksi','approver','gudang','packing'];
const mfDateTime = value => new Intl.DateTimeFormat('sv-SE', {timeZone:mfState().settings.timezone, year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(value ? new Date(value) : new Date()).replace(' ', 'T');
const mfToday = () => mfDateTime().slice(0,10);
const mfPlusDay = n => { const d = new Date(mfToday()+'T12:00:00Z'); d.setUTCDate(d.getUTCDate()+n); return d.toISOString().slice(0,10); };
const mfPendingKey = () => `mfg-command-${ME?.id}`;
const mfPending = () => { try { return JSON.parse(sessionStorage.getItem(mfPendingKey()) || 'null'); } catch { return null; } };

async function mfFlush() {
  clearTimeout(saveTimer);
  for (let i=0; saving && i<250; i++) await new Promise(r=>setTimeout(r,20));
  if (dirty && await flush() === false) fail('Perubahan inventori belum tersimpan. Periksa pesan sebelumnya dan ulangi tindakan.');
  if (saving || dirty) fail('Tunggu perubahan inventori tersimpan sebelum melanjutkan.');
}
async function mfCommand(action, data) {
  if (mfBusy) fail('Tindakan sedang diproses.');
  data = clone(data);
  mfBusy = true;
  try {
    await mfFlush();
    let pending = mfPending();
    const signature = JSON.stringify([action,data]);
    if (pending && pending.signature !== signature) fail('Masih ada tindakan yang belum mendapat jawaban. Klik Periksa tindakan terakhir di halaman Manufaktur.');
    pending ||= {signature, action, data:clone(data), version:VER, requestId:crypto.randomUUID()};
    sessionStorage.setItem(mfPendingKey(), JSON.stringify(pending));
    const response = await api('POST','/api/manufacturing/commands', pending);
    const {users,currentUserId,ui} = S;
    S = {...response.data,users,currentUserId,ui}; VER = response.version;
    sessionStorage.removeItem(mfPendingKey()); setSync('ok');
    return response.result;
  } catch (e) {
    if (e.status && e.status < 500) sessionStorage.removeItem(mfPendingKey());
    if (e.status === 409) { await pullState(); render(); }
    throw e;
  } finally { mfBusy = false; }
}
async function mfPreview(action, data) {
  await mfFlush();
  const r = await api('POST','/api/manufacturing/preview',{action,data});
  if (r.version !== VER) await pullState();
  return r.result;
}
async function mfSave(action,data,message) {
  const result=await mfCommand(action,data); closeModal(); render(); toast(message || 'Tersimpan.'); return result;
}
A.mfRetry = async () => { const p=mfPending(); if(p) await mfSave(p.action,p.data,'Tindakan terakhir sudah dipastikan tersimpan satu kali.'); };
document.addEventListener('click',e=>{
  if(mfBusy && e.target.closest('[data-act]')){e.preventDefault();e.stopImmediatePropagation();toast('Tunggu tindakan selesai.');}
},true);

Object.assign(ROLES, {
  produksi:{label:'Admin / petugas produksi',perms:['mfg.plan','mfg.exec']},
  sales:{label:'Admin Sales',perms:[]},
  packing:{label:'Petugas Packing',perms:['mfg.plan','mfg.exec','inbound','transfer']},
  toko:{label:'Petugas toko',perms:[]}
});
PAGES.manufacturing = ['Manufaktur & Packing','Operasional'];
PAGES.mfgconfig = ['Konfigurasi produksi','Master data'];
PAGE_ICON.mfgconfig='recipe';
const mfInput=(path,value,type='text',extra='')=>`<input type="${type}" data-bind="${path}" value="${esc(value??'')}" ${extra}>`;
const mfSelect=(path,value,rows,extra='')=>`<select data-bind="${path}" ${extra}>${opt('','Pilih',value)}${rows.map(([id,label])=>opt(id,label,value)).join('')}</select>`;
const mfProducts=()=>actP().map(p=>[p.id,`${p.code} · ${p.name} (${p.baseUom})`]);
const mfKitchenSelect=(path,value)=>mfSelect(path,value,actKT().map(k=>[k.id,k.name]));
const mfPlanSelect=(path,value)=>mfSelect(path,value,mfState().plans.map(p=>[p.id,`${p.no} · kirim ${p.deliveryDate}`]));
const mfToolbar=html=>`<div class="toolbar">${html}</div>`;
const mfBody=(title,html)=>`<section class="panel"><header class="ph"><h3>${esc(title)}</h3></header>${html}</section>`;
const mfFoot=(act,label='Simpan')=>()=>`${btn('Batal','closeModal')}${btn(label,act,{}, {k:'pri'})}`;
const mfModal=(title,body,act,label)=>openModal({title,wide:true,body,foot:mfFoot(act,label)});
const mfStatus=o=>chip(o.status, ['selesai','diterima'].includes(o.status)?'ok':o.status==='batal'?'mute':'info');
const mfLabel=pid=>`${P(pid)?.name || '#'+pid} (${P(pid)?.baseUom || ''})`;
const mfStores=()=>actW().filter(w=>!w.isCentral && w.id!==mfState().settings.packingWarehouseId && !actKT().some(k=>k.warehouseId===w.id));
const mfScopeWarehouses=()=>actW().filter(w=>mfCan(['produksi','gudang','packing'],w.id));
const mfLineTable=(key,withPrice=false)=>tbl(['Produk','Jumlah'+(withPrice?' pesanan':''),...(withPrice?['Harga jual per unit']:[]),''],F[key].lines.map((l,i)=>`<tr><td>${mfSelect(`${key}.lines.${i}.productId`,l.productId,mfProducts())}</td><td>${mfInput(`${key}.lines.${i}.qty`,l.qty,'number','min="0" step="any" aria-label="Jumlah"')}</td>${withPrice?`<td>${mfInput(`${key}.lines.${i}.price`,l.price??0,'number','min="0" step="any" aria-label="Harga jual per unit"')}</td>`:''}<td>${btn('Hapus','mfLineRemove',{key,i},{k:'sm'})}</td></tr>`),{cls:'edit'});
A.mfLineAdd=d=>{ F[d.key].lines.push({productId:'',qty:'',price:'0'}); refresh(); };
A.mfLineRemove=d=>{ F[d.key].lines.splice(+d.i,1); refresh(); };

V.manufacturing=()=>{
  const tab=F.mfTab||'orders';
  const tabs=[['orders','RO / SO'],['plans','Rekap'],['mos','MO / WO'],['materials','Bahan dapur'],['packing','Packing / DO'],['schedule','Jadwal kirim'],['history','Riwayat lama']];
  const nav=mfToolbar(seg('mfTab',tab,tabs)+btn('Master produksi','go',{page:'mfgconfig'}));
  const alert=!mfState().settings.packingWarehouseId?`<div class="alert info">${ic('info')}Tentukan Gudang Packing dan konfigurasi produk pada Master produksi sebelum membuat order.</div>`:'';
  const pending=mfPending()?mfToolbar(btn('Periksa tindakan terakhir','mfRetry',{}, {k:'pri'})):'';
  return nav+alert+pending+({orders:mfOrdersView,plans:mfPlansView,mos:mfMosView,materials:mfMaterialsView,packing:mfPackingView,schedule:mfScheduleView,history:mfHistoryView}[tab]||mfOrdersView)();
};

function mfOrdersView() {
  const rows=mfState().orders.filter(o=>ME.role!=='toko'||o.storeId===ME.warehouseId).slice().reverse();
  return mfToolbar((mfCan(['toko','gudang','produksi','packing'])?btn('RO toko','mfNewOrder',{kind:'RO'},{k:'pri'}):'')+(mfCan(['sales'])?btn('Sales Order','mfNewOrder',{kind:'SO'},{k:'pri'}):''))
    +tbl(['Nomor','Pemesan','Tgl order / kirim','SKU','Status',''],rows.map(o=>`<tr><td>${esc(o.no)}</td><td>${esc(o.kind==='RO'?W(o.storeId)?.name:o.customer)}</td><td>${esc(o.orderDate)} / ${esc(o.deliveryDate)}</td><td>${o.lines.map(l=>`${esc(mfLabel(l.productId))}: ${num(l.qty)}`).join('<br>')}</td><td>${mfStatus(o)}${o.planId?`<div class="sub">${esc(mfState().plans.find(p=>p.id===o.planId)?.no)}</div>`:''}</td><td class="acts">${btn('Lihat','mfOrderDetail',{id:o.id},{k:'sm'})}${o.status==='draft'?btn('Ubah','mfNewOrder',{kind:o.kind,id:o.id},{k:'sm'})+btn('Konfirmasi','mfConfirmOrder',{id:o.id},{k:'sm'}):''}</td></tr>`));
}
A.mfNewOrder=d=>{
  const o=mfState().orders.find(x=>x.id===+d.id);
  F.mfOrder=o?clone(o):{kind:d.kind,storeId:ME.role==='toko'?ME.warehouseId:'',customer:'',sourceRef:'',orderDate:mfToday(),deliveryDate:mfPlusDay(d.kind==='RO'?2:1),note:'',lines:[{productId:'',qty:'',price:'0'}]};
  mfModal(o?`Ubah ${o.no}`:`${d.kind==='RO'?'Permintaan toko ke Packing':'Sales Order customer'}`,()=>{
    const f=F.mfOrder;
    return `<div class="formrow">${f.kind==='RO'?fld('Toko peminta',mfSelect('mfOrder.storeId',f.storeId,mfStores().filter(w=>ME.role!=='toko'||w.id===ME.warehouseId).map(w=>[w.id,w.name]))):fld('Nama customer',mfInput('mfOrder.customer',f.customer))}${fld('Tanggal order',mfInput('mfOrder.orderDate',f.orderDate,'date'))}${fld('Tanggal kirim',mfInput('mfOrder.deliveryDate',f.deliveryDate,'date'))}${fld('Referensi eksternal (opsional)',mfInput('mfOrder.sourceRef',f.sourceRef))}</div>${mfLineTable('mfOrder',f.kind==='SO')}${btn('Tambah SKU','mfLineAdd',{key:'mfOrder'})}${fld('Catatan',mfInput('mfOrder.note',f.note))}<p class="note">Jumlah menggunakan satuan dasar produk. Harga paket diisi sebagai harga SKU paket. Batas penerimaan order mengikuti SOP.</p>`;
  },'mfSaveOrder','Simpan draft');
};
A.mfSaveOrder=()=>mfSave('save_order',F.mfOrder,'Draft order tersimpan.');
A.mfConfirmOrder=d=>mfSave('confirm_order',{id:+d.id},'Order dikonfirmasi. Untuk SO, DO sudah dibuat sesuai jumlah pesanan.');
A.mfCancelOrder=d=>mfSave('cancel_order',{id:+d.id},'Order dibatalkan.');
A.mfOrderDetail=d=>{
  const o=mfState().orders.find(x=>x.id===+d.id);
  openModal({title:o.no,body:()=>`<p>${esc(o.customer||W(o.storeId)?.name)} · ${esc(o.orderDate)} → ${esc(o.deliveryDate)}</p>${tbl(['Produk','Jumlah','Harga/unit'],o.lines.map(l=>`<tr><td>${esc(mfLabel(l.productId))}</td><td>${num(l.qty)}</td><td>${rp(l.price)}</td></tr>`))}<p>${esc(o.note)}</p>`,foot:()=>btn('Tutup','closeModal')+(!o.planId&&o.status!=='batal'?btn('Batalkan order','mfCancelOrder',{id:o.id},{k:'ghost-bad'}):'')});
};

function mfPlansView(){
  return mfToolbar(mfCan([...mfPlanRoles,'packing'])?btn('Konsolidasi RO + SO','mfNewPlan',{}, {k:'pri'}):'')
   +tbl(['Rekap','Tanggal produksi','Tanggal kirim','Order',''],mfState().plans.slice().reverse().map(p=>`<tr><td>${esc(p.no)}</td><td>${esc(p.productionDate)}</td><td>${esc(p.deliveryDate)}</td><td>${p.orderIds.length}</td><td>${btn('Rincian & buat MO','mfPlanDetail',{id:p.id},{k:'sm'})}</td></tr>`));
}
A.mfNewPlan=()=>{
  F.mfPlan={deliveryDate:mfPlusDay(1),productionDate:mfToday(),selected:{}};
  mfModal('Konsolidasi kebutuhan di Packing',()=>{
    const f=F.mfPlan, list=mfState().orders.filter(o=>o.status==='dikonfirmasi'&&!o.planId&&o.deliveryDate===f.deliveryDate);
    return `<div class="formrow">${fld('Tanggal kirim',mfInput('mfPlan.deliveryDate',f.deliveryDate,'date','data-rr'))}${fld('Tanggal mulai shift produksi',mfInput('mfPlan.productionDate',f.productionDate,'date'))}</div>${tbl(['Pilih','Order','Pemesan','Isi'],list.map(o=>`<tr><td><input type="checkbox" aria-label="Pilih ${esc(o.no)}" data-bind="mfPlan.selected.${o.id}" ${f.selected[o.id]?'checked':''}></td><td>${esc(o.no)}</td><td>${esc(o.customer||W(o.storeId)?.name)}</td><td>${o.lines.map(l=>`${esc(mfLabel(l.productId))}: ${num(l.qty)}`).join('<br>')}</td></tr>`))}<p class="note">Order yang dipilih dikerjakan bersama. Rekap belum membuat MO sampai admin menekan Buat MO/WO.</p>`;
  },'mfSavePlan','Simpan rekap');
};
A.mfSavePlan=()=>mfSave('create_plan',{deliveryDate:F.mfPlan.deliveryDate,productionDate:F.mfPlan.productionDate,orderIds:Object.entries(F.mfPlan.selected).filter(([id,v])=>v&&mfState().orders.some(o=>o.id===+id&&o.deliveryDate===F.mfPlan.deliveryDate)).map(([id])=>+id)},'Kebutuhan berhasil direkap.');
A.mfPlanDetail=d=>{
  const p=mfState().plans.find(x=>x.id===+d.id); const totals={};
  p.requirements.forEach(r=>{ const t=totals[r.productId]||={qty:0,kind:r.kind,sources:[]}; t.qty+=r.qty; t.sources.push(`${mfState().orders.find(o=>o.id===r.orderId)?.no}: ${num(r.qty)}`); });
  openModal({title:p.no,wide:true,body:()=>`<p>Produksi ${esc(p.productionDate)} · kirim ${esc(p.deliveryDate)}</p>${tbl(['SKU','Jumlah','Pemenuhan','Sumber'],Object.entries(totals).map(([pid,t])=>`<tr><td>${esc(mfLabel(pid))}</td><td>${num(t.qty)}</td><td>${esc(mfKinds[t.kind])}</td><td>${t.sources.map(esc).join('<br>')}</td></tr>`))}<p class="note">Setengah jadi mengikuti buffer dan MO manual. Barang beli dipenuhi lewat PO. Permintaan paket diturunkan menjadi kebutuhan komponennya.</p>`,foot:()=>btn('Tutup','closeModal')+(mfCan(mfPlanRoles)?btn('Buat MO / WO dapur','mfPlanMos',{id:p.id,kind:'kitchen'},{k:'pri'}):'')+(mfCan(mfPackRoles,mfState().settings.packingWarehouseId)?btn('Buat MO perakitan','mfPlanMos',{id:p.id,kind:'package'}):'')});
};
A.mfPlanMos=d=>mfSave('create_plan_mos',{id:+d.id,kind:d.kind},'MO dibuat satu per SKU.');

function mfMosView(){
  const list=S.productions.filter(p=>p.manufacturingVersion===1).slice().reverse();
  return mfToolbar(btn('MO manual / buffer','mfNewMo',{}, {k:'pri'}))+tbl(['MO / WO','Produk','Gudang','Rencana / aktual','Jadwal','Status',''],list.map(p=>`<tr><td>${esc(p.no)}<div class="sub">${esc(p.workOrder?.no||'Perakitan tanpa WO')}</div></td><td>${esc(mfLabel(p.productId))}</td><td>${esc(W(p.sourceWarehouseId)?.name)}</td><td>${num(p.planQty)} / ${p.actualQty==null?'—':num(p.actualQty)}${p.shortageQty?`<div class="sub">Kurang/rusak ${num(p.shortageQty)}</div>`:''}${p.excessQty?`<div class="sub">Lebih ${num(p.excessQty)}</div>`:''}</td><td>${esc(p.scheduledDate)}</td><td>${mfStatus(p)}</td><td class="acts">${btn('Rincian','mfMoDetail',{id:p.id},{k:'sm'})}${['terjadwal','diproses'].includes(p.status)&&mfCan(mfExecRoles,p.sourceWarehouseId)?btn('Catat hasil','mfFinish',{id:p.id},{k:'sm pri'}):''}</td></tr>`));
}
A.mfNewMo=()=>{
  F.mfMo={productId:'',qty:'',productionDate:mfToday(),deliveryDate:mfPlusDay(1),note:''};
  mfModal('MO manual',()=>{
    const f=F.mfMo,p=P(f.productId),cfg=mfConfig(p);
    return `<div class="formrow">${fld('Produk',mfSelect('mfMo.productId',f.productId,actP().filter(p=>mfConfig(p).kind!=='purchased').map(p=>[p.id,`${p.code} · ${p.name}`]),'data-rr'))}${fld('Jumlah '+(p?.baseUom||''),mfInput('mfMo.qty',f.qty,'number','min="0" step="any"'))}</div>${p?`<p><strong>${esc(cfg.kind==='package'?'Packing · tanpa WO':KT(cfg.kitchenId)?.name)}</strong> · BOM ${esc(BOM(cfg.bomId)?.code||'Belum diatur')}</p>`:''}<div class="formrow">${fld('Tanggal produksi',mfInput('mfMo.productionDate',f.productionDate,'date'))}${fld('Tanggal kirim',mfInput('mfMo.deliveryDate',f.deliveryDate,'date'))}</div>${fld('Catatan',mfInput('mfMo.note',f.note))}<p class="note">BOM dan dapur mengikuti master produk. Pembuatan MO tidak dibatasi jam input. Produksi setengah jadi tidak membuat MO turunan.</p>`;
  },'mfCreateMo','Buat MO');
};
A.newMfgPlan=A.mfNewMo;
A.mfCreateMo=()=>mfSave('create_mo',F.mfMo,'MO tersimpan.');
A.mfMoDetail=d=>{
  const p=MFG(d.id);
  openModal({title:`${p.no} · ${p.workOrder?.no||'Packing'}`,wide:true,body:()=>`<p>${esc(mfLabel(p.productId))} · ${num(p.planQty)} ${esc(p.planUom)} · ${esc(W(p.sourceWarehouseId)?.name)}</p>${tbl(['Bahan','Kebutuhan WO / rencana','Aktual dikonsumsi'],p.bomSnapshot.lines.map(l=>`<tr><td>${esc(mfLabel(l.productId))}</td><td>${num(l.qty*p.planQty/p.bomSnapshot.yieldQty,4)}</td><td>${p.status==='selesai'?num(p.ingredientsUsed.find(x=>x.productId===l.productId)?.qtyUsed||0,4):'—'}</td></tr>`))}<p>Hasil baik: ${p.actualQty==null?'belum dicatat':num(p.actualQty)} · Kurang/rusak: ${num(p.shortageQty)} · Lebih: ${num(p.excessQty)}</p><p>Fisik: ${esc(p.physicalStartedAt||'—')} s.d. ${esc(p.physicalFinishedAt||'—')}<br>Dicatat: ${fdt(p.completedAt)}</p>${p.sources.length?tbl(['Sumber','Jumlah'],p.sources.map(s=>`<tr><td>${esc(mfState().orders.find(o=>o.id===s.orderId)?.no)}</td><td>${num(s.qty)}</td></tr>`)):''}<p>${esc(p.note||'')}</p>`,foot:()=>btn('Tutup','closeModal')+btn('Cetak WO / MO','mfPrint',{kind:'mo',id:p.id})+(p.status==='terjadwal'&&mfCan(mfExecRoles,p.sourceWarehouseId)?btn('Mulai produksi','mfStart',{id:p.id}):'')+(p.status==='terjadwal'&&mfCan([...mfPlanRoles,...mfPackRoles],p.sourceWarehouseId)?btn('Batalkan MO','mfCancelMo',{id:p.id},{k:'ghost-bad'}):'')});
};
A.mfStart=d=>{F.mfStart={id:+d.id,physicalStartedAt:mfDateTime()};mfModal('Catat mulai produksi',()=>fld('Waktu mulai fisik',mfInput('mfStart.physicalStartedAt',F.mfStart.physicalStartedAt,'datetime-local')),'mfStartSave','Mulai');};
A.mfStartSave=()=>mfSave('start_mo',F.mfStart,'Waktu mulai tercatat.');
A.mfCancelMo=d=>mfSave('cancel_mo',{id:+d.id},'MO dibatalkan.');
A.mfFinish=d=>{
  const p=MFG(d.id);F.mfFinish={id:p.id,actualQty:p.planQty,physicalStartedAt:p.physicalStartedAt?mfDateTime(p.physicalStartedAt):mfDateTime(),physicalFinishedAt:mfDateTime(),batchNo:p.no,expDate:'',rack:'',note:''};
  mfModal(`Hasil ${p.no}`,()=>{
    const f=F.mfFinish;
    return `<p>${esc(mfLabel(p.productId))} · Rencana ${num(p.planQty)}. ${p.workOrder?'Bahan tetap dihitung untuk jumlah WO; hasil kurang dicatat sebagai rusak tanpa backorder.':'Komponen dikonsumsi sesuai paket yang dirakit.'}</p><div class="formrow">${fld('Waktu mulai fisik',mfInput('mfFinish.physicalStartedAt',f.physicalStartedAt,'datetime-local',p.physicalStartedAt?'disabled':''))}${fld('Waktu selesai fisik',mfInput('mfFinish.physicalFinishedAt',f.physicalFinishedAt,'datetime-local'))}${fld('Hasil baik aktual ('+p.planUom+')',mfInput('mfFinish.actualQty',f.actualQty,'number','min="0" step="any"'))}</div><div class="formrow">${fld('Batch hasil',mfInput('mfFinish.batchNo',f.batchNo))}${fld('Kedaluwarsa (opsional)',mfInput('mfFinish.expDate',f.expDate,'date'))}${fld('Rak (opsional)',mfInput('mfFinish.rack',f.rack))}</div>${fld('Catatan hasil',mfInput('mfFinish.note',f.note))}<p class="note">${p.workOrder?'Pelaksanaan dapur 20.00–10.00; waktu pencatatan boleh sesudahnya.':'Perakitan Packing boleh dilakukan kapan saja.'} Semua bahan dan hasil dibukukan bersama.</p>`;
  },'mfFinishSave','Selesaikan satu kali produksi');
};
A.mfFinishSave=()=>mfSave('complete_mo',F.mfFinish,'Hasil dan konsumsi bahan sudah dibukukan.');
function mfHistoryView(){return tbl(['Jadwal lama','Produk','Rencana / aktual','Status',''],S.productions.filter(p=>!p.manufacturingVersion).map(p=>`<tr><td>${esc(p.no)}</td><td>${esc(mfLabel(p.productId))}</td><td>${num(p.planQty)} / ${num(p.actualQty)}</td><td>${mfStatus(p)}</td><td>${['terjadwal','diproses'].includes(p.status)?btn('Adopsi menjadi MO / WO','mfAdopt',{id:p.id},{k:'sm'}):''}</td></tr>`))+'<p class="note">Riwayat lama dipertahankan. Jadwal yang belum selesai dan belum mencatat konsumsi dapat diadopsi sesudah dapur dan BOM produk ditetapkan pada master.</p>';}
A.mfAdopt=d=>mfSave('adopt_legacy',{id:+d.id},'Jadwal lama ditautkan ke MO/WO baru.');

function mfMaterialsView(){
  return mfToolbar(mfCan(mfPlanRoles)?btn('Permintaan bahan / buffer','mfNewRequest',{}, {k:'pri'}):'')+tbl(['Permintaan','Dapur','Bahan','Transfer / status',''],mfState().requests.slice().reverse().map(r=>{
    const t=r.transferId?byId(S.transfers,r.transferId):null;
    return `<tr><td>${esc(r.no)}</td><td>${esc(KT(r.kitchenId)?.name)}</td><td>${r.lines.map(l=>`${esc(mfLabel(l.productId))}: ${num(l.qty,4)}`).join('<br>')}</td><td>${esc(t?.no||'Belum picking')}<br>${mfStatus(t||r)}</td><td class="acts">${!t&&mfCan(mfPlanRoles,r.warehouseId)?btn('Ubah jumlah','mfNewRequest',{id:r.id},{k:'sm'}):''}${!t&&mfCan(['gudang'],r.sourceWarehouseId)?btn('Buat picking / transfer','mfPrepare',{id:r.id},{k:'sm pri'}):''}${t?btn('Picking list','mfPrint',{kind:'request',id:r.id},{k:'sm'}):''}${t?.status==='draft'&&mfCan(['gudang'],r.sourceWarehouseId)?btn('Kirim bahan','mfShipMaterial',{id:t.id},{k:'sm'}):''}${t?.status==='dikirim'&&mfCan(['gudang','produksi'],r.warehouseId)?btn('Terima bahan','mfReceive',{id:t.id},{k:'sm'}):''}</td></tr>`;
  }));
}
A.mfNewRequest=d=>{
  const old=mfState().requests.find(r=>r.id===+d.id);
  F.mfRequest=old?{...clone(old),loaded:true}:{kitchenId:'',planId:'',productId:'',lines:[],loaded:false,note:''};
  mfModal(old?old.no:'Permintaan Central → dapur',()=>{
    const f=F.mfRequest;
    return `<div class="formrow">${fld('Dapur',mfKitchenSelect('mfRequest.kitchenId',f.kitchenId))}${fld('Rekap (kosong = buffer)',mfPlanSelect('mfRequest.planId',f.planId))}${btn('Hitung saran','mfRequestPreview')}</div>${f.loaded?tbl(['Bahan','WO','Stok fisik','Reservasi','Dalam perjalanan','Minimum','Saran','Permintaan petugas'],f.lines.map((l,i)=>`<tr><td>${esc(mfLabel(l.productId))}</td><td>${num(l.needQty,4)}</td><td>${num(l.physicalQty,4)}</td><td>${num(l.reservedQty,4)}</td><td>${num(l.incomingQty,4)}</td><td>${num(l.minimumQty,4)}</td><td>${num(l.suggestedQty,4)}</td><td>${mfInput(`mfRequest.lines.${i}.qty`,l.qty,'number','min="0" step="any" aria-label="Permintaan petugas"')}</td></tr>`)):''}<div class="formrow">${fld('Tambah bahan lain',mfSelect('mfRequest.productId',f.productId,mfProducts()))}${btn('Tambahkan','mfRequestAdd')}</div>${fld('Catatan',mfInput('mfRequest.note',f.note))}<p class="note">Saran = kebutuhan WO + minimum − stok bebas dari reservasi aktif. Barang dalam perjalanan ditampilkan terpisah. Jumlah kirim mengikuti permintaan petugas; baris nol tidak diminta. Minimum boleh digunakan hingga nol.</p>`;
  },'mfRequestSave','Simpan permintaan');
};
A.mfRequestPreview=async()=>{
  const f=F.mfRequest;const r=await mfPreview('material_preview',{kitchenId:f.kitchenId,planId:f.planId,productIds:f.lines.map(l=>l.productId)});
  f.lines=r.lines.map(l=>({...l,qty:l.suggestedQty}));f.loaded=true;refresh();
};
A.mfRequestAdd=async()=>{
  const f=F.mfRequest;if(!f.productId)fail('Pilih bahan.');const r=await mfPreview('material_preview',{kitchenId:f.kitchenId,planId:f.planId,productIds:[f.productId]});
  const l=r.lines.find(l=>l.productId===+f.productId);if(!f.lines.some(x=>x.productId===l.productId))f.lines.push({...l,qty:l.suggestedQty});f.loaded=true;refresh();
};
A.mfRequestSave=()=>{const f=F.mfRequest;return mfSave('save_request',{id:f.id,kitchenId:f.kitchenId,planId:f.planId,lines:f.lines.filter(l=>+l.qty>0),note:f.note},'Permintaan multi-SKU tersimpan.');};
A.mfPrepare=d=>mfSave('prepare_request',{id:+d.id},'Satu picking list dan transfer siap diproses Central.');
A.mfShipMaterial=d=>mfSave('ship_transfer',{id:+d.id},'Bahan dikirim dari Central.');
A.mfReceive=d=>{
  const t=byId(S.transfers,d.id);F.mfReceive={id:t.id,received:t.lines.map(l=>l.picks.map(p=>p.qty))};
  mfModal(`Penerimaan ${t.no}`,()=>tbl(['Produk','Batch','Dikirim','Diterima'],t.lines.flatMap((l,i)=>l.picks.map((p,j)=>`<tr><td>${esc(mfLabel(l.productId))}</td><td>${esc(p.batchNo)}</td><td>${num(p.qty,4)}</td><td>${mfInput(`mfReceive.received.${i}.${j}`,F.mfReceive.received[i][j],'number','min="0" step="any" aria-label="Jumlah diterima"')}</td></tr>`)))+'<p class="note">Selisih kurang mengikuti proses scrap transit yang sudah ada.</p>','mfReceiveSave','Terima barang');
};
A.mfReceiveSave=()=>mfSave('receive_transfer',F.mfReceive,'Penerimaan tercatat.');
const mfOldShip=A.trfShip,mfOldReceive=A.trfReceive;
A.trfShip=d=>byId(S.transfers,d.id)?.manufacturingVersion?A.mfShipMaterial(d):mfOldShip(d);
A.trfReceive=d=>byId(S.transfers,d.id)?.manufacturingVersion?A.mfReceive(d):mfOldReceive(d);
const mfOldCancelTransfer=A.trfCancel, mfOldSaveTransfer=A.trfSave;
A.trfCancel=d=>byId(S.transfers,d.id)?.manufacturingVersion?mfSave('cancel_transfer',{id:+d.id},'Picking dibatalkan; permintaan dapat disiapkan kembali.'):mfOldCancelTransfer(d);
A.trfSave=()=>{
  const d=trfPayload(),k=actKT().find(k=>k.warehouseId===+d.srcId);
  if(k && +d.dstId===mfState().settings.packingWarehouseId) return mfSave('direct_to_packing',{kitchenId:k.id,lines:d.lines.filter(l=>l.productId)},'Packing langsung menerima sejumlah yang dikirim.');
  if(+d.srcId===mfState().settings.packingWarehouseId) fail('Pengiriman dari Packing dibuat melalui DO pada halaman Manufaktur / Packing.');
  return mfOldSaveTransfer();
};

function mfPackingView(){
  const wid=mfState().settings.packingWarehouseId;
  const stocks=actP().filter(p=>wid&&stockQ(p.id,wid)>0);
  return mfToolbar(btn('Dapur → Packing','mfDirect',{}, {k:'pri'})+(mfCan(mfPackRoles,wid)?btn('Hitung alokasi toko','mfAllocation')+btn('MO perakitan manual','mfNewMo'):'')+btn('Penerimaan supplier','go',{page:'inbound'}))
  +mfBody('Stok Packing',tbl(['Produk','Jumlah'],stocks.map(p=>`<tr><td>${esc(mfLabel(p.id))}</td><td>${num(stockQ(p.id,wid),4)}</td></tr>`)))
  +mfBody('Delivery Order',tbl(['DO / sumber','Tujuan','Tanggal / sesi','Isi','Status',''],mfState().deliveries.slice().sort((a,b)=>(a.kind==='SO'?-1:1)-(b.kind==='SO'?-1:1)||b.id-a.id).map(d=>`<tr><td>${esc(d.no)}<div class="sub">${esc(mfState().orders.find(o=>o.id===d.orderId)?.no)}</div></td><td>${esc(d.customer||W(d.storeId)?.name)}</td><td>${esc(d.deliveryDate)} / ${d.sessionId}</td><td>${d.lines.map(l=>`${esc(mfLabel(l.productId))}: ${num(l.qty)}`).join('<br>')}</td><td>${mfStatus(d)}</td><td class="acts">${btn('Cetak DO','mfPrint',{kind:'delivery',id:d.id},{k:'sm'})}${d.status==='siap'&&mfCan(mfPackRoles,d.warehouseId)?btn('Kirim','mfShipDelivery',{id:d.id},{k:'sm pri'})+btn('Sesi','mfAssignDelivery',{id:d.id},{k:'sm'}):''}${d.status==='dikirim'&&d.transferId&&mfCan(['toko','gudang'],d.storeId)?btn('Terima di toko','mfReceive',{id:d.transferId},{k:'sm'}):''}</td></tr>`)))
  +mfBody('Alokasi toko',tbl(['Nomor','Rekap','Status',''],mfState().allocations.map(a=>`<tr><td>${esc(a.no)}</td><td>${esc(mfState().plans.find(p=>p.id===a.planId)?.no)}</td><td>${a.deliveryIds?'DO dibuat':'Usulan disimpan'}</td><td>${!a.deliveryIds?btn('Ubah','mfAllocation',{id:a.id},{k:'sm'})+btn('Buat DO toko','mfStoreDos',{id:a.id},{k:'sm pri'}):''}</td></tr>`)))+'<p class="note">SO didahulukan, termasuk komponen paket yang belum dirakit. Cetak DO tidak mengurangi stok. Barang Packing keluar pada hari kirim sesuai SOP.</p>';
}
A.mfDirect=()=>{
  F.mfDirect={kitchenId:'',lines:[{productId:'',qty:''}]};
  mfModal('Kirim hasil dapur ke Packing',()=>fld('Dapur asal',mfKitchenSelect('mfDirect.kitchenId',F.mfDirect.kitchenId))+mfLineTable('mfDirect')+btn('Tambah SKU','mfLineAdd',{key:'mfDirect'})+'<p class="note">Satu langkah: stok dapur berkurang dan Packing langsung menerima jumlah yang sama.</p>','mfDirectSave','Kirim & terima otomatis');
};
A.mfDirectSave=()=>mfSave('direct_to_packing',F.mfDirect,'Packing menerima sejumlah yang dikirim dapur.');
A.mfAllocation=d=>{
  const a=mfState().allocations.find(x=>x.id===+d.id);
  F.mfAllocation=a?clone(a):{planId:'',lines:[]};
  mfModal('Alokasi sisa untuk toko',()=>{
    const f=F.mfAllocation;
    return `<div class="formrow">${fld('Rekap',mfPlanSelect('mfAllocation.planId',f.planId))}${btn('Hitung proporsional','mfAllocationPreview')}</div>${tbl(['Toko / RO','SKU','Diminta','Sisa setelah SO','Saran','Alokasi petugas'],f.lines.map((l,i)=>`<tr><td>${esc(W(l.storeId)?.name)}<div class="sub">${esc(mfState().orders.find(o=>o.id===l.orderId)?.no)}</div></td><td>${esc(mfLabel(l.productId))}</td><td>${num(l.requestedQty)}</td><td>${num(l.availableForStores)}</td><td>${num(l.suggestedQty)}</td><td>${mfInput(`mfAllocation.lines.${i}.qty`,l.qty,'number','min="0" step="any" aria-label="Alokasi petugas"')}</td></tr>`))}<p class="note">Saran dibagi proporsional dengan pembulatan menurut kelipatan alokasi produk. Petugas dapat mengubah pembagian; total diperiksa lagi saat DO dibuat dan dikirim.</p>`;
  },'mfAllocationSave','Simpan alokasi');
};
A.mfAllocationPreview=async()=>{const r=await mfPreview('allocation_preview',{planId:F.mfAllocation.planId});F.mfAllocation.lines=r.lines;refresh();};
A.mfAllocationSave=()=>mfSave('save_allocation',F.mfAllocation,'Alokasi tersimpan.');
A.mfStoreDos=d=>mfSave('create_store_deliveries',{id:+d.id},'DO toko dibuat setelah DO SO.');
A.mfShipDelivery=d=>{const o=mfState().deliveries.find(x=>x.id===+d.id);confirmBox('Kirim '+o.no,`<p>Catat pengeluaran fisik ${o.lines.map(l=>`${num(l.qty)} ${esc(mfLabel(l.productId))}`).join(', ')} dari Packing.</p>`,'Kirim',()=>mfSave('ship_delivery',{id:o.id},'Pengiriman tercatat.'));};
A.mfAssignDelivery=d=>{const o=mfState().deliveries.find(x=>x.id===+d.id);F.mfSession={id:o.id,sessionId:o.sessionId};mfModal('Sesi '+o.no,()=>`<p>Tanggal kirim tetap ${esc(o.deliveryDate)}.</p>`+fld('Sesi',mfSelect('mfSession.sessionId',F.mfSession.sessionId,mfState().settings.sessions.map(s=>[s.id,`Sesi ${s.id} · ${s.time}`]))),'mfAssignSave');};
A.mfAssignSave=()=>mfSave('assign_delivery',F.mfSession,'Sesi pengiriman diperbarui.');

function mfScheduleView(){
  F.mfScheduleDate ||= mfToday();
  const s=mfState().schedules.find(x=>x.date===F.mfScheduleDate),sessions=s?.sessions||mfState().settings.sessions;
  return mfToolbar(fld('Tanggal kirim',mfInput('mfScheduleDate',F.mfScheduleDate,'date','data-rr'))+btn('Atur jadwal','mfEditSchedule',{}, {k:'pri'}))+tbl(['Toko','Sesi','Jam'],mfStores().map(w=>{const id=s?.stores.find(r=>r.storeId===w.id)?.sessionId;return `<tr><td>${esc(w.name)}</td><td>${id||'Belum disimpan'}</td><td>${esc(sessions.find(x=>x.id===id)?.time||'—')}</td></tr>`;}))+'<p class="note">Setiap toko dijadwalkan pada tanggal kirim ini. Tiga sesi dapat diubah; jadwal tidak digeser otomatis ke hari berikutnya.</p>';
}
A.mfEditSchedule=()=>{
  const day=F.mfScheduleDate||mfToday(),old=mfState().schedules.find(x=>x.date===day);
  F.mfSchedule={date:day,sessions:clone(old?.sessions||mfState().settings.sessions),stores:mfStores().map(w=>({storeId:w.id,sessionId:old?.stores.find(r=>r.storeId===w.id)?.sessionId||1}))};
  mfModal('Jadwal kirim '+day,()=>{
    const f=F.mfSchedule;
    return `<div class="formrow">${f.sessions.map((s,i)=>fld(`Sesi ${i+1}`,mfInput(`mfSchedule.sessions.${i}.time`,s.time,'time'))).join('')}</div>${tbl(['Toko','Sesi'],f.stores.map((r,i)=>`<tr><td>${esc(W(r.storeId)?.name)}</td><td>${mfSelect(`mfSchedule.stores.${i}.sessionId`,r.sessionId,[[1,'Sesi 1'],[2,'Sesi 2'],[3,'Sesi 3']])}</td></tr>`))}`;
  },'mfScheduleSave');
};
A.mfScheduleSave=()=>mfSave('save_schedule',F.mfSchedule,'Jadwal semua toko disimpan pada tanggal kirim.');

V.mfgconfig=()=>mfToolbar((ME.role==='admin'?btn('Pengaturan Packing & waktu','mfSettings',{}, {k:'pri'}):'')+btn('Minimum per gudang','mfMinimum')+btn('Buka master produk','go',{page:'products'})+btn('Buka BOM','go',{page:'boms'}))
  +tbl(['Produk','Jenis pemenuhan','Dapur','BOM utama','Kelipatan alokasi',''],actP().map(p=>{const c=mfConfig(p);return `<tr><td>${esc(mfLabel(p.id))}</td><td>${esc(mfKinds[c.kind])}</td><td>${esc(KT(c.kitchenId)?.name||'—')}</td><td>${esc(BOM(c.bomId)?.code||'—')}</td><td>${num(c.allocationStep,4)}</td><td>${ME.role==='admin'?btn('Atur','mfProduct',{id:p.id},{k:'sm'}):''}</td></tr>`;}))+'<p class="note">Penentuan dapur dan BOM tersimpan pada produk. Minimum merupakan saran pengisian, bukan stok yang dikunci.</p>';
A.mfProduct=d=>{
  const p=P(d.id);F.mfProduct={productId:p.id,...clone(mfConfig(p))};
  mfModal('Produksi · '+p.name,()=>{
    const f=F.mfProduct;
    return `<div class="formrow">${fld('Pemenuhan produk',mfSelect('mfProduct.kind',f.kind,Object.entries(mfKinds),'data-rr'))}${['kitchen','semi'].includes(f.kind)?fld('Dapur pembuat',mfKitchenSelect('mfProduct.kitchenId',f.kitchenId)):''}${f.kind!=='purchased'?fld('BOM utama',mfSelect('mfProduct.bomId',f.bomId,actBOM().filter(b=>b.productId===p.id).map(b=>[b.id,`${b.code} · ${b.name}`]))):''}${fld('Kelipatan saran alokasi ('+p.baseUom+')',mfInput('mfProduct.allocationStep',f.allocationStep,'number','min="0.0001" step="any"'),'Contoh 1 untuk pcs; 0,0001 untuk bahan yang dibagi pecahan.')}</div>`;
  },'mfProductSave');
};
A.mfProductSave=()=>mfSave('configure_product',F.mfProduct,'Konfigurasi produksi produk tersimpan.');
A.mfMinimum=()=>{
  F.mfMinimum={productId:'',warehouseId:'',qty:0};
  mfModal('Minimum per barang per gudang',()=>{
    const f=F.mfMinimum,p=P(f.productId),w=W(f.warehouseId);
    return `<div class="formrow">${fld('Produk',mfSelect('mfMinimum.productId',f.productId,mfProducts(),'data-hook="mfMinimumLoad" data-rr'))}${fld('Gudang',mfSelect('mfMinimum.warehouseId',f.warehouseId,mfScopeWarehouses().map(w=>[w.id,w.name]),'data-hook="mfMinimumLoad" data-rr'))}${fld('Minimum '+(p?.baseUom||''),mfInput('mfMinimum.qty',f.qty,'number','min="0" step="any"'))}</div>${p&&w?`<p>Stok fisik saat ini ${num(stockQ(p.id,w.id),4)} ${esc(p.baseUom)}. Stok tetap boleh digunakan sampai nol.</p>`:''}`;
  },'mfMinimumSave');
};
H.mfMinimumLoad=()=>{const f=F.mfMinimum,p=P(f.productId),w=W(f.warehouseId);if(p&&w)f.qty=minOf(p,w);};
A.mfMinimumSave=()=>mfSave('set_minimum',F.mfMinimum,'Minimum gudang diperbarui.');
A.mfSettings=()=>{
  F.mfSettings=clone(mfState().settings);
  mfModal('Pengaturan manufaktur',()=>{
    const f=F.mfSettings;
    return `<div class="formrow">${fld('Gudang Packing',mfSelect('mfSettings.packingWarehouseId',f.packingWarehouseId,actW().filter(w=>!w.isCentral&&!actKT().some(k=>k.warehouseId===w.id)).map(w=>[w.id,w.name])))}${fld('Zona waktu',mfInput('mfSettings.timezone',f.timezone))}</div><div class="formrow">${f.sessions.map((s,i)=>fld(`Jam awal sesi ${i+1}`,mfInput(`mfSettings.sessions.${i}.time`,s.time,'time'))).join('')}</div><p class="note">Jam ini menjadi isian awal jadwal harian dan dapat diubah. Shift dapur 20.00–10.00 berlaku pada waktu pelaksanaan fisik; Packing bebas waktu.</p>`;
  },'mfSettingsSave');
};
A.mfSettingsSave=()=>mfSave('save_settings',F.mfSettings,'Pengaturan manufaktur tersimpan.');

A.mfPrint=d=>{
  let title='',meta='',rows=[],heads=['SKU','Produk','Jumlah','Satuan'];
  if(d.kind==='delivery'){
    const o=mfState().deliveries.find(x=>x.id===+d.id);title=o.no;
    meta=`${o.kind} · ${mfState().orders.find(x=>x.id===o.orderId)?.no} · ${o.customer||W(o.storeId)?.name} · ${o.deliveryDate} · sesi ${o.sessionId}`;
    rows=o.lines.map(l=>[P(l.productId)?.code,P(l.productId)?.name,num(l.qty,4),l.uom]);
  }else if(d.kind==='request'){
    const r=mfState().requests.find(x=>x.id===+d.id),t=byId(S.transfers,r.transferId);title='Picking list · '+r.no;
    meta=`${W(r.sourceWarehouseId)?.name} → ${W(r.warehouseId)?.name} · ${t?.no||''}`;
    heads=['SKU','Produk','Jumlah diminta','Satuan','Batch / rak'];
    rows=r.lines.map(l=>[P(l.productId)?.code,P(l.productId)?.name,num(l.qty,4),l.uom,t?.lines.find(x=>x.productId===l.productId)?.picks.map(p=>`${p.batchNo} / ${p.rack||'—'}: ${num(p.qty,4)}`).join('; ')||'']);
  }else{
    const p=MFG(d.id);title=p.workOrder?.no||p.no;meta=`${p.no} · ${W(p.sourceWarehouseId)?.name} · ${p.scheduledDate} · hasil rencana ${num(p.planQty)} ${p.planUom} ${P(p.productId)?.name}`;
    rows=p.bomSnapshot.lines.map(l=>[P(l.productId)?.code,P(l.productId)?.name,num(l.qty*p.planQty/p.bomSnapshot.yieldQty,4),l.uom]);
  }
  $('#printArea').innerHTML=`<h1>${esc(S.settings.company)}</h1><h2>${esc(title)}</h2><p>${esc(meta)}</p>${tbl(heads,rows.map(r=>`<tr>${r.map(c=>`<td>${esc(c)}</td>`).join('')}</tr>`))}<p>Disiapkan: ____________________ &nbsp; Diperiksa: ____________________</p>`;
  window.print();
};

// Make configuration reachable directly from the existing product master.
const mfOldProductsView=V.products;
V.products=()=>mfToolbar(btn('Dapur, BOM & minimum produk','go',{page:'mfgconfig'}))+mfOldProductsView();

// Preserve the existing explicit admin reset flow; ordinary raw state writes
// still cannot erase or forge server-owned manufacturing records.
A.resetData=async d=>{
  need('admin'); await mfFlush();
  const previous=S,oldSave=save;
  try {
    save=()=>{};
    (d.mode==='demo'?seed:emptyState)();
    const fresh=S;
    S=previous;save=oldSave;
    const {users,currentUserId,ui,...data}=fresh;
    const r=await api('PUT','/api/state',{version:VER,data,reset:true});
    S={...data,users:previous.users,currentUserId:ME.id,ui:previous.ui}; VER=r.version;
    PENDING_AUD.length=0;dirty=false;sessionStorage.removeItem(mfPendingKey());
    resetForms();closeModal();render();toast('Data berhasil diatur ulang.');
  } catch(e){S=previous;throw e;} finally {save=oldSave;}
};
