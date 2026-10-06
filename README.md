# Lévi

Lévi is a web application framework written in Mognitio. Version 0.0.2
is a minimal static site generator that turns a single directory of
plain-text pages into HTML files.

## Build and run

The build host is Linux amd64 with [Mognitio](https://github.com/ProjectCuriositas/Mognitio)
v1.0.0. The tested compiler revision is
`fd7d91e24154a9cb04069b884cdf5667d5f4b86c`.
Follow the compiler repository's setup instructions so `mgn` is available.

```sh
mkdir -p build
mgn build mognitio.toml -o build/levi
build/levi build sample/site.cfg
```

Successful execution is silent and returns status 0. This example creates
`about.html` and `home.html` in `sample/public`. The output directory must be
absent or empty; a repeated build does not overwrite existing output.
The generated executable needs no compiler, source tree, or external helper
at runtime.

The same project can run through the compiler:

```sh
mgn run mognitio.toml -- build sample/site.cfg
```

## Input and output

The [sample configuration](sample/site.cfg) contains exactly one `title`,
`input`, and `output` key, each written as `key=value` on its own line.
Data paths are relative to the configuration file's lexical parent directory.
They use lowercase ASCII letters, digits, underscores, and hyphens in slash
separated components, each starting with a letter or digit. Input and output
must be distinct and neither may be an ancestor of the other.

Each selected `.page` file starts with `title=Page title`, followed by a blank
line and the plain-text body. Text must be UTF-8 without a leading BOM; CRLF
is normalized to LF. An isolated CR or a C0 control other than TAB/LF, or DEL,
is rejected. Titles must be nonempty, contain a character other than an ASCII
space, and contain no TAB. Whitespace and quotes are not trimmed.

Only regular files directly inside the input directory with the exact `.page`
suffix are selected. A filename stem contains lowercase ASCII letters or
digits, optionally separated by single hyphens. It maps directly to
`stem.html`. Directories, symlinks, other file types, and other suffixes are
skipped. All selected files are validated in filename order before output
creation or writing begins.

HTML uses a fixed document structure and escapes `&`, `<`, `>`, double quotes,
and single quotes in titles and bodies. See the [sample pages](sample/content/)
and [fixed expected HTML](fixtures/golden/) for complete examples.

Invalid invocation returns status 2. Normal configuration, content, and I/O
failures return status 1 with a single-line diagnostic on stderr. Successful
builds return status 0 with both output streams empty. A write or close
failure stops further output and may leave partial files; no rollback occurs.

## Verification

Verification requires Python 3, strace with path/fd filtering and fault
injection, bubblewrap, GNU time, and `file`. Run as a non-root user on Linux
amd64 with permission to create an isolated bubblewrap namespace. These are
test tools, not dependencies of the generated executable.

With a sibling Mognitio checkout, run:

```sh
python3 tools/verify.py --compiler ../Mognitio --evidence evidence/acceptance
```

Choose a new evidence directory for every run. The harness copies source and
fixtures into a dedicated temporary directory, prepares the Mognitio tests,
compares interpreted and native execution, injects filesystem failures,
checks standalone execution, and measures text processing costs.
It records source hashes, raw streams, initial and final file snapshots,
traces, and coverage. Raw evidence contains local environment details and is
ignored by Git; review and sanitize any summaries before sharing them.

The filesystem tests invoked by `mgn test` need fixtures prepared by the
harness. Running `mgn test` alone does not reset previous output.
Use `--only ordinary`, `--only faults`, or `--only measure` for a targeted run;
the default runs all groups. `tools/stress.py` is a separate, bounded
investigation of native scalar-scanning cost, outside the acceptance gate.

## Scope and limits

This increment has no HTTP server, routing, template language, Markdown,
recursive input, asset copying, clean command, or watch mode. It assumes a
finite, trusted, stationary filesystem and does not protect against
concurrent path replacement.

No input-size or processing-time bound is promised. Native scalar-heavy
processing currently has significant allocation-search overhead. Correct
output and acceptance results do not imply that this performance limitation
has been resolved.

v0.0.2 is a source release for Linux amd64, verified with Mognitio v1.0.0.
The generator behavior is unchanged from v0.0.1; no prebuilt executable is included.
See the [release verification](verification/v0.0.2-release.md) for tested scope and limits.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for public contribution conventions
and validation requirements.

### Observer regression checks

After a full verification run, validate the observer's negative controls:

```sh
python3 tools/regression.py --compiler ../Mognitio --evidence evidence/acceptance
```

Use the evidence directory from that full run, once. The checks reject missing,
duplicate, or failed test identities and missing external or measurement
results. They also execute real empty and incomplete test suites in temporary
source copies. Keep `tools/expectations.json` aligned with reviewed test changes;
never derive the required test set from the run being accepted. Do not use
`python -O` or `PYTHONOPTIMIZE` for verification.
