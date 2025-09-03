#!/usr/bin/env python3
"""
Debug script to understand the question parsing issue.
"""

import regex
from packet_parser import Parser

def debug_question_parsing():
    """Debug the question parsing logic"""
    print("Debugging question parsing...")
    
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
        starts_with_number = bool(regex.match(r'^\d{1,2}\.', question))
        contains_10 = bool(regex.search(r'\[10\]', question))
        contains_bonus_parts = bool(regex.findall(r'\[(?:5|10|15)?[EMH]?\]', question))
        print(f"Starts with number: {starts_with_number}")
        print(f"Contains [10]: {contains_10}")
        print(f"Contains bonus parts: {contains_bonus_parts}")
        
        # Check bonus detection
        isBonus = regex.findall(r"^\[(5|10|15)?[EMH]?\]", question, flags=Parser.REGEX_FLAGS)
        isNumberedBonus = regex.findall(r"^\d{1,2}\.\s*\[(?:5|10|15)?[EMH]?\]", question, flags=Parser.REGEX_FLAGS)
        hasBonusParts = regex.findall(r"\[(?:5|10|15)?[EMH]?\]", question, flags=Parser.REGEX_FLAGS)
        
        # Check the actual logic being used
        would_be_bonus_old = bool(isBonus or isNumberedBonus or (hasBonusParts and regex.match(r'^\d{1,2}\.', question)))
        would_be_bonus_new = bool(isBonus or isNumberedBonus or (hasBonusParts and isNumberedBonus))
        
        print(f"isBonus: {isBonus}")
        print(f"isNumberedBonus: {isNumberedBonus}")
        print(f"hasBonusParts: {hasBonusParts}")
        would_be_bonus_old = bool(isBonus or isNumberedBonus or (hasBonusParts and regex.match(r'^\d{1,2}\.', question)))
        would_be_bonus_new = bool(isBonus or isNumberedBonus or (hasBonusParts and isNumberedBonus))
        print(f"Would be classified as bonus (old logic): {would_be_bonus_old}")
        print(f"Would be classified as bonus (new logic): {would_be_bonus_new}")

if __name__ == "__main__":
    debug_question_parsing()
