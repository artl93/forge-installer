#!/usr/bin/env python3
"""
Jar analysis for Forge modpacks: what a jar provides, what it demands, and
whether it can load at all.

Everything here is derived from what is INSIDE the jars. Nothing is guessed
from filenames -- filenames lie (accessories-neoforge-*.jar is a Forge jar;
expandedweather2dynamics-neoforge-1.21.1-*.jar really is a 1.21.1 NeoForge jar).
"""

import json, re, sys, zipfile
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None


def _toml(text):
    """mods.toml is TOML, but packs ship files with stray control characters
    and unescaped backslashes in descriptions. Fall back to a targeted parse
    rather than losing the whole jar to one bad quote."""
    if tomllib:
        try:
            return tomllib.loads(text)
        except Exception:
            pass
    mods, deps, cur, owner = [], {}, None, None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("[[mods]]"):
            cur = {}; mods.append(cur); owner = None
            continue
        m = re.match(r'\[\[dependencies\.?"?([^\]"]*)"?\]\]', s)
        if m:
            owner = m.group(1) or (mods[0].get("modId") if mods else "")
            cur = {}; deps.setdefault(owner, []).append(cur)
            continue
        if s.startswith("["):
            cur = None
            continue
        kv = re.match(r'([A-Za-z_]+)\s*=\s*(.*)', s)
        if kv and cur is not None:
            k, v = kv.group(1), kv.group(2).strip()
            v = v.split("#")[0].strip() if not v.startswith('"') else v
            if v.startswith('"') or v.startswith("'"):
                v = v[1:].split(v[0])[0] if len(v) > 1 else ""
            elif v in ("true", "false"):
                v = (v == "true")
            cur[k] = v
    out = {"mods": mods}
    if deps:
        out["dependencies"] = deps
    return out


def _read(z, name):
    try:
        return z.read(name).decode("utf-8", "replace")
    except KeyError:
        return None


def _deps_from(doc):
    """Normalise mods.toml dependency blocks.

    A dependency matters to the SERVER only when mandatory and not side=CLIENT.
    Missing side means BOTH (Forge's default), which is the case that bites.
    """
    out = []
    raw = doc.get("dependencies") or {}
    if isinstance(raw, dict):
        blocks = [b for v in raw.values() for b in (v if isinstance(v, list) else [v])]
    elif isinstance(raw, list):
        blocks = raw
    else:
        blocks = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        mid = b.get("modId") or b.get("modid")
        if not mid:
            continue
        out.append({
            "modId": str(mid),
            "mandatory": bool(b.get("mandatory", False)),
            "side": str(b.get("side", "BOTH")).upper(),
            "versionRange": str(b.get("versionRange", "*")),
        })
    return out


# Provided by the loader itself or by the vanilla jar; never a real dependency.
IMPLICIT = {"minecraft", "forge", "neoforge", "fabricloader", "fabric", "java"}


def analyze(path):
    """Return a record describing one jar."""
    p = Path(path)
    r = {
        "file": p.name, "provides": [], "deps": [], "nested": [],
        "loader": None, "mc": None, "problems": [],
        "data": 0, "assets": 0, "classes": 0,
        "mixin_client": 0, "mixin_common": 0, "mixin_server": 0,
    }
    try:
        z = zipfile.ZipFile(p)
    except Exception as e:
        r["problems"].append(f"not a readable zip: {e}")
        return r

    with z:
        names = z.namelist()
        r["data"] = sum(1 for n in names if n.startswith("data/") and n.endswith((".json", ".nbt", ".mcfunction")))
        r["assets"] = sum(1 for n in names if n.startswith("assets/"))
        r["classes"] = sum(1 for n in names if n.endswith(".class"))

        forge_toml = _read(z, "META-INF/mods.toml")
        neo_toml = _read(z, "META-INF/neoforge.mods.toml")
        fabric = _read(z, "fabric.mod.json")

        if forge_toml:
            r["loader"] = "forge"
            doc = _toml(forge_toml)
            for m in doc.get("mods") or []:
                if isinstance(m, dict) and m.get("modId"):
                    r["provides"].append(str(m["modId"]))
            r["deps"] = _deps_from(doc)
            for d in r["deps"]:
                if d["modId"] == "minecraft":
                    r["mc"] = d["versionRange"]
            for cfg in [n for n in names if re.fullmatch(r"[^/]*mixins?[^/]*\.json", n)]:
                try:
                    j = json.loads(z.read(cfg).decode("utf-8", "replace"))
                except Exception:
                    continue
                r["mixin_client"] += len(j.get("client") or [])
                r["mixin_common"] += len(j.get("mixins") or [])
                r["mixin_server"] += len(j.get("server") or [])

        elif neo_toml:
            # A NeoForge-only jar cannot load on Forge 1.20.1: FML reads
            # META-INF/mods.toml and this jar does not have one.
            r["loader"] = "neoforge-only"
            doc = _toml(neo_toml)
            for m in doc.get("mods") or []:
                if isinstance(m, dict) and m.get("modId"):
                    r["provides"].append(str(m["modId"]))
            r["problems"].append(
                "ships only META-INF/neoforge.mods.toml; Forge reads META-INF/mods.toml, "
                "so this jar is inert on Forge")
            if "example neoforge.mods.toml" in neo_toml or 'modId="examplemod"' in neo_toml:
                r["problems"].append("its neoforge.mods.toml is the unmodified example template")

        elif fabric:
            r["loader"] = "fabric"
            try:
                j = json.loads(fabric)
                if j.get("id"):
                    r["provides"].append(str(j["id"]))
            except Exception:
                pass

        else:
            mf = _read(z, "META-INF/MANIFEST.MF") or ""
            if "FMLModType" in mf:
                # A LIBRARY/GAMELIBRARY jar has no modId but still satisfies
                # dependencies by its artifact name (e.g. kotlinforforge).
                r["loader"] = "library"
                m = re.search(r"Automatic-Module-Name:\s*(\S+)", mf)
                stem = re.sub(r"-\d.*$", "", p.name)
                r["provides"].append(stem.lower())
                if m:
                    r["provides"].append(m.group(1).rsplit(".", 1)[-1].lower())
            elif any(n.startswith("META-INF/services/") and
                     ("modlauncher" in n or "forgespi" in n or "spongepowered" in n)
                     for n in names):
                # ModLauncher/FML service providers (ITransformationService,
                # IModLocator, IMixinService) load via ServiceLoader and never
                # need a mods.toml. mixin-booster is one; treating it as broken
                # would drop a jar the pack genuinely uses.
                r["loader"] = "service"
                r["provides"].append(re.sub(r"[-_]\d.*$", "", p.name).lower())
            else:
                r["problems"].append("no mods.toml, fabric.mod.json, FMLModType manifest, or ModLauncher service")

        # JarJar: a jar can satisfy a dependency from a jar nested inside it.
        # PuzzlesLib ships puzzlesaccessapi this way; Create ships ponder.
        for n in names:
            if n.startswith(("META-INF/jarjar/", "META-INF/jars/")) and n.endswith(".jar"):
                r["nested"].append(n.rsplit("/", 1)[-1])
                try:
                    import io
                    with zipfile.ZipFile(io.BytesIO(z.read(n))) as nz:
                        inner = None
                        try:
                            inner = nz.read("META-INF/mods.toml").decode("utf-8", "replace")
                        except KeyError:
                            pass
                        if inner:
                            for m in (_toml(inner).get("mods") or []):
                                if isinstance(m, dict) and m.get("modId"):
                                    r["provides"].append(str(m["modId"]))
                        else:
                            r["provides"].append(re.sub(r"-\d.*$", "", n.rsplit("/", 1)[-1]).lower())
                except Exception:
                    r["provides"].append(re.sub(r"-\d.*$", "", n.rsplit("/", 1)[-1]).lower())

    r["provides"] = sorted(set(x.lower() for x in r["provides"] if x))
    return r


def index(mod_dir):
    return [analyze(p) for p in sorted(Path(mod_dir).glob("*.jar"))]


def unmet(records):
    """Mandatory, non-CLIENT dependencies not provided by anything in the set."""
    have = set(IMPLICIT)
    for r in records:
        have.update(r["provides"])
    missing = []
    for r in records:
        for d in r["deps"]:
            if not d["mandatory"] or d["side"] == "CLIENT":
                continue
            if d["modId"].lower() not in have:
                missing.append((r["file"], d["modId"].lower()))
    return missing


if __name__ == "__main__":
    print(json.dumps(index(sys.argv[1]), indent=2))
