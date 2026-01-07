import sys

def check_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        d_count = 0
        s_count = 0
        
        for i, line in enumerate(lines):
            # Count occurrences in line
            d_in_line = line.count('"""')
            s_in_line = line.count("'''")
            
            if d_in_line > 0:
                d_count += d_in_line
                print(f"L{i+1} [D={d_count}]: {line.strip()}")
            if s_in_line > 0:
                s_count += s_in_line
                print(f"L{i+1} [S={s_count}]: {line.strip()}")
        
        print(f"\nFinal Totals:")
        print(f"Double triple: {d_count}")
        print(f"Single triple: {s_count}")
                
    except Exception as e:
        print(f"Error: {e}")

check_file(r'c:\Users\msg\bitirme\backend\app\main.py')
