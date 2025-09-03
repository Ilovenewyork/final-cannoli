from typing import Literal

import click
import json
import os
import regex

from bcolors import bcolors
from classifier.classify import (
    classify,
    classify_question,
    ALTERNATE_SUBCATEGORIES,
    SUBSUBCATEGORIES,
)

CONSTANT_SUBCATEGORY = ""
# CONSTANT_ALTERNATE_SUBCATEGORY is optional,
# and can be used even if CONSTANT_SUBCATEGORY is empty.
CONSTANT_ALTERNATE_SUBCATEGORY = ""

with open("modules/answer-typos.json") as f:
    ANSWER_TYPOS = json.load(f)

with open("modules/ten-typos.json") as f:
    TEN_TYPOS = json.load(f)

with open("modules/standardize-subcats.json") as f:
    STANDARDIZE_SUBCATS = json.load(f)

with open("modules/standardize-alternate-subcats.json") as f:
    STANDARDIZE_ALTERNATE_SUBCATS = json.load(f)

with open("modules/subcat-to-cat.json") as f:
    SUBCAT_TO_CAT = json.load(f)


def format_text(text: str, modaq=False) -> str:
    text = (
        text.replace("{b}", "<b>")
        .replace("{/b}", "</b>")
        .replace("{u}", "<u>")
        .replace("{/u}", "</u>")
    )

    if modaq:
        text = text.replace("{i}", "<em>").replace("{/i}", "</em>")
    else:
        text = text.replace("{i}", "<i>").replace("{/i}", "</i>")

    return text.strip()


def get_subcategory(text: str) -> str:
    if text[0] == "<" and text[-1] == ">":
        text = text[1:-1]

    text = text.lower()
    text = text.replace("–", " ").replace("—", " ").replace("-", " ")
    text = text.replace("(", "").replace(")", "")
    text_split = regex.split(r"[\/,;:. ]", text)

    for subcat in STANDARDIZE_SUBCATS:
        works = True
        for word in subcat.lower().split(" "):
            if word not in text_split:
                works = False
                break

        if works:
            return STANDARDIZE_SUBCATS[subcat]

    return ""


def get_alternate_subcategory(text: str) -> str:
    if text[0] == "<" and text[-1] == ">":
        text = text[1:-1]

    text = text.lower()
    text = text.replace("–", " ")
    text = text.replace("-", " ")
    text_split = regex.split(r"[\/,; ]", text)

    for subcat in STANDARDIZE_ALTERNATE_SUBCATS:
        works = True
        for word in subcat.lower().split(" "):
            if word not in text_split:
                works = False
                break

        if works:
            return STANDARDIZE_ALTERNATE_SUBCATS[subcat]

    return ""


def remove_formatting(text: str, include_italics=False):
    text = (
        text.replace("{b}", "")
        .replace("{/b}", "")
        .replace("{u}", "")
        .replace("{/u}", "")
    )

    if not include_italics:
        text = text.replace("{i}", "").replace("{/i}", "")

    return text.strip()


def remove_punctuation(s: str, punctuation=""".,!-;:'"\/?@#$%^&*_~()[]{}“”‘’"""):
    return "".join(ch for ch in s if ch not in punctuation)


class Logger:
    @staticmethod
    def error(message: str):
        print(f"{bcolors.FAIL}ERROR:{bcolors.ENDC} {message}")

    @staticmethod
    def warning(message: str):
        print(f"{bcolors.WARNING}WARNING:{bcolors.ENDC} {message}")


class Parser:
    REGEX_FLAGS = regex.IGNORECASE | regex.MULTILINE

    def __init__(
        self,
        has_question_numbers: bool,
        has_category_tags: bool,
        bonus_length: int,
        buzzpoints: bool,
        modaq: bool,
        auto_insert_powermarks: bool,
        classify_unknown: bool,
        space_powermarks: bool,
        always_classify: bool = False,
        constant_subcategory: str = "",
        constant_alternate_subcategory: str = "",
    ) -> None:
        self.has_question_numbers = has_question_numbers
        self.has_category_tags = has_category_tags

        self.bonus_length = bonus_length
        self.buzzpoints = buzzpoints
        self.modaq = modaq
        self.auto_insert_powermarks = auto_insert_powermarks
        self.classify_unknown = classify_unknown
        self.space_powermarks = space_powermarks
        self.always_classify = always_classify

        self.tossup_index: int = 0
        """
        1-indexed
        """
        self.bonus_index: int = 0
        """
        1-indexed
        """

        self.constant_subcategory = constant_subcategory
        self.constant_category = (
            SUBCAT_TO_CAT[constant_subcategory] if constant_subcategory else ""
        )
        self.constant_alternate_subcategory = constant_alternate_subcategory

        if not self.has_category_tags and not self.constant_subcategory == "":
            Logger.warning(
                f"Using fixed category {self.constant_category} and subcategory {self.constant_subcategory}"
            )

        if self.constant_alternate_subcategory:
            Logger.warning(
                f"Using fixed alternate subcategory {self.constant_alternate_subcategory}"
            )

        self.__init_regex__()

    def __init_regex__(self):
        # More flexible regex patterns to handle FARSI and other formats
        if self.has_question_numbers and self.has_category_tags:
            self.REGEX_QUESTION = r'(?s)(?:\d{1,2}\s*[.)]\s*|\*\s*)?(?:.|\n)*?(?:ANSWER|Answer|Ответ|الجواب)\s*[:.]?(?:.|\n)*?(?:<[^>]*>|$)'
        elif self.has_question_numbers:
            self.REGEX_QUESTION = r'(?s)(?:\d{1,2}\s*[.)]\s*|\*\s*)?(?:.|\n)*?(?:ANSWER|Answer|Ответ|الجواب)\s*[:.]?(?:.|\n)*?(?=\n\s*(?:\d{1,2}\s*[.)]|\[|$))'
        else:
            self.REGEX_QUESTION = r'(?s)(?:(?!\n\s*$).)*?(?:ANSWER|Answer|Ответ|الجواب)\s*[:.]?(?:.|\n)*?(?=\n\s*(?:\d{1,2}\s*[.)]|\[|$))'
            
        # More flexible category tag detection
        self.REGEX_CATEGORY_TAG = r'<[^>]*>'
        
        # More flexible tossup patterns
        self.REGEX_TOSSUP_TEXT = r'(?s)(?<=\d{1,2}\s*[.)]\s*|\*\s*)(?:.|\n)*?(?=ANSWER|Answer|Ответ|الجواب|$)'
        self.REGEX_TOSSUP_ANSWER = r'(?s)(?<=ANSWER|Answer|Ответ|الجواب)[:.\s]*(?:.|\n)*?(?=<[^>]*>|$)'
        
        # Bonus patterns
        self.REGEX_BONUS_LEADIN = r'(?<=^ *\d{1,2}\.)(?:.|\n)*?(?=\[(?:10)?[EMH]?\])'
        self.REGEX_BONUS_PARTS = r'(?<=\[(?:10)?[EMH]?\])(?:.|\n)*?(?=^ ?ANSWER|ANSWER:)'
        self.REGEX_BONUS_ANSWERS = r'(?<=ANSWER:|^ ?ANSWER)(?:.|\n)*?(?=\[(?:10)?[EMH]?\]|<[^>]*)'
        self.REGEX_BONUS_TAGS = r'(?<=\[)\d{0,2}?[EMH]?(?=\])'

    def _extract_qa_pair(self, text: str) -> tuple[str, str]:
        """Extract question and answer from a text block."""
        if not text or not text.strip():
            return "", ""
            
        # Look for answer indicators - more specific patterns first
        answer_patterns = [
            # Standard ANSWER: pattern (case insensitive, with optional space after colon)
            r'(?i)((?:.|\n)*?)(?:\n\s*|^)ANSWER\s*[:.]\s*((?:.|\n)*)',
            # Farsi answer patterns
            r'(?i)((?:.|\n)*?)(?:\n\s*|^)(?:جواب|پاسخ)\s*[:.]\s*((?:.|\n)*)',
            # Short forms
            r'(?i)((?:.|\n)*?)(?:\n\s*|^)ANS\.?\s*[:.]?\s*((?:.|\n)*)',
            r'(?i)((?:.|\n)*?)(?:\n\s*|^)A\.?\s*[:.]?\s*((?:.|\n)*)',
            # Look for answer on next line after question mark
            r'((?:.|\n)*?\?)(?:\s*\n+\s*)((?:ANSWER|Ans|A|جواب|پاسخ)[:.]?\s*(?:.|\n)*)',
            # Look for answer in parentheses after question mark
            r'((?:.|\n)*?\?)\s*\(((?:.|\n)*?)\)',
            # Look for answer after a line break and tab/space indentation
            r'((?:.|\n)*?\?)(?:\s*\n+\s+)((?:.|\n)*)'
        ]
        
        for pattern in answer_patterns:
            match = regex.search(pattern, text, flags=regex.DOTALL)
            if match:
                question = match.group(1).strip()
                answer = match.group(2).strip()
                
                # Clean up answer if it still contains answer indicators
                answer = regex.sub(r'^(?:ANSWER|Ans|A|جواب|پاسخ)[:.]?\s*', '', answer, flags=regex.IGNORECASE).strip()
                
                # If we found an answer but no question, try to find a question mark
                if not question and answer:
                    last_q = text.rfind('?')
                    if last_q > 0:
                        question = text[:last_q + 1].strip()
                        answer = text[last_q + 1:].strip()
                
                if question or answer:  # Only return if we found something useful
                    return question, answer
        
        # If no answer pattern matches, try to find a question mark
        last_q = text.rfind('?')
        if last_q > 0:  # Changed from checking if it's in the second half
            return text[:last_q + 1].strip(), text[last_q + 1:].strip()
            
        # If all else fails, try to split on line breaks
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if len(lines) >= 2:
            return '\n'.join(lines[:-1]), lines[-1]
            
        # If we still have nothing, return the entire text as question
        return text.strip(), ""

    def parse_tossup(self, text: str) -> dict:
        print(f"\n=== Parsing Tossup ===")
        print(f"Input text: {text[:200]}...")
        
        try:
            # Initialize default values
            category = subcategory = alternate_subcategory = ""
            metadata = {}
            
            # Parse category info if tags exist
            if self.has_category_tags:
                try:
                    category, subcategory, alternate_subcategory, metadata = self.parse_category(text, "tossup")
                    # Remove any remaining category tags
                    text = regex.sub(r'<[^>]*>', '', text).strip()
                except Exception as e:
                    print(f"Warning: Error parsing category - {str(e)}")

            print(f"After category processing: {text[:200]}...")
            
            # Clean up the text first
            text = self._clean_question_text(text)
            
            # Extract question and answer
            question, answer = self._extract_qa_pair(text)
            
            # If question is empty but answer exists, they might be swapped
            if not question and answer:
                print("Question appears to be empty, checking if answer contains question...")
                # Try to find the last sentence that looks like a question
                sentences = regex.findall(r'([^.!?]+[.!?])(?:\s|$)', answer)
                if len(sentences) > 1:
                    question = sentences[-2].strip()
                    answer = answer[answer.rfind(question) + len(question):].strip()
            
            # If still no question, use the first part of the text
            if not question and not answer:
                print("No question or answer found, using entire text as question")
                question = text.strip()
            
            # Clean up the results
            question = self._clean_question_content(question)
            answer = self._clean_answer_content(answer)
            
            # If we still don't have an answer, try to extract it from the question
            if not answer and question:
                print("No answer found, trying to extract from question...")
                answer_match = regex.search(r'\b(?:answer|ans|جواب|پاسخ)[:.]?\s*([^.!?]+[.!?])', question, flags=regex.IGNORECASE)
                if answer_match:
                    answer = answer_match.group(1).strip()
                    question = question[:answer_match.start()].strip()
            
            print(f"Parsed question: {question[:100]}...")
            print(f"Parsed answer: {answer[:100]}...")
            
            return {
                "question": question,
                "answer": answer,
                "category": category,
                "subcategory": subcategory,
                "alternate_subcategory": alternate_subcategory or None,
                "metadata": metadata,
            }
            
        except Exception as e:
            print(f"Error in parse_tossup: {str(e)}")
            import traceback
            traceback.print_exc()
            return {}

    def _split_bonus_parts(self, text: str) -> list[dict]:
        """Split bonus text into parts with questions and answers."""
        parts = []
        
        # First try splitting by part markers [10], [15], etc.
        part_matches = list(regex.finditer(r'(\[\s*\d+[ehm]?\s*\])', text, flags=regex.IGNORECASE))
        
        if part_matches:
            for i, match in enumerate(part_matches):
                part_start = match.end()
                part_end = part_matches[i+1].start() if i+1 < len(part_matches) else len(text)
                part_text = text[part_start:part_end].strip()
                
                # Extract question and answer
                question, answer = self._extract_qa_pair(part_text)
                
                # If we didn't find an answer, try to extract it more aggressively
                if not answer.strip():
                    # Look for answer at the end of the part
                    answer_match = regex.search(r'(?i)(?:ANSWER|ANS|A|جواب|پاسخ)\s*[:.]?\s*([^\n]+)$', part_text)
                    if answer_match:
                        answer = answer_match.group(1).strip()
                        question = part_text[:answer_match.start()].strip()
                
                parts.append({
                    'question': question,
                    'answer': answer,
                    'value': 10  # Default value
                })
        
        # If no parts found with markers, try to split by common patterns
        if not parts:
            # Look for numbered parts (1), (2), (3) or a), b), c) or 1. 2. 3.
            part_patterns = [
                r'(?i)(\d+[.)]\s*)(.*?)(?=\s*\d+[.)]|\s*$)',  # 1) or 1.
                r'(?i)([a-z][.)]\s*)(.*?)(?=\s*[a-z][.)]|\s*$)',  # a) or a.
                r'(?i)(\(\d+\)\s*)(.*?)(?=\s*\(\d+\)|\s*$)'  # (1) or (2)
            ]
            
            for pattern in part_patterns:
                part_matches = list(regex.finditer(pattern, text, flags=regex.DOTALL))
                if len(part_matches) >= 2:  # Need at least 2 parts to be useful
                    for match in part_matches:
                        part_text = match.group(2).strip()
                        question, answer = self._extract_qa_pair(part_text)
                        parts.append({
                            'question': question,
                            'answer': answer,
                            'value': 10
                        })
                    break
        
        # If still no parts, try to split by double newlines
        if not parts:
            paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
            if len(paragraphs) >= 2:  # Need at least 2 paragraphs to be useful
                # First paragraph is leadin, rest are parts
                for para in paragraphs[1:]:
                    question, answer = self._extract_qa_pair(para)
                    parts.append({
                        'question': question,
                        'answer': answer,
                        'value': 10
                    })
        
        # If we have too many parts (likely false positives), try to merge them
        if len(parts) > 5:  # Unlikely to have more than 5 parts in a bonus
            merged_parts = [{'question': '', 'answer': '', 'value': 10}]
            for i, part in enumerate(parts):
                if i % 3 == 0 and i > 0:  # Every 3 parts, start a new bonus
                    merged_parts.append({'question': '', 'answer': '', 'value': 10})
                
                current = merged_parts[-1]
                if current['question']:
                    current['question'] += '\n\n' + part['question']
                else:
                    current['question'] = part['question']
                
                if part['answer']:
                    if current['answer']:
                        current['answer'] += '\n\n' + part['answer']
                    else:
                        current['answer'] = part['answer']
            
            parts = merged_parts
        
        # Clean up the parts
        for part in parts:
            # Remove any remaining answer indicators
            part['answer'] = regex.sub(r'^(?:ANSWER|ANS|A|جواب|پاسخ)[:.]?\s*', '', part['answer'], flags=regex.IGNORECASE).strip()
            
            # If answer is empty but question has answer in it, try to extract it
            if not part['answer'].strip() and '?' in part['question']:
                q_parts = part['question'].split('?', 1)
                if len(q_parts) > 1:
                    part['question'] = q_parts[0] + '?'
                    part['answer'] = q_parts[1].strip()
        
        return parts

    def parse_bonus(self, text: str) -> dict:
        print(f"\n=== Parsing Bonus ===")
        print(f"Input text: {text[:500]}...")
        
        try:
            # Clean the text first
            text = self._clean_question_text(text)
            
            # Extract leadin (everything before the first bonus part or answer)
            leadin_end = min(
                text.find('[') if '[' in text else float('inf'),
                text.lower().find('answer') if 'answer' in text.lower() else float('inf'),
                text.find('جواب') if 'جواب' in text else float('inf'),
                text.find('پاسخ') if 'پاسخ' in text else float('inf'),
                len(text) // 3  # Default to first third if no clear markers
            )
            
            if leadin_end < len(text):
                leadin = text[:leadin_end].strip()
                remaining_text = text[leadin_end:]
            else:
                leadin = ""
                remaining_text = text
            
            # Clean up leadin (remove bonus headers, numbers, etc.)
            leadin = regex.sub(r'(?i)^(?:BONUS|بونوس)[^\n]*\n?', '', leadin).strip()
            leadin = regex.sub(r'^\s*\d+[.)]\s*', '', leadin).strip()
            
            # Split into parts
            parts = self._split_bonus_parts(remaining_text)
            print(f"Found {len(parts)} bonus parts")
            
            # Clean up the parts
            for part in parts:
                part['question'] = self._clean_question_content(part['question'])
                part['answer'] = self._clean_answer_content(part['answer'])
                
                # Debug output
                print("\n--- Bonus Part ---")
                print(f"Question: {part['question'][:100]}...")
                print(f"Answer: {part['answer'][:100]}...")
            
            # If we have parts but no leadin, try to extract it from the first part
            if parts and not leadin.strip() and parts[0]['question']:
                # Try to find the first sentence as leadin
                first_question = parts[0]['question']
                sentences = regex.findall(r'([^.!?]+[.!?])(?:\s|$)', first_question)
                if sentences:
                    leadin = sentences[0].strip()
                    parts[0]['question'] = first_question[len(leadin):].strip()
            
            # Clean up leadin
            leadin = self._clean_question_content(leadin)
            print(f"\n--- Bonus Leadin ---\n{leadin[:200]}...")
            
            # Create the bonus data structure
            bonus_data = {
                'leadin': leadin,
                'leadin_sanitized': remove_formatting(leadin, include_italics=True),
                'parts': [p['question'] for p in parts],
                'answers': [p['answer'] for p in parts],
                'values': [p['value'] for p in parts],
                'formatted_answers': [
                    format_text(p['answer'], modaq=self.modaq) for p in parts
                ],
                'parts_sanitized': [
                    remove_formatting(p['question'], include_italics=True) for p in parts
                ],
                'formatted_answers_sanitized': [
                    remove_formatting(p['answer'], include_italics=True) for p in parts
                ],
            }
            
            # Parse category information
            category, subcategory, alternate_subcategory, metadata = self.parse_category(
                leadin, 'bonus'
            )
            
            bonus_data.update({
                'category': category,
                'subcategory': subcategory,
                'alternate_subcategory': alternate_subcategory or None,
                'metadata': metadata,
            })
            
            return bonus_data
            
        except Exception as e:
            print(f"Error in parse_bonus: {str(e)}")
            import traceback
            traceback.print_exc()
            return {}

    def parse_category(self, text: str, question_type: str = "tossup") -> tuple:
        """Parse category, subcategory, and metadata from question text.
        
        Args:
            text: The question text to parse
            question_type: Either "tossup" or "bonus"
            
        Returns:
            tuple: (category, subcategory, alternate_subcategory, metadata)
        """
        print(f"Parsing category for {question_type}")
        
        # Default values
        category = ""
        subcategory = ""
        alternate_subcategory = ""
        metadata = {}
        
        try:
            # Look for category tags in angle brackets
            category_match = regex.search(r'<([^>]+)>', text)
            if category_match:
                category_parts = [p.strip() for p in category_match.group(1).split(',') if p.strip()]
                if category_parts:
                    category = category_parts[0]
                    if len(category_parts) > 1:
                        subcategory = category_parts[1]
                    if len(category_parts) > 2:
                        alternate_subcategory = category_parts[2]
                
                # Remove the category tag from the text
                text = text.replace(category_match.group(0), '').strip()
                
            # Look for author in angle brackets
            author_match = regex.search(r'<([^>]*)>$', text)
            if author_match and author_match.group(1).strip():
                metadata['author'] = author_match.group(1).strip()
                text = text.replace(author_match.group(0), '').strip()
                
        except Exception as e:
            print(f"Error parsing category: {str(e)}")
            
        return category, subcategory, alternate_subcategory, metadata

    def _clean_question_text(self, text: str) -> str:
        """Clean up question text by removing headers and footers."""
        if not text:
            return ""
            
        # First, remove any JSON/object artifacts
        text = regex.sub(r'\[object Object\]', '', text)
        
        # Remove common headers and packet metadata (more specific patterns first)
        patterns = [
            # Packet headers and credits (multi-line)
            r'(?i)(?:packet\s*\d+|written\s*by:|edited\s*by:|playtested\s*by:)[^\n]*(?:\n[^\n]*)*?(?=\n\s*\n|$)',
            # Section headers
            r'(?i)^\s*(?:Tossups?|Bonuses?|Bonus Questions?)\s*\d*\s*:?\s*\n*',
            # Question numbers
            r'^\s*\d+[.)]\s*',
            # Farsi packet headers
            r'(?i)\b(?:FARSI|PACKET|PACKET\s*\d+)[^\n]*(?:\n|$)',
            # Non-alphanumeric prefixes
            r'^[^A-Za-z0-9]+',
            # Any remaining bonus indicators
            r'\[\d+[ehm]?\]\s*'
        ]
        
        for pattern in patterns:
            text = regex.sub(pattern, '', text, flags=regex.MULTILINE | regex.IGNORECASE)
        
        # Remove any remaining HTML/formatting tags
        text = regex.sub(r'<[^>]*>', '', text)
        
        # Normalize whitespace but preserve paragraph breaks
        text = '\n\n'.join(p.strip() for p in text.split('\n\n') if p.strip())
        text = ' '.join(text.split())
        
        return text.strip()
    
    def _clean_question_content(self, text: str) -> str:
        """Clean up question content."""
        # Remove question numbers if present
        if self.has_question_numbers:
            text = regex.sub(r'^\d+[.)]\s*', '', text, flags=regex.MULTILINE)
        
        # Remove any remaining HTML/formatting tags
        text = regex.sub(r'<[^>]*>', '', text)
        
        # Normalize whitespace
        text = regex.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def _clean_answer_content(self, text: str) -> str:
        """Clean up answer content."""
        # Remove any HTML/formatting tags
        text = regex.sub(r'<[^>]*>', '', text)
        
        # Remove any bonus part indicators or point values
        text = regex.sub(r'\[\s*\d+[ehm]?\s*\]', '', text, flags=regex.IGNORECASE)
        
        # Remove any trailing metadata or author credits
        text = regex.sub(r'\s*\([^)]*\)$', '', text)  # Remove parentheticals at end
        text = regex.sub(r'\s*\[[^]]*\]$', '', text)  # Remove square brackets at end
        
        # Normalize whitespace
        text = regex.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def preprocess_packet(self, packet_text: str) -> str:
        if not packet_text:
            print("Warning: Empty packet text in preprocess_packet")
            return ""
            
        print("\n=== Starting packet preprocessing ===")
        original_length = len(packet_text)
        print(f"Original length: {original_length} characters")
        
        try:
            # Normalize line endings
            packet_text = packet_text.replace('\r\n', '\n').replace('\r', '\n')
            print(f"After normalizing line endings: {len(packet_text)} characters")
            
            # Handle FARSI-specific formatting - more flexible number patterns
            packet_text = regex.sub(
                r'^(\d+)\s*[.)]\s*', 
                r'\1. ', 
                packet_text, 
                flags=regex.MULTILINE
            )
            print(f"After fixing question numbers: {len(packet_text)} characters")
            
            # Handle various answer indicator formats
            answer_patterns = [
                (r'\n\s*(?:ANSWER|Answer|Ответ|الجواب)\s*[:.]?\s*', '\nANSWER: '),
                (r'\n\s*جواب\s*[:.]?\s*', '\nANSWER: '),  # Farsi answer indicator
                (r'\n\s*پاسخ\s*[:.]?\s*', '\nANSWER: '),  # Another Farsi answer indicator
            ]
            
            for pattern, replacement in answer_patterns:
                packet_text = regex.sub(
                    pattern,
                    replacement,
                    packet_text,
                    flags=regex.IGNORECASE | regex.MULTILINE
                )
            
            print(f"After standardizing answer indicators: {len(packet_text)} characters")
            
            # Clean up bonus part markers - more flexible matching
            bonus_patterns = [
                (r'\[\s*(\d{1,2})\s*([ehm]?)\s*\]', r'[\1\2]'),  # [10], [15e], etc.
                (r'\n\s*([A-Z])\s*[.)]\s*', r'\n[10] '),  # A), B), etc.
                (r'\n\s*\(([A-Z])\)\s*', r'\n[10] '),    # (A), (B), etc.
                (r'\n\s*[\u0660-\u0669]+\s*[.)]\s*', '\n[10] '),  # Arabic numerals
            ]
            
            for pattern, replacement in bonus_patterns:
                packet_text = regex.sub(
                    pattern,
                    replacement,
                    packet_text,
                    flags=regex.IGNORECASE | regex.MULTILINE
                )
            
            print(f"After cleaning bonus markers: {len(packet_text)} characters")
            
            # Normalize whitespace
            packet_text = regex.sub(r'\s+', ' ', packet_text)  # Replace multiple spaces
            packet_text = regex.sub(r'\n{3,}', '\n\n', packet_text)  # Normalize multiple newlines
            
            # Ensure each question starts on a new line
            packet_text = regex.sub(r'(?<=\n)(\d+\.)', r'\n\1', packet_text)
            
            print(f"After normalizing whitespace: {len(packet_text)} characters")
            
            # Debug: Print first 500 characters of processed text
            print("\n=== First 500 characters after preprocessing ===")
            print(packet_text[:500] + "..." if len(packet_text) > 500 else packet_text)
            
            if not packet_text.strip():
                print("Warning: Packet text is empty after preprocessing!")
            
            return packet_text
            
        except Exception as e:
            print(f"Error in preprocess_packet: {str(e)}")
            import traceback
            traceback.print_exc()
            return packet_text  # Return original if preprocessing fails

    def parse_packet(self, packet_text: str, packet_name: str = "") -> dict:
        self.tossup_index = 1
        self.bonus_index = 1
        tossups = []
        bonuses = []
        
        print(f"\n=== Starting to parse packet: {packet_name} ===")
        print(f"Initial text length: {len(packet_text) if packet_text else 0} characters")
        if packet_text:
            print(f"First 200 chars: {packet_text[:200]}")
            print(f"Last 200 chars: {packet_text[-200:]}")

        try:
            # Ensure packet_text is a string
            if not isinstance(packet_text, str):
                print("Input is not a string, attempting to convert...")
                if hasattr(packet_text, 'decode'):
                    packet_text = packet_text.decode('utf-8', errors='replace')
                    print("Decoded bytes to string")
                else:
                    packet_text = str(packet_text)
                    print("Converted to string using str()")

            # Normalize line endings and clean up the text
            packet_text = packet_text.replace('\r\n', '\n').replace('\r', '\n')
            print(f"After normalizing line endings: {len(packet_text)} characters")
            
            packet_text = self.preprocess_packet(packet_text)
            print(f"After preprocessing: {len(packet_text)} characters")
            if packet_text:
                print(f"First 200 chars after preprocessing: {packet_text[:200]}")

            # If the text is empty after preprocessing, return empty results
            if not packet_text or not packet_text.strip():
                print("Warning: Packet text is empty after preprocessing!")
                return {"tossups": [], "bonuses": [], "metadata": {"packet_name": packet_name, "error": "Empty packet after preprocessing"}}

            # Split into questions using a more robust method
            questions = []
            
            print(f"\n=== Attempting to split questions ===")
            print(f"Using has_question_numbers: {self.has_question_numbers}")
            print(f"Using has_category_tags: {self.has_category_tags}")
            
            # Try multiple splitting strategies
            
            # Strategy 1: Split on question numbers (e.g., "1.", "2)")
            question_blocks = regex.split(r'(?m)^(\d+[.)]\s*)', packet_text)
            print(f"Found {len(question_blocks)} question blocks using number split")
            
            if len(question_blocks) > 1:
                print("Found numbered questions, reconstructing...")
                # Reconstruct questions from numbered blocks
                for i in range(1, len(question_blocks), 2):
                    question = question_blocks[i] + question_blocks[i+1] if i+1 < len(question_blocks) else question_blocks[i]
                    question = question.strip()
                    if question:
                        questions.append(question)
            else:
                # Strategy 2: Split on TOSSUP/BONUS indicators
                print("No numbered questions found, trying TOSSUP/BONUS split...")
                tossup_markers = list(regex.finditer(r'(?i)(?:TOSSUP|BONUS)\s*\d*\s*[.:]?', packet_text))
                print(f"Found {len(tossup_markers)} TOSSUP/BONUS markers")
                
                if tossup_markers:
                    for i in range(len(tossup_markers)):
                        start = tossup_markers[i].start()
                        end = tossup_markers[i+1].start() if i+1 < len(tossup_markers) else len(packet_text)
                        question = packet_text[start:end].strip()
                        if question:
                            questions.append(question)
                else:
                    # Strategy 3: Split on ANSWER markers
                    print("No TOSSUP/BONUS markers found, trying ANSWER split...")
                    answer_markers = list(regex.finditer(r'(?i)(?:ANSWER|جواب|پاسخ)\s*[:.]', packet_text))
                    print(f"Found {len(answer_markers)} answer markers")
                    
                    if answer_markers:
                        last_pos = 0
                        for i, marker in enumerate(answer_markers):
                            # Find the start of the question (previous newline or start of text)
                            question_start = packet_text.rfind('\n', last_pos, marker.start())
                            if question_start == -1:
                                question_start = last_pos
                            else:
                                question_start += 1  # Skip the newline
                                
                            # Find the end of the answer (next question start or end of text)
                            next_marker = answer_markers[i+1].start() if i+1 < len(answer_markers) else len(packet_text)
                            answer_end = next_marker
                            
                            question = packet_text[question_start:answer_end].strip()
                            if question:
                                questions.append(question)
                            last_pos = answer_end
                        
                        # Add any remaining text after the last answer marker
                        if last_pos < len(packet_text):
                            question = packet_text[last_pos:].strip()
                            if question:
                                questions.append(question)
                    else:
                        # Strategy 4: Split on double newlines as last resort
                        print("No answer markers found, trying double newline split...")
                        questions = [q.strip() for q in packet_text.split('\n\n') if q.strip()]
            
            # Clean up any empty or very short questions
            questions = [q for q in questions if len(q.strip()) > 10]  # At least 10 chars to be a real question
            
            print(f"\n=== Found {len(questions)} potential questions ===")
            for i, q in enumerate(questions[:5]):  # Print first 5 questions for debugging
                print(f"\nQuestion {i+1} (first 100 chars): {q[:100]}...")

            # Process each question
            print(f"\n=== Processing {len(questions)} questions ===")
            for i, question in enumerate(questions):
                if not question or not question.strip():
                    print(f"Skipping empty question {i+1}")
                    continue
                    
                print(f"\n--- Processing Question {i+1} ---")
                print(f"First 200 chars: {question[:200]}")
                
                # Check if it's a bonus (look for [10], [15], [20] or similar patterns, or starts with BONUS)
                is_bonus = bool(regex.search(r'(?:^|\s)(?:BONUS|\[\s*\d+[ehm]?\s*\])', question, regex.IGNORECASE))
                print(f"Is bonus: {is_bonus}")
                
                try:
                    if is_bonus:
                        print("Attempting to parse as bonus...")
                        bonus = self.parse_bonus(question)
                        if bonus:
                            print(f"Successfully parsed bonus: {bonus.get('leadin', '')[:100]}...")
                            bonuses.append(bonus)
                        else:
                            print("Failed to parse bonus - trying as tossup...")
                            tossup = self.parse_tossup(question)
                            if tossup:
                                tossups.append(tossup)
                    else:
                        print("Attempting to parse as tossup...")
                        tossup = self.parse_tossup(question)
                        if tossup:
                            print(f"Successfully parsed tossup: {tossup.get('question', '')[:100]}...")
                            tossups.append(tossup)
                        else:
                            print("Failed to parse as tossup - trying as bonus...")
                            bonus = self.parse_bonus(question)
                            if bonus:
                                bonuses.append(bonus)
                except Exception as e:
                    print(f"Error processing question: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    print(f"Question text: {question[:200]}...")
                    continue
                    
            return {
                "tossups": tossups,
                "bonuses": bonuses,
                "metadata": {"packet_name": packet_name}
            }
            
        except Exception as e:
            print(f"Error in parse_packet: {str(e)}")
            # Return whatever we have so far
            return {
                "tossups": tossups,
                "bonuses": bonuses,
                "metadata": {"packet_name": packet_name, "error": str(e)}
            }

        # First pass: identify all potential questions and their types
        potential_questions = []
        current_bonus_group = []
        
        for question in packet_questions:
            question = question.strip()
            if not question:
                continue
                
            # Check for bonus indicators
            is_bonus = any([
                # Starts with [10], [15e], etc.
                regex.search(r'^\s*\[\s*\d+[ehm]?\s*\]', question, flags=Parser.REGEX_FLAGS),
                # Contains multiple answer indicators
                len(regex.findall(r'(?i)(?:ANSWER|ANS|A|جواب|پاسخ)\s*[:.]', question)) > 1,
                # Contains bonus part markers
                len(regex.findall(r'\[\s*\d+[ehm]?\s*\]', question)) > 1,
                # Contains part indicators
                len(regex.findall(r'(?i)(?:Part\s*[A-C]|[A-C]\s*[.)])', question)) > 1
            ])
            
            # If we're in a bonus group and this looks like a continuation, keep it in the group
            if current_bonus_group and (is_bonus or len(current_bonus_group) < 3):
                current_bonus_group.append(question)
                # If we've collected 3 parts, add them as a single bonus
                if len(current_bonus_group) >= 3:
                    potential_questions.append({
                        'text': '\n\n'.join(current_bonus_group),
                        'is_bonus': True
                    })
                    current_bonus_group = []
                continue
            
            # If we were in a bonus group but this isn't a continuation, process what we have
            if current_bonus_group:
                potential_questions.append({
                    'text': '\n\n'.join(current_bonus_group),
                    'is_bonus': True
                })
                current_bonus_group = []
            
            # Start a new bonus group or add as a regular question
            if is_bonus:
                current_bonus_group = [question]
            else:
                potential_questions.append({
                    'text': question,
                    'is_bonus': False
                })
        
        # Add any remaining bonus parts
        if current_bonus_group:
            potential_questions.append({
                'text': '\n\n'.join(current_bonus_group),
                'is_bonus': True
            })
        
        # Process the identified questions
        for q in potential_questions:
            question = q['text']
            is_bonus = q['is_bonus']
            
            # Handle question numbering if needed
            if self.has_question_numbers and not regex.match(r'^\s*\d+\.', question):
                question = f"{self.bonus_index if is_bonus else self.tossup_index}. {question}"
            
            if is_bonus:
                bonuses.append(question)
                self.bonus_index += 1
            else:
                tossups.append(question)
                self.tossup_index += 1

        # ... (rest of the method remains the same)

        data = {
            "tossups": [],
            "bonuses": [],
        }

        missing_directives = regex.search(
            "description acceptable", packet_text, flags=Parser.REGEX_FLAGS
        )
        missing_directives = (
            0 if missing_directives is None else len(missing_directives)
        )
        not_sanitized = self.modaq or self.buzzpoints

        for tossup in tossups:
            tossup_parsed = self.parse_tossup(tossup)
            data["tossups"].append(tossup_parsed)
            self.tossup_index += 1
            question_text = (
                tossup_parsed["question"]
                if not_sanitized
                else tossup_parsed["question_sanitized"]
            )
            missing_directives -= int("description acceptable" in question_text.lower())

        for bonus in bonuses:
            bonus_parsed = self.parse_bonus(bonus)
            data["bonuses"].append(bonus_parsed)
            self.bonus_index += 1
            leadin_text = (
                bonus_parsed["leadin"]
                if not_sanitized
                else bonus_parsed["leadin_sanitized"]
            )
            missing_directives -= int("description acceptable" in leadin_text.lower())
            for part in (
                bonus_parsed["parts"]
                if not_sanitized
                else bonus_parsed["parts_sanitized"]
            ):
                missing_directives -= int("description acceptable" in part.lower())

        if missing_directives > 0:
            Logger.warning(
                f"{missing_directives} 'description acceptable' directive(s) may not have parsed in this packet"
            )

        return data


@click.command()
@click.option(
    "-i",
    "--input-directory",
    default="packets/",
    show_default=True,
    type=click.Path(exists=True),
)
@click.option(
    "-o", "--output-directory", default="output/", show_default=True, type=str
)
@click.option("-e", "-l", "--bonus-length", default=3, show_default=True, type=int)
@click.option(
    "-a",
    "--always-classify",
    is_flag=True,
    help="Always auto classify categories, even if category tag is detected.",
)
@click.option(
    "-b",
    "--buzzpoints",
    is_flag=True,
    help="Output in a format compatible with buzzpoints. Cannot be used with -m/--modaq.",
)
@click.option(
    "-c",
    "--classify-unknown",
    is_flag=True,
    default=True,
    show_default=True,
    help="Auto classify unrecognized categories in tags.",
)
@click.option(
    "-f",
    "--force-overwrite",
    is_flag=True,
    help="Overwrite existing files in output/ directory.",
)
@click.option(
    "-m",
    "--modaq",
    is_flag=True,
    help="Output in a format compatible with MODAQ. Cannot be used with -b/--buzzpoints.",
)
@click.option(
    "-p",
    "--auto-insert-powermarks",
    is_flag=True,
    help="Insert powermarks for questions that are bolded in power but do not have an explicit powermark.",
)
@click.option(
    "-s",
    "--space-powermarks",
    is_flag=True,
    help="Ensure powermarks are surrounded by spaces.",
)
def ensure_directories_exist():
    """Ensure that all required directories exist."""
    import os
    from pathlib import Path
    
    base_dir = Path(__file__).parent
    required_dirs = [
        'p-docx',
        'output',
        'p-pdf',
        'packets'
    ]
    
    for dir_name in required_dirs:
        dir_path = base_dir / dir_name
        dir_path.mkdir(exist_ok=True)
        print(f"Ensured directory exists: {dir_path}")

def main(
    input_directory,
    output_directory,
    bonus_length,
    always_classify,
    buzzpoints,
    classify_unknown,
    force_overwrite,
    modaq,
    auto_insert_powermarks,
    space_powermarks,
):
    # Ensure required directories exist
    ensure_directories_exist()
    if buzzpoints and modaq:
        Logger.error("Cannot output in both buzzpoints and MODAQ formats")
        exit(1)

    ########## START OF PROMPTS ##########

    try:
        os.mkdir(output_directory)
    except FileExistsError:
        Logger.warning("Output directory already exists!")
        if force_overwrite:
            Logger.warning("Overwriting files in output directory")
        else:
            print(
                "Use -f/--force-overwrite to overwrite existing files in output directory"
            )
            exit(0)

    HAS_QUESTION_NUMBERS = input("Do you have question numbers? (y/n) ") == "y"
    HAS_CATEGORY_TAGS = input("Do you have category tags? (y/n) ") == "y"
    print("Using category tags" if HAS_CATEGORY_TAGS else "Using question classifier")

    ########## END OF PROMPTS ##########

    parser = Parser(
        HAS_QUESTION_NUMBERS,
        HAS_CATEGORY_TAGS,
        bonus_length,
        buzzpoints,
        modaq,
        auto_insert_powermarks,
        classify_unknown,
        space_powermarks,
        always_classify,
        CONSTANT_SUBCATEGORY,
        CONSTANT_ALTERNATE_SUBCATEGORY,
    )

    for filename in sorted(os.listdir(input_directory)):
        if filename == ".DS_Store":
            continue

        with open(os.path.join(input_directory, filename), encoding="utf-8") as f:
            packet_text = f.read()

        packet = parser.parse_packet(packet_text, filename)

        output_path = os.path.join(output_directory, os.path.splitext(filename)[0] + ".json")
        with open(output_path, "w", encoding="utf-8") as g:
            json.dump(packet, g, indent=2, ensure_ascii=False)

    print(f"Successfully processed {len(os.listdir(input_directory))} files from {input_directory}")
    return 0


if __name__ == "__main__":
    main()
