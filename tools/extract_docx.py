import sys
import zipfile
from xml.etree import ElementTree as ET


def extract_text(docx_path: str) -> str:
    # Minimal DOCX text extractor (no external deps)
    # Walks paragraphs <w:p> and collects text from <w:t>
    with zipfile.ZipFile(docx_path) as z:
        with z.open('word/document.xml') as f:
            tree = ET.parse(f)
    root = tree.getroot()
    # WordprocessingML namespace map
    ns = {
        'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    }

    paras = []
    for p in root.findall('.//w:p', ns):
        texts = []
        for t in p.findall('.//w:t', ns):
            # Combine text runs, preserving spaces
            texts.append(t.text or '')
        # Respect line breaks inside runs if any
        para_text = ''.join(texts).replace('\r', '\n')
        # Skip entirely empty paragraphs to reduce noise
        paras.append(para_text)
    # Join with newlines; multiple newlines indicate section breaks
    return '\n'.join(paras)


def main():
    if len(sys.argv) < 2:
        print('Usage: python tools/extract_docx.py <path-to-docx>', file=sys.stderr)
        sys.exit(2)
    docx_path = sys.argv[1]
    try:
        text = extract_text(docx_path)
    except KeyError:
        print('Error: word/document.xml not found in DOCX (is the file valid?)', file=sys.stderr)
        sys.exit(1)
    except zipfile.BadZipFile:
        print('Error: Not a valid DOCX/ZIP file', file=sys.stderr)
        sys.exit(1)
    # Ensure UTF-8 output on Windows consoles
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # type: ignore[attr-defined]
    except Exception:
        pass
    sys.stdout.write(text)


if __name__ == '__main__':
    main()
