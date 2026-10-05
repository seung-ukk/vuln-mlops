# Runtime Builder (lab app draft)

Runtime Builder is the small application that will replace the socket-based
Stage 5 workload. Argo CD deploys it from the restricted `stage4-lab` Git
branch. The baseline profile rejects build requests; the Git-controlled legacy
profile enables the old source resolver.

The API has three internal routes:

- `GET /build/info` reports the active profile.
- `POST /build` accepts a short `source_ref` and reports only completed/failed.
- `GET /proof` returns a validated synthetic AWS proof after a build has
  produced one. It does not return shell output or temporary credentials.

The legacy resolver was kept for the exercise to show what happens when a
source reference is incorporated into a shell command. The app image also has
a maintenance module for checking its own AWS identity and one fixed lab S3
object. Participants should inspect the build profile, API schema, and source
resolver to connect those facts; an operator shell or kubeconfig is not part
of the participant path.

The IAM role is restricted to `proof/final-flag.txt` in the dedicated private
lab bucket. The object content is synthetic and provisioned outside Terraform.
This draft is not deployed until its image is published, pinned by OCI digest,
and the Stage 4→IAM participant relay replaces the current socket path.
