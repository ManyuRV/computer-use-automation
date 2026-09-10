"""Surface abstraction: the seam between 'how we perceive/act on a surface'
and the recorded flow.

WebSurface is the one concrete implementation (Playwright + Chrome). The
interface is deliberately small - observe() returns an accessibility-tree
document, act() executes a primitive against a locator chain - so a desktop
(Win32/UIA, macOS AX) surface can slot in behind the same contract; the
artifact and replay engine never touch Playwright types directly.
"""
from __future__ import annotations
from typing import Optional
from playwright.sync_api import sync_playwright, Page, Locator as PWLocator, Error as PWError
from .schema import Locator, LocatorStrategy


class WebSurface:
    def __init__(self, headless: bool = True):
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(channel="chrome", headless=headless)
        self.context = self.browser.new_context()
        self.page: Page = self.context.new_page()
        self.last_status: Optional[int] = None
        self.page.on("response", lambda r: setattr(self, "last_status", r.status))

    # ---- perception ----
    def observe_aria(self) -> str:
        try:
            return self.page.locator("body").aria_snapshot(timeout=5000)
        except PWError:
            return "<no accessibility tree>"

    def page_text(self) -> str:
        try:
            return self.page.locator("body").inner_text(timeout=5000)
        except PWError:
            return ""

    @property
    def url(self) -> str:
        return self.page.url

    # ---- locator resolution (chain, in recorded priority order) ----
    def resolve(self, chain: list[Locator]) -> PWLocator:
        errors = []
        for loc in chain:
            for cand in self._candidates(loc):
                try:
                    if cand.count() > 0:
                        return cand.first
                except PWError as e:
                    errors.append(f"{loc.describe()}: {e}")
        raise LookupError("no locator in chain matched: " + " | ".join(errors))

    def _candidates(self, loc: Locator):
        """Yield candidate locators, most specific first. Accessible names are
        unreliable on legacy surfaces, so role+name falls back to role-only."""
        yield self._candidate(loc)
        if loc.strategy == "role" and loc.name:
            yield self.page.get_by_role(loc.role)

    def _candidate(self, loc: Locator) -> PWLocator:
        if loc.strategy == "role":
            return self.page.get_by_role(loc.role, name=loc.name, exact=True)
        if loc.strategy == "text":
            return self.page.get_by_text(loc.value, exact=False)
        if loc.strategy == "css":
            return self.page.locator(loc.value)
        return self.page.locator(f"xpath={loc.value}")

    def build_locator_chain(self, role: Optional[str], name: Optional[str],
                            text: Optional[str]) -> list[Locator]:
        """Record a robustness-ordered chain for the element the agent chose."""
        chain: list[Locator] = []
        if role:
            chain.append(Locator(strategy="role", role=role, name=name, value=""))
        if text:
            chain.append(Locator(strategy="text", value=text))
        # Compute css + xpath fallbacks off the primary candidate.
        primary = chain[0] if chain else None
        if primary is not None:
            try:
                el = self._candidate(primary).first.element_handle(timeout=3000)
                if el:
                    css, xp = el.evaluate(
                        """(e) => {
                          const css = (() => { let p=[]; let n=e;
                            while(n && n!==document.body){ let s=n.tagName.toLowerCase();
                              if(n.parentElement){ const i=[...n.parentElement.children].indexOf(n)+1; s+=`:nth-child(${i})`; }
                              p.unshift(s); n=n.parentElement; } return 'body>'+p.join('>'); })();
                          const xp = (() => { let p=[]; let n=e;
                            while(n && n.nodeType===1){ let i=1,s=n.previousSibling;
                              while(s){ if(s.nodeName===n.nodeName) i++; s=s.previousSibling; }
                              p.unshift(n.nodeName.toLowerCase()+'['+i+']'); n=n.parentNode; }
                            return '/'+p.join('/'); })();
                          return [css, xp]; }""")
                    chain.append(Locator(strategy="css", value=css))
                    chain.append(Locator(strategy="xpath", value=xp))
            except PWError:
                pass
        return chain

    # ---- actions ----
    def act(self, action: str, chain: list[Locator], value: Optional[str] = None, extract_mode: Optional[str] = None) -> str:
        """Execute one primitive. Returns extracted text for extract, else ''."""
        if action == "wait":
            self.page.wait_for_timeout(2000)
            return ""
        target = self.resolve(chain)
        if action == "click":
            target.click(timeout=8000)
        elif action == "fill":
            target.fill(value or "", timeout=8000)
        elif action == "select":
            target.select_option(value=value, timeout=8000)
        elif action == "extract":
            if extract_mode == "adjacent_cell":
                # legacy label/value table: read the cell after the label cell
                return target.locator("xpath=following-sibling::*[1]").inner_text(timeout=5000)
            return target.inner_text(timeout=5000)
        elif action == "assert_text":
            pass  # handled by checkpoint logic
        else:
            raise ValueError(f"unknown surface action {action}")
        return ""

    def navigate(self, url: str):
        self.page.goto(url, wait_until="domcontentloaded", timeout=30000)

    def close(self):
        self.context.close(); self.browser.close(); self._pw.stop()
