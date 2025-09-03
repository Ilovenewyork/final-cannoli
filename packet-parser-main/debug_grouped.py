#!/usr/bin/env python3
"""
Debug script for the grouped format (tossup-tossup-bonus-bonus).
"""

import regex
from packet_parser import Parser

def debug_grouped_format():
    """Debug the grouped format parsing"""
    print("Debugging grouped format...")
    
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
    
    # Preprocess the packet
    packet_text = parser.preprocess_packet(packet_text)
    print("Preprocessed packet:")
    print(packet_text)
    print("\n" + "="*50 + "\n")
    
    # Find all questions
    packet_questions = regex.findall(
        parser.REGEX_QUESTION, packet_text, flags=Parser.REGEX_FLAGS
    )
    
    print(f"Found {len(packet_questions)} questions:")
    for i, question in enumerate(packet_questions):
        print(f"\nQuestion {i+1}:")
        print(f"Length: {len(question)}")
        print(f"First 100 chars: {question[:100]}")
        
        # Check bonus detection
        isBonus = regex.findall(r"^\[(5|10|15)?[EMH]?\]", question, flags=Parser.REGEX_FLAGS)
        isNumberedBonus = regex.findall(r"^\d{1,2}\.\s*\[(?:5|10|15)?[EMH]?\]", question, flags=Parser.REGEX_FLAGS)
        hasBonusParts = regex.findall(r"\[(?:5|10|15)?[EMH]?\]", question, flags=Parser.REGEX_FLAGS)
        
        print(f"isBonus: {isBonus}")
        print(f"isNumberedBonus: {isNumberedBonus}")
        print(f"hasBonusParts: {hasBonusParts}")
        
        would_be_bonus = bool(isBonus or isNumberedBonus or (hasBonusParts and isNumberedBonus))
        print(f"Would be classified as bonus: {would_be_bonus}")

if __name__ == "__main__":
    debug_grouped_format()

