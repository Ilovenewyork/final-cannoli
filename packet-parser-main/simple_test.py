#!/usr/bin/env python3
"""
Simple test to debug the bonus classification issue.
"""

from packet_parser import Parser

def test_simple():
    """Test with a simple packet"""
    print("Testing simple packet...")
    
    packet_text = """1. This is a tossup.
ANSWER: answer
<Science>

1. This is a bonus. For 10 points each:
[10] First part.
ANSWER: first
[10] Second part.
ANSWER: second
[10] Third part.
ANSWER: third
<Science>"""

    parser = Parser(
        has_question_numbers=True,
        has_category_tags=True,
        bonus_length=3,
        buzzpoints=False,
        modaq=False,
        auto_insert_powermarks=False,
        classify_unknown=True,
        space_powermarks=False,
        always_classify=False
    )
    
    result = parser.parse_packet(packet_text, "simple_test")
    print(f"Found {len(result['tossups'])} tossups and {len(result['bonuses'])} bonuses")
    
    if len(result['tossups']) == 1 and len(result['bonuses']) == 1:
        print("✓ Simple test passed!")
    else:
        print(f"❌ Simple test failed! Expected 1 tossup and 1 bonus, got {len(result['tossups'])} tossups and {len(result['bonuses'])} bonuses")

if __name__ == "__main__":
    test_simple()

