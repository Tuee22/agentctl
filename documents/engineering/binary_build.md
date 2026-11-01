# Binary Build

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Haskell package, quality legs and digest-keyed build](../../DEVELOPMENT_PLAN/phase-3-haskell-package-and-build.md)

> **Purpose**: State where the Cabal project lives and why, how a digest of its sources and pins keys the build, how the binary is built, published and identified, and what the wheel and sdist carry.

This page is the prose home of R5 in the [requirements table](../../DEVELOPMENT_PLAN/00-overview.md#requirements);
its data home is `tests/oracles/pins.toml`. One build function in `src/agentctl/bootstrap/build.py` does
everything below, and both the passthrough commands and `agentctl check` call it, so the binary a user runs
is built exactly as the gate builds it. The GHC and cabal it uses come from the
[toolchain bootstrap](toolchain_bootstrap.md); how the binary is handed a command, and the handshake it
answers, are in [the Python and Haskell boundary](../architecture/python_haskell_boundary.md).

## The Cabal Project as Package Data

The Cabal project is a directory of the Python package, `src/agentctl/haskell/`:

| Path | Holds |
|---|---|
| `agentctl-core.cabal` | the `AgentCtl.*` library, the executables `agentctl-core`, `agentctl-core-eval` and `agentctl-fake-agent`, the test suite `agentctl-core-test`, and the common warnings stanza of the [code standards](code_standards.md) |
| `cabal.project` | the pinned Hackage `index-state` |
| `fourmolu.yaml`, `.hlint.yaml` | the committed style configuration the `fourmolu` and `hlint` legs read |
| `app/`, `src/`, `test/` | the executables' mains, the library, and the tasty suite |

It lives inside the package for three reasons:

- **Editable installs see every edit.** An editable install links the package directory, so the sources check
  builds are the checkout's own, byte for byte.
- **Wheels and sdists carry it with no extra rule.** hatchling's ordinary selection includes package data and
  honours `.gitignore`.
- **One location in every install kind.** The build finds the project beside `agentctl/bootstrap/`, whether
  that is the checkout under an editable install or `site-packages` under a wheel install. cabal writes only
  under `--builddir` and `CABAL_DIR`, so nothing is ever written beside the sources.

```text
WRONG  [tool.hatch.build.targets.wheel.force-include]  "haskell" = "agentctl/haskell"
RIGHT  the Cabal project is src/agentctl/haskell/, ordinary package data, with no force-include rule
```

The WRONG form copies the tree into editable wheels as a snapshot, so check would build stale sources after
the first edit, and its directory walk ignores `.gitignore`, so a checkout with a local build ships
`dist-newstyle/` ([decision D-23](../../DEVELOPMENT_PLAN/rationale.md#decisions)).

## The Digest

The digest is a SHA-256 over three inputs, each path and each body entering length-prefixed so that no two
different inputs produce the same byte stream:

1. the relative POSIX path and the bytes of `agentctl-core.cabal`, `cabal.project`, and every file under
   `app/`, `src/` and `test/`, in sorted path order;
2. the bytes of `src/agentctl/bootstrap/pins.toml`, which holds the GHC and cabal pins;
3. the host's platform triple, the one that selects the ghcup pin, so a home directory shared between machines
   never hands one of them the other's binary.

`fourmolu.yaml` and `.hlint.yaml` change no binary and are left out, as is everything outside the project
except the pins, so a documentation or Python edit never rebuilds Haskell. `tests/unit/test_digest.py::test_oracle_rows`
applies the digest rows of `tests/oracles/pins.toml`: it computes every expected digest with `hashlib` from this
rule, never with the subject's own helper, and requires that editing a `.hs` file, the `.cabal` file,
`cabal.project` or a pin changes the digest while editing `fourmolu.yaml` or a file outside the project does
not.

## Build and Publish

A command that needs the binary takes these steps, and stops at the first that answers:

1. **Digest hit.** If `data/bin/<digest>/agentctl-core` (`agentctl-core.exe` on Windows) exists, nothing is built
   and nothing is spawned before the handoff (`tests/integration/test_build_cache.py::test_second_run_spawns_nothing`).
2. **Lock.** Otherwise the build takes a lock in `cache/build/<digest>` and looks again, so concurrent
   invocations build once and the others find the published binary.
3. **Toolchain.** The provisioning plan of the [toolchain bootstrap](toolchain_bootstrap.md) runs, and is empty on
   a provisioned host.
4. **Index.** `cabal update` runs only when the private package index does not yet reach the pinned
   `index-state`. agentctl records the `index-state` each successful update ran for, so a warm run makes no
   network request.
5. **Build.** `<cabal> build exe:agentctl-core --enable-tests -w <ghc> --builddir=<cache>/build/<digest>`, run in
   the project directory with absolute `<cabal>` and `<ghc>` from `ghcup whereis`.
6. **Publish.** The file `cabal list-bin exe:agentctl-core` names, under the same flags, is copied into a
   temporary directory under `data/bin/`, asked for the handshake, and only when it answers with the protocol
   version Python expects is that directory renamed to `data/bin/<digest>`. A rename that finds the digest
   already published discards the copy.

The flags are the ones check's `cabal-build` leg uses, which builds `all` instead of one executable
([the eight legs](quality_gate.md#the-eight-legs)). `--enable-tests` therefore gives a user's build the same
solver plan as the gate's without compiling the tests, and a binary published by a passthrough command is the
one check's identity step compares. A failed build or a wrong handshake publishes nothing and leaves every
other digest's directory as it was (`tests/integration/test_build_cache.py::test_failed_build_keeps_previous`,
`tests/integration/test_build_cache.py::test_handshake_mismatch_rejected`).

**A private cabal directory.** Every cabal invocation sets `CABAL_DIR` to `cache/cabal`, which then holds
cabal's configuration, the package index and the store. The user's cabal configuration therefore cannot change
the flags, repositories or store this build uses, and agentctl never updates the user's package index or adds
to the user's store. The pinned fourmolu and hlint are built through the same directory into
`cache/tools/<pin-digest>`. Dependencies compiled into the store are shared between digests, so a source edit
recompiles only the project's own components. The formats of these directories are in
[files and state](../reference/files_and_state.md).

**Never on PATH.** `[project.scripts]` in `pyproject.toml` names only `agentctl`, so pipx links nothing else;
agentctl writes into no directory on PATH; and the binary refuses to run without the handoff. A user never
needs its path, and no user-facing document names it.

## Binary Identity

Binary identity is the SHA-256 of the file `cabal list-bin exe:agentctl-core` names. Check's `binary-identity`
step runs after the `cabal-build` leg: it asks `cabal list-bin` for the path built in this run, publishes that
binary through step 6 when its digest has no directory yet, and then requires the SHA-256 of the built file to
equal the SHA-256 of `data/bin/<digest>/agentctl-core`, and `agentctl-core` to resolve nowhere on PATH. The
suite's end-to-end tests run the published binary, so they exercise the bytes cabal built from this tree in
this run; a stub placed at the digest path, or a binary published from other sources, fails the step.

- **No embedded digest.** The handshake reports the protocol version and the command list only. A digest the
  binary reported about itself would be a subject self-report, which never counts as evidence; the digest path
  and the hash of the built file identify it from outside
  ([decision D-25](../../DEVELOPMENT_PLAN/rationale.md#decisions)).
- **Test executables stay unpublished.** The suite runs `agentctl-core-eval` and `agentctl-fake-agent` from the
  paths `cabal list-bin` gives in the same build directory.
- **Reproducibility is not claimed.** GHC does not promise bit-identical output between builds. A published
  binary whose build directory was deleted, as clearing the `cache` directory does, can differ from a rebuild of
  the same digest; the step then fails naming both hashes, and deleting that one `data/bin/<digest>` directory
  is the remedy. agentctl itself never overwrites it.

## Packaging

- **Wheel.** The `agentctl` package, including `agentctl/haskell/` with every tracked file under
  `src/agentctl/haskell/`, and `agentctl/bootstrap/pins.toml`.
- **sdist.** Every file the VCS does not ignore, which includes the Cabal project, `tests/` and `pyproject.toml`.
- **What never ships.** `.gitignore` lists `dist-newstyle/`. Check builds outside the tree, so a
  `dist-newstyle/` exists only after an inner-loop `cabal build` in the checkout, and hatchling's selection
  leaves it out. No binary is committed or shipped: every host compiles its own from the bundled sources.

A wheel and an sdist built from a copy of the checkout must contain every tracked file under
`src/agentctl/haskell/` and no `dist-newstyle/` path
(`tests/integration/test_haskell_legs.py::test_wheel_ships_haskell_sources`). That a non-editable install
provisions and builds from those sources on a pristine host is confirmed by
[Clean-host bootstrap acceptance](../../DEVELOPMENT_PLAN/phase-12-clean-container-acceptance.md), whose Stage A
installs a copied tree without `--editable`.

## Upgrade

Upgrading is reinstalling with pipx (`pipx reinstall agentctl`, `pipx upgrade agentctl`, or
`pipx install --force` with the new source).
The new package data has a new digest, so the next command builds into a new `cache/build/<digest>` and
publishes a new `data/bin/<digest>`; the older directory is neither overwritten nor deleted.

- A pane trampoline, a supervisor, or on Windows a running `agentctl-core.exe` keeps running the older binary
  undisturbed, so an upgrade never restarts an agent.
- A failed build of the new digest publishes nothing; the command reports the build error and exits non-zero.
- No rollback machinery exists, because an upgrade replaces nothing. Older digests' directories stay until the
  user removes agentctl's per-user directories, as [installation](../operations/installation.md) describes.

## Related

- [toolchain_bootstrap.md](toolchain_bootstrap.md) — where the GHC and cabal that build the binary come from.
- [quality_gate.md](quality_gate.md#check-steps) — the `cabal-build`, `binary-identity` and `cabal-test` steps that use this build.
- [code_standards.md](code_standards.md) — the warnings stanza and style files inside the Cabal project.
- [python_haskell_boundary.md](../architecture/python_haskell_boundary.md) — the handoff and the handshake the publish step asks for.
- [files_and_state.md](../reference/files_and_state.md) — the formats of `cache` and `data`.
- [rationale.md](../../DEVELOPMENT_PLAN/rationale.md#rejected-alternatives) — why no binary is on PATH and no digest is embedded.
- [system-components.md](../../DEVELOPMENT_PLAN/system-components.md#haskell-package) — the inventory of the Cabal project.
- [Haskell package, quality legs and digest-keyed build](../../DEVELOPMENT_PLAN/phase-3-haskell-package-and-build.md) — the phase that builds this contract.
