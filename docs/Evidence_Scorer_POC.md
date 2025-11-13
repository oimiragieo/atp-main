# Evidence Scorer (POC)

Validates that claims contain citations that are actually provided alongside the
response. In this POC, claims include citation markers like `[1]`, `[2]`, and
callers provide a list of citations with matching indices.

- Engine: `router_service/evidence.py`
- Tests: `tests/test_evidence_scorer_poc.py`
- Metrics: `evidence_fail_total` increments on missing citations.

Example
```
from router_service.evidence import Citation, validate_citations
text = 'See [1] and [2] for details.'
citations = [Citation(index=1, source='docA'), Citation(index=2, source='docB')]
assert validate_citations(text, citations) is True
```

Future
- Enforce source type/schema and validate URLs/doc IDs.
- Attach citation spans or structured evidence payloads.
