"""Emit coverage only after independently checking every required observation."""
import json
from evidence import coverage

def write_coverage(session):
    result = coverage(session)
    (session.evidence / 'coverage.json').write_text(json.dumps(result, indent=2) + '\n')
