def find_imbalance(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        in_double = False
        in_single = False
        
        i = 0
        while i < len(content):
            if content[i:i+3] == '"""' and not in_single:
                in_double = not in_double
                # Find line number
                line_no = content.count('\n', 0, i) + 1
                state = "OPENING" if in_double else "CLOSING"
                print(f"L{line_no}: Double Triple {state}")
                i += 3
            elif content[i:i+3] == "'''" and not in_double:
                in_single = not in_single
                line_no = content.count('\n', 0, i) + 1
                state = "OPENING" if in_single else "CLOSING"
                print(f"L{line_no}: Single Triple {state}")
                i += 3
            else:
                i += 1
        
        if in_double: print("FINAL ERROR: Double triple unterminated!")
        if in_single: print("FINAL ERROR: Single triple unterminated!")
                
    except Exception as e:
        print(f"Error: {e}")

find_imbalance(r'c:\Users\msg\bitirme\backend\app\main.py')
