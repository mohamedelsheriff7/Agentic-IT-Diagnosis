"""Versioned caller result, independent of conversational rendering."""
def build_contract(result, session):
    snapshot = session.get('snapshot', {})
    if snapshot.get('ticket', {}).get('ticket_id') != result.get('ticket_id'):
        snapshot = {}
    return {
        'contract_version': '1.0', 'ticket_id': result.get('ticket_id'),
        'diagnostic_result_id': result.get('diagnostic_result_id'),
        'diagnostic_result_version': result.get('diagnostic_result_version'),
        'diagnosis': result.get('diagnosis_code'), 'outcome': result.get('outcome', 'INCONCLUSIVE'),
        'evidence': snapshot.get('evidence', []), 'evidence_ids': result.get('evidence_ids', []),
        'confidence': result.get('confidence', 'LOW'), 'confidence_basis': result.get('confidence_basis', {}),
        'recommended_action': result.get('recommended_action', 'ASK_MORE'),
        'rationale': result.get('rationale') or result.get('error') or 'Investigation requires further information.',
        'next_question': result.get('next_question'),
        'knowledge_sources': result.get('knowledge_sources', []),
        'historical_ticket_ids': result.get('historical_ticket_ids', []),
        'trace': snapshot.get('trace', []), 'completed_actions': result.get('completed_actions', []),
        'resolution_progress': snapshot.get('ticket', {}).get('metadata', {}).get('resolution_progress'),
        'error': result.get('error'),
        'account_check_status': result.get('account_check_status'),
        'diagnostic_blocker': result.get('diagnostic_blocker'),
    }
