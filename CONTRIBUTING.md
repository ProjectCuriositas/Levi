# Contributing

Write pull request titles and descriptions in English. Keep repository
documentation and code comments in English as well.

Describe the problem, resulting behavior, and relevant validation so a reader
can review the change without access to private discussions or documents.
Use repository-relative paths and examples that work in an ordinary checkout.

Keep public contributions free of personal or machine-specific context:

- Do not include personal names, usernames, hostnames, IP addresses, credentials,
  private repository references, or local installation paths.
- Do not copy private specifications, chat transcripts, machine setup notes,
  or agent session history into a pull request or repository file.
- Describe prerequisites and platform constraints as project requirements.
  Do not frame instructions around a contributor's personal workstation.
- Review logs, screenshots, and generated artifacts for private information
  before including them.

## Validation

Run the checks appropriate to the change. For implementation or test changes,
use the verification harness documented
on the target version branch. On branches that include `tools/verify.py`, run
from the repository root with a sibling Mognitio checkout:

```sh
python3 tools/verify.py --compiler ../Mognitio --evidence evidence/contribution-check
git diff --check
```

For documentation-only changes, check relative links, code fences, and
whitespace. Report commands, outcomes, and any unverified behavior honestly.
Use sanitized summaries when raw output contains local paths or other
machine-specific details.

Use a new evidence directory for each run. The harness prepares the filesystem
fixtures required by the Mognitio tests; invoking `mgn test` alone does not
prepare or reset those fixtures. A targeted run may help while developing,
but it does not replace full acceptance verification for an implementation
change. Follow the target branch's README for compiler and host prerequisites.

Raw evidence may contain absolute paths, host information, and fixture data.
Keep it local and ignored by Git. Publish only reviewed, sanitized summaries.
Do not make contribution checks depend on access to a private repository.
