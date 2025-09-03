#!/usr/bin/env python3
"""
Debug script to understand the actual FARSI packet format.
"""

import regex
from packet_parser import Parser

def debug_farsi_packet():
    """Debug the actual FARSI packet"""
    print("Debugging actual FARSI packet...")
    
    try:
        import docx
        doc = docx.Document('../controllers/sample_packets/FARSI Packet 1.docx')
        packet_text = '\n'.join([p.text for p in doc.paragraphs])
        
        # Clean up the text for parsing
        packet_text = packet_text.replace('\n\n', '\n').strip()
        
        print("Original FARSI packet (first 500 chars):")
        print(packet_text[:500])
        print("\n" + "="*50 + "\n")
        
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
        print("Preprocessed FARSI packet (first 500 chars):")
        print(packet_text[:500])
        print("\n" + "="*50 + "\n")
        
        # Find all questions
        packet_questions = regex.findall(
            parser.REGEX_QUESTION, packet_text, flags=Parser.REGEX_FLAGS
        )
        
        print(f"Found {len(packet_questions)} questions:")
        for i, question in enumerate(packet_questions[:5]):  # Show first 5
            print(f"\nQuestion {i+1}:")
            print(f"Length: {len(question)}")
            print(f"First 200 chars: {question[:200]}")
            
            # Check if it starts with a number
            starts_with_number = bool(regex.match(r'^\d{1,2}\.', question))
            print(f"Starts with number: {starts_with_number}")
            
            # Check bonus detection
            isBonus = regex.findall(r"^\[(5|10|15)?[EMH]?\]", question, flags=Parser.REGEX_FLAGS)
            isNumberedBonus = regex.findall(r"^\d{1,2}\.\s*\[(?:5|10|15)?[EMH]?\]", question, flags=Parser.REGEX_FLAGS)
            hasBonusParts = regex.findall(r"\[(?:5|10|15)?[EMH]?\]", question, flags=Parser.REGEX_FLAGS)
            
            print(f"isBonus: {isBonus}")
            print(f"isNumberedBonus: {isNumberedBonus}")
            print(f"hasBonusParts: {hasBonusParts}")
            
            would_be_bonus = bool(isBonus or isNumberedBonus or (hasBonusParts and isNumberedBonus))
            print(f"Would be classified as bonus: {would_be_bonus}")
        
    except ImportError:
        print("python-docx not available")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_farsi_packet()

