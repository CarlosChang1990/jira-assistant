import re

def test_regex():
    versions = [
        "OPS1.58.0",
        "NGS4.11.0",
        "Car2go 1.140",
        "GB2.81.0",
        "My System 2.0",
        "Win10 1.0.0" # Tricky one
    ]
    
    # Old Regex
    old_pattern = re.compile(r"^([a-zA-Z0-9\s]+?)(?=\d)")
    
    # New Regex: Look for (optional space) + Digit + Dot
    # This assumes version always has a dot.
    new_pattern = re.compile(r"^(.+?)(?=\s?\d+\.\d+)")
    
    print(f"{'Version Name':<20} | {'Old Regex':<10} | {'New Regex':<10}")
    print("-" * 50)
    
    for v in versions:
        m_old = old_pattern.match(v)
        res_old = m_old.group(1).strip() if m_old else "NO MATCH"
        
        m_new = new_pattern.match(v)
        res_new = m_new.group(1).strip() if m_new else "NO MATCH"
        
        print(f"{v:<20} | {res_old:<10} | {res_new:<10}")

if __name__ == "__main__":
    test_regex()
