'use strict';

/* Search the current form's eligible products; only IDs enter its data binding.
   The catalogue already lives in app_state. Render at most 50 matches at once,
   not thousands of native <option> elements for every transaction line. */
const ProductPicker = (() => {
  const fields = new Map(), PAGE_SIZE = 50;
  let active = null, quiet = 0;
  const normalize = value => String(value).normalize('NFKD').replace(/\p{M}/gu, '').toLocaleLowerCase();
  const inputId = path => `product-search-${path}`;
  const hiddenFor = input => input.parentElement.querySelector('input[type=hidden]');
  const caption = (input, value) => fields.get(input.dataset.productSearch)?.rows.find(r => r.value === value)?.label || '';

  function field(path, value, rows, options = {}) {
    const id = inputId(path), selected = String(value ?? '');
    const items = rows.map(([v, label]) => ({value: String(v), label: String(label), search: normalize(label)}));
    fields.set(path, {rows: items, options});
    const label = items.find(r => r.value === selected)?.label || '';
    const row = path.match(/\.lines\.(\d+)\./);
    const ariaLabel = options.label || (row ? `Produk baris ${+row[1] + 1}` : 'Produk');
    return `<span class="product-picker"><input type="hidden" data-bind="${esc(path)}" value="${esc(selected)}" ${options.extra || ''}>
      <input type="text" id="${esc(id)}" data-product-search="${esc(path)}" role="combobox" aria-label="${esc(ariaLabel)}" aria-autocomplete="list" aria-haspopup="listbox" aria-expanded="false" autocomplete="off" spellcheck="false" placeholder="${esc(options.placeholder || 'Ketik nama atau kode SKU…')}" value="${esc(label)}" ${options.disabled ? 'disabled' : ''}></span>`;
  }

  function close() {
    if (active) {
      const {input} = active;
      input.value = caption(input, hiddenFor(input).value);
      input.setAttribute('aria-expanded', 'false');
      input.removeAttribute('aria-activedescendant');
      input.removeAttribute('aria-controls');
      active = null;
    }
    document.getElementById('product-picker-popup')?.remove();
  }

  function position() {
    if (!active) return;
    const {input} = active, popup = document.getElementById('product-picker-popup');
    if (!input.isConnected || !popup) { close(); return; }
    const rect = input.getBoundingClientRect(), viewport = window.visualViewport;
    const left = viewport?.offsetLeft || 0, top = viewport?.offsetTop || 0;
    const width = viewport?.width || window.innerWidth, height = viewport?.height || window.innerHeight;
    if (rect.bottom < top || rect.top > top + height) { close(); return; }
    const popupWidth = Math.min(Math.max(rect.width, 300), width - 16);
    const below = top + height - rect.bottom - 8, above = rect.top - top - 8;
    const upwards = below < 220 && above > below;
    popup.style.width = `${popupWidth}px`;
    popup.style.left = `${Math.max(left + 8, Math.min(rect.left, left + width - popupWidth - 8))}px`;
    popup.style.maxHeight = `${Math.max(80, Math.min(360, upwards ? above : below))}px`;
    popup.style.top = `${upwards ? Math.max(top + 8, rect.top - popup.offsetHeight - 4) : rect.bottom + 4}px`;
  }

  function highlight() {
    if (!active) return;
    const popup = document.getElementById('product-picker-popup');
    popup.querySelectorAll('[role=option]').forEach(el => el.setAttribute('aria-selected', String(+el.dataset.index === active.index)));
    const option = popup.querySelector(`[data-index="${active.index}"]`);
    if (option) {
      active.input.setAttribute('aria-activedescendant', option.id);
      option.scrollIntoView({block: 'nearest'});
    } else active.input.removeAttribute('aria-activedescendant');
  }

  function draw() {
    if (!active) return;
    const {input, matches, start} = active, config = fields.get(input.dataset.productSearch);
    let popup = document.getElementById('product-picker-popup');
    if (!popup) {
      popup = document.createElement('div'); popup.id = 'product-picker-popup'; popup.className = 'product-picker-popup';
      // Keep the list within the accessible modal, outside its scrolling body.
      (input.closest('[role=dialog]') || document.body).appendChild(popup);
    }
    const end = Math.min(start + PAGE_SIZE, matches.length);
    popup.innerHTML = `<div id="product-picker-count" class="product-picker-count" role="status" aria-live="polite">${matches.length ? `${matches.length} hasil · ${start + 1}–${end}` : 'Tidak ada produk yang cocok.'}</div>
      <div id="product-picker-options" role="listbox" aria-label="Hasil pencarian produk">${matches.slice(start, end).map((r, i) => `<div id="product-picker-option-${start + i}" role="option" aria-selected="false" aria-posinset="${start + i + 1}" aria-setsize="${matches.length}" data-index="${start + i}" data-value="${esc(r.value)}">${esc(r.label)}</div>`).join('')}</div>
      <div class="product-picker-actions">${config.options.allowEmpty !== false && hiddenFor(input).value ? `<button type="button" data-picker-clear>${esc(config.options.empty || 'Kosongkan pilihan')}</button>` : ''}${matches.length > PAGE_SIZE ? `<button type="button" data-picker-page="-1" ${start === 0 ? 'disabled' : ''}>Sebelumnya</button><button type="button" data-picker-page="1" ${end === matches.length ? 'disabled' : ''}>Berikutnya</button>` : ''}</div>`;
    input.setAttribute('aria-expanded', 'true');
    input.setAttribute('aria-controls', 'product-picker-options');
    position(); highlight();
  }

  function open(input, query = '') {
    if (quiet || input.disabled || !fields.has(input.dataset.productSearch)) return;
    if (active?.input !== input) close();
    const terms = normalize(query).trim().split(/\s+/).filter(Boolean);
    const matches = fields.get(input.dataset.productSearch).rows.filter(r => terms.every(term => r.search.includes(term)));
    active = {input, query, matches, start: 0, index: -1};
    draw();
  }

  function choose(value) {
    if (!active) return;
    const {input} = active, config = fields.get(input.dataset.productSearch), hidden = hiddenFor(input);
    if (value === '' ? config.options.allowEmpty === false : !config.rows.some(r => r.value === value)) return;
    // Dispatch the original form's change hook once (UOM, price, BOM, etc.).
    hidden.value = value;
    close(); quiet++;
    try {
      hidden.dispatchEvent(new Event('change', {bubbles: true}));
      document.getElementById(input.id)?.focus({preventScroll: true});
    } finally { quiet--; }
  }

  document.addEventListener('focusin', e => {
    if (e.target.matches('[data-product-search]') && !quiet) {
      open(e.target); e.target.select();
    }
  });
  document.addEventListener('input', e => {
    if (e.target.matches('[data-product-search]')) open(e.target, e.target.value);
  });
  document.addEventListener('focusout', () => {
    setTimeout(() => {
      if (active && document.activeElement !== active.input && !document.activeElement?.closest('#product-picker-popup')) close();
    }, 0);
  });
  document.addEventListener('pointerdown', e => {
    if (e.target.closest('#product-picker-popup')) {
      if (e.target.closest('[role=option],button')) e.preventDefault();
    } else if (active && e.target !== active.input) close();
  }, true);
  document.addEventListener('click', e => {
    const popup = e.target.closest('#product-picker-popup');
    if (!popup) {
      if (e.target.matches('[data-product-search]') && active?.input !== e.target) { open(e.target); e.target.select(); }
      return;
    }
    const option = e.target.closest('[role=option]'), button = e.target.closest('button');
    if (option) choose(option.dataset.value);
    else if (button && !button.disabled && active) {
      if (button.hasAttribute('data-picker-clear')) choose('');
      else { active.start += +button.dataset.pickerPage * PAGE_SIZE; active.index = -1; draw(); }
    }
  });
  document.addEventListener('keydown', e => {
    if (e.isComposing) return;
    if (!active && e.target.matches('[data-product-search]') && ['ArrowDown', 'ArrowUp'].includes(e.key)) open(e.target);
    if (!active || (e.target !== active.input && !e.target.closest('#product-picker-popup'))) return;
    if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); close(); return; }
    if (e.target !== active.input) return;
    if (e.key === 'Tab') { close(); return; }
    if (e.key === 'Enter') {
      e.preventDefault(); e.stopImmediatePropagation();
      if (active.index >= 0) choose(active.matches[active.index].value);
    } else if (['ArrowDown', 'ArrowUp', 'PageDown', 'PageUp'].includes(e.key)) {
      e.preventDefault();
      const step = ({ArrowDown: 1, ArrowUp: -1, PageDown: PAGE_SIZE, PageUp: -PAGE_SIZE})[e.key];
      active.index = Math.max(0, Math.min(active.matches.length - 1, active.index + step));
      if (!active.matches.length) active.index = -1;
      active.start = Math.max(0, Math.floor(active.index / PAGE_SIZE) * PAGE_SIZE);
      draw();
    }
  }, true);
  window.addEventListener('resize', position);
  document.addEventListener('scroll', e => { if (!e.target.closest?.('#product-picker-popup')) position(); }, true);
  window.visualViewport?.addEventListener('resize', position);
  window.visualViewport?.addEventListener('scroll', position);

  return {
    field, close,
    beforeRender() {
      const snapshot = active && document.activeElement === active.input ? {
        id: active.input.id, query: active.query, text: active.input.value,
        value: hiddenFor(active.input).value, start: active.start, index: active.index,
        selectionStart: active.input.selectionStart, selectionEnd: active.input.selectionEnd
      } : null;
      quiet++; close(); return snapshot;
    },
    afterRender(snapshot) {
      quiet--;
      for (const path of fields.keys()) if (!document.getElementById(inputId(path))) fields.delete(path);
      const input = snapshot && document.getElementById(snapshot.id);
      if (input && input === document.activeElement && hiddenFor(input).value === snapshot.value) {
        input.value = snapshot.text; open(input, snapshot.query);
        input.setSelectionRange(snapshot.selectionStart, snapshot.selectionEnd);
        if (active) {
          active.index = Math.min(snapshot.index, active.matches.length - 1);
          active.start = Math.min(snapshot.start, Math.max(0, Math.floor((active.matches.length - 1) / PAGE_SIZE) * PAGE_SIZE));
          draw();
        }
      }
    }
  };
})();

function productPicker(path, value, products, options = {}) {
  const label = options.format || (p => `${p.code} · ${p.name}`);
  return ProductPicker.field(path, value, products.map(p => [p.id, label(p)]), options);
}
