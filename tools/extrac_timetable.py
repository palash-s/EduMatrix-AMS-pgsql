import pandas as pd
import re
import warnings
from io import StringIO

warnings.filterwarnings('ignore')

# Special slots that don't require subject code or faculty
SPECIAL_SLOT_KEYWORDS = [
    'library slot', 'library', 'mentor meeting', 'mentor', 'scil', 
    'project meeting', 'pp-ii', 'oe', 'oe:online', 'break', 
    'long break', 'short break', 'aps', 'forl'
]

def is_special_slot(text):
    """Check if the slot is a special slot (no subject/faculty required)."""
    if not text:
        return False
    text_lower = str(text).strip().lower()
    for keyword in SPECIAL_SLOT_KEYWORDS:
        if keyword in text_lower:
            return True
    return False

def get_session_type(abbr_type):
    """Maps L, P, T to full names."""
    abbr = str(abbr_type).strip().upper()
    if abbr == 'L': return 'Lecture'
    if abbr == 'P': return 'Practical'
    if abbr == 'T': return 'Tutorial'
    return 'Lecture' # Default fallback

def get_batch_and_section(raw_section, session_type):
    """
    Returns (Output Section Name, Batch Code).
    Batch is only assigned if Session Type is 'Practical'.
    """
    # Clean up input (remove hyphens, spaces, lower case)
    # e.g. "DA-1" -> "da1", "Core - 1" -> "core1"
    clean = str(raw_section).strip().lower().replace('-', '').replace(' ', '')
    
    # Defaults
    out_section = str(raw_section).strip()
    batch = ""
    
    # 1. Determine Section Name for Output
    if 'da' in clean:
        out_section = "DA"
    elif 'core' in clean:
        out_section = "CORE"
    elif 'smad' in clean:
        out_section = "SMAD"
        
    # 2. Determine Batch (Only for Practicals)
    if session_type == 'Practical':
        if 'da1' in clean or 'core1' in clean:
            batch = 'A'
        elif 'da2' in clean or 'core2' in clean:
            batch = 'B'
        elif 'core3' in clean:
            batch = 'C'
            
    return out_section, batch

def process_timetable(file_path):
    # 1. Read File (Header at row 2)
    try:
        df = pd.read_csv(file_path, header=2)
    except:
        df = pd.read_excel(file_path, header=2)
    
    # 2. Split Grid and Legend
    # Find split based on 'Course Code' column
    legend_start = 13 # Default
    for i, col in enumerate(df.columns):
        if str(col).strip() == 'Course Code':
            legend_start = i
            break
            
    grid_df = df.iloc[:, :legend_start].copy()
    legend_df = df.iloc[:, legend_start:].copy()
    legend_df.columns = [str(c).strip() for c in legend_df.columns]

    # 3. Build Course Database
    course_db = {}
    faculty_db = {}
    
    # Identify relevant legend columns
    col_abbr = next((c for c in legend_df.columns if 'Abbreviation' in c or 'Abbr' in c), None)
    col_code = next((c for c in legend_df.columns if 'Course Code' in c), None)
    col_name = next((c for c in legend_df.columns if 'Course Name' in c), None)
    col_type = next((c for c in legend_df.columns if 'Session Type' in c or 'Type' in c), None)
    col_fac_abbr = next((c for c in legend_df.columns if 'Faculty_Abbreviation' in c), None)
    col_emp = next((c for c in legend_df.columns if 'EMP_ID' in c), None)
    
    for _, row in legend_df.iterrows():
        if pd.isna(row.get(col_abbr)): continue
        
        # Key: Uppercase abbreviation
        key = str(row[col_abbr]).strip().upper()
        
        # Session Type Mapping (L->Lecture, P->Practical)
        raw_type = str(row[col_type]).strip() if col_type else 'L'
        stype = get_session_type(raw_type)
        
        course_db[key] = {
            'code': str(row[col_code]).strip() if col_code else '',
            'name': str(row[col_name]).strip() if col_name else key,
            'type': stype
        }
        
        # Faculty
        if col_fac_abbr and col_emp and not pd.isna(row[col_fac_abbr]):
            fabbr = str(row[col_fac_abbr]).strip()
            eid = str(row[col_emp]).strip().replace('.0', '')
            faculty_db[fabbr] = eid

    # 4. Process Grid Rows
    # Find time columns (e.g. 8.45-9.40)
    time_cols = [c for c in grid_df.columns if re.search(r"\d{1,2}[:.]\d{2}", str(c))]
    
    # Fill Day column
    if 'Day' in str(grid_df.columns[0]):
         grid_df.iloc[:, 0] = grid_df.iloc[:, 0].fillna(method='ffill')
         
    output_rows = []
    
    for idx, row in grid_df.iterrows():
        day = row.iloc[0]
        class_lvl = row.iloc[1]
        raw_sec = row.iloc[2]
        
        if pd.isna(raw_sec): raw_sec = "Unknown"
        
        skip_next = False
        
        for i, col_name in enumerate(time_cols):
            if skip_next:
                skip_next = False
                continue
                
            cell_val = row[col_name]
            
            # Skip invalid cells
            if pd.isna(cell_val) or str(cell_val).strip() == "" or "Break" in str(cell_val):
                continue
            if "Break" in col_name: continue

            # Time Parsing - use normalize_time to handle 24-hour conversion
            time_parts = re.split(r'[-–]', col_name)
            start_time = normalize_time(time_parts[0].strip())
            end_time = normalize_time(time_parts[1].strip()) if len(time_parts) > 1 else start_time
            
            # Merge Logic (Next cell identical or empty)
            if i + 1 < len(time_cols):
                next_col = time_cols[i+1]
                next_val = row[next_col]
                if (pd.isna(next_val) or str(next_val).strip() == "") or (str(next_val).strip() == str(cell_val).strip()):
                    next_time_parts = re.split(r'[-–]', next_col)
                    end_time = normalize_time(next_time_parts[1].strip()) if len(next_time_parts) > 1 else end_time
                    skip_next = True
            
            # Cell Content Parsing (Split by '/')
            text = str(cell_val).strip()
            items = [x.strip() for x in text.split('/')]
            
            for item in items:
                # Format: ABBR:FAC:ROOM
                parts = item.split(':')
                abbr = parts[0].strip()
                fac = parts[1].strip() if len(parts) > 1 else '-'
                room = parts[2].strip() if len(parts) > 2 else '-'
                
                # Check if this is a special slot (Library, Mentor Meeting, SCIL, etc.)
                if is_special_slot(item):
                    # Extract display name for special slot
                    slot_name = abbr
                    if 'library' in item.lower():
                        slot_name = 'Library Slot'
                    elif 'mentor' in item.lower():
                        slot_name = 'Mentor Meeting'
                    elif 'scil' in item.lower():
                        slot_name = 'SCIL'
                    elif 'pp-ii' in item.lower() or 'pp-' in item.lower():
                        slot_name = 'PP-II'
                    elif 'oe' in item.lower():
                        slot_name = 'Open Elective'
                    elif 'project' in item.lower():
                        slot_name = 'Project Meeting'
                    elif 'aps' in item.lower():
                        slot_name = 'Aptitude & Professional Skills'
                    elif 'forl' in item.lower():
                        slot_name = 'Foreign Language'
                    
                    final_sec, batch = get_batch_and_section(raw_sec, 'Lecture')
                    output_rows.append({
                        'Day': day,
                        'Start Time': start_time,
                        'End Time': end_time,
                        'Subject Code': '?',  # Mark as special slot
                        'Course Name': slot_name,
                        'Employee Code': '-',  # No faculty
                        'Faculty_Abbreviation': '-',
                        'Abbreviation_course': abbr.upper(),
                        'Class Level': class_lvl,
                        'Section Name': final_sec,
                        'Session Type': 'Lecture',
                        'Batch': batch,
                        'Room Number': room if room != '-' else ''
                    })
                    continue
                
                # Loose logic for "Subject Room" (no colon)
                if len(parts) == 1 and abbr.upper() not in course_db:
                    sub_parts = abbr.split()
                    if len(sub_parts) > 1 and sub_parts[0].upper() in course_db:
                        abbr = sub_parts[0]
                        room = " ".join(sub_parts[1:])
                
                # Lookup Info
                info = course_db.get(abbr.upper(), {'code': '?', 'name': abbr, 'type': 'Lecture'})
                emp_code = faculty_db.get(fac, '-')
                
                # Get Normalized Section and Batch
                final_sec, batch = get_batch_and_section(raw_sec, info['type'])
                
                output_rows.append({
                    'Day': day,
                    'Start Time': start_time,
                    'End Time': end_time,
                    'Subject Code': info['code'] if info['code'] else '?',
                    'Course Name': info['name'],
                    'Employee Code': emp_code,
                    'Faculty_Abbreviation': fac,
                    'Abbreviation_course': abbr.upper(),
                    'Class Level': class_lvl,
                    'Section Name': final_sec,
                    'Session Type': info['type'],
                    'Batch': batch,
                    'Room Number': room
                })
                
    # 5. Return Final DataFrame
    return pd.DataFrame(output_rows)


def process_timetable_from_content(file_content, filename='timetable.csv'):
    """
    Process timetable from file content (string or bytes).
    Used by the bulk upload endpoint.
    """
    if isinstance(file_content, bytes):
        file_content = file_content.decode('utf-8')
    
    # Create a StringIO object to read as file
    from io import StringIO
    file_like = StringIO(file_content)
    
    # Determine file type and read
    try:
        df = pd.read_csv(file_like, header=2)
    except:
        # Try Excel format
        import io
        file_like = io.BytesIO(file_content.encode() if isinstance(file_content, str) else file_content)
        df = pd.read_excel(file_like, header=2)
    
    return _process_dataframe(df)


def _process_dataframe(df):
    """Internal function to process the dataframe once loaded."""
    # Split Grid and Legend
    legend_start = 13
    for i, col in enumerate(df.columns):
        if str(col).strip() == 'Course Code':
            legend_start = i
            break
            
    grid_df = df.iloc[:, :legend_start].copy()
    legend_df = df.iloc[:, legend_start:].copy()
    legend_df.columns = [str(c).strip() for c in legend_df.columns]

    # Build Course Database
    course_db = {}
    faculty_db = {}
    
    col_abbr = next((c for c in legend_df.columns if 'Abbreviation' in c or 'Abbr' in c), None)
    col_code = next((c for c in legend_df.columns if 'Course Code' in c), None)
    col_name = next((c for c in legend_df.columns if 'Course Name' in c), None)
    col_type = next((c for c in legend_df.columns if 'Session Type' in c or 'Type' in c), None)
    col_fac_abbr = next((c for c in legend_df.columns if 'Faculty_Abbreviation' in c), None)
    col_emp = next((c for c in legend_df.columns if 'EMP_ID' in c), None)
    
    for _, row in legend_df.iterrows():
        if pd.isna(row.get(col_abbr)): continue
        
        key = str(row[col_abbr]).strip().upper()
        raw_type = str(row[col_type]).strip() if col_type else 'L'
        stype = get_session_type(raw_type)
        
        course_db[key] = {
            'code': str(row[col_code]).strip() if col_code and not pd.isna(row[col_code]) else '',
            'name': str(row[col_name]).strip() if col_name and not pd.isna(row[col_name]) else key,
            'type': stype
        }
        
        if col_fac_abbr and col_emp and not pd.isna(row.get(col_fac_abbr)):
            fabbr = str(row[col_fac_abbr]).strip()
            eid = str(row[col_emp]).strip().replace('.0', '')
            if eid and eid != 'nan' and eid != '-':
                faculty_db[fabbr] = eid

    # Process Grid
    time_cols = [c for c in grid_df.columns if re.search(r"\d{1,2}[:.]\d{2}", str(c))]
    
    if 'Day' in str(grid_df.columns[0]):
         grid_df.iloc[:, 0] = grid_df.iloc[:, 0].fillna(method='ffill')
         
    output_rows = []
    
    for idx, row in grid_df.iterrows():
        day = row.iloc[0]
        if pd.isna(day): continue
        
        class_lvl = row.iloc[1]
        raw_sec = row.iloc[2]
        
        if pd.isna(raw_sec): raw_sec = "Unknown"
        if pd.isna(class_lvl): continue
        
        skip_next = False
        
        for i, col_name in enumerate(time_cols):
            if skip_next:
                skip_next = False
                continue
                
            cell_val = row[col_name]
            
            if pd.isna(cell_val) or str(cell_val).strip() == "":
                continue
            if "Break" in str(cell_val) or "Break" in col_name:
                continue

            # Time Parsing - handle both formats
            time_parts = re.split(r'[-–]', col_name)
            start_time = time_parts[0].strip().replace('.', ':')
            end_time = time_parts[1].strip().replace('.', ':') if len(time_parts) > 1 else start_time
            
            # Normalize time format (add leading zeros)
            start_time = normalize_time(start_time)
            end_time = normalize_time(end_time)
            
            # Merge Logic
            if i + 1 < len(time_cols):
                next_col = time_cols[i+1]
                next_val = row[next_col]
                if (pd.isna(next_val) or str(next_val).strip() == "") or (str(next_val).strip() == str(cell_val).strip()):
                    next_time_parts = re.split(r'[-–]', next_col)
                    end_time = normalize_time(next_time_parts[1].strip().replace('.', ':')) if len(next_time_parts) > 1 else end_time
                    skip_next = True
            
            # Cell Content Parsing
            text = str(cell_val).strip()
            items = [x.strip() for x in text.split('/')]
            
            for item in items:
                if not item: continue
                
                # Check if this is a special slot first
                if is_special_slot(item):
                    slot_name = extract_special_slot_name(item)
                    final_sec, batch = get_batch_and_section(raw_sec, 'Lecture')
                    
                    # Try to extract room from the item
                    room = '-'
                    if ':' in item:
                        parts = item.split(':')
                        if len(parts) >= 2:
                            room = parts[-1].strip() if parts[-1].strip() else '-'
                    
                    output_rows.append({
                        'Day': day,
                        'Start Time': start_time,
                        'End Time': end_time,
                        'Subject Code': '?',
                        'Course Name': slot_name,
                        'Employee Code': '-',
                        'Class Level': class_lvl,
                        'Section Name': final_sec,
                        'Session Type': 'Lecture',
                        'Batch': '',
                        'Room Number': room
                    })
                    continue
                
                # Regular slot parsing
                parts = item.split(':')
                abbr = parts[0].strip()
                fac = parts[1].strip() if len(parts) > 1 else '-'
                room = parts[2].strip() if len(parts) > 2 else '-'
                
                # Loose logic for "Subject Room"
                if len(parts) == 1 and abbr.upper() not in course_db:
                    sub_parts = abbr.split()
                    if len(sub_parts) > 1 and sub_parts[0].upper() in course_db:
                        abbr = sub_parts[0]
                        room = " ".join(sub_parts[1:])
                
                info = course_db.get(abbr.upper(), {'code': '?', 'name': abbr, 'type': 'Lecture'})
                emp_code = faculty_db.get(fac, '-')
                
                final_sec, batch = get_batch_and_section(raw_sec, info['type'])
                
                output_rows.append({
                    'Day': day,
                    'Start Time': start_time,
                    'End Time': end_time,
                    'Subject Code': info['code'] if info['code'] else '?',
                    'Course Name': info['name'],
                    'Employee Code': emp_code,
                    'Class Level': class_lvl,
                    'Section Name': final_sec,
                    'Session Type': info['type'],
                    'Batch': batch,
                    'Room Number': room
                })
                
    return pd.DataFrame(output_rows)


def normalize_time(time_str):
    """Normalize time to HH:MM 24-hour format.
    Converts afternoon times (1:xx - 7:xx) to 24-hour format (13:xx - 19:xx).
    School hours are typically 8 AM to 5 PM.
    """
    time_str = str(time_str).strip().replace('.', ':').replace(' ', '')
    parts = time_str.split(':')
    if len(parts) >= 2:
        hour = int(parts[0])
        minute = int(parts[1])
        
        # Convert afternoon times to 24-hour format
        # Times 1-7 are PM (13:00 - 19:00) in a typical school schedule
        if hour >= 1 and hour <= 7:
            hour += 12
            
        return f'{hour:02d}:{minute:02d}'
    return time_str


def extract_special_slot_name(item):
    """Extract a clean display name for special slots."""
    item_lower = item.lower()
    
    if 'library' in item_lower:
        return 'Library Slot'
    elif 'mentor' in item_lower:
        return 'Mentor Meeting'
    elif 'scil' in item_lower:
        return 'SCIL'
    elif 'pp-ii' in item_lower or 'pp-' in item_lower:
        return 'PP-II'
    elif 'oe:online' in item_lower or item_lower.startswith('oe'):
        return 'Open Elective'
    elif 'project' in item_lower:
        return 'Project Meeting'
    elif 'aps' in item_lower:
        return 'Aptitude & Professional Skills'
    elif 'forl' in item_lower:
        return 'Foreign Language'
    
    # Default: use the abbreviation part
    parts = item.split(':')
    return parts[0].strip() if parts else item


# --- EXECUTION (for standalone use) ---
if __name__ == '__main__':
    input_file = '[formated-master-timetable-IT-25-26].csv'
    df_result = process_timetable(input_file)
    df_result.to_csv('Clean_Output.csv', index=False)
    print(f"Processed {len(df_result)} rows")
    print(df_result.head(10))