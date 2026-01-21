"""
Test BeautifulSoup parsing of the HR4405 HTML structure
"""
from bs4 import BeautifulSoup

# Simplified HTML structure from HR4405-119
html = '''
<ol class="bill_progress">
    <li class="passed">Introduced</li>
    <li class="passed">Passed House</li>
    <li class="passed">Passed Senate</li>
    <li class="passed">To President</li>
    <li class="selected last">Became Law</li>
</ol>
'''

soup = BeautifulSoup(html, 'html.parser')

# Test Method 1: find with class_='selected'
print("Testing: soup.find('li', class_='selected')")
selected_item = soup.find('li', class_='selected')
if selected_item:
    print(f"  ✅ Found: {selected_item.text.strip()}")
else:
    print(f"  ❌ Not found")

# Test Method 2: find all and check 'selected' in classes
print("\nTesting: checking 'selected' in classes")
bill_progress_list = soup.find('ol', class_='bill_progress')
if bill_progress_list:
    for li in bill_progress_list.find_all('li'):
        classes = li.get('class', [])
        if 'selected' in classes:
            print(f"  ✅ Found selected item: {li.text.strip()}")
            print(f"     Classes: {classes}")
        elif 'passed' in classes:
            print(f"  - Passed: {li.text.strip()}")

# Test Method 3: hidden paragraph (from full HTML)
html_with_hidden = '''
<p class="hide_fromsighted">This bill has the status Became Law</p>
<ol class="bill_progress">
    <li class="passed">Introduced</li>
    <li class="passed">Passed House</li>
    <li class="passed">Passed Senate</li>
    <li class="passed">To President</li>
    <li class="selected last">Became Law</li>
</ol>
'''

soup2 = BeautifulSoup(html_with_hidden, 'html.parser')
print("\nTesting: hidden paragraph method")
status_paragraphs = soup2.find_all('p', class_='hide_fromsighted')
for para in status_paragraphs:
    if para and 'This bill has the status' in para.text:
        status = para.text.replace('This bill has the status', '').strip()
        print(f"  ✅ Found status from paragraph: '{status}'")
