#!/usr/bin/env python3
"""
Script to test bill tracker parsing logic with the specific HTML structure.
"""

import sys
import os
from bs4 import BeautifulSoup

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def test_parsing():
    # HTML structure from the provided example
    html_content = '''
    <ol class="bill_progress">
        <li class="">
            Introduced
            <div class="sol-step-info" style="display:none">Array
            (
                [actionDate] => 2025-07-15
                [displayText] => Introduced in House
                [description] => Introduced
                [chamberOfAction] => House
            )
            </div>
        </li>
        <li class="">
            Passed House
            <div class="sol-step-info" style="display:none">Array
            (
                [actionDate] => 2025-11-18
                [displayText] => Passed/agreed to in House: On motion to suspend the rules and pass the bill Agreed to by recorded vote (2/3 required): 427 - 1 (Roll no. 289). (text: CR H4725)
                [description] => Passed House
                [chamberOfAction] => House
            )
            </div>
        </li>
        <li class="">
            Passed Senate
            <div class="sol-step-info" style="display:none">Array
            (
                [actionDate] => 2025-11-19
                [displayText] => Passed/agreed to in Senate: Received in the Senate, read twice, considered, read the third time, and passed, under the order of 11/18/2025, without amendment by Unanimous Consent.
                [description] => Passed Senate
                [chamberOfAction] => Senate
            )
            </div>
        </li>
        <li class="">
            To President
            <div class="sol-step-info" style="display:none">Array
            (
                [actionDate] => 2025-11-19
                [displayText] => Presented to President.
                [description] => To President
                [chamberOfAction] => 
            )
            </div>
        </li>
        <li class="selected last">
            Became Law
            <div class="sol-step-info" style="display:none">Array
            (
                [actionDate] => 2025-11-19
                [displayText] => Signed by President.
                [description] => Became Law
                [chamberOfAction] => 
            )
            </div>
        </li>
    </ol>
    '''
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Parse bill status from the progress bar
    tracker = soup.find('ol', class_=['bill_progress', 'bill-progress'])
    steps = []
    
    if tracker:
        for li in tracker.find_all('li'):
            # Get only the direct text from the li element, excluding hidden div content
            text_parts = []
            for content in li.contents:
                # Skip hidden divs with class 'sol-step-info'
                if hasattr(content, 'name') and content.name == 'div' and 'sol-step-info' in (content.get('class', [])):
                    continue
                # Extract text from text nodes and direct strings
                elif hasattr(content, 'string') and content.string:
                    text_parts.append(content.string)
                elif isinstance(content, str):
                    text_parts.append(content)
                
            name = ''.join(text_parts).strip()
            classes = (li.get('class') or [])
            selected = ('selected' in classes) or ('current' in classes)
            if name:
                steps.append({"name": name, "selected": selected})
                print(f"Step: '{name}', Classes: {classes}, Selected: {selected}")
    
    print("\nParsed steps:")
    for step in steps:
        print(f"  - {step['name']}: {'selected' if step['selected'] else 'not selected'}")

if __name__ == "__main__":
    test_parsing()