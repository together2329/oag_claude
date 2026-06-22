# OAG Authoring Packet Rules

These rules are enforced by `oag_authoring_packet_check.py`.

- `rtl__*.json` must use `schema_version: oag_rtl_authoring_packet.v1`.
- RTL packets must list `contract_refs_to_implement`.
- RTL packets must list at least one behavior, cycle, protocol, or domain target
  when used for locked implementation.
- RTL packets must forbid TB and simulation evidence as truth sources.
- `tb__*.json` must use `schema_version: oag_tb_authoring_packet.v1`.
- TB packets must set `expected_source_policy: contract_oracle_only`.
- TB packets must forbid DUT/RTL/post-hoc expected sources.
- TB packets must list scenario and scoreboard refs when used for locked TB
  implementation.
- Missing role-specific packets are warnings in draft and blockers only when
  `--require-packets` or `--require-locked` is used.
