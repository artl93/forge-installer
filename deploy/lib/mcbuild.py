#!/usr/bin/env python3
"""
mcbuild -- resolve a modpack from any source and assemble a server build.

Sources understood:
  * an installed CurseForge/Prism/MultiMC instance directory (has mods/)
  * a .zip of one
  * a Modrinth .mrpack            (jars are downloaded from its index)
  * a CurseForge export .zip      (manifest.json + overrides/, NO jars --
                                   detected and explained, since fetching
                                   those needs a CurseForge API key)

Loaders understood: Forge, NeoForge, Fabric. The server runtime is installed
from the loader's own maven/meta endpoint, so no pre-existing build is needed.
"""

import argparse, json, os, re, shutil, subprocess, sys, urllib.request, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import packlib

KB = Path(__file__).resolve().parent / "client-only-mods.txt"

CLIENT_DIRS = {
    "shaderpacks", "resourcepacks", "saves", "screenshots", "downloads",
    "profileImage", "logs", "crash-reports", "schematics", "essential",
    "Distant_Horizons_server_data", "local", ".mixin.out", "configureddefaults",
    "assets", "versions", "natives", "libraries",
}
CLIENT_FILES = {
    "options.txt", "servers.dat", "servers.dat_old", "servers.essential.dat",
    "minecraftinstance.json", "manifest.json", "modlist.html", "usercache.json",
    ".DS_Store", "instance.cfg", "mmc-pack.json", "modrinth.index.json",
}
KUBEJS_CLIENT = {"client_scripts", "assets", "probe"}

CF_API = "https://api.curseforge.com/v1"
FORGE_MAVEN = "https://maven.minecraftforge.net/net/minecraftforge/forge"
NEO_MAVEN = "https://maven.neoforged.net/releases/net/neoforged/neoforge"
FABRIC_META = "https://meta.fabricmc.net/v2/versions"


def log(m): print(f"  {m}", flush=True)


def fetch(url, dest, expect_min=1024):
    log(f"downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "mcpack/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    n = dest.stat().st_size
    if n < expect_min:
        raise SystemExit(f"ERROR: {url} returned only {n} bytes")
    log(f"got {n//1024} KB")


# ------------------------------------------------------------------ sources
def _mutable_copy(src: Path, work: Path) -> Path:
    """Return a directory we are allowed to write into.

    Applying overrides/ and downloading jars both WRITE into the pack dir. If
    the source is something the user owns -- an export they unzipped in
    Downloads -- doing that in place silently litters their directory. So work
    on a copy unless we are already inside our own extraction.
    """
    try:
        if src == work or work in src.parents:
            return src
    except Exception:
        pass
    work.mkdir(parents=True, exist_ok=True)
    dst = work / src.name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    log(f"working on a copy (the source directory is left untouched)")
    return dst


def resolve_source(src: Path, work: Path, cfkey=None):
    """Return a directory containing mods/ (+ config/ etc), unpacking as needed."""
    src = src.expanduser()
    if src.is_file() and src.suffix in (".zip", ".mrpack"):
        work.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(src) as z:
            z.extractall(work)
        log(f"unpacked {src.name}")
        src = work
    if not src.is_dir():
        raise SystemExit(f"ERROR: source not found: {src}")

    # A zip often contains a single top-level folder.
    if not (src / "mods").is_dir():
        subs = [d for d in src.iterdir() if d.is_dir()]
        for d in subs:
            if (d / "mods").is_dir() or (d / "modrinth.index.json").exists() \
               or (d / "manifest.json").exists():
                src = d
                break

    idx = src / "modrinth.index.json"
    if idx.exists():
        src = _mutable_copy(src, work)
        return resolve_mrpack(src, src / "modrinth.index.json")

    mf = src / "manifest.json"
    if mf.exists() and not (src / "mods").is_dir():
        ov = src / "overrides"
        if (ov / "mods").is_dir() and any((ov / "mods").glob("*.jar")):
            log("CurseForge export with jars in overrides/")
            return ov
        key = cf_key(cfkey)
        if key:
            log("CurseForge manifest-only export -- downloading mods via the API")
            src = _mutable_copy(src, work)
            return fetch_curseforge(src, src / "manifest.json", key)
        raise SystemExit(
            "ERROR: this is a CurseForge manifest-only export. It lists mods by\n"
            "       project/file id but contains no jars.\n\n"
            "       Either:\n"
            "         * pass --cf-key KEY (free at https://console.curseforge.com/),\n"
            "           or set CURSEFORGE_API_KEY, and mcpack will download them; or\n"
            "         * install the pack in the CurseForge app and point mcpack at\n"
            "           the resulting instance directory -- no key needed.")

    if not (src / "mods").is_dir():
        raise SystemExit(f"ERROR: no mods/ found under {src}")
    return src


def cf_key(explicit=None):
    return explicit or os.environ.get("CURSEFORGE_API_KEY") or ""


def fetch_curseforge(root: Path, manifest: Path, key: str):
    """Download a CurseForge manifest-only export's jars via the official API.

    Needs a free API key from console.curseforge.com, passed as --cf-key or
    CURSEFORGE_API_KEY.

    CurseForge lets an author forbid third-party distribution. For those files
    the API returns no downloadUrl, and this reports them instead of trying to
    route around it -- that setting is the author's decision. Get those few
    through the CurseForge app and drop them into mods/, or just install the
    pack in the app and point mcpack at the instance.
    """
    d = json.loads(manifest.read_text(errors="replace"))
    files = d.get("files") or []
    if not files:
        raise SystemExit("ERROR: manifest.json lists no files")
    log(f"manifest lists {len(files)} mods")

    ov = root / "overrides"
    if ov.is_dir():
        for item in ov.iterdir():
            tgt = root / item.name
            if item.is_dir():
                shutil.copytree(item, tgt, dirs_exist_ok=True)
            else:
                shutil.copy2(item, tgt)
        log("applied overrides/")
    mods = root / "mods"
    mods.mkdir(exist_ok=True)

    hdr = {"x-api-key": key, "Accept": "application/json",
           "Content-Type": "application/json", "User-Agent": "mcpack/1.0"}
    ids = [int(f["fileID"]) for f in files if f.get("fileID")]
    meta = {}
    # Bulk endpoint: one round trip per 300 files instead of one per mod.
    for i in range(0, len(ids), 300):
        chunk = ids[i:i + 300]
        body = json.dumps({"fileIds": chunk}).encode()
        req = urllib.request.Request(f"{CF_API}/mods/files", data=body,
                                     headers=hdr, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                for e in json.loads(r.read()).get("data") or []:
                    meta[e["id"]] = e
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise SystemExit(
                    "ERROR: CurseForge rejected the API key (HTTP %d).\n"
                    "       Get one free at https://console.curseforge.com/ and pass\n"
                    "       --cf-key KEY or set CURSEFORGE_API_KEY." % e.code)
            raise SystemExit(f"ERROR: CurseForge API returned HTTP {e.code}")
        log(f"resolved {len(meta)}/{len(ids)} file records")

    blocked, got = [], 0
    for fid in ids:
        e = meta.get(fid)
        if not e:
            blocked.append((fid, "no record returned"))
            continue
        name = e.get("fileName") or f"{fid}.jar"
        url = e.get("downloadUrl")
        dest = mods / name
        if dest.exists():
            got += 1
            continue
        if not url:
            blocked.append((fid, name))
            continue
        try:
            fetch(url, dest, expect_min=64)
            got += 1
        except Exception as ex:
            blocked.append((fid, f"{name}: {ex}"))

    log(f"downloaded {got}/{len(ids)} mods")
    if blocked:
        print("\n  COULD NOT DOWNLOAD -- the author disabled third-party distribution")
        print("  for these, so the API gives no download URL:")
        for fid, what in blocked:
            print(f"    - {what}   (fileID {fid})")
        print("\n  Get them from the CurseForge site/app and drop them into")
        print(f"    {mods}")
        print("  then re-run. Or simply install the pack in the CurseForge app and")
        print("  point mcpack at the resulting instance directory -- no key needed.")
        raise SystemExit(f"ERROR: {len(blocked)} mods could not be downloaded")
    return root


def resolve_mrpack(root: Path, index: Path):
    """Modrinth packs list direct download URLs -- no API key needed. Files
    marked client-only in the index are skipped outright."""
    d = json.loads(index.read_text())
    mods = root / "mods"
    mods.mkdir(exist_ok=True)
    ov = root / "overrides"
    if ov.is_dir():
        for item in ov.iterdir():
            tgt = root / item.name
            if item.is_dir():
                shutil.copytree(item, tgt, dirs_exist_ok=True)
            else:
                shutil.copy2(item, tgt)
    files = d.get("files") or []
    log(f"mrpack lists {len(files)} files")
    for f in files:
        env = (f.get("env") or {})
        if env.get("server") == "unsupported":
            continue
        path = root / f["path"]
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        urls = f.get("downloads") or []
        if not urls:
            continue
        fetch(urls[0], path, expect_min=64)
    return root


def detect_loader(src: Path, work_src: Path):
    """(minecraft_version, loader, loader_version)"""
    for base in (src, work_src):
        mi = base / "minecraftinstance.json"
        if mi.exists():
            try:
                d = json.loads(mi.read_text(errors="replace"))
                nm = (d.get("baseModLoader") or {}).get("name") or ""
                for pat, ldr in (("forge-", "forge"), ("neoforge-", "neoforge"),
                                 ("fabric-", "fabric")):
                    m = re.search(pat + r"([\d.]+)", nm)
                    if m:
                        return d.get("gameVersion") or "1.20.1", ldr, m.group(1)
            except Exception:
                pass
        mf = base / "manifest.json"
        if mf.exists():
            try:
                d = json.loads(mf.read_text(errors="replace"))
                mc = d.get("minecraft") or {}
                for L in mc.get("modLoaders") or []:
                    i = L.get("id", "")
                    for pat, ldr in (("forge-", "forge"), ("neoforge-", "neoforge"),
                                     ("fabric-", "fabric")):
                        if i.startswith(pat):
                            return mc.get("version", "1.20.1"), ldr, i[len(pat):]
            except Exception:
                pass
        idx = base / "modrinth.index.json"
        if idx.exists():
            try:
                dep = (json.loads(idx.read_text()).get("dependencies") or {})
                mc = dep.get("minecraft", "1.20.1")
                for k, ldr in (("forge", "forge"), ("neoforge", "neoforge"),
                               ("fabric-loader", "fabric")):
                    if k in dep:
                        return mc, ldr, dep[k]
            except Exception:
                pass
        mm = base / "mmc-pack.json"
        if mm.exists():
            try:
                comps = json.loads(mm.read_text()).get("components") or []
                mc = next((c["version"] for c in comps if c.get("uid") == "net.minecraft"), "1.20.1")
                for uid, ldr in (("net.minecraftforge", "forge"),
                                 ("net.neoforged", "neoforge"),
                                 ("net.fabricmc.fabric-loader", "fabric")):
                    v = next((c["version"] for c in comps if c.get("uid") == uid), None)
                    if v:
                        return mc, ldr, v
            except Exception:
                pass
    return None, None, None


# ------------------------------------------------------------------ runtime
def install_runtime(out: Path, mc, loader, ver, copy_from=None):
    """Put libraries/ + run.sh + unix_args into `out`.

    Preferred path is the loader's own installer, so any pack works without a
    pre-existing build. --runtime-from short-circuits it when you already have
    the identical version on disk (faster, and works offline)."""
    if copy_from:
        rt = Path(copy_from).expanduser()
        probe = {
            "forge": rt / "libraries/net/minecraftforge/forge" / f"{mc}-{ver}",
            "neoforge": rt / "libraries/net/neoforged/neoforge" / str(ver),
        }.get(loader)
        if probe and probe.is_dir():
            shutil.copytree(rt / "libraries", out / "libraries", dirs_exist_ok=True)
            for f in ("run.sh", "user_jvm_args.txt"):
                if (rt / f).exists():
                    shutil.copy2(rt / f, out / f)
            log(f"runtime copied from {rt.name}")
            return True
        log(f"--runtime-from has no {loader} {mc}-{ver}; installing instead")

    if loader == "fabric":
        return install_fabric(out, mc, ver)
    if loader not in ("forge", "neoforge"):
        raise SystemExit(f"ERROR: unsupported loader '{loader}'")

    if loader == "forge":
        art = f"{mc}-{ver}"
        url = f"{FORGE_MAVEN}/{art}/forge-{art}-installer.jar"
    else:
        art = str(ver)
        url = f"{NEO_MAVEN}/{art}/neoforge-{art}-installer.jar"

    jar = out / f"{loader}-installer.jar"
    try:
        fetch(url, jar, expect_min=100_000)
    except Exception as e:
        raise SystemExit(
            f"ERROR: could not download the {loader} {art} installer.\n"
            f"       {e}\n"
            f"       URL: {url}\n"
            f"       Check the version exists, or pass --runtime-from <existing build>.")
    log(f"running the {loader} installer (--installServer)")
    p = subprocess.run(["java", "-jar", jar.name, "--installServer"],
                       cwd=out, capture_output=True, text=True)
    if p.returncode != 0:
        tail = (p.stdout + p.stderr).strip().splitlines()[-15:]
        raise SystemExit("ERROR: installer failed:\n       " + "\n       ".join(tail))
    jar.unlink(missing_ok=True)
    (out / f"{loader}-installer.jar.log").unlink(missing_ok=True)
    if not (out / "run.sh").exists():
        raise SystemExit("ERROR: installer produced no run.sh")
    (out / "run.sh").chmod(0o755)
    log(f"{loader} {art} server runtime installed")
    return True


def install_fabric(out: Path, mc, ver):
    meta = json.loads(urllib.request.urlopen(
        f"{FABRIC_META}/loader/{mc}", timeout=60).read())
    if not meta:
        raise SystemExit(f"ERROR: no Fabric loader for Minecraft {mc}")
    loader_v = ver or meta[0]["loader"]["version"]
    inst = json.loads(urllib.request.urlopen(
        f"{FABRIC_META}/installer", timeout=60).read())[0]["version"]
    url = f"{FABRIC_META}/loader/{mc}/{loader_v}/{inst}/server/jar"
    fetch(url, out / "fabric-server-launch.jar", expect_min=10_000)
    (out / "run.sh").write_text(
        "#!/usr/bin/env sh\n"
        "java @user_jvm_args.txt -jar fabric-server-launch.jar nogui \"$@\"\n")
    (out / "run.sh").chmod(0o755)
    log(f"fabric {loader_v} server runtime installed")
    return True


# ----------------------------------------------------------------- classify
def load_kb():
    ids = set()
    if KB.exists():
        for line in KB.read_text().splitlines():
            line = line.split("#")[0].strip()
            if line:
                ids.add(line.lower())
    return ids


def classify(recs, kb, force_keep, force_drop):
    keep, client, broken, advice = [], [], [], []
    for r in recs:
        ids = set(r["provides"])
        if ids & force_keep:
            keep.append(r); continue
        if r["loader"] == "neoforge-only" or (r["loader"] is None and not ids):
            broken.append((r, "; ".join(r["problems"]) or "no loadable metadata")); continue
        if ids & force_drop:
            client.append((r, "forced by --drop")); continue
        if ids & kb:
            client.append((r, "known client-only")); continue
        if (r["data"] == 0 and r["mixin_common"] == 0 and r["mixin_server"] == 0
                and (r["mixin_client"] > 0 or r["assets"] > 0)):
            advice.append((r["file"], sorted(ids)))
        keep.append(r)
    return keep, client, broken, advice


def resolve_deps(keep, client, broken):
    moved, unloadable = [], []
    for _ in range(20):
        have = set(packlib.IMPLICIT)
        for r in keep:
            have.update(r["provides"])
        missing = {}
        for r in keep:
            for d in r["deps"]:
                if d["mandatory"] and d["side"] != "CLIENT":
                    mid = d["modId"].lower()
                    if mid not in have:
                        missing.setdefault(mid, []).append(r)
        if not missing:
            break
        progress = False
        for mid, requesters in missing.items():
            prov = next((c for c in client if mid in c[0]["provides"]), None)
            if prov:
                client.remove(prov); keep.append(prov[0])
                moved.append((prov[0]["file"], mid)); progress = True
            else:
                for r in requesters:
                    if r in keep:
                        keep.remove(r)
                        broken.append((r, f"requires '{mid}', which no jar in this pack provides"))
                        unloadable.append((r["file"], mid)); progress = True
        if not progress:
            break
    return moved, unloadable


def copy_content(src: Path, dst: Path):
    dst.mkdir(parents=True, exist_ok=True)
    for item in sorted(src.iterdir()):
        if item.name in CLIENT_DIRS or item.name in CLIENT_FILES or item.name == "mods":
            continue
        if item.name.startswith("."):
            continue
        target = dst / item.name
        if item.is_dir():
            if item.name == "kubejs":
                target.mkdir(exist_ok=True)
                for sub in sorted(item.iterdir()):
                    if sub.name in KUBEJS_CLIENT:
                        continue
                    if sub.is_dir():
                        shutil.copytree(sub, target / sub.name, dirs_exist_ok=True)
                    else:
                        shutil.copy2(sub, target / sub.name)
            else:
                shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def main():
    ap = argparse.ArgumentParser(prog="mcbuild")
    ap.add_argument("source"); ap.add_argument("out")
    ap.add_argument("--heap", default="8G")
    ap.add_argument("--runtime-from", dest="runtime_from")
    ap.add_argument("--no-runtime", action="store_true")
    ap.add_argument("--cf-key", dest="cf_key",
                    help="CurseForge API key (or set CURSEFORGE_API_KEY) -- "
                         "only needed for a manifest-only export")
    ap.add_argument("--keep", action="append", default=[])
    ap.add_argument("--drop", action="append", default=[])
    a = ap.parse_args()

    out = Path(a.out).expanduser()
    work = out.parent / (out.name + ".src")
    if work.exists():
        shutil.rmtree(work)

    src = resolve_source(Path(a.source), work, a.cf_key)
    mc, loader, lver = detect_loader(Path(a.source).expanduser(), src)
    if not loader:
        raise SystemExit(
            "ERROR: could not determine the mod loader.\n"
            "       Expected minecraftinstance.json, manifest.json,\n"
            "       modrinth.index.json or mmc-pack.json alongside mods/.")
    log(f"pack   : Minecraft {mc}, {loader} {lver}")

    recs = packlib.index(src / "mods")
    keep, client, broken, advice = classify(
        recs, load_kb(), {x.lower() for x in a.keep}, {x.lower() for x in a.drop})
    moved, unloadable = resolve_deps(keep, client, broken)
    log(f"jars   : {len(recs)} -> keep {len(keep)}, client-only {len(client)}, unloadable {len(broken)}")

    if moved:
        print("\n  restored from the client-only pile (a kept mod hard-requires them):")
        for f, m in moved:
            print(f"    + {f}   provides '{m}'")
    if broken:
        print("\n  NOT DEPLOYED -- cannot load:")
        for r, why in broken:
            print(f"    - {r['file']}\n        {why}")
    unmet = packlib.unmet(keep)
    if unmet:
        print("\n  STILL UNMET (the server will abort at load):")
        for f, m in unmet:
            print(f"    ! {m}  <- {f}")

    if out.exists():
        shutil.rmtree(out)
    copy_content(src, out)
    for d in ("mods", "_client_only", "_unloadable"):
        (out / d).mkdir(parents=True, exist_ok=True)
    for r in keep:
        shutil.copy2(src / "mods" / r["file"], out / "mods" / r["file"])
    for r, _ in client:
        shutil.copy2(src / "mods" / r["file"], out / "_client_only" / r["file"])
    for r, _ in broken:
        shutil.copy2(src / "mods" / r["file"], out / "_unloadable" / r["file"])

    (out / "eula.txt").write_text("eula=true\n")
    (out / "user_jvm_args.txt").write_text(
        f"-Xmx{a.heap}\n-Xms{a.heap}\n-XX:+UseG1GC\n-XX:MaxGCPauseMillis=100\n"
        "-XX:+AlwaysPreTouch\n-XX:+ParallelRefProcEnabled\n-XX:+DisableExplicitGC\n")

    if not a.no_runtime:
        install_runtime(out, mc, loader, lver, a.runtime_from)
        # the installer writes its own user_jvm_args.txt; ours wins
        (out / "user_jvm_args.txt").write_text(
            f"-Xmx{a.heap}\n-Xms{a.heap}\n-XX:+UseG1GC\n-XX:MaxGCPauseMillis=100\n"
            "-XX:+AlwaysPreTouch\n-XX:+ParallelRefProcEnabled\n-XX:+DisableExplicitGC\n")

    (out / "BUILD-REPORT.json").write_text(json.dumps({
        "source": str(a.source), "minecraft": mc, "loader": loader,
        "loader_version": lver, "heap": a.heap,
        "total": len(recs), "kept": len(keep),
        "client_only": [c[0]["file"] for c in client],
        "unloadable": [[r["file"], w] for r, w in broken],
        "restored_for_deps": moved, "unmet": unmet, "advice": advice,
    }, indent=2))
    if work.exists() and work != src:
        shutil.rmtree(work, ignore_errors=True)
    log(f"built  : {out}  ({len(keep)} mods)")
    if advice:
        log(f"note   : {len(advice)} jars look client-side but were kept; the boot test decides")


if __name__ == "__main__":
    main()
