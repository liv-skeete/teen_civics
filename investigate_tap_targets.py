"""
Investigate specific tap target issues found in QA
"""

from playwright.sync_api import sync_playwright

def investigate_elements():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # Test at 1024px where nav issues occur
        page.set_viewport_size({"width": 1024, "height": 768})
        page.goto('http://localhost:5000/')
        page.wait_for_timeout(500)
        
        print("=== Navigation Links at 1024px ===")
        nav_links = page.query_selector_all('.nav-link')
        for i, link in enumerate(nav_links):
            box = link.bounding_box()
            text = link.inner_text()
            computed = page.evaluate('''(el) => {
                const style = window.getComputedStyle(el);
                return {
                    padding: style.padding,
                    height: style.height,
                    lineHeight: style.lineHeight,
                    fontSize: style.fontSize
                };
            }''', link)
            print(f"\nNav Link {i}: '{text}'")
            print(f"  Bounding box height: {box['height']:.1f}px")
            print(f"  Computed height: {computed['height']}")
            print(f"  Padding: {computed['padding']}")
            print(f"  Line height: {computed['lineHeight']}")
            print(f"  Font size: {computed['fontSize']}")
        
        # Check Archive page for the 18px button issue
        page.goto('http://localhost:5000/archive')
        page.wait_for_timeout(500)
        
        print("\n\n=== Archive Page Inputs/Buttons ===")
        inputs = page.query_selector_all('input, button, .btn')
        for i, inp in enumerate(inputs):
            try:
                box = inp.bounding_box()
                if box:
                    tag = page.evaluate('(el) => el.tagName', inp)
                    classes = page.evaluate('(el) => el.className', inp)
                    type_attr = page.evaluate('(el) => el.type', inp)
                    computed = page.evaluate('''(el) => {
                        const style = window.getComputedStyle(el);
                        return {
                            height: style.height,
                            padding: style.padding,
                            fontSize: style.fontSize
                        };
                    }''', inp)
                    
                    print(f"\nElement {i}: <{tag}> class='{classes}' type='{type_attr}'")
                    print(f"  Bounding box height: {box['height']:.1f}px")
                    print(f"  Computed height: {computed['height']}")
                    print(f"  Padding: {computed['padding']}")
                    print(f"  Font size: {computed['fontSize']}")
            except:
                pass
        
        browser.close()

if __name__ == '__main__':
    investigate_elements()