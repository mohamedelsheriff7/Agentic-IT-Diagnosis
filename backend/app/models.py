from sqlalchemy import create_engine, event, String, Integer, Boolean, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

class Base(DeclarativeBase):
    pass

class Reference(Base):
    __tablename__ = 'reference_data'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, index=True)
    data: Mapped[dict] = mapped_column(JSON)

class Ticket(Base):
    __tablename__ = 'tickets'
    ticket_id: Mapped[str] = mapped_column(String, primary_key=True)
    ticket_class: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, index=True)
    reported_priority: Mapped[int] = mapped_column(Integer)
    impact: Mapped[int] = mapped_column(Integer)
    urgency: Mapped[int] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String)
    domain: Mapped[str | None] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String, index=True)
    subcategory: Mapped[str | None] = mapped_column(String)
    diagnosis_code: Mapped[str | None] = mapped_column(ForeignKey('reference_data.id'))
    owner_group_id: Mapped[str | None] = mapped_column(ForeignKey('reference_data.id'))
    owner_id: Mapped[str | None] = mapped_column(ForeignKey('reference_data.id'))
    reported_by_id: Mapped[str] = mapped_column(ForeignKey('reference_data.id'))
    affected_person_id: Mapped[str] = mapped_column(ForeignKey('reference_data.id'))
    asset_id: Mapped[str | None] = mapped_column(ForeignKey('reference_data.id'))
    configuration_item_id: Mapped[str | None] = mapped_column(ForeignKey('reference_data.id'))
    location_id: Mapped[str | None] = mapped_column(ForeignKey('reference_data.id'))
    reported_at: Mapped[str] = mapped_column(String, index=True)
    target_finish_at: Mapped[str | None] = mapped_column(String)
    actual_finish_at: Mapped[str | None] = mapped_column(String)
    resolved_at: Mapped[str | None] = mapped_column(String)
    closed_at: Mapped[str | None] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)
    linked_solution_id: Mapped[str | None] = mapped_column(ForeignKey('reference_data.id'))
    resolution_summary: Mapped[str | None] = mapped_column(String)
    is_global: Mapped[bool] = mapped_column(Boolean, default=False)
    global_ticket_id: Mapped[str | None] = mapped_column(ForeignKey('tickets.ticket_id'))
    severity: Mapped[str | None] = mapped_column(String)
    security_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    privileged_access: Mapped[bool] = mapped_column(Boolean, default=False)
    active_scope: Mapped[str | None] = mapped_column(String, unique=True)

class Worklog(Base):
    __tablename__ = 'worklogs'
    worklog_id: Mapped[str] = mapped_column(String, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey('tickets.ticket_id'), index=True)
    data: Mapped[dict] = mapped_column(JSON)

class Evidence(Base):
    __tablename__ = 'evidence'
    evidence_id: Mapped[str] = mapped_column(String, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey('tickets.ticket_id'), index=True)
    data: Mapped[dict] = mapped_column(JSON)

class Relationship(Base):
    __tablename__ = 'ticket_relationships'
    child_id: Mapped[str] = mapped_column(ForeignKey('tickets.ticket_id'), primary_key=True)
    global_id: Mapped[str] = mapped_column(ForeignKey('tickets.ticket_id'), index=True)

class Diagnostic(Base):
    __tablename__ = 'diagnostic_results'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey('tickets.ticket_id'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('ticket_id', 'version'),)

class Review(Base):
    __tablename__ = 'human_reviews'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey('tickets.ticket_id'))
    group_id: Mapped[str] = mapped_column(ForeignKey('reference_data.id'))
    state: Mapped[str] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSON)

class Notification(Base):
    __tablename__ = 'notifications'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey('tickets.ticket_id'))
    group_id: Mapped[str] = mapped_column(ForeignKey('reference_data.id'))
    data: Mapped[dict] = mapped_column(JSON)

class Assignment(Base):
    __tablename__ = 'assignments'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey('tickets.ticket_id'))
    group_id: Mapped[str] = mapped_column(ForeignKey('reference_data.id'))
    data: Mapped[dict] = mapped_column(JSON)

class Idempotency(Base):
    __tablename__ = 'idempotency_records'
    action_id: Mapped[str] = mapped_column(String, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String)
    response: Mapped[dict] = mapped_column(JSON)

def database(url):
    engine = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 30})
    @event.listens_for(engine, 'connect')
    def pragmas(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=30000')
    Base.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)
