# Runbook Repository

This directory contains operational runbooks for the ATP platform. Runbooks are standardized procedures for handling common operational scenarios, incidents, and maintenance tasks.

## Structure

- `templates/` - Runbook templates
- `incident_response/` - Incident response runbooks
- `maintenance/` - Maintenance and operational runbooks
- `emergency/` - Emergency procedures

## Runbook Format

All runbooks must follow the standard template format defined in `templates/standard_runbook.md`.

## Validation

Runbooks are validated using the linter:

```bash
python tools/runbook_linter.py runbooks/
```

## Required Sections

Every runbook must include these sections:
- Title
- Description
- Prerequisites
- Steps
- Verification
- Rollback (if applicable)
- Contacts
- References

## Testing

Runbook validation tests can be run with:

```bash
python -m pytest tests/test_runbook_validation.py
```
