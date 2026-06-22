# Assertion And Formal Policy

Assertions and formal proof are part of the verification methodology toolbox.
They are not required for every IP, but the TB agent should identify them when
they are the right proof shape.

## Assertion Candidates

Use assertions for local, precise rules:

- bus setup/enable timing;
- valid/ready handshake stability;
- no mutation during forbidden phases;
- reset release behavior;
- error response timing;
- interrupt set/clear priority;
- FIFO full/empty invariants;
- one-hot or mutually exclusive state;
- CDC/RDC assumptions and qualifiers.

Assertions complement scoreboards. They do not replace end-to-end expected vs
observed comparison when the obligation is behavioral.

## Formal Candidates

Use formal candidates when exhaustive bounded or unbounded proof is stronger
than simulation:

- deadlock freedom in a bounded controller;
- no overflow/underflow;
- ordering preservation;
- unreachable illegal states;
- priority resolution;
- protocol safety;
- reset safety;
- parameterized corner cases.

The TB agent may record formal candidates even if another role owns the formal
implementation.

## Evidence Strength

Simulation assertion pass is evidence. Formal proof is stronger evidence.

Development closure may accept assertion-assisted simulation when policy allows
it. Release closure should require the proof strength named in the contract or
an approved decision receipt that scopes the limitation.

## Required Trace

Assertion or formal evidence should trace to:

- requirement;
- obligation;
- contract;
- behavior or cycle rule;
- property id;
- tool report or simulation log;
- validation record;
- gate decision when required.

Do not claim a formal/assertion contract without proof/assertion evidence refs.
