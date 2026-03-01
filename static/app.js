// ── Toast System ──────────────────────────────────────────────────────────────

function showToast(message, type, options) {
  type = type || 'info';
  options = options || {};

  const container = document.getElementById('toast-container');
  if (!container) return;

  const id = 'toast-' + Date.now();
  const icons = {
    success: 'fa-check-circle',
    danger:  'fa-exclamation-triangle',
    warning: 'fa-triangle-exclamation',
    info:    'fa-circle-info',
  };

  const undoHtml = options.undoUrl
    ? '<button class="app-toast-undo" data-url="' + options.undoUrl + '">' +
      '<i class="fas fa-rotate-left"></i> Undo</button>'
    : '';

  const el = document.createElement('div');
  el.id = id;
  el.className = 'app-toast app-toast-' + type;
  el.innerHTML =
    '<div class="app-toast-body">' +
      '<i class="fas ' + (icons[type] || icons.info) + ' app-toast-icon"></i>' +
      '<span class="app-toast-message">' + message + '</span>' +
      undoHtml +
      '<button class="app-toast-close" onclick="dismissToast(\'' + id + '\')">' +
        '<i class="fas fa-xmark"></i>' +
      '</button>' +
    '</div>';

  container.appendChild(el);

  var delay = options.undoUrl ? 10000 : 4000;
  el._timer = setTimeout(function () { dismissToast(id); }, delay);

  if (options.undoUrl) {
    el.querySelector('.app-toast-undo').addEventListener('click', function () {
      clearTimeout(el._timer);
      dismissToast(id);
      fetchAction(options.undoUrl, { method: 'POST' })
        .then(function (data) {
          if (data.ok) {
            window.location.reload();
          } else {
            showToast(data.message || 'Undo failed.', 'danger');
          }
        })
        .catch(function () {
          showToast('Undo failed — please try again.', 'danger');
        });
    });
  }
}

function dismissToast(id) {
  var el = document.getElementById(id);
  if (!el) return;
  clearTimeout(el._timer);
  el.classList.add('app-toast-hide');
  setTimeout(function () { el.remove(); }, 300);
}

// ── Fetch Helper ──────────────────────────────────────────────────────────────

function fetchAction(url, options) {
  options = options || {};
  var headers = Object.assign({ 'X-Requested-With': 'XMLHttpRequest' }, options.headers || {});
  return fetch(url, Object.assign({}, options, { headers: headers }))
    .then(function (resp) {
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      return resp.json();
    });
}

// ── Helper: update stock badge, status badge, and row highlight ───────────────

function applyStockState(stockBadge, statusBadge, row, stock, isLow) {
  stockBadge.textContent = stock;
  stockBadge.className   = 'badge ' + (isLow ? 'bg-danger' : 'bg-success') + ' fs-6';
  if (statusBadge) {
    statusBadge.textContent = isLow ? 'Low Stock' : 'Adequate';
    statusBadge.className   = 'badge ' + (isLow ? 'bg-warning text-dark' : 'bg-success');
  }
  row.className = isLow ? 'table-warning' : '';
}

// ── 1. Use Implant (inventory page) ──────────────────────────────────────────

document.addEventListener('click', function (e) {
  var btn = e.target.closest('[data-action="use-implant"]');
  if (!btn) return;
  e.preventDefault();

  // In-flight guard: ignore rapid double-clicks
  if (btn.classList.contains('is-loading')) return;

  var row         = btn.closest('tr');
  var stockBadge  = row.querySelector('[data-stock]');
  var statusBadge = row.querySelector('[data-status-badge]');
  var minStock    = parseInt(row.dataset.minStock, 10);
  var unitsCard   = document.querySelector('[data-stat="units"]');

  var oldStock = parseInt(stockBadge.textContent, 10);
  if (oldStock <= 0) return;

  var newStock = oldStock - 1;
  var isLow    = newStock <= minStock;
  var wasLow   = oldStock <= minStock;

  // Optimistic update
  btn.classList.add('is-loading');
  applyStockState(stockBadge, statusBadge, row, newStock, isLow);
  if (unitsCard) unitsCard.textContent = parseInt(unitsCard.textContent, 10) - 1;

  var url = btn.closest('form').action;
  fetchAction(url, { method: 'POST' })
    .then(function (data) {
      btn.classList.remove('is-loading');
      if (data.ok) {
        showToast(data.message, 'info');
      } else {
        applyStockState(stockBadge, statusBadge, row, oldStock, wasLow);
        if (unitsCard) unitsCard.textContent = parseInt(unitsCard.textContent, 10) + 1;
        showToast(data.message, 'warning');
      }
    })
    .catch(function () {
      btn.classList.remove('is-loading');
      applyStockState(stockBadge, statusBadge, row, oldStock, wasLow);
      if (unitsCard) unitsCard.textContent = parseInt(unitsCard.textContent, 10) + 1;
      showToast('Action failed — please try again.', 'danger');
    });
});

// ── 2. Add Implant to Procedure ───────────────────────────────────────────────

document.addEventListener('submit', function (e) {
  var form = e.target.closest('[data-action="add-procedure-implant"]');
  if (!form) return;
  e.preventDefault();

  var formData    = new FormData(form);
  var brand       = form.dataset.brand;
  var size        = form.dataset.size;
  var quantity    = parseInt(formData.get('quantity'), 10) || 1;
  var procedureId = form.dataset.procedureId;

  var list        = document.getElementById('selected-items-list');
  var emptyMsg    = document.getElementById('no-items-msg');
  var countBadge  = document.querySelector('[data-selected-count]');

  // Optimistic: append loading placeholder
  var tempId  = 'temp-item-' + Date.now();
  var tempRow = document.createElement('div');
  tempRow.className = 'procedure-item-row';
  tempRow.id = tempId;
  tempRow.innerHTML =
    '<div>' +
      '<div class="procedure-item-name">' + brand + ' ' + size + '</div>' +
      '<div class="procedure-item-qty">Qty: ' + quantity + '</div>' +
    '</div>' +
    '<button class="btn btn-outline-danger btn-sm" disabled>' +
      '<i class="fas fa-spinner fa-spin"></i>' +
    '</button>';

  if (emptyMsg) emptyMsg.style.display = 'none';
  list.appendChild(tempRow);
  // Note: count badge is NOT incremented here — only incremented once confirmed as a new item

  fetchAction(form.action, { method: 'POST', body: formData })
    .then(function (data) {
      if (data.ok) {
        if (data.is_existing) {
          // Quantity merged into an existing item — update its display, remove placeholder
          var existingRow = list.querySelector('[data-item-id="' + data.item_id + '"]');
          if (existingRow) {
            existingRow.querySelector('.procedure-item-qty').textContent = 'Qty: ' + data.quantity;
          }
          var placeholder = document.getElementById(tempId);
          if (placeholder) placeholder.remove();
          if (emptyMsg && list.children.length === 0) emptyMsg.style.display = '';
        } else {
          // New item confirmed — replace placeholder with interactive row and bump count
          var sizeFilter  = formData.get('size_filter') || '';
          var brandFilter = formData.get('brand_filter') || '';
          var removeUrl   = '/procedures/' + procedureId + '/remove-implant/' + data.item_id;

          var realRow = document.createElement('div');
          realRow.className = 'procedure-item-row';
          realRow.dataset.itemId = data.item_id;
          realRow.innerHTML =
            '<div>' +
              '<div class="procedure-item-name">' + data.brand + ' ' + data.size + '</div>' +
              '<div class="procedure-item-qty">Qty: ' + data.quantity + '</div>' +
            '</div>' +
            '<form method="POST" action="' + removeUrl + '" class="d-inline"' +
                ' data-action="remove-procedure-implant">' +
              '<input type="hidden" name="size_filter" value="' + sizeFilter + '">' +
              '<input type="hidden" name="brand_filter" value="' + brandFilter + '">' +
              '<button type="submit" class="btn btn-outline-danger btn-sm" title="Remove">' +
                '<i class="fas fa-xmark"></i>' +
              '</button>' +
            '</form>';

          var placeholder = document.getElementById(tempId);
          if (placeholder) placeholder.replaceWith(realRow);
          if (countBadge) countBadge.textContent = parseInt(countBadge.textContent, 10) + 1;
        }
      } else {
        var placeholder = document.getElementById(tempId);
        if (placeholder) placeholder.remove();
        if (emptyMsg && list.children.length === 0) emptyMsg.style.display = '';
        showToast(data.message || 'Failed to add implant.', 'danger');
      }
    })
    .catch(function () {
      var placeholder = document.getElementById(tempId);
      if (placeholder) placeholder.remove();
      if (emptyMsg && list.children.length === 0) emptyMsg.style.display = '';
      showToast('Action failed — please try again.', 'danger');
    });
});

// ── 3. Remove Implant from Procedure ─────────────────────────────────────────

document.addEventListener('submit', function (e) {
  var form = e.target.closest('[data-action="remove-procedure-implant"]');
  if (!form) return;
  e.preventDefault();

  var formData   = new FormData(form);
  var row        = form.closest('.procedure-item-row');
  var rowHTML    = row.outerHTML;
  var parent     = row.parentNode;
  var nextSib    = row.nextSibling;
  var countBadge = document.querySelector('[data-selected-count]');
  var emptyMsg   = document.getElementById('no-items-msg');

  // Optimistic: remove the row
  row.remove();
  if (countBadge) countBadge.textContent = Math.max(0, parseInt(countBadge.textContent, 10) - 1);
  if (emptyMsg && parent.children.length === 0) emptyMsg.style.display = '';

  fetchAction(form.action, { method: 'POST', body: formData })
    .then(function (data) {
      if (!data.ok) {
        revertRemove(parent, nextSib, rowHTML, countBadge, emptyMsg);
        showToast(data.message || 'Failed to remove.', 'danger');
      }
    })
    .catch(function () {
      revertRemove(parent, nextSib, rowHTML, countBadge, emptyMsg);
      showToast('Action failed — please try again.', 'danger');
    });
});

function revertRemove(parent, nextSib, rowHTML, countBadge, emptyMsg) {
  var temp = document.createElement('div');
  temp.innerHTML = rowHTML;
  parent.insertBefore(temp.firstChild, nextSib);
  if (countBadge) countBadge.textContent = parseInt(countBadge.textContent, 10) + 1;
  if (emptyMsg) emptyMsg.style.display = 'none';
}

// ── 4. Confirm Procedure ──────────────────────────────────────────────────────

document.addEventListener('submit', function (e) {
  var form = e.target.closest('[data-action="confirm-procedure"]');
  if (!form) return;
  e.preventDefault();

  var patientName = form.dataset.patientName;
  var procedureId = form.dataset.procedureId;

  if (!confirm('Confirm procedure for ' + patientName + '?\nThis will deduct the selected implants from stock.')) return;

  var card     = form.closest('.procedure-card');
  var formData = new FormData(form);

  card.style.opacity       = '0.4';
  card.style.pointerEvents = 'none';

  fetchAction(form.action, { method: 'POST', body: formData })
    .then(function (data) {
      if (data.ok) {
        card.remove();
        showToast(data.message, 'success', { undoUrl: '/procedures/' + procedureId + '/undo' });
      } else {
        card.style.opacity       = '';
        card.style.pointerEvents = '';
        showToast(data.message, 'warning');
      }
    })
    .catch(function () {
      card.style.opacity       = '';
      card.style.pointerEvents = '';
      showToast('Confirmation failed — please try again.', 'danger');
    });
});

// ── 5. Cancel Procedure ───────────────────────────────────────────────────────

document.addEventListener('submit', function (e) {
  var form = e.target.closest('[data-action="cancel-procedure"]');
  if (!form) return;
  e.preventDefault();

  var patientName = form.dataset.patientName;
  if (!confirm('Cancel procedure for ' + patientName + '?')) return;

  var card     = form.closest('.procedure-card');
  var formData = new FormData(form);

  card.style.opacity       = '0.4';
  card.style.pointerEvents = 'none';

  fetchAction(form.action, { method: 'POST', body: formData })
    .then(function (data) {
      if (data.ok) {
        card.remove();
      } else {
        card.style.opacity       = '';
        card.style.pointerEvents = '';
        showToast(data.message || 'Cancel failed.', 'danger');
      }
    })
    .catch(function () {
      card.style.opacity       = '';
      card.style.pointerEvents = '';
      showToast('Cancel failed — please try again.', 'danger');
    });
});
