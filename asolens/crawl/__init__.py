"""App bundle auditing — the "from the inside" half of the toolkit.

`static_audit` works today on any `.app` you can build; it is the part that
pays off immediately. `dynamic_sweep` drives the iOS Simulator and is
deliberately minimal (launch, screenshot, tap, repeat) — a real UI crawler
needs an accessibility tree, which `simctl` does not expose. See the module
docstring in `ios_sim` for what that would take.
"""

from asolens.crawl.ios_sim import dynamic_sweep, static_audit  # noqa: F401
