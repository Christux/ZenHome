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
    let editingItem = null;
    let taskFilter = 'ALL';
    let calendarView = 'month';
    let recurrenceRules = [];
    let checklistItemOwnerId = null;

    function applySearch() {
        const query = $('#searchInput').val().trim().toLocaleLowerCase('fr-FR');
        const page = $('.page:not(.d-none)');
        const cards = page.find('.item-card, .kanban-card');
        let matches = 0;

        cards.each(function () {
            const matchesQuery = !query || $(this).text().toLocaleLowerCase('fr-FR').includes(query);
            $(this).toggleClass('search-hidden', !matchesQuery);
            if (matchesQuery) matches += 1;
        });

        page.find('.search-empty').remove();
        if (query && cards.length && matches === 0) {
            page.append('<div class="search-empty">Aucun élément ne correspond à votre recherche.</div>');
        }
    }

    function showPage(page, push = false) {
        $('.nav-link[data-page]').removeClass('active');
        $(`.nav-link[data-page="${page}"]`).addClass('active');
        $('.page').addClass('d-none');
        $(`#page-${page}`).removeClass('d-none');
        $('#sidebar').removeClass('open');
        document.title = `ZenHome — ${$('.nav-link.active').text().trim() || 'Accueil'}`;
        if (push) history.pushState({ page }, '', pagePath[page]);
        applySearch();
    }

    function itemCard(item) {
        const content = item.content ? `<div class="item-content">${escapeHtml(item.content)}</div>` : '';
        const card = $(
            `<div class="card item-card" data-item-id="${item.id}" data-item-type="${item.type_code}" data-item-status="${item.status_code}">
                <div class="card-body"><div class="d-flex justify-content-between">
                    <div class="flex-grow-1"><span class="type-badge ${typeClass[item.type_code]}">${item.type_code}</span>
                    <div class="item-title mt-2">${escapeHtml(item.title)}</div>${content}</div>
                    <div class="edit-actions"><button class="btn btn-sm btn-light edit-item" title="Modifier"><i class="bi bi-pencil"></i></button></div>
                </div></div>
            </div>`
        );
        return card.data('item', item);
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

    function applyTaskFilter() {
        $('#tasksList .item-card').each(function () {
            const matchesFilter = taskFilter === 'ALL' || $(this).data('item-status') === taskFilter;
            $(this).toggleClass('task-filter-hidden', !matchesFilter);
        });
    }

    function renderKanban(tasks) {
        $('[data-kanban-status]').each(function () {
            const column = $(this);
            const status = column.data('kanban-status');
            const columnTasks = tasks.filter(task => task.status_code === status);
            column.find('.kanban-card').remove();
            column.find('.kanban-column-count').text(columnTasks.length);
            column.append(columnTasks.map(task => `
                <div class="kanban-card" draggable="true" data-item-id="${task.id}" data-item-status="${task.status_code}">
                    <div class="fw-semibold small">${escapeHtml(task.title)}</div>
                    ${task.content ? `<small>${escapeHtml(task.content)}</small>` : ''}
                </div>`).join(''));
        });
    }

    function renderCalendarView() {
        const days = $('#page-calendar .calendar-day');
        days.removeClass('calendar-hidden');
        if (calendarView === 'week') days.slice(0, 14).addClass('calendar-hidden');
        if (calendarView === 'day') days.not('.today').addClass('calendar-hidden');
        $('#page-calendar').attr('data-calendar-view', calendarView);
    }

    function renderChecklist(item) {
        const rows = item.checklist_items.map(check => `
            <div class="check-row ${check.is_checked ? 'checked' : ''}" data-checklist-item-id="${check.id}">
                <input type="checkbox" class="form-check-input check-box" ${check.is_checked ? 'checked' : ''}>
                <span class="check-label">${escapeHtml(check.label)}</span>
                <div class="check-edit gap-1"><button class="btn btn-sm btn-light edit-check"><i class="bi bi-pencil"></i></button>
                <button class="btn btn-sm btn-light delete-check"><i class="bi bi-trash"></i></button></div>
            </div>`).join('');
        const card = $(`<div class="card item-card checklist-card" data-item-id="${item.id}" data-item-type="CHECKLIST"><div class="card-body">
            <div class="d-flex justify-content-between align-items-start"><div><span class="type-badge badge-checklist">CHECKLIST</span>
            <div class="item-title mt-2">${escapeHtml(item.title)}</div></div><div class="d-flex gap-1"><button class="btn btn-sm btn-light edit-item" title="Modifier l’élément"><i class="bi bi-pencil"></i></button><button class="btn btn-sm btn-light edit-checklist" title="Modifier les cases"><i class="bi bi-list-check"></i></button></div></div>
            <div class="check-items mt-3">${rows}</div><div class="check-edit mt-3"><button class="btn btn-sm btn-outline-secondary add-check"><i class="bi bi-plus"></i> Ajouter une case</button></div>
            <div class="progress mt-3" style="height:5px;"><div class="progress-bar"></div></div></div></div>`);
        card.data('item', { id: item.id, title: item.title, content: item.content, type_code: 'CHECKLIST' });
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
            $('#notesCount').text(notes.length);
            $('#tasksCount').text(tasks.length);
            $('#checklistsCount').text(checklists.length);
            $('#notesList').empty().append(notes.map(itemCard));
            $('#tasksList').empty().append(tasks.map(renderTask));
            renderKanban(tasks);
            applyTaskFilter();
            $('#page-checklist > .item-card').remove();
            const details = await Promise.all(checklists.map(item => api(`/api/items/${item.id}/detail`)));
            $('#checklistList').empty().append(details.map(renderChecklist));
            applySearch();
        } catch (error) {
            console.error('Chargement ZenHome impossible.', error);
        }
    }

    async function loadRecurrenceRules() {
        try {
            recurrenceRules = await api('/api/recurrence-rules');
            $('#newRecurrence').empty().append('<option value="">Aucune</option>');
            recurrenceRules.forEach(rule => {
                $('#newRecurrence').append($('<option>', { value: rule.id, text: rule.label }));
            });
        } catch (error) {
            console.error('Chargement des récurrences impossible.', error);
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
    $('#searchInput').on('input search', applySearch);
    $('#taskFilters [data-task-status]').on('click', function () {
        taskFilter = $(this).data('task-status');
        $('#taskFilters [data-task-status]').removeClass('active');
        $(this).addClass('active');
        applyTaskFilter();
    });
    $('[data-calendar-view]').on('click', function () {
        calendarView = $(this).data('calendar-view');
        $('[data-calendar-view]').removeClass('active');
        $(this).addClass('active');
        renderCalendarView();
    });
    $('.floating-add').on('click', prepareCreateModal);

    function openChecklistItemModal(card) {
        checklistItemOwnerId = card.data('item-id');
        $('#checklistItemLabel').val('');
        bootstrap.Modal.getOrCreateInstance(document.getElementById('checklistItemModal')).show();
        $('#checklistItemModal').one('shown.bs.modal', () => $('#checklistItemLabel').trigger('focus'));
    }

    function prepareCreateModal() {
        editingItem = null;
        $('#itemModalTitle').text('Nouvel élément');
        $('#createItem').text('Créer');
        $('#newTitle, #newContent, #newDate').val('');
        $('#newRecurrence').val('');
        $('#typeNote').prop('checked', true);
        $('input[name="itemType"]').prop('disabled', false);
        $('#itemTypeField').removeClass('d-none');
    }

    async function openEditModal(card) {
        const item = card.data('item') || {
            id: card.data('item-id'),
            title: card.find('.item-title').text().trim(),
            content: card.find('.item-content').text().trim(),
            type_code: card.data('item-type')
        };
        const details = await api(`/api/items/${item.id}/detail`);
        const schedule = details.schedules?.[0];
        editingItem = item;
        $('#itemModalTitle').text('Modifier l’élément');
        $('#createItem').text('Enregistrer');
        $('#newTitle').val(item.title || '');
        $('#newContent').val(item.content || '');
        $('#newDate').val(schedule?.start_at?.slice(0, 10) || '');
        $('#newRecurrence').val(schedule?.recurrence_rule_id || '');
        $(`#type${item.type_code === 'CHECKLIST' ? 'Checklist' : item.type_code === 'TASK' ? 'Task' : 'Note'}`).prop('checked', true);
        $('input[name="itemType"]').prop('disabled', true);
        $('#itemTypeField').addClass('d-none');
        bootstrap.Modal.getOrCreateInstance(document.getElementById('addModal')).show();
    }

    $('#createItem').on('click', async function () {
        const title = $('#newTitle').val().trim();
        if (!title) return $('#newTitle').trigger('focus');
        const typeCode = $('#typeChecklist').is(':checked') ? 'CHECKLIST' : $('#typeTask').is(':checked') ? 'TASK' : 'NOTE';
        try {
            if (editingItem) {
                await api(`/api/items/${editingItem.id}`, { method: 'PATCH', data: { title, content: $('#newContent').val().trim() || null } });
                const schedules = await api(`/api/items/${editingItem.id}/schedules`);
                await Promise.all(schedules.map(schedule => api(`/api/schedules/${schedule.id}`, { method: 'DELETE' })));
                const date = $('#newDate').val();
                if (date) {
                    await api(`/api/items/${editingItem.id}/schedules`, {
                        method: 'POST',
                        data: {
                            start_at: `${date}T09:00:00`,
                            recurrence_rule_id: $('#newRecurrence').val() ? Number($('#newRecurrence').val()) : null
                        }
                    });
                }
                bootstrap.Modal.getInstance(document.getElementById('addModal')).hide();
                await loadItems(); await loadDashboard();
                return;
            }
            const item = await api('/api/items', { method: 'POST', data: { title, content: $('#newContent').val().trim() || null, type_code: typeCode } });
            const date = $('#newDate').val();
            if (date) await api(`/api/items/${item.id}/schedules`, {
                method: 'POST',
                data: {
                    start_at: `${date}T09:00:00`,
                    recurrence_rule_id: $('#newRecurrence').val() ? Number($('#newRecurrence').val()) : null
                }
            });
            $('#newTitle, #newContent, #newDate').val('');
            bootstrap.Modal.getInstance(document.getElementById('addModal')).hide();
            await loadItems(); await loadDashboard(); showPage(typeCode === 'TASK' ? 'tasks' : typeCode === 'CHECKLIST' ? 'checklist' : 'notes');
        } catch (error) { alert(editingItem ? 'Impossible de modifier cet élément.' : 'Impossible de créer cet élément.'); }
    });

    $(document).on('change', '.task-status-select', async function () {
        const select = $(this), itemId = select.closest('.item-card').data('item-id');
        try {
            await api(`/api/items/${itemId}/status`, { method: 'PATCH', data: { status_code: select.val() } });
            select.closest('.item-card').data('item-status', select.val()).attr('data-item-status', select.val());
            applyTaskFilter();
            await loadDashboard();
        }
        catch (error) { alert('Impossible de modifier le statut.'); await loadItems(); }
    });

    $(document).on('dragstart', '.kanban-card', function (event) {
        $(this).addClass('dragging');
        event.originalEvent.dataTransfer.effectAllowed = 'move';
        event.originalEvent.dataTransfer.setData('text/plain', String($(this).data('item-id')));
    });

    $(document).on('dragend', '.kanban-card', function () {
        $('.kanban-card').removeClass('dragging');
        $('[data-kanban-status]').removeClass('drag-over');
    });

    $(document).on('dragover', '[data-kanban-status]', function (event) {
        event.preventDefault();
        event.originalEvent.dataTransfer.dropEffect = 'move';
        $(this).addClass('drag-over');
    });

    $(document).on('dragleave', '[data-kanban-status]', function (event) {
        if (!this.contains(event.relatedTarget)) $(this).removeClass('drag-over');
    });

    $(document).on('drop', '[data-kanban-status]', async function (event) {
        event.preventDefault();
        const column = $(this);
        const itemId = event.originalEvent.dataTransfer.getData('text/plain');
        const statusCode = column.data('kanban-status');
        const card = $(`.kanban-card[data-item-id="${itemId}"]`);
        if (!itemId || !card.length || card.data('item-status') === statusCode) return column.removeClass('drag-over');
        column.removeClass('drag-over');
        card.addClass('dragging');
        try {
            await api(`/api/items/${itemId}/status`, { method: 'PATCH', data: { status_code: statusCode } });
            await loadItems();
            await loadDashboard();
        } catch (error) {
            alert('Impossible de modifier le statut.');
        } finally {
            $('.kanban-card').removeClass('dragging');
        }
    });

    $(document).on('click', '.edit-item', async function () {
        try {
            await openEditModal($(this).closest('.item-card'));
        } catch (error) {
            alert('Impossible de charger la planification.');
        }
    });

    $(document).on('click', '.edit-checklist', function () { $(this).closest('.checklist-card').toggleClass('editing'); });
    $(document).on('change', '.check-box', async function () {
        const row = $(this).closest('.check-row'), label = row.find('.check-label').text();
        try { await api(`/api/checklist-items/${row.data('checklist-item-id')}`, { method: 'PATCH', data: { label, is_checked: $(this).is(':checked') } }); row.toggleClass('checked', $(this).is(':checked')); updateChecklistProgress(row.closest('.checklist-card')); }
        catch (error) { alert('Impossible de modifier la checklist.'); await loadItems(); }
    });
    $(document).on('click', '.add-check', async function () {
        openChecklistItemModal($(this).closest('.checklist-card'));
    });
    $('#addChecklistItem').on('click', async function () {
        const label = $('#checklistItemLabel').val().trim();
        if (!label || !checklistItemOwnerId) return $('#checklistItemLabel').trigger('focus');
        $(this).prop('disabled', true);
        try {
            await api(`/api/items/${checklistItemOwnerId}/checklist-items`, { method: 'POST', data: { label } });
            bootstrap.Modal.getInstance(document.getElementById('checklistItemModal')).hide();
            await loadItems();
        } catch (error) {
            alert('Impossible d’ajouter cette case.');
        } finally {
            $(this).prop('disabled', false);
        }
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
    showPage(initialPage); renderCalendarView(); loadRecurrenceRules(); loadItems(); loadDashboard();
});
