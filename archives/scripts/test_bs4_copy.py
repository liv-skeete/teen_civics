from bs4 import BeautifulSoup

# Test if __copy__ method works on BeautifulSoup elements
html = """
<ol class="bill_progress">
  <li class="passed">Introduced
    <div class="sol-step-info" style="display:none">Array
    (
        [actionDate] => 2025-07-10
        [displayText] => Reported by the Committee on Natural Resources. H. Rept. 119-191.
        [externalActionCode] => 5000
        [description] => Introduced
        [chamberOfAction] => House
    )
    </div>
  </li>
</ol>
"""

soup = BeautifulSoup(html, 'html.parser')
li = soup.find('li')

print("Original li text (with hidden div):")
print(repr(li.get_text(strip=True)))

# Try the copy approach
try:
    li_clone = li.__copy__()
    print("Copy method works")
except Exception as e:
    print(f"Copy method failed: {e}")

# Try alternative approach - extracting text nodes only
print("\nTrying alternative approach:")
text_parts = []
for content in li.contents:
    if hasattr(content, 'name') and content.name == 'div' and 'sol-step-info' in (content.get('class', [])):
        # Skip the hidden div
        continue
    elif hasattr(content, 'string'):
        # This is a text node
        text_parts.append(content.string or '')
    elif isinstance(content, str):
        # This is direct text
        text_parts.append(content)

clean_text = ''.join(text_parts).strip()
print(f"Cleaned text: {repr(clean_text)}")