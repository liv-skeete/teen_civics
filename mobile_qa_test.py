"""
Mobile QA Validation Script
Tests all pages across specified viewports for mobile responsiveness
"""

from playwright.sync_api import sync_playwright
import json
import sys
from typing import Dict, List, Tuple

# Test configuration
VIEWPORTS = [320, 360, 390, 414, 768, 1024]
LANDSCAPE_VIEWPORTS = [(568, 320), (736, 414)]  # (width, height) for landscape tests

PAGES = {
    '/': 'Home',
    '/archive': 'Archive',
    '/about': 'About',
    '/resources': 'Resources',
    '/contact': 'Contact',
    '/this-route-does-not-exist': '404',
    '/bill/hjres105-119-providing-congressional-disapproval': 'Bill',
}

BASE_URL = 'http://localhost:5000'

class MobileQAValidator:
    def __init__(self):
        self.results = {}
        self.cross_page_issues = []
        
    def check_horizontal_scroll(self, page) -> Tuple[bool, str]:
        """Check if page has horizontal scroll"""
        scroll_width = page.evaluate('document.scrollingElement.scrollWidth')
        window_width = page.evaluate('window.innerWidth')
        
        has_overflow = scroll_width > window_width + 1  # 1px tolerance
        
        if has_overflow:
            return False, f"Horizontal scroll detected: scrollWidth={scroll_width}px, windowWidth={window_width}px"
        return True, "No horizontal scroll"
    
    def check_nav_usability(self, page, viewport_width: int) -> Tuple[bool, str]:
        """Check navigation usability"""
        issues = []
        
        if viewport_width <= 768:
            # Check for hamburger menu
            toggle = page.query_selector('.nav-toggle')
            if toggle:
                # Check if toggle is visible
                is_visible = toggle.is_visible()
                if not is_visible:
                    issues.append("Nav toggle not visible")
                else:
                    # Try to click toggle
                    try:
                        toggle.click()
                        page.wait_for_timeout(300)  # Wait for animation
                        
                        # Check if nav menu appeared
                        nav_links = page.query_selector('.nav-links')
                        if nav_links:
                            is_expanded = nav_links.is_visible()
                            if not is_expanded:
                                issues.append("Nav menu did not expand on toggle")
                        
                        # Click again to close
                        toggle.click()
                        page.wait_for_timeout(300)
                    except Exception as e:
                        issues.append(f"Toggle interaction failed: {str(e)}")
        
        # Check tap target sizes
        nav_links = page.query_selector_all('.nav-link, .btn, .page-link')
        small_targets = []
        
        for i, link in enumerate(nav_links[:5]):  # Sample first 5
            try:
                box = link.bounding_box()
                if box and box['height'] < 44:
                    small_targets.append(f"Element {i}: {box['height']:.1f}px")
            except:
                pass
        
        if small_targets:
            issues.append(f"Small tap targets (<44px): {', '.join(small_targets)}")
        
        if issues:
            return False, "; ".join(issues)
        return True, "Navigation usable"
    
    def check_readability(self, page) -> Tuple[bool, str]:
        """Check content readability"""
        issues = []
        
        # Check body font size
        body_font = page.evaluate('''
            () => {
                const body = document.body;
                return window.getComputedStyle(body).fontSize;
            }
        ''')
        
        font_size_px = float(body_font.replace('px', ''))
        if font_size_px < 16:
            issues.append(f"Body font too small: {font_size_px}px")
        
        # Check for oversized headlines
        h1_elements = page.query_selector_all('h1')
        for h1 in h1_elements[:3]:  # Check first 3
            try:
                font_size = page.evaluate('(el) => window.getComputedStyle(el).fontSize', h1)
                size_px = float(font_size.replace('px', ''))
                if size_px > 48:
                    issues.append(f"H1 oversized: {size_px}px")
                    break
            except:
                pass
        
        if issues:
            return False, "; ".join(issues)
        return True, "Content readable"
    
    def check_images_fit(self, page) -> Tuple[bool, str]:
        """Check images fit within containers"""
        issues = []
        
        images = page.query_selector_all('img')
        window_width = page.evaluate('window.innerWidth')
        
        for i, img in enumerate(images[:10]):  # Check first 10 images
            try:
                box = img.bounding_box()
                if box and box['width'] > window_width:
                    issues.append(f"Image {i} overflows: {box['width']:.0f}px > {window_width}px")
            except:
                pass
        
        if issues:
            return False, "; ".join(issues)
        return True, "Images fit properly"
    
    def check_text_containment(self, page) -> Tuple[bool, str]:
        """Check long text/URLs don't cause overflow"""
        # This is partially covered by horizontal scroll check
        # Additional check for specific elements
        selectors = ['.bill-title', '.resource-link', '.meta-value', '.summary-text']
        issues = []
        
        window_width = page.evaluate('window.innerWidth')
        
        for selector in selectors:
            elements = page.query_selector_all(selector)
            for elem in elements[:3]:  # Check first 3 of each type
                try:
                    box = elem.bounding_box()
                    if box and box['width'] > window_width:
                        issues.append(f"{selector} overflows")
                        break
                except:
                    pass
        
        if issues:
            return False, "; ".join(issues)
        return True, "Text contained properly"
    
    def check_forms(self, page) -> Tuple[bool, str]:
        """Check form usability"""
        issues = []
        
        # Check search inputs
        search_inputs = page.query_selector_all('input[type="search"]')
        if search_inputs:
            for inp in search_inputs:
                try:
                    enterkeyhint = inp.get_attribute('enterkeyhint')
                    if enterkeyhint != 'search':
                        issues.append("Search input missing enterkeyhint='search'")
                        break
                except:
                    pass
        
        # Check input/button sizes
        inputs = page.query_selector_all('input, button, .btn')
        for i, inp in enumerate(inputs[:5]):
            try:
                box = inp.bounding_box()
                if box and box['height'] < 44:
                    issues.append(f"Input/button {i} too small: {box['height']:.1f}px")
                    break
            except:
                pass
        
        if issues:
            return False, "; ".join(issues)
        return True, "Forms usable"
    
    def check_focus_visibility(self, page) -> Tuple[bool, str]:
        """Check focus styles are visible"""
        # Tab through a few focusable elements
        focusable = page.query_selector_all('a, button, input')
        
        if focusable:
            try:
                # Focus first element
                focusable[0].focus()
                page.wait_for_timeout(100)
                
                # Check if outline is visible
                outline = page.evaluate('''
                    () => {
                        const el = document.activeElement;
                        const style = window.getComputedStyle(el);
                        return {
                            outline: style.outline,
                            outlineWidth: style.outlineWidth,
                            boxShadow: style.boxShadow
                        };
                    }
                ''')
                
                has_focus_style = (
                    outline['outlineWidth'] != '0px' or 
                    outline['boxShadow'] != 'none'
                )
                
                if not has_focus_style:
                    return False, "Focus styles not visible"
            except:
                pass
        
        return True, "Focus visible"
    
    def test_page(self, page, url: str, page_name: str, viewport_width: int, viewport_height: int = None) -> Dict:
        """Test a single page at a viewport"""
        if viewport_height is None:
            viewport_height = 667  # Default mobile height
        
        page.set_viewport_size({"width": viewport_width, "height": viewport_height})
        
        try:
            page.goto(f"{BASE_URL}{url}", wait_until='networkidle', timeout=10000)
            page.wait_for_timeout(500)  # Let animations settle
        except Exception as e:
            return {
                'pass': False,
                'notes': f"Failed to load: {str(e)}"
            }
        
        # Run all checks
        checks = {
            'horizontal_scroll': self.check_horizontal_scroll(page),
            'nav_usability': self.check_nav_usability(page, viewport_width),
            'readability': self.check_readability(page),
            'images_fit': self.check_images_fit(page),
            'text_containment': self.check_text_containment(page),
            'forms': self.check_forms(page),
            'focus_visibility': self.check_focus_visibility(page),
        }
        
        # Determine overall pass/fail
        all_passed = all(result[0] for result in checks.values())
        
        # Collect notes
        notes = []
        for check_name, (passed, note) in checks.items():
            if not passed:
                notes.append(f"{check_name}: {note}")
        
        return {
            'pass': all_passed,
            'notes': '; '.join(notes) if notes else 'All checks passed',
            'checks': {k: {'pass': v[0], 'note': v[1]} for k, v in checks.items()}
        }
    
    def run_tests(self):
        """Run all tests"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            
            print("Starting Mobile QA Validation...")
            print(f"Testing against: {BASE_URL}\n")
            
            # Test each page at each viewport
            for url, page_name in PAGES.items():
                print(f"\nTesting {page_name} ({url})...")
                self.results[page_name] = {}
                
                for viewport in VIEWPORTS:
                    print(f"  Viewport {viewport}px...", end=' ')
                    result = self.test_page(page, url, page_name, viewport)
                    self.results[page_name][f'{viewport}px'] = result
                    print("✓" if result['pass'] else "✗")
                
                # Landscape spot-check for Home and Bill pages
                if page_name in ['Home', 'Bill']:
                    for width, height in LANDSCAPE_VIEWPORTS:
                        print(f"  Landscape {width}x{height}...", end=' ')
                        result = self.test_page(page, url, page_name, width, height)
                        self.results[page_name][f'Landscape {width}x{height}'] = result
                        print("✓" if result['pass'] else "✗")
            
            browser.close()
        
        return self.generate_report()
    
    def generate_report(self) -> str:
        """Generate formatted QA report"""
        report = ["=" * 80]
        report.append("MOBILE QA VALIDATION REPORT")
        report.append("=" * 80)
        report.append("")
        
        # Per-page results
        for page_name, viewports in self.results.items():
            report.append(f"\n{page_name} Page")
            report.append("-" * 40)
            
            for viewport, result in viewports.items():
                status = "✓ PASS" if result['pass'] else "✗ FAIL"
                report.append(f"  {viewport}: {status}")
                if not result['pass']:
                    report.append(f"    Notes: {result['notes']}")
        
        # Cross-page observations
        report.append("\n" + "=" * 80)
        report.append("CROSS-PAGE OBSERVATIONS")
        report.append("=" * 80)
        
        # Analyze for recurring issues
        issue_counts = {}
        for page_name, viewports in self.results.items():
            for viewport, result in viewports.items():
                if not result['pass']:
                    for check_name, check_result in result.get('checks', {}).items():
                        if not check_result['pass']:
                            key = f"{check_name}: {check_result['note']}"
                            issue_counts[key] = issue_counts.get(key, 0) + 1
        
        if issue_counts:
            recurring = [(issue, count) for issue, count in issue_counts.items() if count > 2]
            if recurring:
                report.append("\nRecurring Issues (3+ occurrences):")
                for issue, count in sorted(recurring, key=lambda x: -x[1]):
                    report.append(f"  • {issue} ({count} occurrences)")
            else:
                report.append("\nNo recurring issues detected across multiple pages/viewports.")
        else:
            report.append("\nNo issues detected.")
        
        # Acceptance summary
        report.append("\n" + "=" * 80)
        report.append("ACCEPTANCE SUMMARY")
        report.append("=" * 80)
        
        # Calculate pass rates for each criterion
        criteria = {
            'horizontal_scroll': 'Horizontal scroll',
            'nav_usability': 'Navigation usability',
            'readability': 'Readability',
            'images_fit': 'Images/media fit',
            'text_containment': 'Text containment',
            'forms': 'Forms usability',
            'focus_visibility': 'Focus visibility'
        }
        
        for criterion_key, criterion_name in criteria.items():
            total = 0
            passed = 0
            
            for page_name, viewports in self.results.items():
                for viewport, result in viewports.items():
                    if 'checks' in result and criterion_key in result['checks']:
                        total += 1
                        if result['checks'][criterion_key]['pass']:
                            passed += 1
            
            if total > 0:
                pass_rate = (passed / total) * 100
                status = "✓ PASS" if pass_rate >= 95 else "✗ FAIL"
                report.append(f"  {criterion_name}: {status} ({passed}/{total} = {pass_rate:.1f}%)")
        
        # Overall risk assessment
        report.append("\n" + "=" * 80)
        report.append("RISK ASSESSMENT")
        report.append("=" * 80)
        
        total_tests = sum(len(viewports) for viewports in self.results.values())
        failed_tests = sum(
            1 for viewports in self.results.values()
            for result in viewports.values()
            if not result['pass']
        )
        
        pass_rate = ((total_tests - failed_tests) / total_tests * 100) if total_tests > 0 else 0
        
        if pass_rate >= 95:
            risk = "LOW"
            recommendation = "Site is mobile-ready for production."
        elif pass_rate >= 85:
            risk = "MEDIUM"
            recommendation = "Minor issues present. Review and fix before production."
        elif pass_rate >= 70:
            risk = "HIGH"
            recommendation = "Significant issues detected. Fixes required before production."
        else:
            risk = "CRITICAL"
            recommendation = "Major mobile usability issues. Immediate fixes required."
        
        report.append(f"\nOverall Pass Rate: {pass_rate:.1f}% ({total_tests - failed_tests}/{total_tests})")
        report.append(f"Risk Level: {risk}")
        report.append(f"Recommendation: {recommendation}")
        
        report.append("\n" + "=" * 80)
        
        return "\n".join(report)

if __name__ == '__main__':
    validator = MobileQAValidator()
    
    try:
        report = validator.run_tests()
        print("\n" + report)
        
        # Save to file
        with open('mobile_qa_report.txt', 'w') as f:
            f.write(report)
        
        print("\nReport saved to: mobile_qa_report.txt")
        
    except Exception as e:
        print(f"\nError running tests: {str(e)}")
        sys.exit(1)