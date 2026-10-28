import re
from datetime import timezone

class DomainError(Exception):
    def __init__(self, status, code, message, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details or []

def fail(message, code='POLICY_REJECTED', status=422):
    raise DomainError(status, code, message)

def utc(value):
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')

def redact(value):
    if isinstance(value, dict):
        return {k: ('[REDACTED]' if k.lower() in {'password','token','reset_token','secret','api_key','authorization'} else redact(v)) for k,v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r'''(?i)\b(password|passwd|token|reset_token|secret|api[_-]?key)\s*(?:[:=]|\bis\b|\bwas\b)\s*(?:"[^"]*"|'[^']*'|[^\s,;]+)''', r'\1=[REDACTED]', value)
        value = re.sub(r'(?i)\bBearer\s+\S+', 'Bearer [REDACTED]', value)
        value = re.sub(r'\bSYNTH_SECRET_[A-Za-z0-9_-]+', '[REDACTED]', value)
    return value

def mandatory(ticket):
    return ticket.security_sensitive or ticket.privileged_access or ticket.reported_priority == 1

def active(ticket):
    if ticket.status in ('RESOLVED','CLOSED'):
        fail('Ticket is no longer active', 'INVALID_STATUS', 409)
