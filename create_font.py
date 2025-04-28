from fontTools.ttLib import TTFont
import tempfile
import os
from fontTools.merge import Merger

def create_bold_italic_font(bold_path, italic_path, output_path):
    """Create a permanent bold-italic font by combining features"""
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Create temporary files for intermediate steps
    with tempfile.NamedTemporaryFile(suffix='.ttf', delete=False) as bold_temp, \
         tempfile.NamedTemporaryFile(suffix='.ttf', delete=False) as italic_temp:
        
        bold_temp_path = bold_temp.name
        italic_temp_path = italic_temp.name
    
    # Load fonts and save to temporary files to ensure they're properly formatted
    bold_font = TTFont(bold_path)
    bold_font.save(bold_temp_path)
    
    italic_font = TTFont(italic_path)
    # Store the italic angle for later
    italic_angle = italic_font['post'].italicAngle if 'post' in italic_font else -12
    italic_font.save(italic_temp_path)
    
    # Perform the merge using temporary file paths
    merger = Merger()
    merged_font = merger.merge([bold_temp_path, italic_temp_path])
    
    # Fix font metadata
    if 'name' in merged_font:
        for name_record in merged_font['name'].names:
            if name_record.nameID in (1, 4):  # Family name or full name
                try:
                    current_name = name_record.toUnicode()
                    if 'Bold' not in current_name and 'Italic' not in current_name:
                        new_name = f"{current_name} Bold Italic"
                    elif 'Bold' not in current_name:
                        new_name = current_name.replace('Italic', 'Bold Italic')
                    elif 'Italic' not in current_name:
                        new_name = current_name.replace('Bold', 'Bold Italic')
                    else:
                        new_name = current_name
                    
                    name_record.string = new_name.encode('utf-16-be') if name_record.isUnicode() else new_name
                except Exception as e:
                    print(f"Warning: Could not update name record: {e}")
    
    # Update font style
    if 'OS/2' in merged_font:
        # Set weight to bold (700)
        merged_font['OS/2'].usWeightClass = 700
        
    # Set italic bit
    if 'head' in merged_font:
        merged_font['head'].macStyle |= 0x3  # Set both bold (0x1) and italic (0x2) bits
    
    # Set italic angle
    if 'post' in merged_font:
        merged_font['post'].italicAngle = italic_angle
    
    # Save the merged font
    merged_font.save(output_path)
    
    # Clean up temporary files
    try:
        os.unlink(bold_temp_path)
        os.unlink(italic_temp_path)
    except:
        pass
    
    print("Success!")
    return output_path

bold_path = "fonts/mangatb.ttf"
italic_path = "fonts/mangati.ttf" 
output_path = "fonts/mangatbi.ttf"
create_bold_italic_font(bold_path, italic_path, output_path)