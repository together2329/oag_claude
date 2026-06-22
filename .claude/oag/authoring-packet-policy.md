# OAG Authoring Packet Policy

Authoring packets are generated compiler outputs, not hand-authored truth.
They turn locked ROCEV truth into role-specific work inputs for native
subagents.

## Packet Roles

- `module__*.json`: module ownership and local contract context.
- `rtl__*.json`: implementation packet for RTL agents.
- `tb__*.json`: proof-instrument packet for TB agents.
- `evidence__*.json`: evidence and validation planning packet.

RTL and TB agents should not independently reinterpret original user prose.
They consume generated packets from the same contract graph.

## RTL Packet Requirements

RTL packets must name:

- allowed truth sources
- forbidden TB/simulation sources
- contract refs to implement
- behavior refs to implement
- cycle/protocol refs to implement
- PPA notes requirement
- CDC/RDC notes requirement

## TB Packet Requirements

TB packets must name:

- expected-source policy
- forbidden DUT-derived expected sources
- scenario refs
- scoreboard row refs
- contract refs
- coverage/assertion/formal candidates when available

TB expected behavior must come from contract/model/oracle truth, never from RTL
expressions, DUT outputs, or post-hoc simulation behavior.
