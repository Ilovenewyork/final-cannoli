#!/usr/bin/env python3
"""
Test script for the enhanced packet parser to verify it handles both formats correctly.
"""

import sys
import os

from packet_parser import Parser

def test_alternating_format():
    """Test the alternating format (tossup-bonus-tossup-bonus)"""
    print("Testing alternating format...")
    
    # Sample alternating format packet
    packet_text = """1. This is a tossup question about science.
ANSWER: science answer
<Science>

1. This is a bonus leadin. For 10 points each:
[10] First bonus part.
ANSWER: first answer
[10] Second bonus part.
ANSWER: second answer
[10] Third bonus part.
ANSWER: third answer
<Science>

2. This is another tossup question.
ANSWER: another answer
<Literature>

2. This is another bonus leadin. For 10 points each:
[10] First part.
ANSWER: first
[10] Second part.
ANSWER: second
[10] Third part.
ANSWER: third
<Literature>"""

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
    
    result = parser.parse_packet(packet_text, "test_alternating")
    print(f"Found {len(result['tossups'])} tossups and {len(result['bonuses'])} bonuses")
    
    assert len(result['tossups']) == 2, f"Expected 2 tossups, got {len(result['tossups'])}"
    assert len(result['bonuses']) == 2, f"Expected 2 bonuses, got {len(result['bonuses'])}"
    print("✓ Alternating format test passed!")

def test_grouped_format():
    """Test the grouped format (tossup-tossup-bonus-bonus)"""
    print("Testing grouped format...")
    
    # Sample grouped format packet (like FARSI)
    packet_text = """1. This is the first tossup question about science.
ANSWER: science answer
<Science>

2. This is the second tossup question about literature.
ANSWER: literature answer
<Literature>

This is the first bonus leadin. For 10 points each:
[10] First bonus part.
ANSWER: first answer
[10] Second bonus part.
ANSWER: second answer
[10] Third bonus part.
ANSWER: third answer
<Science>

This is the second bonus leadin. For 10 points each:
[10] First part.
ANSWER: first
[10] Second part.
ANSWER: second
[10] Third part.
ANSWER: third
<Literature>"""

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
    
    result = parser.parse_packet(packet_text, "test_grouped")
    print(f"Found {len(result['tossups'])} tossups and {len(result['bonuses'])} bonuses")
    
    assert len(result['tossups']) == 2, f"Expected 2 tossups, got {len(result['tossups'])}"
    assert len(result['bonuses']) == 2, f"Expected 2 bonuses, got {len(result['bonuses'])}"
    print("✓ Grouped format test passed!")

def test_grouped_format_no_tags():
    """Test the grouped format without category tags"""
    print("Testing grouped format without category tags...")
    
    # Sample grouped format packet without category tags
    packet_text = """1. This is the first tossup question about science.
ANSWER: science answer

2. This is the second tossup question about literature.
ANSWER: literature answer

This is the first bonus leadin. For 10 points each:
[10] First bonus part.
ANSWER: first answer
[10] Second bonus part.
ANSWER: second answer
[10] Third bonus part.
ANSWER: third answer

This is the second bonus leadin. For 10 points each:
[10] First part.
ANSWER: first
[10] Second part.
ANSWER: second
[10] Third part.
ANSWER: third"""

    parser = Parser(
        has_question_numbers=True,
        has_category_tags=False,
        bonus_length=3,
        buzzpoints=False,
        modaq=False,
        auto_insert_powermarks=False,
        classify_unknown=True,
        space_powermarks=False,
        always_classify=False
    )
    
    result = parser.parse_packet(packet_text, "test_grouped_no_tags")
    print(f"Found {len(result['tossups'])} tossups and {len(result['bonuses'])} bonuses")
    
    assert len(result['tossups']) == 2, f"Expected 2 tossups, got {len(result['tossups'])}"
    assert len(result['bonuses']) == 2, f"Expected 2 bonuses, got {len(result['bonuses'])}"
    print("✓ Grouped format without tags test passed!")

if __name__ == "__main__":
    print("Testing enhanced packet parser...")
    print("=" * 50)
    
    try:
        test_alternating_format()
        test_grouped_format()
        test_grouped_format_no_tags()
        print("\n" + "=" * 50)
        print("🎉 All tests passed! The enhanced parser works correctly.")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
