/**
 * @typedef {Object} ApiOptions
 * @property {string} [method]
 * @property {Object} [data]
 * @property {string} [dataType]
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
    const itemUpdateChannel = 'BroadcastChannel' in window ? new BroadcastChannel('zenhome-item-updates') : null;
    let sharedRefreshTimer = null;

    /** Notify other open ZenHome tabs after a successful write. */
    function notifyOtherTabs() {
        const update = { updatedAt: Date.now() };
        if (itemUpdateChannel) {
            itemUpdateChannel.postMessage(update);
            return;
        }
        try {
            localStorage.setItem('zenhome-item-updated', JSON.stringify(update));
        } catch (error) {
            // Cross-tab refresh is unavailable when browser storage is disabled.
        }
    }

    /**
     * Send a JSON request to the ZenHome API.
     *
     * @param {string} url API endpoint.
     * @param {ApiOptions} [options] Request method and payload.
     * @returns {JQuery.jqXHR<any>} The pending API request.
     */
    const api = (url, options = {}) => {
        const method = (options.method || 'GET').toUpperCase();
        const request = $.ajax({
            url,
            contentType: 'application/json',
            dataType: options.dataType ?? (method === 'DELETE' ? undefined : 'json'),
            ...options,
            data: options.data ? JSON.stringify(options.data) : undefined
        });
        if (method !== 'GET' && method !== 'HEAD') {
            request.done(function syncUpdatedItem() {
                notifyOtherTabs();
                scheduleSharedRefresh();
            });
        }
        return request;
    };

    /** @param {string|null|undefined} value @returns {string} Escaped HTML text. */
    const escapeHtml = (value = '') => $('<div>').text(value).html();
    const typeClass = { NOTE: 'badge-note', CHECKLIST: 'badge-checklist', TASK: 'badge-task' };
    const calendarTypeClass = { NOTE: 'note', CHECKLIST: 'checklist', TASK: 'task' };
    const statusLabel = { TODO: 'À faire', IN_PROGRESS: 'En cours', DONE: 'Terminée', CANCELLED: 'Annulée' };
    const pagePath = { dashboard: '/', notes: '/notes', checklist: '/checklists', tasks: '/tasks', kanban: '/kanban', calendar: '/calendar' };
    let editingItem = null;
    let taskFilter = 'ALL';
    let calendarView = 'month';
    let calendarDate = new Date();
    let recurrenceRules = [];
    let checklistItemOwnerId = null;
    let confirmationResolve = null;
    let currentItemId = null;
    let createItemType = 'NOTE';
    const pageItemType = { notes: 'NOTE', checklist: 'CHECKLIST', tasks: 'TASK', kanban: 'TASK' };
    const itemTypeLabel = { NOTE: 'note', CHECKLIST: 'checklist', TASK: 'tâche' };

    /** Reload the page when backend or frontend files change in development. */
    function startDevelopmentReload() {
        let previousSignature = null;
        const checkForChanges = async function checkForChanges() {
            try {
                const response = await fetch('/api/dev/version', { cache: 'no-store' });
                if (response.status === 404) return false;
                if (!response.ok) return true;
                const { signature } = await response.json();
                if (previousSignature && signature !== previousSignature) location.reload();
                previousSignature = signature;
            } catch (error) {
                // The development server may be restarting after a backend edit.
            }
            return true;
        };

        const interval = setInterval(async function pollDevelopmentVersion() {
            if (!await checkForChanges()) clearInterval(interval);
        }, 1000);
        checkForChanges();
    }

    /** Filter the visible page cards using the search field. */
    function applySearch() {
        const query = $('#searchInput').val().trim().toLocaleLowerCase('fr-FR');
        const page = $('.page:not(.d-none)');
        const cards = page.find('.item-card, .kanban-card, .dashboard-occurrence');
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
        $('#itemDetailScreen').addClass('d-none').attr('aria-busy', 'false');
        currentItemId = null;
        $('#sidebar').removeClass('open');
        document.title = `ZenHome — ${$('.nav-link.active').text().trim() || 'Accueil'}`;
        if (push) history.pushState({ page }, '', pagePath[page]);
        applySearch();
    }

    /** @param {Item} item Item to render. @returns {JQuery} The item card. */
    function itemCard(item) {
        const content = item.content ? `<div class="item-content">${escapeHtml(item.content)}</div>` : '';
        const deleteButton = '<button class="btn btn-sm btn-light delete-item" title="Supprimer"><i class="bi bi-trash"></i></button>';
        const card = $(
            `<div class="card item-card item-openable" data-item-id="${item.id}" data-item-type="${item.type_code}" data-item-status="${item.status_code}" role="group" aria-label="Ouvrir l’élément : ${escapeHtml(item.title)}" tabindex="0">
                <div class="card-body"><div class="d-flex justify-content-between">
                    <div class="flex-grow-1"><span class="type-badge ${typeClass[item.type_code]}">${item.type_code}</span>
                    <div class="item-title mt-2">${escapeHtml(item.title)}</div>${content}</div>
                    <div class="edit-actions"><button class="btn btn-sm btn-light edit-item" title="Modifier"><i class="bi bi-pencil"></i></button>${deleteButton}</div>
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
        card.find('.edit-actions').before(select);
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
                <div class="kanban-card item-openable" draggable="true" data-item-id="${task.id}" data-item-type="TASK" data-item-status="${task.status_code}" role="link" tabindex="0">
                    <div class="fw-semibold small">${escapeHtml(task.title)}</div>
                    ${task.content ? `<small>${escapeHtml(task.content)}</small>` : ''}
                </div>`;
            }).join(''));
        });
    }

    /** @param {Date} value Date to format for the occurrences API. @returns {string} Local ISO date. */
    function calendarDateValue(value) {
        return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
    }

    /** @param {Date} value Date to clone. @param {number} amount Number of days. @returns {Date} Shifted date. */
    function shiftCalendarDate(value, amount) {
        const shifted = new Date(value);
        shifted.setDate(shifted.getDate() + amount);
        return shifted;
    }

    /** @param {Date} value Date to clone. @param {number} amount Number of months. @returns {Date} Shifted month. */
    function shiftCalendarMonth(value, amount) {
        const targetMonth = new Date(value.getFullYear(), value.getMonth() + amount, 1);
        const lastDay = new Date(targetMonth.getFullYear(), targetMonth.getMonth() + 1, 0).getDate();
        return new Date(targetMonth.getFullYear(), targetMonth.getMonth(), Math.min(value.getDate(), lastDay));
    }

    /** @returns {{start: Date, end: Date, days: Date[]}} Dates visible in the selected calendar view. */
    function calendarRange() {
        const mondayOffset = (calendarDate.getDay() + 6) % 7;
        let start = new Date(calendarDate);
        let dayCount = 1;
        if (calendarView === 'month') {
            start = new Date(calendarDate.getFullYear(), calendarDate.getMonth(), 1);
            start = shiftCalendarDate(start, (start.getDay() + 6) % 7 * -1);
            dayCount = 42;
        } else if (calendarView === 'week') {
            start = shiftCalendarDate(start, -mondayOffset);
            dayCount = 7;
        }
        const days = Array.from({ length: dayCount }, (_, index) => shiftCalendarDate(start, index));
        return { start, end: shiftCalendarDate(start, dayCount - 1), days };
    }

    /** Update the calendar heading for the selected view. */
    function renderCalendarLabel(range) {
        const formatter = new Intl.DateTimeFormat('fr-FR', { month: 'long', year: 'numeric' });
        let label = formatter.format(calendarDate);
        if (calendarView === 'week') {
            label = `${range.start.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })} - ${range.end.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })}`;
        } else if (calendarView === 'day') {
            label = calendarDate.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
        }
        $('#calendarPeriodLabel').text(label.charAt(0).toUpperCase() + label.slice(1));
    }

    /** @param {Date} day Day to render. @param {object[]} occurrences Occurrences for the visible range. @param {boolean} muted Whether the day belongs to another month. @returns {string} Day HTML. */
    function renderCalendarDay(day, occurrences, muted) {
        const dayValue = calendarDateValue(day);
        const events = occurrences.filter(occurrence => occurrence.starts_at.startsWith(dayValue));
        const today = dayValue === calendarDateValue(new Date());
        const eventHtml = events.map(occurrence => `
            <div class="calendar-event ${calendarTypeClass[occurrence.type_code] || ''} item-openable" title="${escapeHtml(occurrence.item_title)}" data-occurrence-id="${occurrence.id}" data-item-id="${occurrence.item_id}" role="link" tabindex="0">
                ${escapeHtml(occurrence.item_title)}
            </div>`).join('');
        return `<div class="calendar-day${muted ? ' muted' : ''}${today ? ' today' : ''}" data-calendar-date="${dayValue}">
            <div class="day-number">${day.getDate()}</div>${eventHtml}
        </div>`;
    }

    /** Load real occurrences and render the selected calendar view. */
    async function renderCalendarView() {
        const range = calendarRange();
        const endExclusive = shiftCalendarDate(range.end, 1);
        $('#page-calendar').attr('data-calendar-view', calendarView);
        renderCalendarLabel(range);
        const weekdays = calendarView === 'day' ? '' : ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
            .map(day => `<div class="calendar-weekday">${day}</div>`).join('');
        $('#calendarGrid').html(`${weekdays}<div class="calendar-loading">Chargement...</div>`);
        try {
            const occurrences = await api(`/api/occurrences?start_at=${calendarDateValue(range.start)}T00:00:00&end_at=${calendarDateValue(endExclusive)}T00:00:00`);
            const cells = range.days.map(day => renderCalendarDay(
                day,
                occurrences,
                calendarView === 'month' && day.getMonth() !== calendarDate.getMonth(),
            )).join('');
            $('#calendarGrid').html(`${weekdays}${cells}`);
        } catch (error) {
            $('#calendarGrid').html(`${weekdays}<div class="calendar-loading">Impossible de charger les occurrences.</div>`);
            console.error('Chargement du calendrier impossible.', error);
        }
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
        const card = $(`<div class="card item-card checklist-card item-openable" data-item-id="${item.id}" data-item-type="CHECKLIST" data-item-status="${item.status_code || ''}" role="group" aria-label="Ouvrir l’élément : ${escapeHtml(item.title)}" tabindex="0"><div class="card-body">
            <div class="d-flex justify-content-between align-items-start"><div><span class="type-badge badge-checklist">CHECKLIST</span>
            <div class="item-title mt-2">${escapeHtml(item.title)}</div></div><div class="d-flex gap-1"><button class="btn btn-sm btn-light edit-item" title="Modifier l’élément"><i class="bi bi-pencil"></i></button><button class="btn btn-sm btn-light edit-checklist" title="Modifier les cases"><i class="bi bi-list-check"></i></button><button class="btn btn-sm btn-light delete-item" title="Supprimer"><i class="bi bi-trash"></i></button></div></div>
            <div class="check-items mt-3">${rows}</div><div class="check-edit mt-3 gap-2"><button class="btn btn-sm btn-outline-secondary add-check"><i class="bi bi-plus"></i> Ajouter une case</button><button class="btn btn-sm btn-outline-secondary reset-checklist"><i class="bi bi-arrow-counterclockwise"></i> Réinitialiser</button></div>
            <div class="progress mt-3" style="height:5px;"><div class="progress-bar"></div></div></div></div>`);
        card.data('item', item);
        updateChecklistProgress(card);
        return card;
    }

    /** Render the permanent full-screen item route without changing history. */
    async function renderItemDetail(itemId) {
        $('#itemDetailScreen').attr('aria-busy', 'true');
        $('#itemDetailContent').html('<div class="text-muted">Chargement de l’élément...</div>');
        try {
            const item = await api(`/api/items/${itemId}/detail`);
            if (currentItemId !== itemId) return;
            const card = item.type_code === 'CHECKLIST' ? renderChecklist(item)
                : item.type_code === 'TASK' ? renderTask(item)
                    : itemCard(item);
            card.addClass('item-detail-card');
            const formatDateTime = value => {
                const date = new Date(value.replace(' ', 'T'));
                return Number.isNaN(date.getTime()) ? value : date.toLocaleString('fr-FR', { dateStyle: 'long', timeStyle: 'short' });
            };
            const schedules = item.schedules?.length
                ? item.schedules.map(schedule => `<div>${escapeHtml(formatDateTime(schedule.start_at))}${schedule.end_at ? ` – ${escapeHtml(formatDateTime(schedule.end_at))}` : ''}</div>`).join('')
                : '<div class="text-muted">Aucune échéance planifiée</div>';
            const notifications = item.notification_configs?.length
                ? item.notification_configs.map(config => `<div>${escapeHtml(config.label || `Rappel ${config.offset_minutes} min avant`)}${config.is_enabled ? '' : ' (désactivé)'}</div>`).join('')
                : '<div class="text-muted">Aucun rappel configuré</div>';
            const createdAt = item.created_at ? new Date(item.created_at).toLocaleString('fr-FR') : '—';
            const updatedAt = item.updated_at ? new Date(item.updated_at).toLocaleString('fr-FR') : '—';
            $('#itemDetailType').text(item.type_label || item.type_code);
            $('#itemDetailStatus').text(item.status_label || statusLabel[item.status_code] || '');
            $('#itemDetailPermalink').attr('href', `/item/${item.id}`).text(`${location.origin}/item/${item.id}`);
            document.title = `ZenHome — ${item.title}`;
            $('#itemDetailContent').empty().append(card).append(`
                <section class="item-detail-info" aria-label="Informations complémentaires">
                    <div><h2>Planification</h2>${schedules}</div>
                    <div><h2>Rappels</h2>${notifications}</div>
                    <div><h2>Historique</h2><div>Créé le ${escapeHtml(createdAt)}</div><div>Modifié le ${escapeHtml(updatedAt)}</div></div>
                </section>`);
            $('#itemDetailScreen').attr('aria-busy', 'false');
        } catch (error) {
            if (currentItemId !== itemId) return;
            $('#itemDetailContent').html('<div class="alert alert-warning">Cet élément est introuvable ou ne peut pas être chargé.</div>');
            $('#itemDetailScreen').attr('aria-busy', 'false');
        }
    }

    /** Open an item and optionally add its permanent URL to browser history. */
    function openItemView(itemId, push = false) {
        const fromPage = $('.page:not(.d-none)').attr('id')?.replace('page-', '') || 'dashboard';
        currentItemId = Number(itemId);
        if (push) history.pushState({ itemId: currentItemId, fromPage }, '', `/item/${currentItemId}`);
        $('#itemDetailScreen').removeClass('d-none');
        renderItemDetail(currentItemId);
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
            if (currentItemId !== null) await renderItemDetail(currentItemId);
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
            const counts = data.counts || {};
            $('[data-dashboard-count="today"]').text(counts.today || 0);
            $('[data-dashboard-count="tasks_done"]').text(counts.tasks_done || 0);
            $('[data-dashboard-count="checklists_open"]').text(counts.checklists_open || 0);
            $('[data-dashboard-count="upcoming"]').text(data.upcoming_occurrences.length || 0);
            renderDashboardOccurrences(data.upcoming_occurrences || []);
        } catch (error) { console.error(error); }
    }

    /** Refresh every data-backed view after another tab changes an item. */
    function scheduleSharedRefresh() {
        clearTimeout(sharedRefreshTimer);
        sharedRefreshTimer = setTimeout(function refreshSharedViews() {
            loadItems();
            loadDashboard();
            renderCalendarView();
        }, 250);
    }

    if (itemUpdateChannel) itemUpdateChannel.addEventListener('message', scheduleSharedRefresh);
    $(window).on('storage', function handleSharedUpdate(event) {
        if (event.originalEvent.key === 'zenhome-item-updated') scheduleSharedRefresh();
    });

    /** Render the dashboard's real occurrences in the two date sections. */
    function renderDashboardOccurrences(occurrences) {
        const today = calendarDateValue(new Date());
        const typeLabels = { NOTE: 'NOTE', CHECKLIST: 'CHECKLIST', TASK: 'TÂCHE' };
        const renderOccurrence = occurrence => {
            const date = new Date(occurrence.starts_at.replace(' ', 'T'));
            const dateLabel = date.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long' });
            const timeLabel = date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
            return `<div class="card p-3 mb-2 dashboard-occurrence item-openable" data-item-id="${occurrence.item_id}" role="link" tabindex="0">
                <div class="d-flex justify-content-between gap-2">
                    <span class="type-badge ${typeClass[occurrence.type_code]}">${typeLabels[occurrence.type_code] || occurrence.type_code}</span>
                    <span class="small text-muted">${dateLabel} · ${timeLabel}</span>
                </div>
                <div class="fw-semibold mt-2">${escapeHtml(occurrence.title)}</div>
            </div>`;
        };
        const todayOccurrences = occurrences.filter(occurrence => occurrence.starts_at.startsWith(today));
        $('#dashboardTodayList').html(todayOccurrences.length ? todayOccurrences.map(renderOccurrence).join('') : '<div class="text-muted">Aucun élément prévu aujourd’hui.</div>');
        const upcomingOccurrences = occurrences.filter(occurrence => !occurrence.starts_at.startsWith(today));
        $('#dashboardUpcomingList').html(upcomingOccurrences.length ? upcomingOccurrences.slice(0, 5).map(renderOccurrence).join('') : '<div class="text-muted">Aucun élément à venir.</div>');
        applySearch();
    }

    /** Navigate to the page selected in the sidebar. */
    $('.nav-link[data-page]').on('click', function handlePageNavigation(event) {
        event.preventDefault();
        const page = $(this).data('page');
        showPage(page, true);
        if (page === 'calendar') renderCalendarView();
    });
    $(document).on('click', '.page .item-card, .page .kanban-card, .page .dashboard-occurrence, .page .calendar-event', function openClickedItem(event) {
        if ($(event.target).closest('button, a, input, select, textarea, [data-bs-toggle]').length) return;
        const itemId = Number($(this).data('item-id'));
        if (Number.isInteger(itemId) && itemId > 0) openItemView(itemId, true);
    });
    $(document).on('keydown', '.page .item-openable', function openFocusedItem(event) {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        if ($(event.target).closest('button, a, input, select, textarea').length) return;
        event.preventDefault();
        const itemId = Number($(this).data('item-id'));
        if (Number.isInteger(itemId) && itemId > 0) openItemView(itemId, true);
    });
    $('#itemDetailBack').on('click', function returnFromItemDetail() {
        if (history.state?.itemId && location.pathname === `/item/${history.state.itemId}`) {
            history.back();
            return;
        }
        showPage(history.state?.fromPage || 'dashboard', true);
    });
    $('#copyItemLink').on('click', async function copyPermanentItemLink() {
        try {
            const permalink = new URL($('#itemDetailPermalink').attr('href'), location.origin).href;
            await navigator.clipboard.writeText(permalink);
            $(this).attr('aria-label', 'Lien copié').attr('title', 'Lien copié');
            setTimeout(() => $(this).attr('aria-label', 'Copier le lien').attr('title', 'Copier le lien'), 1500);
        } catch (error) {
            alert('Impossible de copier le lien depuis ce navigateur.');
        }
    });
    $(window).on('popstate', function restoreRouteFromHistory() {
        const itemMatch = location.pathname.match(/^\/item\/(\d+)$/);
        if (itemMatch) {
            showPage(history.state?.fromPage || 'dashboard');
            openItemView(Number(itemMatch[1]));
            return;
        }
        const page = ({ '/notes': 'notes', '/checklists': 'checklist', '/tasks': 'tasks', '/kanban': 'kanban', '/calendar': 'calendar' })[location.pathname] || 'dashboard';
        showPage(page);
        if (page === 'calendar') renderCalendarView();
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
    $('#calendarPrevious').on('click', function showPreviousCalendarPeriod() {
        calendarDate = calendarView === 'month' ? shiftCalendarMonth(calendarDate, -1) : shiftCalendarDate(calendarDate, calendarView === 'week' ? -7 : -1);
        renderCalendarView();
    });
    $('#calendarNext').on('click', function showNextCalendarPeriod() {
        calendarDate = calendarView === 'month' ? shiftCalendarMonth(calendarDate, 1) : shiftCalendarDate(calendarDate, calendarView === 'week' ? 7 : 1);
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
        $('#itemTypeCreateField').toggleClass('d-none', activePage !== 'dashboard');
        $(`input[name="newItemType"][value="${createItemType}"]`).prop('checked', true);
        const today = new Date();
        const todayValue = [today.getFullYear(), String(today.getMonth() + 1).padStart(2, '0'), String(today.getDate()).padStart(2, '0')].join('-');
        updateCreateModalFields();
        $('#newTitle, #newContent').val('');
        $('#newDate').val(todayValue);
        $('#newRecurrence').val('');
        $('#newChecklistItems').empty();
        if (createItemType === 'CHECKLIST') appendNewChecklistItem();
    }

    /** Update creation fields that depend on the selected item type. */
    function updateCreateModalFields() {
        $('#itemModalTitle').text(`Nouvelle ${itemTypeLabel[createItemType]}`);
        $('#createItem').text('Créer');
        const supportsRecurrence = createItemType !== 'TASK';
        $('#dateCreateLabel').text(createItemType === 'TASK' ? 'Date d’échéance' : 'Planification');
        $('#recurrenceCreateField').toggleClass('d-none', !supportsRecurrence);
        $('#dateCreateField').toggleClass('col-md-6', supportsRecurrence).toggleClass('col-12', !supportsRecurrence);
        $('#checklistCreateFields').toggleClass('d-none', createItemType !== 'CHECKLIST');
    }

    /** Change the item type selected from the dashboard creation modal. */
    $('input[name="newItemType"]').on('change', function handleCreateItemTypeChange() {
        createItemType = $('input[name="newItemType"]:checked').val();
        updateCreateModalFields();
        $('#newChecklistItems').empty();
        if (createItemType === 'CHECKLIST') appendNewChecklistItem();
    });

    /** Add an empty checklist row to the item creation form. */
    function appendNewChecklistItem() {
        $('#newChecklistItems').append(`
            <div class="checklist-create-row input-group mb-2">
                <span class="input-group-text">
                    <input class="form-check-input new-check-checked" type="checkbox" aria-label="Case cochée">
                </span>
                <input class="form-control new-check-label" maxlength="250" placeholder="Ex. Acheter du lait">
                <button type="button" class="btn btn-light remove-new-check" title="Supprimer la case">
                    <i class="bi bi-trash"></i>
                </button>
            </div>`);
    }

    /** Read non-empty checklist rows from the item creation form. */
    function readNewChecklistItems() {
        return $('#newChecklistItems .checklist-create-row').map(function readChecklistRow() {
            const row = $(this);
            const label = row.find('.new-check-label').val().trim();
            return label ? { label, is_checked: row.find('.new-check-checked').is(':checked') } : null;
        }).get();
    }

    /** Create checklist rows using the same API payload as the existing add-row flow. */
    function addChecklistItems(itemId, checklistItems) {
        return Promise.all(checklistItems.map(function addChecklistItem(checklistItem) {
            return api(`/api/items/${itemId}/checklist-items`, { method: 'POST', data: checklistItem });
        }));
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
        $('#itemTypeCreateField').addClass('d-none');
        $('#newTitle').val(item.title || '');
        $('#newContent').val(item.content || '');
        $('#newDate').val(schedule?.start_at?.slice(0, 10) || '');
        $('#newRecurrence').val(schedule?.recurrence_rule_id || '');
        $('#checklistCreateFields').addClass('d-none');
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
            const item = await api('/api/items', {
                method: 'POST',
                data: {
                    title,
                    content: $('#newContent').val().trim() || null,
                    type_code: createItemType,
                    checklist_items: createItemType === 'CHECKLIST' ? readNewChecklistItems() : []
                }
            });
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
            if (currentItemId === Number(itemId)) $('#itemDetailStatus').text(statusLabel[select.val()] || select.val());
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
    /** Delete a note after confirmation. */
    $(document).on('click', '.delete-item', async function handleItemDelete() {
        const card = $(this).closest('.item-card');
        const confirmed = await requestConfirmation({
            title: 'Supprimer cet élément ?',
            message: 'Cette action est irréversible.',
            confirmLabel: 'Supprimer',
            variant: 'danger'
        });
        if (!confirmed) return;
        $(this).prop('disabled', true);
        try {
            const itemId = Number(card.data('item-id'));
            await api(`/api/items/${itemId}`, { method: 'DELETE' });
            if (currentItemId === itemId) {
                $('#itemDetailBack').trigger('click');
                currentItemId = null;
            }
            await loadItems();
            await loadDashboard();
        } catch (error) {
            alert('Impossible de supprimer cet élément.');
            $(this).prop('disabled', false);
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
    /** Add a checklist row to the item creation form. */
    $(document).on('click', '.add-new-check', function handleAddNewChecklistItem() {
        appendNewChecklistItem();
        $('#newChecklistItems .new-check-label').last().trigger('focus');
    });
    /** Remove a checklist row from the item creation form. */
    $(document).on('click', '.remove-new-check', function handleRemoveNewChecklistItem() {
        $(this).closest('.checklist-create-row').remove();
    });
    /** Create the checklist item entered in the modal. */
    $('#addChecklistItem').on('click', async function handleChecklistItemSubmit() {
        const label = $('#checklistItemLabel').val().trim();
        if (!label || !checklistItemOwnerId) return $('#checklistItemLabel').trigger('focus');
        $(this).prop('disabled', true);
        try {
            await addChecklistItems(checklistItemOwnerId, [{ label }]);
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

    startDevelopmentReload();
    const initialItemMatch = location.pathname.match(/^\/item\/(\d+)$/);
    const initialPage = ({ '/notes': 'notes', '/checklists': 'checklist', '/tasks': 'tasks', '/kanban': 'kanban', '/calendar': 'calendar' })[location.pathname] || 'dashboard';
    showPage(initialPage); renderCalendarView(); loadRecurrenceRules(); loadItems(); loadDashboard();
    if (initialItemMatch) openItemView(Number(initialItemMatch[1]));
});
