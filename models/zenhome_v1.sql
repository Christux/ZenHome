PRAGMA foreign_keys = ON;

-- ============================================================
-- Tables dictionnaires
-- ============================================================

CREATE TABLE item_types (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    label       TEXT NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE item_statuses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    label       TEXT NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE recurrence_types (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    label       TEXT NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE occurrence_statuses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    label       TEXT NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE notification_statuses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    label       TEXT NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

-- ============================================================
-- Utilisateurs et éléments
-- ============================================================

CREATE TABLE users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    type_id     INTEGER NOT NULL,
    status_id   INTEGER NOT NULL,

    title       TEXT NOT NULL,
    content     TEXT,
    is_favorite INTEGER NOT NULL DEFAULT 0 CHECK (is_favorite IN (0, 1)),
    is_archived INTEGER NOT NULL DEFAULT 0 CHECK (is_archived IN (0, 1)),

    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

    FOREIGN KEY (type_id)
        REFERENCES item_types(id),

    FOREIGN KEY (status_id)
        REFERENCES item_statuses(id)
);

CREATE TABLE checklist_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     INTEGER NOT NULL,

    label       TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0,
    is_checked  INTEGER NOT NULL DEFAULT 0 CHECK (is_checked IN (0, 1)),
    checked_at  TEXT,

    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (item_id)
        REFERENCES items(id)
        ON DELETE CASCADE,

    UNIQUE (item_id, position)
);

-- ============================================================
-- Récurrence
-- ============================================================

CREATE TABLE recurrence_rules (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    recurrence_type_id  INTEGER NOT NULL,

    label               TEXT NOT NULL,
    expression          TEXT NOT NULL,

    -- Utilisé pour les règles mensuelles et périodiques.
    day_of_month        INTEGER
                        CHECK (day_of_month IS NULL OR day_of_month BETWEEN 1 AND 31),

    -- Utilisé notamment pour les règles annuelles.
    month_of_year       INTEGER
                        CHECK (month_of_year IS NULL OR month_of_year BETWEEN 1 AND 12),

    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (recurrence_type_id)
        REFERENCES recurrence_types(id)
);

-- 1 = lundi, 2 = mardi, ..., 7 = dimanche.
-- Sert aux règles de type WEEKLY.
CREATE TABLE recurrence_rule_weekdays (
    recurrence_rule_id  INTEGER NOT NULL,
    weekday             INTEGER NOT NULL CHECK (weekday BETWEEN 1 AND 7),

    PRIMARY KEY (recurrence_rule_id, weekday),

    FOREIGN KEY (recurrence_rule_id)
        REFERENCES recurrence_rules(id)
        ON DELETE CASCADE
);

CREATE TABLE schedules (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id             INTEGER NOT NULL,
    recurrence_rule_id  INTEGER,

    -- Date/heure de départ et, éventuellement, de fin.
    -- Une règle NULL correspond à une planification unique.
    start_at            TEXT NOT NULL,
    end_at              TEXT,
    is_active           INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),

    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (item_id)
        REFERENCES items(id)
        ON DELETE CASCADE,

    FOREIGN KEY (recurrence_rule_id)
        REFERENCES recurrence_rules(id)
);

CREATE TABLE schedule_occurrences (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_id     INTEGER NOT NULL,
    status_id       INTEGER NOT NULL,

    starts_at       TEXT NOT NULL,
    ends_at         TEXT,
    completed_at    TEXT,

    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (schedule_id)
        REFERENCES schedules(id)
        ON DELETE CASCADE,

    FOREIGN KEY (status_id)
        REFERENCES occurrence_statuses(id),

    UNIQUE (schedule_id, starts_at)
);

-- ============================================================
-- Notifications
-- ============================================================

-- La configuration appartient à l'item.
CREATE TABLE notification_configs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         INTEGER NOT NULL,

    label           TEXT,
    offset_minutes  INTEGER NOT NULL DEFAULT 0,
    is_enabled      INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),

    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (item_id)
        REFERENCES items(id)
        ON DELETE CASCADE
);

-- La notification concrète appartient à une occurrence.
CREATE TABLE notifications (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_occurrence_id  INTEGER NOT NULL,
    notification_config_id  INTEGER NOT NULL,
    status_id               INTEGER NOT NULL,

    notify_at               TEXT NOT NULL,
    sent_at                 TEXT,
    error_message           TEXT,

    created_at              TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (schedule_occurrence_id)
        REFERENCES schedule_occurrences(id)
        ON DELETE CASCADE,

    FOREIGN KEY (notification_config_id)
        REFERENCES notification_configs(id)
        ON DELETE CASCADE,

    FOREIGN KEY (status_id)
        REFERENCES notification_statuses(id),

    UNIQUE (schedule_occurrence_id, notification_config_id)
);

-- ============================================================
-- Index
-- ============================================================

CREATE INDEX idx_items_user_id
    ON items(user_id);

CREATE INDEX idx_items_type_id
    ON items(type_id);

CREATE INDEX idx_items_status_id
    ON items(status_id);

CREATE INDEX idx_checklist_items_item_id
    ON checklist_items(item_id);

CREATE INDEX idx_recurrence_rules_type_id
    ON recurrence_rules(recurrence_type_id);

CREATE INDEX idx_schedules_item_id
    ON schedules(item_id);

CREATE INDEX idx_schedules_recurrence_rule_id
    ON schedules(recurrence_rule_id);

CREATE INDEX idx_schedule_occurrences_schedule_id
    ON schedule_occurrences(schedule_id);

CREATE INDEX idx_schedule_occurrences_status_starts_at
    ON schedule_occurrences(status_id, starts_at);

CREATE INDEX idx_notification_configs_item_id
    ON notification_configs(item_id);

CREATE INDEX idx_notifications_status_notify_at
    ON notifications(status_id, notify_at);

CREATE INDEX idx_notifications_occurrence_id
    ON notifications(schedule_occurrence_id);

-- ============================================================
-- Données initiales des dictionnaires
-- ============================================================

INSERT INTO item_types (code, label, sort_order) VALUES
    ('NOTE',      'Note',       10),
    ('CHECKLIST', 'Checklist',  20),
    ('TASK',      'Tâche',      30);

INSERT INTO item_statuses (code, label, sort_order) VALUES
    ('TODO',        'À faire',   10),
    ('IN_PROGRESS', 'En cours',  20),
    ('DONE',        'Terminée',  30),
    ('CANCELLED',   'Annulée',   40);

INSERT INTO recurrence_types (code, label, sort_order) VALUES
    ('NONE',      'Aucune',        0),
    ('DAILY',     'Quotidien',    10),
    ('WEEKLY',    'Hebdomadaire', 20),
    ('MONTHLY',   'Mensuel',      30),
    ('QUARTERLY', 'Trimestriel',  40),
    ('HALF_YEAR', 'Semestriel',   50),
    ('YEARLY',    'Annuel',       60);

INSERT INTO recurrence_rules (recurrence_type_id, label, expression)
SELECT id, 'Chaque jour', 'DAILY' FROM recurrence_types WHERE code = 'DAILY';
INSERT INTO recurrence_rules (recurrence_type_id, label, expression)
SELECT id, 'Chaque semaine', 'WEEKLY' FROM recurrence_types WHERE code = 'WEEKLY';
INSERT INTO recurrence_rules (recurrence_type_id, label, expression)
SELECT id, 'Chaque mois', 'MONTHLY' FROM recurrence_types WHERE code = 'MONTHLY';
INSERT INTO recurrence_rules (recurrence_type_id, label, expression)
SELECT id, 'Chaque année', 'YEARLY' FROM recurrence_types WHERE code = 'YEARLY';

INSERT INTO occurrence_statuses (code, label, sort_order) VALUES
    ('PENDING',   'À venir',  10),
    ('COMPLETED', 'Terminée', 20),
    ('SKIPPED',   'Ignorée',  30),
    ('CANCELLED', 'Annulée',  40);

INSERT INTO notification_statuses (code, label, sort_order) VALUES
    ('PENDING',   'En attente', 10),
    ('SENT',      'Envoyée',    20),
    ('FAILED',    'Échec',      30),
    ('CANCELLED', 'Annulée',    40);
