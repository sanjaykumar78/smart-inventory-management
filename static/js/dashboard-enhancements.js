document.addEventListener('DOMContentLoaded', function(){
  const table = document.getElementById('productsTable');
  const rows = Array.from(table?.querySelectorAll('tbody tr') || []);
  const liveSearch = document.getElementById('liveSearch');
  const filterCategory = document.getElementById('filterCategory');
  const filterRegion = document.getElementById('filterRegion');
  const filterStatus = document.getElementById('filterStatus');
  const emptyRow = document.getElementById('emptyTableRow');
  const addProductForm = document.getElementById('addProductForm');
  const productModal = document.getElementById('productModal');
  const modal = productModal ? new bootstrap.Modal(productModal) : null;

  function applyFilters(){
    const query = (liveSearch?.value || '').toLowerCase().trim();
    const category = (filterCategory?.value || '').toLowerCase();
    const region = (filterRegion?.value || '').toLowerCase();
    const status = (filterStatus?.value || '').toLowerCase();
    let visibleCount = 0;

    rows.forEach(function(row){
      const text = (row.textContent || '').toLowerCase();
      const rowCategory = (row.getAttribute('data-category') || '').toLowerCase();
      const rowRegion = (row.getAttribute('data-region') || '').toLowerCase();
      const rowStatus = (row.getAttribute('data-status') || '').toLowerCase();
      const matchesQuery = !query || text.includes(query);
      const matchesCategory = !category || rowCategory === category;
      const matchesRegion = !region || rowRegion === region;
      const matchesStatus = !status || rowStatus === status;
      const visible = matchesQuery && matchesCategory && matchesRegion && matchesStatus;

      row.style.display = visible ? '' : 'none';
      if(visible) visibleCount += 1;
    });

    if(emptyRow){ emptyRow.classList.toggle('d-none', visibleCount !== 0); }
  }

  [liveSearch, filterCategory, filterRegion, filterStatus].forEach(function(el){
    el?.addEventListener('input', applyFilters);
  });

  document.querySelectorAll('.delete-product').forEach(function(button){
    button.addEventListener('click', function(){
      const sku = this.getAttribute('data-sku');
      if(!confirm(`Delete ${sku}?`)) return;
      fetch(`/products/delete/${sku}`, {method:'POST'})
        .then(async function(response){
          const result = await response.json().catch(function(){ return {}; });
          if(!response.ok || !result.success){ throw new Error(result.message || 'Delete failed'); }
          this.closest('tr').remove();
          applyFilters();
        }.bind(this))
        .catch(function(error){ alert(error.message || 'Unable to delete product'); });
    });
  });

  document.getElementById('openAddProductModal')?.addEventListener('click', function(){
    addProductForm?.reset();
    modal?.show();
  });

  addProductForm?.addEventListener('submit', async function(event){
    event.preventDefault();
    const formData = new FormData(addProductForm);
    try{
      const response = await fetch('/products/add', {method:'POST', body: formData});
      const result = await response.json();
      if(!response.ok || !result.success){ throw new Error(result.message || 'Unable to add product'); }
      modal?.hide();
      addProductForm.reset();
      window.location.reload();
    } catch(error){
      alert(error.message || 'Unable to add product');
    }
  });

  applyFilters();
});

