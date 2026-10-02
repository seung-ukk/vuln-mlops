# Project instructions

Before changing code or manifests, read these files in order:

1. `docs/LAB_PLAN.md`
2. `docs/STAGE_CONTRACTS.md`
3. `docs/STATUS.md`

Use `docs/STATUS.md` to determine the active milestone. Keep changes limited to that
milestone unless the user explicitly expands the scope.

For every security-lab stage:

- implement the intended attack path and shortcut-denial tests together;
- preserve namespace, resource-name, network, node, and AWS tag boundaries;
- keep proof channels synthetic and do not expose arbitrary file or credential data;
- do not add real credentials, production resources, reverse shells, or unrestricted IAM;
- do not upgrade the intentionally pinned vulnerable MLflow profile silently;
- use current reviewed versions for operational components that do not rely on a CVE;
- run the relevant tests and update `docs/STATUS.md` before finishing;
- do not commit or push unless the user explicitly requests it.

