#!/bin/bash

##### Convert all files to .txt, and for .docx and .pdf also get the answerline formatting #####
if [ -z "$TYPE" ]; then
    read -p "File type (p = pdf, d = docx, c = doc): " TYPE
    case $TYPE in
        p | pdf) TYPE="pdf" ;;
        d | docx) TYPE="docx" ;;
        c | doc) TYPE="doc" ;;
        t | txt) TYPE="txt" ;;
        *) echo "Invalid file type" && exit 1 ;;
    esac
fi

echo "Parsing ${TYPE} to text..."
mkdir -p "packets"

counter=0
for filename in p-$TYPE/*.$TYPE; do
    echo "Parsing ${filename}..."
    counter=$((counter+1))
    BASENAME=$(basename "$filename")
    BASENAME_NOEXT="${BASENAME%.*}"

    case $TYPE in
        pdf)
            python modules/pdf-to-docx.py "$filename"
            python modules/docx-to-txt.py "${filename%.pdf}.docx" "packets/${BASENAME_NOEXT}.txt"
            ;;
        docx)
            python modules/docx-to-txt.py "$filename" "packets/${BASENAME_NOEXT}.txt"
            ;;
        txt)
            cp "$filename" "packets/${BASENAME_NOEXT}.txt"
            ;;
    esac
done

echo "Parsed ${counter} ${TYPE}s."
