from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session as ORMSession, sessionmaker, with_loader_criteria
from .config import settings


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_foreign_keys(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@event.listens_for(ORMSession, "do_orm_execute")
def _organization_filter(execute_state):
    """Apply defense-in-depth organization filtering to every tenant session query."""
    organization_id = execute_state.session.info.get("organization_id")
    if not organization_id or not execute_state.is_select:
        return
    statement = execute_state.statement
    for mapper in Base.registry.mappers:
        model = mapper.class_
        if getattr(model, "__tenant_scoped__", False):
            statement = statement.options(with_loader_criteria(
                model, lambda row: row.organization_id == organization_id, include_aliases=True))
    execute_state.statement = statement


@event.listens_for(ORMSession, "before_flush")
def _organization_write_guard(db, _flush_context, _instances):
    organization_id = db.info.get("organization_id")
    if not organization_id:
        return
    for record in db.new:
        if getattr(record, "__tenant_scoped__", False):
            if getattr(record, "organization_id", None) in (None, organization_id):
                record.organization_id = organization_id
            else:
                raise ValueError("Cross-organization record creation is not permitted")
    for record in set(db.dirty).union(db.deleted):
        if getattr(record, "__tenant_scoped__", False) and getattr(record, "organization_id", None) != organization_id:
            raise ValueError("Cross-organization record changes are not permitted")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
