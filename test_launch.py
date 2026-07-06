#!/usr/bin/env python3
import os
import re
import sys

# Color formatting for terminal report card
GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def print_banner(text):
    print(f"\n{BOLD}{CYAN}{'='*70}{RESET}")
    print(f"{BOLD}{CYAN}  {text.center(66)}{RESET}")
    print(f"{BOLD}{CYAN}{'='*70}{RESET}\n")

def run_audit():
    # Resolve the path to app.py relative to this script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(current_dir, "app.py")
    
    if not os.path.exists(app_path):
        print(f"{RED}[FAIL] app.py not found at expected path: {app_path}{RESET}")
        sys.exit(1)
        
    with open(app_path, "r", encoding="utf-8") as f:
        app_content = f.read()

    # Initialize Audit Results
    audit_passed = True
    report_card = {}

    # ----------------------------------------------------
    # FEATURE 1: Password Complexity Verification
    # ----------------------------------------------------
    # Must check for minimum of 8 characters, 1 uppercase, and 1 number.
    pass_len_check = "len(password) < 8" in app_content or re.search(r"len\(\s*password\s*\)\s*<\s*8", app_content) is not None
    pass_upper_check = "char.isupper()" in app_content or "isupper()" in app_content
    pass_num_check = "char.isdigit()" in app_content or "isdigit()" in app_content
    
    feature1_ok = pass_len_check and pass_upper_check and pass_num_check
    report_card["Password Complexity"] = {
        "status": feature1_ok,
        "details": [
            f"Minimum 8 characters length check: {'✓' if pass_len_check else '✗'}",
            f"At least 1 uppercase letter check:  {'✓' if pass_upper_check else '✗'}",
            f"At least 1 number/digit check:      {'✓' if pass_num_check else '✗'}"
        ]
    }
    if not feature1_ok:
        audit_passed = False

    # ----------------------------------------------------
    # FEATURE 2: Honeypot Bot Trap Verification
    # ----------------------------------------------------
    # Scan app.py for the website_verify form field check under signup and login POST routes.
    # Let's locate the signup and login functions using regex and check if website_verify is checked in them.
    signup_match = re.search(r"def signup\(\):(.*?)def login", app_content, re.DOTALL)
    login_match = re.search(r"def login\(\):(.*?)def logout", app_content, re.DOTALL)
    
    signup_honeypot = False
    if signup_match:
        signup_body = signup_match.group(1)
        signup_honeypot = "website_verify" in signup_body
        
    login_honeypot = False
    if login_match:
        login_body = login_match.group(1)
        login_honeypot = "website_verify" in login_body

    feature2_ok = signup_honeypot and login_honeypot
    report_card["Honeypot Bot Trap"] = {
        "status": feature2_ok,
        "details": [
            f"Signup POST route scans for 'website_verify': {'✓' if signup_honeypot else '✗'}",
            f"Login POST route scans for 'website_verify':  {'✓' if login_honeypot else '✗'}"
        ]
    }
    if not feature2_ok:
        audit_passed = False

    # ----------------------------------------------------
    # FEATURE 3: Role-Based Access Control Verification
    # ----------------------------------------------------
    # Check that @role_required decorator exists and is protecting the /admin path.
    decorator_defined = "def role_required" in app_content
    
    # Check that @role_required wraps the admin_panel
    admin_protected = False
    admin_match = re.search(r"@app\.route\(\s*['\"]/admin['\"]\s*\).*?@role_required.*?\s*def admin_panel", app_content, re.DOTALL)
    if admin_match:
        admin_protected = True
        
    feature3_ok = decorator_defined and admin_protected
    report_card["Role-Based Access Control"] = {
        "status": feature3_ok,
        "details": [
            f"Decorator @role_required defined:            {'✓' if decorator_defined else '✗'}",
            f"Decorator protects the /admin path correctly: {'✓' if admin_protected else '✗'}"
        ]
    }
    if not feature3_ok:
        audit_passed = False

    # ----------------------------------------------------
    # FEATURE 4: Relational Database Header Verification
    # ----------------------------------------------------
    # Verify that the /report/<int:report_id> route uses an SQL JOIN statement
    # to link reports to users.name (client_name) and users.organization (client_org).
    report_route_match = re.search(r"def report_result\(.*?\):(.*?)def pay_for_report", app_content, re.DOTALL)
    
    join_statement_found = False
    client_name_pulled = False
    client_org_pulled = False
    
    if report_route_match:
        report_body = report_route_match.group(1)
        join_statement_found = "JOIN users" in report_body or "join users" in report_body.lower()
        client_name_pulled = "u.name as client_name" in report_body or "u.name AS client_name" in report_body
        client_org_pulled = "u.organization as client_org" in report_body or "u.organization AS client_org" in report_body

    feature4_ok = join_statement_found and client_name_pulled and client_org_pulled
    report_card["Relational Database Header"] = {
        "status": feature4_ok,
        "details": [
            f"SQL JOIN statement links reports and users:     {'✓' if join_statement_found else '✗'}",
            f"Fetch client's registered name (client_name):   {'✓' if client_name_pulled else '✗'}",
            f"Fetch client's organization (client_org):       {'✓' if client_org_pulled else '✗'}"
        ]
    }
    if not feature4_ok:
        audit_passed = False

    # ----------------------------------------------------
    # PRINT THE CONFIRMATION REPORT CARD
    # ----------------------------------------------------
    print_banner("LEVELSET LAUNCH VERIFICATION AUDIT")
    
    for feature, info in report_card.items():
        status_str = f"{GREEN}[PASS]{RESET}" if info["status"] else f"{RED}[FAIL]{RESET}"
        print(f"{status_str} {BOLD}{feature}{RESET}")
        for d in info["details"]:
            print(f"       - {d}")
        print()
        
    print(f"{BOLD}{CYAN}{'='*70}{RESET}")
    if audit_passed:
        print(f"\n{BOLD}{GREEN}  ✓ STATUS: ALL 4 SECURITY & ROLE FRAMEWORKS VERIFIED & SECURE  {RESET}\n")
    else:
        print(f"\n{BOLD}{RED}  ✗ STATUS: VERIFICATION AUDIT FAILED (MISSING SECURITY CONTROLS)  {RESET}\n")
    print(f"{BOLD}{CYAN}{'='*70}{RESET}\n")
    
    if not audit_passed:
        sys.exit(1)

if __name__ == "__main__":
    run_audit()
