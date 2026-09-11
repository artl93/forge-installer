# deploy/

## mcpack — any modpack → a running dedicated server

```
mcpack build  <source> <out>   [--heap 10G] [--port N] [--runtime-from DIR]
mcpack deploy <build>  --host user@host --name <instance> [--update] [--run]
mcpack all    <source> --host user@host --name <instance> [--heap 10G]
```

**Sources**: an installed CurseForge/Prism/MultiMC instance directory, a `.zip`
of one, a Modrinth `.mrpack`, or a CurseForge manifest-only export.

| source | needs a key? |
|---|---|
| installed instance directory | no |
| Modrinth `.mrpack` | no |
| CurseForge export **with** jars in `overrides/` | no |
| CurseForge **manifest-only** export | yes — `--cf-key` or `CURSEFORGE_API_KEY` |

A CurseForge manifest lists mods as project/file ids only. Resolving those needs
a free key from <https://console.curseforge.com/>. Note that CurseForge lets an
author **forbid third-party distribution**; for those files the API returns no
download URL. mcpack reports them by name rather than routing around the
author's setting — fetch those few by hand, or just install the pack in the
CurseForge app and point mcpack at the instance, which needs no key at all.

Sources are never modified. When a step has to write into the pack (applying
`overrides/`, downloading jars), mcpack copies it first.

**Loaders**: Forge, NeoForge, Fabric. The server runtime is installed from the
loader's own maven, so no pre-existing server build is required.

### Why there is a boot test in the middle

Forge mod metadata has **no field saying which side a mod belongs on**.
`displayTest` is about version handshakes; a mod's `[[mods]]` block has no
`side` at all. So "does the server need this?" cannot be read out of a jar —
only decided, then proven. Both directions of error happen in real packs:

* `sereneseasonsplus` hard-requires `betterdays`, which reads like a HUD mod.
  Drop it and the server aborts at load.
* `createenergycannons` reads as server-safe but touches client-only particle
  classes during common setup and crashes the server.

So `mcpack build` boots the build, reads the failure, corrects the classifier
and rebuilds — up to 6 times. Missing dependency → restore that mod. Mod blew
up during load → drop it. **A build that has not reached `Done (...)!` is not
finished.**

### The knowledge base

`lib/client-only-mods.txt` holds modIds proven client-only, keyed by modId so
it survives version bumps. Every boot-test correction should be added to it —
the script prints exactly what to add. That file is what makes each pack
cheaper to convert than the last.

Classification is deliberately conservative: a mod is dropped only when the
knowledge base names it, `--drop` names it, or it genuinely cannot load.
Heuristic suspicions are printed as advice and never acted on, because a wrong
drop fails in a much harder-to-read way than a wrong keep.

### Deploy safety

* Never modifies an existing `minecraft@.service` — other instances depend on
  its exact shape. It is created only if absent.
* Snapshots any existing instance to `/opt/minecraft/backups/` before touching it.
* `--update` preserves `world/`, `server.properties`, ops/whitelist/bans.
  Without it, a fresh install still refuses to clobber those if present.
* Stops and disables every other instance first — they share port 25565.
* The remote installer is written to the host and *not* executed unless you
  pass `--run`. Read it first.

## Files

| file | role |
|---|---|
| `mcpack` | CLI: build → boot-test correction loop → deploy |
| `lib/mcbuild.py` | source resolution, loader detect, runtime install, classify, assemble |
| `lib/packlib.py` | jar analysis: what a jar provides and demands |
| `lib/client-only-mods.txt` | accumulated client-only modIds |

`packlib` reads jar *contents*, never filenames — filenames lie. It resolves
both nesting conventions (`META-INF/jarjar/` **and** `META-INF/jars/`; missing
the second one caused a wrong "this pack is broken" call), honours
`side="CLIENT"` on dependencies, and recognises FML `LIBRARY` and ModLauncher
service-provider jars that carry no `mods.toml`.

## Helpers

`mc-switch` and `mc-archive` operate on instances already installed on a
server. Both honour `MC_ROOT` (default `/opt/minecraft`).

```
mc-switch list                 # instances, which runs, which autostarts, heap
mc-switch to <instance>        # make it the only running + autostarting one
mc-switch stop                 # stop everything, disable autostart
mc-switch console <instance>   # attach to its screen session
mc-archive <instance>          # snapshot to $MC_ROOT/backups/
```
