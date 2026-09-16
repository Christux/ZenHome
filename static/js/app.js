$(function () {
    const api = (url, options = {}) => $.ajax({
        url,
        contentType: 'application/json',
        dataType: 'json',
        ...options,
        data: options.data ? JSON.stringify(options.data) : undefined
    });

    const escapeHtml = (value = '') => $('<div>').text(value).html();
    const typeClass = { NOTE: 'badge-note', CHECKLIST: 'badge-checklist', TASK: 'badge-task' };
    const statusLabel = { TODO: 'À faire', IN_PROGRESS: 'En cours', DONE: 'Terminée', CANCELLED: 'Annulée' };
    const pagePath = { dashboard: '/', notes: '/notes', checklist: '/checklists', tasks: '/tasks', kanban: '/kanban', calendar: '/calendar' };

    function showPage(page, push = false) {
        $('.nav-link[data-page]').removeClass('active');
        $(`.nav-link[data-page="${page}"]`).addClass('active');
        $('.page').addClass('d-none');
        $(`#page-${page}`).removeClass('d-none');
        $('#sidebar').removeClass('open');
        document.title = `ZenHome — ${$('.nav-link.active').text().trim() || 'Accueil'}`;
        if (push) history.pushState({ page }, '', pagePath[page]);
    }

    function itemCard(item) {
        const content = item.content ? `<div class="item-content">${escapeHtml(item.content)}</div>` : '';
        return $(
            `<div class="card item-card" data-item-id="${item.id}">
                <div class="card-body"><div class="d-flex justify-content-between">
                    <div class="flex-grow-1"><span class="type-badge ${typeClass[item.type_code]}">${item.type_code}</span>
                    <div class="item-title mt-2">${escapeHtml(item.title)}</div>${content}</div>
                    <div class="edit-actions"><button class="btn btn-sm btn-light edit-item" title="Modifier"><i class="bi bi-pencil"></i></button></div>
                </div></div>
            </div>`
        );
    }

    function renderTask(item) {
        const card = itemCard(item);
        const select = $(`<select class="form-select form-select-sm task-status-select" style="width:120px;height:32px;">
            <option value="TODO">À faire</option><option value="IN_PROGRESS">En cours</option>
            <option value="DONE">Terminée</option><option value="CANCELLED">Annulée</option></select>`);
        select.val(item.status_code);
        card.find('.edit-actions').replaceWith(select);
        return card;
    }

    function renderChecklist(item) {
        const rows = item.checklist_items.map(check => `
            <div class="check-row ${check.is_checked ? 'checked' : ''}" data-checklist-item-id="${check.id}">
                <input type="checkbox" class="form-check-input check-box" ${check.is_checked ? 'checked' : ''}>
                <span class="check-label">${escapeHtml(check.label)}</span>
                <div class="check-edit gap-1"><button class="btn btn-sm btn-light edit-check"><i class="bi bi-pencil"></i></button>
                <button class="btn btn-sm btn-light delete-check"><i class="bi bi-trash"></i></button></div>
            </div>`).join('');
        const card = $(`<div class="card item-card checklist-card" data-item-id="${item.id}"><div class="card-body">
            <div class="d-flex justify-content-between align-items-start"><div><span class="type-badge badge-checklist">CHECKLIST</span>
            <div class="item-title mt-2">${escapeHtml(item.title)}</div></div><button class="btn btn-sm btn-light edit-checklist"><i class="bi bi-pencil"></i></button></div>
            <div class="check-items mt-3">${rows}</div><div class="check-edit mt-3"><button class="btn btn-sm btn-outline-secondary add-check"><i class="bi bi-plus"></i> Ajouter une case</button></div>
            <div class="progress mt-3" style="height:5px;"><div class="progress-bar"></div></div></div></div>`);
        updateChecklistProgress(card);
        return card;
    }

    function updateChecklistProgress(card) {
        const total = card.find('.check-box').length;
        const checked = card.find('.check-box:checked').length;
        card.find('.progress-bar').css('width', total ? `${Math.round(checked / total * 100)}%` : '0%');
    }

    async function loadItems() {
        try {
            const [notes, tasks, checklists] = await Promise.all([
                api('/api/items?item_type=NOTE'), api('/api/items?item_type=TASK'), api('/api/items?item_type=CHECKLIST')
            ]);
            $('#notesList').empty().append(notes.map(itemCard));
            $('#tasksList').empty().append(tasks.map(renderTask));
            $('#page-checklist > .item-card').remove();
            const details = await Promise.all(checklists.map(item => api(`/api/items/${item.id}/detail`)));
            $('#checklistList').empty().append(details.map(renderChecklist));
        } catch (error) {
            console.error('Chargement ZenHome impossible.', error);
        }
    }

    async function loadDashboard() {
        try {
            const data = await api('/api/dashboard');
            const values = [data.counts.total || 0, data.counts.done || 0, data.counts.todo || 0, data.upcoming_occurrences.length || 0];
            $('#page-dashboard .stat-number').each((index, node) => $(node).text(values[index]));
        } catch (error) { console.error(error); }
    }

    $('.nav-link[data-page]').on('click', function (event) {
        event.preventDefault();
        showPage($(this).data('page'), true);
    });
    $('#mobileMenu').on('click', () => $('#sidebar').toggleClass('open'));

    $('#createItem').on('click', async function () {
        const title = $('#newTitle').val().trim();
        if (!title) return $('#newTitle').trigger('focus');
        const typeCode = $('#typeChecklist').is(':checked') ? 'CHECKLIST' : $('#typeTask').is(':checked') ? 'TASK' : 'NOTE';
        try {
            const item = await api('/api/items', { method: 'POST', data: { title, content: $('#newContent').val().trim() || null, type_code: typeCode } });
            const date = $('#newDate').val();
            if (date) await api(`/api/items/${item.id}/schedules`, { method: 'POST', data: { start_at: `${date}T09:00:00` } });
            $('#newTitle, #newContent, #newDate').val('');
            bootstrap.Modal.getInstance(document.getElementById('addModal')).hide();
            await loadItems(); await loadDashboard(); showPage(typeCode === 'TASK' ? 'tasks' : typeCode === 'CHECKLIST' ? 'checklist' : 'notes');
        } catch (error) { alert('Impossible de créer cet élément.'); }
    });

    $(document).on('change', '.task-status-select', async function () {
        const select = $(this), itemId = select.closest('.item-card').data('item-id');
        try { await api(`/api/items/${itemId}/status`, { method: 'PATCH', data: { status_code: select.val() } }); await loadDashboard(); }
        catch (error) { alert('Impossible de modifier le statut.'); await loadItems(); }
    });

    $(document).on('click', '.edit-item', async function () {
        const card = $(this).closest('.item-card'), itemId = card.data('item-id');
        const title = prompt('Titre :', card.find('.item-title').text().trim());
        if (title === null || !title.trim()) return;
        const content = prompt('Contenu :', card.find('.item-content').text().trim());
        try { await api(`/api/items/${itemId}`, { method: 'PATCH', data: { title: title.trim(), content } }); await loadItems(); }
        catch (error) { alert('Impossible de modifier cet élément.'); }
    });

    $(document).on('click', '.edit-checklist', function () { $(this).closest('.checklist-card').toggleClass('editing'); });
    $(document).on('change', '.check-box', async function () {
        const row = $(this).closest('.check-row'), label = row.find('.check-label').text();
        try { await api(`/api/checklist-items/${row.data('checklist-item-id')}`, { method: 'PATCH', data: { label, is_checked: $(this).is(':checked') } }); row.toggleClass('checked', $(this).is(':checked')); updateChecklistProgress(row.closest('.checklist-card')); }
        catch (error) { alert('Impossible de modifier la checklist.'); await loadItems(); }
    });
    $(document).on('click', '.add-check', async function () {
        const card = $(this).closest('.checklist-card'), label = prompt('Nom de la nouvelle case :');
        if (!label) return;
        try { await api(`/api/items/${card.data('item-id')}/checklist-items`, { method: 'POST', data: { label } }); await loadItems(); }
        catch (error) { alert('Impossible d’ajouter cette case.'); }
    });
    $(document).on('click', '.edit-check', async function () {
        const row = $(this).closest('.check-row'), label = prompt('Modifier le libellé :', row.find('.check-label').text());
        if (!label) return;
        try { await api(`/api/checklist-items/${row.data('checklist-item-id')}`, { method: 'PATCH', data: { label, is_checked: row.find('.check-box').is(':checked') } }); await loadItems(); }
        catch (error) { alert('Impossible de modifier cette case.'); }
    });
    $(document).on('click', '.delete-check', async function () {
        if (!confirm('Supprimer cette case ?')) return;
        try { await api(`/api/checklist-items/${$(this).closest('.check-row').data('checklist-item-id')}`, { method: 'DELETE' }); await loadItems(); }
        catch (error) { alert('Impossible de supprimer cette case.'); }
    });

    const initialPage = ({ '/notes': 'notes', '/checklists': 'checklist', '/tasks': 'tasks', '/kanban': 'kanban', '/calendar': 'calendar' })[location.pathname] || 'dashboard';
    showPage(initialPage); loadItems(); loadDashboard();
});
