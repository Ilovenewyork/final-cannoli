#!/usr/bin/env python3
"""
Check for numbered questions in the FARSI packet.
"""

import regex

def check_farsi_numbers():
    """Check for numbered questions in the FARSI packet"""
    print("Checking for numbered questions in FARSI packet...")
    
    try:
        import docx
        doc = docx.Document('../controllers/sample_packets/FARSI Packet 1.docx')
        packet_text = '\n'.join([p.text for p in doc.paragraphs])
        
        # Look for numbered questions
        numbered_questions = regex.findall(r'^\d+\.', packet_text, flags=regex.MULTILINE)
        print(f"Found {len(numbered_questions)} numbered questions: {numbered_questions}")
        
        # Look for bonus parts
        bonus_parts = regex.findall(r'\[10[hm]?\]', packet_text)
        print(f"Found {len(bonus_parts)} bonus parts: {bonus_parts[:10]}...")  # Show first 10
        
        # Look for ANSWER patterns
        answer_patterns = regex.findall(r'ANSWER:', packet_text)
        print(f"Found {len(answer_patterns)} ANSWER patterns")
        
        # Show some context around numbered questions
        lines = packet_text.split('\n')
        for i, line in enumerate(lines):
            if regex.match(r'^\d+\.', line):
                print(f"\nLine {i+1}: {line}")
                if i > 0:
                    print(f"Previous line: {lines[i-1]}")
                if i < len(lines) - 1:
                    print(f"Next line: {lines[i+1]}")
        
    except ImportError:
        print("python-docx not available")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_farsi_numbers()

