#!/usr/bin/env python3
"""
Make simple transfer list from ASSIST API data
"""

import json
import requests
import argparse
import os

def fetch_api_data(url):
    """Fetch data from ASSIST API"""
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return None

def get_transfer_data(from_code, to_code):
    """Get transfer data and return as JSON object"""
    # Build API URL using the provided arguments
    api_url = f"https://assist.org/api/articulation/Agreements?Key=75/{from_code}/to/{to_code}/AllPrefixes"
    raw_data = fetch_api_data(api_url)
    
    if not raw_data:
        return None
    
    result = raw_data['result']
    
    # Parse institutions
    receiving = json.loads(result['receivingInstitution'])
    sending = json.loads(result['sendingInstitution'])
    academic_year = json.loads(result['academicYear'])
    articulations = json.loads(result['articulations'])
    
    # Create simple structure (matching reference format)
    simple_data = {
        "from_college": sending['names'][0]['name'],
        "to_college": receiving['names'][0]['name'],
        "academic_year": academic_year['code'],
        "transfers": []
    }
    
    # Extract transfers (matching reference format)
    for dept in articulations:
        for course in dept['articulations']:
            if course['type'] == 'Course':
                course_info = course['course']
                
                transfer = {
                    "from_course": f"{course_info['prefix']} {course_info['courseNumber']}",
                    "course_title": course_info['courseTitle'],
                    "units": course_info.get('minUnits', 'N/A'),
                    "department": course_info['department']
                }
                
                # Check for transfer mapping (same as reference)
                if course.get('sendingArticulation') and course['sendingArticulation'].get('items'):
                    transfers_to = []
                    for item in course['sendingArticulation']['items']:
                        if 'items' in item:
                            for to_course in item['items']:
                                transfers_to.append(f"{to_course['prefix']} {to_course['courseNumber']}: {to_course['courseTitle']}")
                    transfer["transfers_to"] = transfers_to if transfers_to else ["No equivalent course"]
                else:
                    transfer["transfers_to"] = ["No equivalent course"]
                
                simple_data["transfers"].append(transfer)
    
    return simple_data

def main(from_code, to_code):
    """Main function for command line usage"""
    transfer_data = get_transfer_data(from_code, to_code)
    
    if not transfer_data:
        print("Failed to fetch data from API")
        return
    
    # Save to file in same directory as script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(script_dir, 'simple_transfers.json')
    
    with open(json_path, 'w') as f:
        json.dump(transfer_data, f, indent=2)
    
    print(f"Created simple_transfers.json with {len(transfer_data['transfers'])} courses")
    print(f"{transfer_data['from_college']} → {transfer_data['to_college']}")

# Store the JSON data in the file as a variable for easy access
SAMPLE_DATA = None

def store_data_in_file(from_code, to_code):
    """Store JSON data directly in this file"""
    global SAMPLE_DATA
    SAMPLE_DATA = get_transfer_data(from_code, to_code)
    return SAMPLE_DATA

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build transfer list from ASSIST API")
    parser.add_argument("from_code", help="Sending institution code")
    parser.add_argument("to_code", help="Receiving institution code")
    args = parser.parse_args()
    main(args.from_code, args.to_code)
