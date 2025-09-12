import os
import re
from pathlib import Path
from collections import Counter

def get_available_series(data_dir: Path):
    if not data_dir.exists():
        return []
    
    series = []
    for item in data_dir.iterdir():
        if item.is_dir():
            series.append(item.name)
    
    return sorted(series)

def extract_text_from_srt(content: str) -> str:
    lines = content.split('\n')
    text_lines = []
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        if not line:
            i += 1
            continue
            
        if line.isdigit():
            i += 1
            continue
            
        if '-->' in line:
            i += 1
            continue
            
        if line and not line.isdigit() and '-->' not in line:
            text_lines.append(line)
        
        i += 1
    
    return ' '.join(text_lines)

def extract_text_from_sub(content: str) -> str:
    lines = content.split('\n')
    text_lines = []
    
    for line in lines:
        line = line.strip()
        
        if not line:
            continue
            
        if re.match(r'^\d{2}:\d{2}:\d{2}', line):
            continue
            
        if line.isdigit():
            continue
            
        if line:
            text_lines.append(line)
    
    return ' '.join(text_lines)

def clean_text(text: str) -> str:
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('\u2019', "'").replace('\u2018', "'")
    text = text.replace('\u2013', ' ').replace('\u2014', ' ').replace('\u2212', ' ')
    return text

def count_words_in_file(file_path: Path) -> Counter:
    try:
        with open(file_path, 'r', encoding='cp1252', errors='ignore') as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='latin-1', errors='ignore') as f:
                content = f.read()
        except:
            return Counter()
    except:
        return Counter()
    
    if file_path.suffix.lower() == '.srt':
        text = extract_text_from_srt(content)
    elif file_path.suffix.lower() == '.sub':
        text = extract_text_from_sub(content)
    else:
        return Counter()
    
    text = clean_text(text)
    text = text.lower()
    tokens = re.findall(r"\w+(?:['-]\w+)*", text, flags=re.UNICODE)
    return Counter(tokens)

def count_words_in_series(series_name: str, data_dir: Path) -> Counter:
    series_dir = data_dir / series_name
    
    if not series_dir.exists():
        return Counter()
    
    subtitle_files = []
    for ext in ['.srt', '.sub']:
        subtitle_files.extend(series_dir.glob(f'*{ext}'))
    
    if not subtitle_files:
        return Counter()
    
    total_counter = Counter()
    
    for file_path in subtitle_files:
        file_counter = count_words_in_file(file_path)
        total_counter.update(file_counter)
    
    return total_counter

def save_word_count(counter: Counter, output_file: Path):
    with open(output_file, 'w', encoding='utf-8') as f:
        for word, count in counter.most_common():
            f.write(f"{word}:{count}\n")

def main():
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    data_dir = project_root / 'data'
    word_freq_dir = project_root / "data_word_frequency"
    word_freq_dir.mkdir(exist_ok=True)
    
    series_list = get_available_series(data_dir)
    
    for series_name in series_list:
        word_counter = count_words_in_series(series_name, data_dir)
        if word_counter:
            output_file = word_freq_dir / f"{series_name}.txt"
            save_word_count(word_counter, output_file)

if __name__ == "__main__":
    main()
