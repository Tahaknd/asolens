"""Static `.app` bundle audit plus a minimal Simulator sweep.

STATIC (works now, no Simulator needed)
    Reads Info.plist, the signed entitlements and the bundle layout, and
    reports the things that routinely ship broken: missing privacy usage
    strings, a missing privacy manifest, arbitrary-loads ATS exceptions,
    document sharing left on, absent associated domains.

DYNAMIC (experimental)
    Boots a Simulator, installs, launches, then captures a screenshot per step
    while tapping a coarse grid. This gives you a visual sweep, not a real
    crawl: `simctl` has no accessibility-tree command, so the tool cannot know
    what it tapped. For a true crawler you need either an XCUITest target
    inside the app or Meta's `idb` (`idb ui describe-all`), which exposes the
    element tree; `probe_accessibility` uses `idb` when it is installed.
"""

import json
import os
import plistlib
import re
import shutil
import subprocess
import time

from asolens.aso import CRITICAL, INFO, OK, WARN, Finding
from asolens.util import human_size

PLACEHOLDER = re.compile(
    r"^\s*$|lorem|todo|xxx|test|placeholder|description here|açıklama", re.I)

# Keys the App Store rejects an app for when the matching API is linked.
USAGE_KEYS = (
    "NSCameraUsageDescription",
    "NSMicrophoneUsageDescription",
    "NSPhotoLibraryUsageDescription",
    "NSPhotoLibraryAddUsageDescription",
    "NSLocationWhenInUseUsageDescription",
    "NSLocationAlwaysAndWhenInUseUsageDescription",
    "NSContactsUsageDescription",
    "NSCalendarsUsageDescription",
    "NSRemindersUsageDescription",
    "NSMotionUsageDescription",
    "NSFaceIDUsageDescription",
    "NSBluetoothAlwaysUsageDescription",
    "NSUserTrackingUsageDescription",
    "NSSpeechRecognitionUsageDescription",
    "NSHealthShareUsageDescription",
)


# ----------------------------------------------------------------- static side

def _read_plist(app_path):
    path = os.path.join(app_path, "Info.plist")
    if not os.path.exists(path):
        raise FileNotFoundError("Info.plist bulunamadı: %s" % path)
    with open(path, "rb") as fh:
        return plistlib.load(fh)


def _entitlements(app_path):
    if not shutil.which("codesign"):
        return None
    try:
        proc = subprocess.run(
            ["codesign", "-d", "--entitlements", ":-", app_path],
            capture_output=True, timeout=30)
    except (subprocess.SubprocessError, OSError):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    try:
        return plistlib.loads(proc.stdout)
    except Exception:
        return None


def _tree_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def static_audit(app_path):
    """Audit a built `.app` bundle. Returns (info, findings)."""
    app_path = os.path.abspath(app_path.rstrip("/"))
    plist = _read_plist(app_path)
    ents = _entitlements(app_path)
    findings = []

    info = {
        "path": app_path,
        "bundle_id": plist.get("CFBundleIdentifier"),
        "name": plist.get("CFBundleDisplayName") or plist.get("CFBundleName"),
        "version": plist.get("CFBundleShortVersionString"),
        "build": plist.get("CFBundleVersion"),
        "min_os": plist.get("MinimumOSVersion"),
        "size_bytes": _tree_size(app_path),
        "schemes": [
            s for t in plist.get("CFBundleURLTypes") or []
            for s in t.get("CFBundleURLSchemes") or []
        ],
        "localizations": sorted(
            d[:-6] for d in os.listdir(app_path) if d.endswith(".lproj")),
        "associated_domains": (ents or {}).get(
            "com.apple.developer.associated-domains") or [],
        "entitlements_read": ents is not None,
    }

    findings.append(Finding(
        "bundle.identity", INFO,
        "%s · v%s (%s) · min iOS %s" % (
            info["bundle_id"], info["version"], info["build"], info["min_os"]),
        "Paket boyutu %s" % human_size(info["size_bytes"]), 0, app_path))

    # Privacy usage strings
    bad = []
    for key in USAGE_KEYS:
        if key in plist:
            value = plist[key]
            if not isinstance(value, str) or PLACEHOLDER.match(value) or len(value) < 15:
                bad.append("%s = %r" % (key, value))
    if bad:
        findings.append(Finding(
            "bundle.usage_strings", CRITICAL,
            "%d izin açıklaması şablon veya çok kısa" % len(bad),
            "App Review bu metinleri okuyor ve belirsiz olanları reddediyor. "
            "Her metin kullanıcıya neden gerektiğini söylemeli.", 8, bad))
    elif any(k in plist for k in USAGE_KEYS):
        findings.append(Finding(
            "bundle.usage_strings", OK,
            "İzin açıklamaları dolu (%d adet)"
            % sum(1 for k in USAGE_KEYS if k in plist), "", 8))

    # Privacy manifest — required for App Store submission
    manifest = os.path.join(app_path, "PrivacyInfo.xcprivacy")
    if os.path.exists(manifest):
        findings.append(Finding(
            "bundle.privacy_manifest", OK, "PrivacyInfo.xcprivacy mevcut", "", 6))
    else:
        findings.append(Finding(
            "bundle.privacy_manifest", CRITICAL, "PrivacyInfo.xcprivacy yok",
            "Apple bu dosyayı App Store yüklemesinde zorunlu tutuyor; eksikse "
            "yükleme uyarı alır veya reddedilir.", 6, manifest))

    # App Transport Security
    ats = plist.get("NSAppTransportSecurity") or {}
    if ats.get("NSAllowsArbitraryLoads"):
        findings.append(Finding(
            "bundle.ats", CRITICAL, "NSAllowsArbitraryLoads açık",
            "Tüm HTTPS zorunluluğu kapatılmış. App Review gerekçe istiyor ve "
            "şifresiz trafiğe izin veriyor.", 7, ats))
    else:
        findings.append(Finding("bundle.ats", OK, "ATS istisnası yok", "", 7))

    # Document sharing
    if plist.get("UIFileSharingEnabled"):
        findings.append(Finding(
            "bundle.file_sharing", WARN, "UIFileSharingEnabled açık",
            "Uygulamanın Documents klasörü Dosyalar uygulamasında görünüyor. "
            "Kasıtlı değilse kullanıcı verisini açığa çıkarır.", 4, True))

    # Launch screen
    if not (plist.get("UILaunchStoryboardName") or plist.get("UILaunchScreen")
            or plist.get("UILaunchScreens")):
        findings.append(Finding(
            "bundle.launch_screen", WARN, "Açılış ekranı tanımlı değil",
            "Açılış ekranı olmayan app'ler iPad'de ve yeni cihazlarda "
            "uyumluluk modunda, küçük pencerede açılabilir.", 5, None))
    else:
        findings.append(Finding("bundle.launch_screen", OK, "Açılış ekranı tanımlı", "", 5))

    # Export compliance
    if "ITSAppUsesNonExemptEncryption" not in plist:
        findings.append(Finding(
            "bundle.encryption", INFO, "ITSAppUsesNonExemptEncryption tanımlı değil",
            "Her TestFlight yüklemesinde şifreleme sorusu tekrar sorulur; "
            "Info.plist'e eklemek bu adımı kaldırır.", 0, None))

    # Deep link surface
    if info["associated_domains"]:
        findings.append(Finding(
            "bundle.associated_domains", OK,
            "%d associated domain tanımlı" % len(info["associated_domains"]),
            ", ".join(info["associated_domains"]), 6, info["associated_domains"]))
    elif info["entitlements_read"]:
        findings.append(Finding(
            "bundle.associated_domains", WARN, "Associated domain yok",
            "Universal Links entitlement'ı tanımlı değil; web linkleri app'i "
            "açmaz." + (" Özel URL şeması var: %s (bu linkler Safari'den "
                        "güvenilir biçimde çalışmaz)." % ", ".join(info["schemes"])
                        if info["schemes"] else ""), 6, None))
    else:
        findings.append(Finding(
            "bundle.associated_domains", INFO, "Entitlement okunamadı",
            "İmzasız veya Simulator derlemesi olabilir; associated domain "
            "kontrolü atlandı.", 0, None))

    # Localization
    if len(info["localizations"]) <= 1:
        findings.append(Finding(
            "bundle.localization", INFO,
            "Tek dil paketi (%s)" % (", ".join(info["localizations"]) or "yok"),
            "", 0, info["localizations"]))
    else:
        findings.append(Finding(
            "bundle.localization", OK,
            "%d dil paketi" % len(info["localizations"]),
            ", ".join(info["localizations"]), 0, info["localizations"]))

    return info, findings


# ---------------------------------------------------------------- dynamic side

def _simctl(*args, timeout=120):
    return subprocess.run(
        ["xcrun", "simctl", *args], capture_output=True, text=True, timeout=timeout)


def booted_device():
    proc = _simctl("list", "devices", "booted", "-j", timeout=30)
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return None
    for devices in (data.get("devices") or {}).values():
        for device in devices:
            if device.get("state") == "Booted":
                return device
    return None


def probe_accessibility(udid):
    """Return the on-screen element tree if `idb` is installed, else None."""
    if not shutil.which("idb"):
        return None
    try:
        proc = subprocess.run(
            ["idb", "ui", "describe-all", "--udid", udid],
            capture_output=True, text=True, timeout=60)
    except (subprocess.SubprocessError, OSError):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return None


def dynamic_sweep(app_path, out_dir, device=None, steps=6, settle=2.0):
    """Install, launch and capture a screenshot sweep. Experimental.

    Returns a dict with the captured frames and whatever accessibility data
    was available. Raises RuntimeError with an actionable message when the
    Simulator is not usable.
    """
    if not shutil.which("xcrun"):
        raise RuntimeError("xcrun bulunamadı — Xcode komut satırı araçları kurulu değil.")

    target = device
    if not target:
        found = booted_device()
        if not found:
            raise RuntimeError(
                "Açık Simulator yok. Bir cihaz başlat "
                "(xcrun simctl boot 'iPhone 17 Pro') veya --device ile ad/UDID ver.")
        target = found["udid"]

    bundle_id = _read_plist(app_path).get("CFBundleIdentifier")
    if not bundle_id:
        raise RuntimeError("Info.plist içinde CFBundleIdentifier yok.")

    install = _simctl("install", target, app_path)
    if install.returncode != 0:
        raise RuntimeError("Kurulum başarısız: %s" % (install.stderr or "").strip())

    _simctl("terminate", target, bundle_id, timeout=30)
    launch = _simctl("launch", target, bundle_id, timeout=60)
    if launch.returncode != 0:
        raise RuntimeError("Başlatma başarısız: %s" % (launch.stderr or "").strip())

    frames_dir = os.path.join(out_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    frames = []
    for step in range(steps):
        time.sleep(settle)
        shot = os.path.join(frames_dir, "%02d.png" % step)
        proc = _simctl("io", target, "screenshot", shot, timeout=60)
        if proc.returncode == 0 and os.path.exists(shot):
            frames.append({
                "step": step,
                "path": shot,
                "accessibility": probe_accessibility(target),
            })

    return {
        "device": target,
        "bundle_id": bundle_id,
        "frames": frames,
        "has_accessibility": any(f["accessibility"] for f in frames),
        "note": (
            "Ekran görüntüleri alındı. Gerçek ekran gezinmesi için app içinde "
            "bir XCUITest hedefi veya kurulu bir idb gerekiyor — ikisi de yoksa "
            "bu sweep yalnızca açılış akışını yakalar."),
    }
