"""Build a throwaway .app bundle that trips most static checks.

Used to exercise `maa crawl` without needing a real Xcode build.
"""

import os
import plistlib
import shutil
import sys

PLIST = {
    "CFBundleIdentifier": "com.example.brokenapp",
    "CFBundleName": "BrokenApp",
    "CFBundleDisplayName": "Broken App",
    "CFBundleShortVersionString": "1.0",
    "CFBundleVersion": "1",
    "MinimumOSVersion": "15.0",
    "CFBundleURLTypes": [
        {"CFBundleURLSchemes": ["brokenapp"], "CFBundleURLName": "com.example.brokenapp"}
    ],
    # deliberately bad: placeholder and too-short usage strings
    "NSCameraUsageDescription": "TODO",
    "NSPhotoLibraryUsageDescription": "Needed",
    "NSLocationWhenInUseUsageDescription":
        "Konumunuzu yakındaki mağazaları göstermek için kullanıyoruz.",
    # deliberately bad: blanket ATS exception and document sharing on
    "NSAppTransportSecurity": {"NSAllowsArbitraryLoads": True},
    "UIFileSharingEnabled": True,
    # no UILaunchScreen, no ITSAppUsesNonExemptEncryption
}


def build(dest):
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(os.path.join(dest, "en.lproj"))
    with open(os.path.join(dest, "Info.plist"), "wb") as fh:
        plistlib.dump(PLIST, fh)
    with open(os.path.join(dest, "en.lproj", "Localizable.strings"), "w") as fh:
        fh.write('"hello" = "Hello";\n')
    with open(os.path.join(dest, "BrokenApp"), "wb") as fh:
        fh.write(b"\x00" * 2048)
    return dest


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/BrokenApp.app"
    os.makedirs(os.path.dirname(target), exist_ok=True)
    print(build(target))
