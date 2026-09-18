# Offline evaluation application

This Django application is an offline research tool. It does not expose API
endpoints, store user sessions, or duplicate the regression tests under
`recommendations/tests`.

Its responsibilities are:

- create and validate reproducible experiment inputs;
- generate deterministic scenario drafts for human review;
- freeze approved scenarios in a later explicit step;
- run recommendation configurations after protocol approval; and
- calculate and export offline metrics and manifests.

The current implementation covers protocol steps 6-8 only. It deliberately
stops at `scenarios.draft.json`; step 9 requires human approval before runner
and result artifacts are implemented or executed.
