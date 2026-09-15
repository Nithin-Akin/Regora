import logging

def record_event(name: str, entity_id):
    """Record an audit event without exposing user credentials."""
    logging.info("event=%s entity=%s", name, entity_id)
