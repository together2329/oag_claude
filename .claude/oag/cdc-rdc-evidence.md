# OAG CDC/RDC Evidence

CDC/RDC closure needs evidence that matches the strength of the claim.

## Development Evidence

Development-grade evidence may include:

- `ontology/domain_intent.yaml`;
- generated `ontology/generated/domain_crossing_matrix.json`;
- lightweight `oag_domain_crossing_check.py` output;
- RTL synchronizer structure notes;
- reset sequence tests;
- functional scenarios that observe synchronizer consequences;
- decision receipts for scoped assumptions.

This evidence can close development obligations only when OAG policy allows
development-grade domain closure.

## Release Evidence

Release-grade CDC/RDC closure requires at least one of:

- static CDC report;
- static RDC report;
- formal proof or metastability-injection evidence;
- signoff tool report;
- explicitly approved equivalent evidence with `decision_receipt_id`.

Simulation-only evidence is not release-grade CDC/RDC evidence.

## Contract Evidence Fields

CDC contracts should name:

```yaml
contract_type: cdc
clock_domain_refs: []
crossing_refs: []
mitigation_refs: []
cdc_evidence_refs: []
```

RDC contracts should name:

```yaml
contract_type: rdc
reset_domain_refs: []
rdc_crossing_refs: []
reset_sequence_or_isolation_or_sync_refs: []
rdc_evidence_refs: []
```

Waivers or approved equivalents must include:

- `decision_receipt_id`;
- approver;
- scope;
- obligations covered;
- assumptions;
- substitute artifact;
- reason tool-grade evidence is not required for the current profile.

## Validator Rule

For a CDC/RDC closure claim, validate:

- domain intent exists;
- every relevant clock, reset, async input, and crossing is classified;
- each crossing has an approved mitigation or scoped assumption;
- mitigation resolves to RTL structure, cycle rule, synchronizer entry, or
  decision receipt;
- simulation evidence is not promoted beyond its strength;
- release claims have static/formal/tool-grade evidence or approved equivalent.
