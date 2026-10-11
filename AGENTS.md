# Project instructions

Before changing code or manifests, read these files in order:

1. `docs/LAB_PLAN.md`
2. `docs/STAGE_CONTRACTS.md`
3. `docs/STATUS.md`

Use `docs/STATUS.md` to determine the active milestone. Keep changes limited to that
milestone unless the user explicitly expands the scope.

For the active participant attack chain:

- implement the intended attack path and its smoke test first; keep focused
  denial checks for the Git scope, fixed hostPath, direct Pod IAM access, and
  dedicated-node proof-tag permission; defer exhaustive shortcut discovery;
- preserve namespace, resource-name, network, node, and AWS tag boundaries;
- keep proof channels synthetic and do not expose arbitrary file or credential
  data; the per-deployment, path-scoped lab Git credential may appear only in
  the intended internal operations log;
- do not add real credentials, production resources, or unrestricted IAM;
- the only permitted reverse-shell path is the isolated ModelGate validator Pod
  calling a dedicated lab attacker EC2 private address for this exercise;
  never add an arbitrary Internet callback or expose shell output through a
  public proof API;
- do not upgrade the intentionally pinned vulnerable MLflow profile silently;
- use current reviewed versions for operational components that do not rely on a CVE;
- run the relevant tests and update `docs/STATUS.md` before finishing;
- do not commit or push unless the user explicitly requests it.
