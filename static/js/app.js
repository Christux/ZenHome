/**
 * @typedef {Object} ApiOptions
 * @property {string} [method]
 * @property {Object} [data]
 */

/**
 * @typedef {Object} Item
 * @property {number} id
 * @property {string} title
 * @property {string|null} [content]
 * @property {string} type_code
 * @property {string} [status_code]
 * @property {ChecklistItem[]} [checklist_items]
 */

/**
 * @typedef {Object} ChecklistItem
 * @property {number} id
 * @property {string} label
 * @property {boolean} is_checked
 */

/**
 * @typedef {Object} Schedule
 * @property {number} id
 * @property {string} [start_at]
 * @property {number|null} [recurrence_rule_id]
 */

/**
 * @typedef {Object} RecurrenceRule
 * @property {number} id
 * @property {string} label
 */

/**
 * @typedef {'dashboard'|'notes'|'checklist'|'tasks'|'kanban'|'calendar'} PageName
 */

/** Initialize the ZenHome interface and register its event handlers. */
$(function initializeApp() {
    /**
     * Send a JSON request to the ZenHome API.
     *
     * @param {string} url API endpoint.
     * @param {ApiOptions} [options] Request method and payload.
     * @returns {JQuery.jqXHR<any>} The pending API request.
     */
    const api = (url, options = {}) => $.ajax({
        url,
        contentType: 'application/json',
        dataType: 'json',
        ...options,
        data: options.data ? JSON.stringify(options.data) : undefined
    });

    /** @param {string|null|undefined} value @returns {string} Escaped HTML text. */
    const escapeHtml = (value = '') => $('<div>').text(value).html();
    const typeClass = { NOTE: 'badge-note', CHECKLIST: 'badge-checklist', TASK: 'badge-task' };
    const statusLabel = { TODO: 'À faire', IN_PROGRESS: 'En cours', DONE: 'Terminée', CANCELLED: 'Annulée' };
    const pagePath = { dashboard: '/', notes: '/notes', checklist: '/checklists', tasks: '/tasks', kanban: '/kanban', calendar: '/calendar' };
    let editingItem = null;
    let taskFilter = 'ALL';
    let calendarView = 'month';
    let recurrenceRules = [];
    let checklistItemOwnerId = null;
    let confirmationResolve = null;
    let createItemType = 'NOTE';
    const pageItemType = { notes: 'NOTE', checklist: 'CHECKLIST', tasks: 'TASK', kanban: 'TASK' };
    const itemTypeLabel = { NOTE: 'note', CHECKLIST: 'checklist', TASK: 'tâche' };

    /** Filter the visible page cards using the search field. */
    function applySearch() {
        const query = $('#searchInput').val().trim().toLocaleLowerCase('fr-FR');
        const page = $('.page:not(.d-none)');
        const cards = page.find('.item-card, .kanban-card');
        let matches = 0;

        /** Hide cards that do not match the current search query. */
        cards.each(function filterCardBySearch() {
            const matchesQuery = !query || $(this).text().toLocaleLowerCase('fr-FR').includes(query);
            $(this).toggleClass('search-hidden', !matchesQuery);
            if (matchesQuery) matches += 1;
        });

        page.find('.search-empty').remove();
        if (query && cards.length && matches === 0) {
            page.append('<div class="search-empty">Aucun élément ne correspond à votre recherche.</div>');
        }
    }

    /**
     * Display a page and optionally add it to the browser history.
     * @param {PageName} page Page to display.
     * @param {boolean} [push] Whether to update the browser history.
     */
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

    /** @param {Item} item Item to render. @returns {JQuery} The item card. */
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

    /** @param {Item} item Task to render. @returns {JQuery} The task card. */
    function renderTask(item) {
        const card = itemCard(item);
        const select = $(`<select class="form-select form-select-sm task-status-select" style="width:120px;height:32px;">
            <option value="TODO">À faire</option><option value="IN_PROGRESS">En cours</option>
            <option value="DONE">Terminée</option><option value="CANCELLED">Annulée</option></select>`);
        select.val(item.status_code);
        card.find('.edit-actions').replaceWith(select);
        return card;
    }

    /** Apply the selected task status filter to the task list. */
    function applyTaskFilter() {
        $('#tasksList .item-card').each(function filterTaskCard() {
            const matchesFilter = taskFilter === 'ALL' || $(this).data('item-status') === taskFilter;
            $(this).toggleClass('task-filter-hidden', !matchesFilter);
        });
    }

    /** @param {Item[]} tasks Tasks to distribute across the Kanban columns. */
    function renderKanban(tasks) {
        /** Render the tasks belonging to one Kanban column. */
        $('[data-kanban-status]').each(function renderKanbanColumn() {
            const column = $(this);
            const status = column.data('kanban-status');
            /** Keep only tasks assigned to the current column. */
            const columnTasks = tasks.filter(function filterTasksByStatus(task) {
                return task.status_code === status;
            });
            column.find('.kanban-card').remove();
            column.find('.kanban-column-count').text(columnTasks.length);
            /** Build the HTML card for one Kanban task. */
            column.append(columnTasks.map(function renderKanbanTask(task) {
                return `
                <div class="kanban-card" draggable="true" data-item-id="${task.id}" data-item-status="${task.status_code}">
                    <div class="fw-semibold small">${escapeHtml(task.title)}</div>
                    ${task.content ? `<small>${escapeHtml(task.content)}</small>` : ''}
                </div>`;
            }).join(''));
        });
    }

    /** Apply the selected calendar view to the calendar grid. */
    function renderCalendarView() {
        const days = $('#page-calendar .calendar-day');
        days.removeClass('calendar-hidden');
        if (calendarView === 'week') days.slice(0, 14).addClass('calendar-hidden');
        if (calendarView === 'day') days.not('.today').addClass('calendar-hidden');
        $('#page-calendar').attr('data-calendar-view', calendarView);
    }

    /** @param {Item} item Checklist to render. @returns {JQuery} The checklist card. */
    function renderChecklist(item) {
        /** Build the HTML row for one checklist item. */
        const rows = item.checklist_items.map(function renderChecklistItem(check) {
            return `
            <div class="check-row ${check.is_checked ? 'checked' : ''}" data-checklist-item-id="${check.id}">
                <input type="checkbox" class="form-check-input check-box" ${check.is_checked ? 'checked' : ''}>
                <span class="check-label">${escapeHtml(check.label)}</span>
                <div class="check-edit gap-1"><button class="btn btn-sm btn-light edit-check"><i class="bi bi-pencil"></i></button>
                <button class="btn btn-sm btn-light delete-check"><i class="bi bi-trash"></i></button></div>
            </div>`;
        }).join('');
        const card = $(`<div class="card item-card checklist-card" data-item-id="${item.id}" data-item-type="CHECKLIST"><div class="card-body">
            <div class="d-flex justify-content-between align-items-start"><div><span class="type-badge badge-checklist">CHECKLIST</span>
            <div class="item-title mt-2">${escapeHtml(item.title)}</div></div><div class="d-flex gap-1"><button class="btn btn-sm btn-light edit-item" title="Modifier l’élément"><i class="bi bi-pencil"></i></button><button class="btn btn-sm btn-light edit-checklist" title="Modifier les cases"><i class="bi bi-list-check"></i></button></div></div>
            <div class="check-items mt-3">${rows}</div><div class="check-edit mt-3 gap-2"><button class="btn btn-sm btn-outline-secondary add-check"><i class="bi bi-plus"></i> Ajouter une case</button><button class="btn btn-sm btn-outline-secondary reset-checklist"><i class="bi bi-arrow-counterclockwise"></i> Réinitialiser</button></div>
            <div class="progress mt-3" style="height:5px;"><div class="progress-bar"></div></div></div></div>`);
        card.data('item', { id: item.id, title: item.title, content: item.content, type_code: 'CHECKLIST' });
        updateChecklistProgress(card);
        return card;
    }

    /** @param {JQuery} card Checklist card whose progress bar must be updated. */
    function updateChecklistProgress(card) {
        const total = card.find('.check-box').length;
        const checked = card.find('.check-box:checked').length;
        card.find('.progress-bar').css('width', total ? `${Math.round(checked / total * 100)}%` : '0%');
    }

    /** Load notes, tasks, and checklists, then refresh their views. */
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
            /** Load the detailed representation of one checklist. */
            const details = await Promise.all(checklists.map(function loadChecklistDetails(item) {
                return api(`/api/items/${item.id}/detail`);
            }));
            $('#checklistList').empty().append(details.map(renderChecklist));
            applySearch();
        } catch (error) {
            console.error('Chargement ZenHome impossible.', error);
        }
    }

    /** Load recurrence rules used by the create and edit forms. */
    async function loadRecurrenceRules() {
        try {
            recurrenceRules = await api('/api/recurrence-rules');
            $('#newRecurrence').empty().append('<option value="">Aucune</option>');
            /** Add one recurrence rule to the selector. */
            recurrenceRules.forEach(function renderRecurrenceRule(rule) {
                $('#newRecurrence').append($('<option>', { value: rule.id, text: rule.label }));
            });
        } catch (error) {
            console.error('Chargement des récurrences impossible.', error);
        }
    }

    /** Load dashboard counters from the API. */
    async function loadDashboard() {
        try {
            const data = await api('/api/dashboard');
            const values = [data.counts.total || 0, data.counts.done || 0, data.counts.todo || 0, data.upcoming_occurrences.length || 0];
            /** Display one dashboard counter value. */
            $('#page-dashboard .stat-number').each(function renderDashboardValue(index, node) {
                $(node).text(values[index]);
            });
        } catch (error) { console.error(error); }
    }

    /** Navigate to the page selected in the sidebar. */
    $('.nav-link[data-page]').on('click', function handlePageNavigation(event) {
        event.preventDefault();
        showPage($(this).data('page'), true);
    });
    /** Toggle the mobile sidebar visibility. */
    $('#mobileMenu').on('click', function toggleMobileMenu() {
        $('#sidebar').toggleClass('open');
    });
    $('#searchInput').on('input search', applySearch);
    /** Apply the task status selected by the user. */
    $('#taskFilters [data-task-status]').on('click', function handleTaskFilterChange() {
        taskFilter = $(this).data('task-status');
        $('#taskFilters [data-task-status]').removeClass('active');
        $(this).addClass('active');
        applyTaskFilter();
    });
    /** Apply the calendar view selected by the user. */
    $('[data-calendar-view]').on('click', function handleCalendarViewChange() {
        calendarView = $(this).data('calendar-view');
        $('[data-calendar-view]').removeClass('active');
        $(this).addClass('active');
        renderCalendarView();
    });
    $('.floating-add').on('click', prepareCreateModal);

    /** @param {JQuery} card Checklist card receiving the new item. */
    function openChecklistItemModal(card) {
        checklistItemOwnerId = card.data('item-id');
        $('#checklistItemLabel').val('');
        bootstrap.Modal.getOrCreateInstance(document.getElementById('checklistItemModal')).show();
        /** Focus the checklist item label after the modal opens. */
        $('#checklistItemModal').one('shown.bs.modal', function focusChecklistItemLabel() {
            $('#checklistItemLabel').trigger('focus');
        });
    }

    /**
     * Display the shared confirmation modal and wait for the user's choice.
     * @param {{title: string, message: string, confirmLabel?: string, variant?: string}} options Modal content.
     * @returns {Promise<boolean>} Whether the action was confirmed.
     */
    function requestConfirmation({ title, message, confirmLabel = 'Confirmer', variant = 'dark' }) {
        /** Resolve the confirmation promise when the modal is answered. */
        return new Promise(function createConfirmationPromise(resolve) {
            confirmationResolve = resolve;
            $('#confirmationModalTitle').text(title);
            $('#confirmationModalMessage').text(message);
            $('#confirmAction').text(confirmLabel).removeClass('btn-dark btn-danger btn-primary').addClass(`btn-${variant}`);
            bootstrap.Modal.getOrCreateInstance(document.getElementById('confirmationModal')).show();
        });
    }

    /** @param {boolean} value Confirmation result. */
    function resolveConfirmation(value) {
        if (!confirmationResolve) return;
        const resolve = confirmationResolve;
        confirmationResolve = null;
        resolve(value);
    }

    /** Reset and prepare the modal for creating an item. */
    function prepareCreateModal() {
        editingItem = null;
        const activePage = $('.page:not(.d-none)').attr('id')?.replace('page-', '');
        createItemType = pageItemType[activePage] || 'NOTE';
        const today = new Date();
        const todayValue = [today.getFullYear(), String(today.getMonth() + 1).padStart(2, '0'), String(today.getDate()).padStart(2, '0')].join('-');
        $('#itemModalTitle').text(`Nouvelle ${itemTypeLabel[createItemType]}`);
        $('#createItem').text('Créer');
        $('#newTitle, #newContent').val('');
        $('#newDate').val(todayValue);
        $('#newRecurrence').val('');
    }

    /** @param {JQuery} card Card containing the item to edit. */
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
        bootstrap.Modal.getOrCreateInstance(document.getElementById('addModal')).show();
    }

    /** Create a new item or save the item currently being edited. */
    $('#createItem').on('click', async function handleItemSubmit() {
        const title = $('#newTitle').val().trim();
        if (!title) return $('#newTitle').trigger('focus');
        try {
            if (editingItem) {
                await api(`/api/items/${editingItem.id}`, { method: 'PATCH', data: { title, content: $('#newContent').val().trim() || null } });
                const schedules = await api(`/api/items/${editingItem.id}/schedules`);
                /** Delete one existing schedule before replacing it. */
                await Promise.all(schedules.map(function deleteSchedule(schedule) {
                    return api(`/api/schedules/${schedule.id}`, { method: 'DELETE' });
                }));
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
            const item = await api('/api/items', { method: 'POST', data: { title, content: $('#newContent').val().trim() || null, type_code: createItemType } });
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
            await loadItems(); await loadDashboard();
        } catch (error) { alert(editingItem ? 'Impossible de modifier cet élément.' : 'Impossible de créer cet élément.'); }
    });

    /** Persist a task status selected from a task card. */
    $(document).on('change', '.task-status-select', async function handleTaskStatusChange() {
        const select = $(this), itemId = select.closest('.item-card').data('item-id');
        try {
            await api(`/api/items/${itemId}/status`, { method: 'PATCH', data: { status_code: select.val() } });
            select.closest('.item-card').data('item-status', select.val()).attr('data-item-status', select.val());
            applyTaskFilter();
            await loadDashboard();
        }
        catch (error) { alert('Impossible de modifier le statut.'); await loadItems(); }
    });

    /** Start moving a task card between Kanban columns. */
    $(document).on('dragstart', '.kanban-card', function handleKanbanDragStart(event) {
        $(this).addClass('dragging');
        event.originalEvent.dataTransfer.effectAllowed = 'move';
        event.originalEvent.dataTransfer.setData('text/plain', String($(this).data('item-id')));
    });

    /** Clear Kanban drag state after a drag operation ends. */
    $(document).on('dragend', '.kanban-card', function handleKanbanDragEnd() {
        $('.kanban-card').removeClass('dragging');
        $('[data-kanban-status]').removeClass('drag-over');
    });

    /** Mark a Kanban column as a valid drop target. */
    $(document).on('dragover', '[data-kanban-status]', function handleKanbanDragOver(event) {
        event.preventDefault();
        event.originalEvent.dataTransfer.dropEffect = 'move';
        $(this).addClass('drag-over');
    });

    /** Remove the drop target state when a card leaves a column. */
    $(document).on('dragleave', '[data-kanban-status]', function handleKanbanDragLeave(event) {
        if (!this.contains(event.relatedTarget)) $(this).removeClass('drag-over');
    });

    /** Persist a task status after dropping it into a Kanban column. */
    $(document).on('drop', '[data-kanban-status]', async function handleKanbanDrop(event) {
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

    /** Open the edit modal for the selected item. */
    $(document).on('click', '.edit-item', async function handleItemEdit() {
        try {
            await openEditModal($(this).closest('.item-card'));
        } catch (error) {
            alert('Impossible de charger la planification.');
        }
    });

    /** Toggle checklist editing controls. */
    $(document).on('click', '.edit-checklist', function toggleChecklistEditing() { $(this).closest('.checklist-card').toggleClass('editing'); });
    /** Persist a checklist item's checked state. */
    $(document).on('change', '.check-box', async function handleChecklistItemToggle() {
        const row = $(this).closest('.check-row'), label = row.find('.check-label').text();
        try { await api(`/api/checklist-items/${row.data('checklist-item-id')}`, { method: 'PATCH', data: { label, is_checked: $(this).is(':checked') } }); row.toggleClass('checked', $(this).is(':checked')); updateChecklistProgress(row.closest('.checklist-card')); }
        catch (error) { alert('Impossible de modifier la checklist.'); await loadItems(); }
    });
    /** Open the modal for adding a checklist item. */
    $(document).on('click', '.add-check', async function handleAddChecklistItem() {
        openChecklistItemModal($(this).closest('.checklist-card'));
    });
    /** Create the checklist item entered in the modal. */
    $('#addChecklistItem').on('click', async function handleChecklistItemSubmit() {
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
    /** Reset every checked item in a checklist after confirmation. */
    $(document).on('click', '.reset-checklist', async function handleChecklistReset() {
        const card = $(this).closest('.checklist-card');
        const confirmed = await requestConfirmation({
            title: 'Réinitialiser la checklist ?',
            message: 'Toutes les cases seront décochées.',
            confirmLabel: 'Réinitialiser',
            variant: 'primary'
        });
        if (!confirmed) return;
        $(this).prop('disabled', true);
        try {
            await api(`/api/items/${card.data('item-id')}/checklist-items/reset`, { method: 'POST' });
            await loadItems();
        } catch (error) {
            alert('Impossible de réinitialiser la checklist.');
            $(this).prop('disabled', false);
        }
    });
    /** Edit and persist a checklist item label. */
    $(document).on('click', '.edit-check', async function handleChecklistItemEdit() {
        const row = $(this).closest('.check-row'), label = prompt('Modifier le libellé :', row.find('.check-label').text());
        if (!label) return;
        try { await api(`/api/checklist-items/${row.data('checklist-item-id')}`, { method: 'PATCH', data: { label, is_checked: row.find('.check-box').is(':checked') } }); await loadItems(); }
        catch (error) { alert('Impossible de modifier cette case.'); }
    });
    /** Delete a checklist item after confirmation. */
    $(document).on('click', '.delete-check', async function handleChecklistItemDelete() {
        const confirmed = await requestConfirmation({
            title: 'Supprimer cette case ?',
            message: 'Cette action est irréversible.',
            confirmLabel: 'Supprimer',
            variant: 'danger'
        });
        if (!confirmed) return;
        try { await api(`/api/checklist-items/${$(this).closest('.check-row').data('checklist-item-id')}`, { method: 'DELETE' }); await loadItems(); }
        catch (error) { alert('Impossible de supprimer cette case.'); }
    });

    /** Confirm the action currently displayed in the confirmation modal. */
    $('#confirmAction').on('click', function handleConfirmation() {
        resolveConfirmation(true);
        bootstrap.Modal.getInstance(document.getElementById('confirmationModal')).hide();
    });
    /** Cancel a confirmation when its modal closes without approval. */
    $('#confirmationModal').on('hidden.bs.modal', function handleConfirmationDismissal() {
        resolveConfirmation(false);
    });

    const initialPage = ({ '/notes': 'notes', '/checklists': 'checklist', '/tasks': 'tasks', '/kanban': 'kanban', '/calendar': 'calendar' })[location.pathname] || 'dashboard';
    showPage(initialPage); renderCalendarView(); loadRecurrenceRules(); loadItems(); loadDashboard();
});
