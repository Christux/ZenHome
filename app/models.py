from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass


class ItemStatuses(Base):
    __tablename__ = 'item_statuses'

    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('1'))
    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True)

    items: Mapped[list['Items']] = relationship('Items', back_populates='status')


class ItemTypes(Base):
    __tablename__ = 'item_types'

    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('1'))
    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True)

    items: Mapped[list['Items']] = relationship('Items', back_populates='type')


class NotificationStatuses(Base):
    __tablename__ = 'notification_statuses'

    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('1'))
    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True)

    notifications: Mapped[list['Notifications']] = relationship('Notifications', back_populates='status')


class OccurrenceStatuses(Base):
    __tablename__ = 'occurrence_statuses'

    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('1'))
    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True)

    schedule_occurrences: Mapped[list['ScheduleOccurrences']] = relationship('ScheduleOccurrences', back_populates='status')


class RecurrenceTypes(Base):
    __tablename__ = 'recurrence_types'

    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('1'))
    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True)

    recurrence_rules: Mapped[list['RecurrenceRules']] = relationship('RecurrenceRules', back_populates='recurrence_type')


class Users(Base):
    __tablename__ = 'users'

    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('1'))
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True)

    items: Mapped[list['Items']] = relationship('Items', back_populates='user')


class Items(Base):
    __tablename__ = 'items'
    __table_args__ = (
        Index('idx_items_status_id', 'status_id'),
        Index('idx_items_type_id', 'type_id'),
        Index('idx_items_user_id', 'user_id')
    )

    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    type_id: Mapped[int] = mapped_column(ForeignKey('item_types.id'), nullable=False)
    status_id: Mapped[int] = mapped_column(ForeignKey('item_statuses.id'), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    is_favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('0'))
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('0'))
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True)
    content: Mapped[Optional[str]] = mapped_column(Text)

    status: Mapped['ItemStatuses'] = relationship('ItemStatuses', back_populates='items')
    type: Mapped['ItemTypes'] = relationship('ItemTypes', back_populates='items')
    user: Mapped['Users'] = relationship('Users', back_populates='items')
    checklist_items: Mapped[list['ChecklistItems']] = relationship('ChecklistItems', back_populates='item')
    notification_configs: Mapped[list['NotificationConfigs']] = relationship('NotificationConfigs', back_populates='item')
    schedules: Mapped[list['Schedules']] = relationship('Schedules', back_populates='item')


class RecurrenceRules(Base):
    __tablename__ = 'recurrence_rules'
    __table_args__ = (
        CheckConstraint('day_of_month IS NULL OR day_of_month BETWEEN 1 AND 31'),
        CheckConstraint('month_of_year IS NULL OR month_of_year BETWEEN 1 AND 12'),
        Index('idx_recurrence_rules_type_id', 'recurrence_type_id')
    )

    recurrence_type_id: Mapped[int] = mapped_column(ForeignKey('recurrence_types.id'), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    expression: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True)
    day_of_month: Mapped[Optional[int]] = mapped_column(Integer)
    month_of_year: Mapped[Optional[int]] = mapped_column(Integer)

    recurrence_type: Mapped['RecurrenceTypes'] = relationship('RecurrenceTypes', back_populates='recurrence_rules')
    recurrence_rule_weekdays: Mapped[list['RecurrenceRuleWeekdays']] = relationship('RecurrenceRuleWeekdays', back_populates='recurrence_rule')
    schedules: Mapped[list['Schedules']] = relationship('Schedules', back_populates='recurrence_rule')


class ChecklistItems(Base):
    __tablename__ = 'checklist_items'
    __table_args__ = (
        UniqueConstraint('item_id', 'position'),
        Index('idx_checklist_items_item_id', 'item_id')
    )

    item_id: Mapped[int] = mapped_column(ForeignKey('items.id', ondelete='CASCADE'), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    is_checked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('0'))
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True)
    checked_at: Mapped[Optional[str]] = mapped_column(Text)

    item: Mapped['Items'] = relationship('Items', back_populates='checklist_items')


class NotificationConfigs(Base):
    __tablename__ = 'notification_configs'
    __table_args__ = (
        Index('idx_notification_configs_item_id', 'item_id'),
    )

    item_id: Mapped[int] = mapped_column(ForeignKey('items.id', ondelete='CASCADE'), nullable=False)
    offset_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('1'))
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True)
    label: Mapped[Optional[str]] = mapped_column(Text)

    item: Mapped['Items'] = relationship('Items', back_populates='notification_configs')
    notifications: Mapped[list['Notifications']] = relationship('Notifications', back_populates='notification_config')


class RecurrenceRuleWeekdays(Base):
    __tablename__ = 'recurrence_rule_weekdays'
    __table_args__ = (
        CheckConstraint('weekday BETWEEN 1 AND 7'),
    )

    recurrence_rule_id: Mapped[int] = mapped_column(ForeignKey('recurrence_rules.id', ondelete='CASCADE'), primary_key=True)
    weekday: Mapped[int] = mapped_column(Integer, primary_key=True)

    recurrence_rule: Mapped['RecurrenceRules'] = relationship('RecurrenceRules', back_populates='recurrence_rule_weekdays')


class Schedules(Base):
    __tablename__ = 'schedules'
    __table_args__ = (
        Index('idx_schedules_item_id', 'item_id'),
        Index('idx_schedules_recurrence_rule_id', 'recurrence_rule_id')
    )

    item_id: Mapped[int] = mapped_column(ForeignKey('items.id', ondelete='CASCADE'), nullable=False)
    start_at: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('1'))
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True)
    recurrence_rule_id: Mapped[Optional[int]] = mapped_column(ForeignKey('recurrence_rules.id'))
    end_at: Mapped[Optional[str]] = mapped_column(Text)

    item: Mapped['Items'] = relationship('Items', back_populates='schedules')
    recurrence_rule: Mapped[Optional['RecurrenceRules']] = relationship('RecurrenceRules', back_populates='schedules')
    schedule_occurrences: Mapped[list['ScheduleOccurrences']] = relationship('ScheduleOccurrences', back_populates='schedule')


class ScheduleOccurrences(Base):
    __tablename__ = 'schedule_occurrences'
    __table_args__ = (
        UniqueConstraint('schedule_id', 'starts_at'),
        Index('idx_schedule_occurrences_schedule_id', 'schedule_id'),
        Index('idx_schedule_occurrences_status_starts_at', 'status_id', 'starts_at')
    )

    schedule_id: Mapped[int] = mapped_column(ForeignKey('schedules.id', ondelete='CASCADE'), nullable=False)
    status_id: Mapped[int] = mapped_column(ForeignKey('occurrence_statuses.id'), nullable=False)
    starts_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True)
    ends_at: Mapped[Optional[str]] = mapped_column(Text)
    completed_at: Mapped[Optional[str]] = mapped_column(Text)

    schedule: Mapped['Schedules'] = relationship('Schedules', back_populates='schedule_occurrences')
    status: Mapped['OccurrenceStatuses'] = relationship('OccurrenceStatuses', back_populates='schedule_occurrences')
    notifications: Mapped[list['Notifications']] = relationship('Notifications', back_populates='schedule_occurrence')


class Notifications(Base):
    __tablename__ = 'notifications'
    __table_args__ = (
        UniqueConstraint('schedule_occurrence_id', 'notification_config_id'),
        Index('idx_notifications_occurrence_id', 'schedule_occurrence_id'),
        Index('idx_notifications_status_notify_at', 'status_id', 'notify_at')
    )

    schedule_occurrence_id: Mapped[int] = mapped_column(ForeignKey('schedule_occurrences.id', ondelete='CASCADE'), nullable=False)
    notification_config_id: Mapped[int] = mapped_column(ForeignKey('notification_configs.id', ondelete='CASCADE'), nullable=False)
    status_id: Mapped[int] = mapped_column(ForeignKey('notification_statuses.id'), nullable=False)
    notify_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True)
    sent_at: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    notification_config: Mapped['NotificationConfigs'] = relationship('NotificationConfigs', back_populates='notifications')
    schedule_occurrence: Mapped['ScheduleOccurrences'] = relationship('ScheduleOccurrences', back_populates='notifications')
    status: Mapped['NotificationStatuses'] = relationship('NotificationStatuses', back_populates='notifications')
