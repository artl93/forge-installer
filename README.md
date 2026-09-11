# mcpack

Turn any Minecraft modpack into a verified, running dedicated server.

```
mcpack build  <source> <out>   [--heap 10G] [--runtime-from DIR] [--cf-key KEY]
mcpack deploy <build>  --host user@host --name <instance> [--update] [--run]
mcpack all    <source> --host user@host --name <instance> [--heap 10G]
```

A modpack ships as a *client* pack. Making a server out of one means deciding
which mods the server actually needs, resolving what those mods depend on,
installing a matching server runtime, and proving the result boots. `mcpack`
does all four.

## Why this isn't a file copy

**Forge mod metadata has no field saying which side a mod belongs on.**
`displayTest` governs version handshakes, not sides, and a mod's own `[[mods]]`
block has no `side` at all. So "does the server need this?" cannot be read out
of a jar — only decided, and then proven by booting. Errors happen in both
directions, and both are silent until they aren't:

* `sereneseasonsplus` hard-requires `betterdays`, which looks like a HUD mod.
  Drop it and the server aborts at load.
* `createenergycannons` looks server-safe but touches client-only particle
  classes during common setup, and crashes the server.

So `mcpack build` boots the build, reads the failure, corrects the
classification and rebuilds — until it reaches `Done (...)!` or stops making
progress. **A build that has not booted is not finished.**

The loop distinguishes the two failures Forge reports in one block, by
`Actual version`:

| Forge says | meaning | correction |
|---|---|---|
| `Actual version: '[MISSING]'` | the jar is absent | restore it |
| `Actual version: '6.0.8'` | present, out of range | the *requester* can't run here; drop it |

## Sources

| source | needs a key? |
|---|---|
| installed CurseForge / Prism / MultiMC instance | no |
| Modrinth `.mrpack` | no |
| CurseForge export **with** jars in `overrides/` | no |
| CurseForge **manifest-only** export | yes — `--cf-key`, or `CURSEFORGE_API_KEY` |

A CurseForge manifest lists mods as project/file ids only; resolving them needs
a free key from <https://console.curseforge.com/>. CurseForge also lets authors
forbid third-party distribution — for those files the API returns no download
URL, and `mcpack` reports them by name rather than routing around the author's
setting.

Sources are never modified. When a step has to write into the pack (applying
`overrides/`, downloading jars), `mcpack` copies it first.

## Loaders

Forge, NeoForge and Fabric. The server runtime is installed from the loader's
own maven, so no pre-existing server build is needed. `--runtime-from DIR`
reuses an identical runtime already on disk (faster, and works offline).

## Deploying

```
mcpack deploy ./build --host me@box --name survival --update
```

Uploads the build, writes an installer to the host, and prints the command to
run it. It is **not executed** unless you pass `--run`; read it first.

* Never modifies an existing `minecraft@.service` — other instances depend on
  its exact shape. It is created only if absent.
* Snapshots any existing instance before touching it.
* `--update` preserves `world/`, `server.properties`, ops/whitelist/bans.
  Without it, a fresh install still refuses to clobber those if present.
* Stops and disables other instances first — they share port 25565.
* `--root DIR` (default `/opt/minecraft`) and `--user NAME` (default
  `minecraft`) for hosts with a different layout. `mc-switch` and `mc-archive`
  read the same values from `MC_ROOT` / `MC_USER`, so set them to match if you
  deployed under a non-default account.

## Layout

| path | role |
|---|---|
| `deploy/mcpack` | CLI: build → boot-test correction loop → deploy |
| `deploy/lib/mcbuild.py` | source resolution, loader detect, runtime install, assemble |
| `deploy/lib/packlib.py` | jar analysis: what a jar provides and demands |
| `deploy/lib/client-only-mods.txt` | accumulated client-only modIds |
| `deploy/mc-switch` | swap which instance runs and autostarts |
| `deploy/mc-archive` | snapshot an instance |
| `install-forge.sh` | standalone Forge installer (predates `mcpack`) |

`packlib` reads jar *contents*, never filenames — filenames lie. It resolves
both nesting conventions (`META-INF/jarjar/` **and** `META-INF/jars/`),
honours `side="CLIENT"` on dependencies, and recognises FML `LIBRARY` and
ModLauncher service-provider jars that carry no `mods.toml`.

`client-only-mods.txt` is the accumulating asset: every boot-test correction
belongs in it, and the tool prints exactly what to add. Classification is
deliberately conservative — a mod is dropped only when that list names it,
`--drop` names it, or it genuinely cannot load. Heuristic suspicions are
printed as advice and never acted on, because a wrong drop fails in a much
harder-to-read way than a wrong keep.

## Requirements

Python 3.9+, Java (matching the pack's Minecraft version), `rsync`, `ssh`.
Servers need `screen` and systemd.

## License

See [LICENSE](LICENSE).
