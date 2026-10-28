from sqlalchemy import select
from .models import Reference, Ticket, Evidence, Relationship, Diagnostic
from .policy import fail

def ticket(db, ticket_id):
    result = db.get(Ticket, ticket_id)
    if result is None:
        fail('Unknown ticket ID', 'NOT_FOUND', 404)
    return result

def reference(db, identifier, kind):
    result = db.get(Reference, identifier)
    if result is None or result.kind != kind:
        fail(f'Unknown {kind} ID: {identifier}', 'UNKNOWN_REFERENCE', 404)
    return result.data

def refs(db, kind):
    return [r.data for r in db.scalars(select(Reference).where(Reference.kind == kind))]

def validate_sources(db, ticket_id, body):
    for identifier in body.get('evidence_ids', []):
        evidence = db.get(Evidence, identifier)
        if not evidence or evidence.ticket_id != ticket_id:
            fail('Evidence must exist and belong to this ticket', 'INVALID_EVIDENCE')
    for identifier in body.get('knowledge_article_ids', []):
        reference(db, identifier, 'diagnostic_articles')
    for identifier in body.get('historical_ticket_ids', []):
        if ticket(db, identifier).status not in ('RESOLVED','CLOSED'):
            fail('Historical reference must be resolved or closed')

def related(db, t):
    if t.is_global:
        return sorted(db.scalars(select(Relationship.child_id).where(Relationship.global_id == t.ticket_id)))
    return [t.global_ticket_id] if t.global_ticket_id else []

def latest(db, ticket_id):
    return db.scalar(select(Diagnostic).where(Diagnostic.ticket_id == ticket_id).order_by(Diagnostic.version.desc()).limit(1))
