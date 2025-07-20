
from app.mcp.server import register_tool
from app.services.salesforce import get_salesforce_connection
from datetime import date, timedelta
import json
import logging
from typing import Dict, List, Optional, Any

# Configure logging
logger = logging.getLogger(__name__)

# --- INTERNAL HELPER FUNCTIONS (Not exposed as tools) ---

def _find_user_id(sf: Any, username: str) -> Optional[str]:
    """Finds a user's ID based on their username."""
    try:
        result = sf.query(f"SELECT Id FROM User WHERE Username = '{username}' AND IsActive = true LIMIT 1")
        if result['totalSize'] > 0:
            return result['records'][0]['Id']
    except Exception as e:
        logger.error(f"Error finding user '{username}': {e}")
    return None

def _find_profile_id(sf: Any, profile_name: str) -> Optional[str]:
    """Finds a profile's ID based on its name."""
    try:
        result = sf.query(f"SELECT Id FROM Profile WHERE Name = '{profile_name}' LIMIT 1")
        if result['totalSize'] > 0:
            return result['records'][0]['Id']
    except Exception as e:
        logger.error(f"Error finding profile '{profile_name}': {e}")
    return None

def _find_permission_set_ids(sf: Any, ps_names: List[str]) -> List[str]:
    """Finds Permission Set IDs based on a list of names."""
    if not ps_names:
        return []
    
    # Format names for the IN clause
    formatted_names = ','.join([f"'{name}'" for name in ps_names])
    try:
        result = sf.query(f"SELECT Id FROM PermissionSet WHERE Name IN ({formatted_names})")
        return [record['Id'] for record in result['records']]
    except Exception as e:
        logger.error(f"Error finding permission sets '{ps_names}': {e}")
    return []


# --- CORE SALESFORCE ADMIN TOOLS ---

@register_tool
def get_user_details(username: str) -> str:
    """
    Retrieves detailed information about a specific Salesforce user.
    Args:
        username: The full username of the user to look up (e.g., 'admin@myorg.com').
    Returns:
        A formatted string with user details or an error message.
    """
    sf = get_salesforce_connection()
    if not isinstance(sf, object): return sf

    try:
        query = f"""
        SELECT Name, Username, Email, Profile.Name, IsActive, UserType, LastLoginDate
        FROM User
        WHERE Username = '{username}'
        LIMIT 1
        """
        result = sf.query(query)
        if result['totalSize'] == 0:
            return f"❌ User Not Found: No active user found with username '{username}'."
        
        user = result['records'][0]
        details = f"""✅ User Details Found:
• Name: {user['Name']}
• Username: {user['Username']}
• Email: {user['Email']}
• Profile: {user['Profile']['Name']}
• Is Active: {user['IsActive']}
• User Type: {user['UserType']}
• Last Login: {user.get('LastLoginDate', 'Never')}
"""
        return details
    except Exception as e:
        logger.error(f"Failed to get user details for {username}: {e}")
        return f"❌ Error retrieving details for user '{username}': {e}"

@register_tool
def create_salesforce_user(first_name: str, last_name: str, email: str, username: str, profile_name: str, alias: Optional[str] = None) -> str:
    """
    Creates a new user in Salesforce with a specific profile.
    Args:
        first_name: The user's first name.
        last_name: The user's last name.
        email: The user's email address.
        username: The desired username, must be unique and in email format.
        profile_name: The exact name of the profile to assign to the user.
        alias: A short alias for the user (8 characters max). If not provided, one will be generated.
    Returns:
        Success message with the new User ID or a detailed error message.
    """
    sf = get_salesforce_connection()
    if not isinstance(sf, object): return sf

    profile_id = _find_profile_id(sf, profile_name)
    if not profile_id:
        return f"❌ Profile Not Found: Could not find a profile named '{profile_name}'. Please check the name and try again."

    if not alias:
        alias = (first_name[:1] + last_name[:7]).lower()

    user_data = {
        'FirstName': first_name,
        'LastName': last_name,
        'Email': email,
        'Username': username,
        'Alias': alias,
        'ProfileId': profile_id,
        'TimeZoneSidKey': 'America/Los_Angeles', # A default value is required
        'LocaleSidKey': 'en_US', # A default value is required
        'EmailEncodingKey': 'UTF-8', # A default value is required
        'LanguageLocaleKey': 'en_US' # A default value is required
    }

    try:
        logger.info(f"Attempting to create user: {username}")
        result = sf.User.create(user_data)
        if result.get('success'):
            user_id = result.get('id')
            return f"✅ User '{username}' created successfully with ID: {user_id}. An activation email has been sent."
        else:
            errors = result.get('errors', [])
            error_details = '; '.join([err.get('message', 'Unknown error') for err in errors])
            return f"❌ User Creation Failed for '{username}'. Errors: {error_details}"
    except Exception as e:
        logger.error(f"Exception during user creation for {username}: {e}")
        return f"❌ An exception occurred while creating user '{username}': {e}"

@register_tool
def assign_permission_sets_to_user(username: str, permission_set_names: List[str]) -> str:
    """
    Assigns one or more permission sets to a user. Use this AFTER a user has been created.
    Args:
        username: The username of the user to whom the permission sets will be assigned.
        permission_set_names: A list of the exact names of the permission sets to assign.
    Returns:
        A summary of the assignment results.
    """
    sf = get_salesforce_connection()
    if not isinstance(sf, object): return sf

    user_id = _find_user_id(sf, username)
    if not user_id:
        return f"❌ User Not Found: Could not find an active user with username '{username}'."

    ps_ids = _find_permission_set_ids(sf, permission_set_names)
    if not ps_ids:
        return f"❌ Permission Sets Not Found: None of the specified permission sets could be found: {permission_set_names}."

    assignments = []
    for ps_id in ps_ids:
        assignments.append({'AssigneeId': user_id, 'PermissionSetId': ps_id})

    try:
        logger.info(f"Assigning {len(assignments)} permission sets to user {username}")
        # The API for this is bulk-friendly, but we call it like this for simplicity.
        # For true bulk, simple-salesforce's `bulk.PermissionSetAssignment.insert()` would be used.
        results = [sf.PermissionSetAssignment.create(assignment) for assignment in assignments]
        
        success_count = sum(1 for r in results if r.get('success'))
        failed_count = len(results) - success_count
        
        if failed_count > 0:
            errors = [err.get('message') for r in results if not r.get('success') for err in r.get('errors', [])]
            return f" partial success: {success_count} assigned, {failed_count} failed. Errors: {'; '.join(errors)}"
        
        return f"✅ Successfully assigned {success_count} permission sets to user '{username}'."
    except Exception as e:
        logger.error(f"Failed to assign permission sets to {username}: {e}")
        return f"❌ An exception occurred during permission set assignment: {e}"

@register_tool
def deactivate_salesforce_user(username_to_deactivate: str, replacement_username: str) -> str:
    """
    Deactivates a user and reassigns all their owned Accounts, Contacts, Leads, and Opportunities to another active user. This is a critical, multi-step process.
    Args:
        username_to_deactivate: The username of the user to deactivate.
        replacement_username: The username of the active user who will receive ownership of the records.
    Returns:
        A detailed summary of the deactivation and reassignment process.
    """
    sf = get_salesforce_connection()
    if not isinstance(sf, object): return sf

    if username_to_deactivate.lower() == replacement_username.lower():
        return "❌ Error: The user to deactivate cannot be the same as the replacement user."

    user_to_deactivate_id = _find_user_id(sf, username_to_deactivate)
    if not user_to_deactivate_id:
        return f"❌ User to Deactivate Not Found: Could not find an active user with username '{username_to_deactivate}'."

    replacement_user_id = _find_user_id(sf, replacement_username)
    if not replacement_user_id:
        return f"❌ Replacement User Not Found: Could not find an active user with username '{replacement_username}'."

    summary = [f"🚀 Starting deactivation process for '{username_to_deactivate}'..."]
    total_reassigned = 0

    objects_to_reassign = ['Account', 'Contact', 'Lead', 'Opportunity']
    try:
        for sObject in objects_to_reassign:
            logger.info(f"Querying for {sObject} records owned by {username_to_deactivate}")
            query = f"SELECT Id FROM {sObject} WHERE OwnerId = '{user_to_deactivate_id}'"
            records_to_update = sf.query_all(query).get('records', [])
            
            if not records_to_update:
                summary.append(f"⚪ No {sObject} records found for reassignment.")
                continue

            record_count = len(records_to_update)
            total_reassigned += record_count
            logger.info(f"Found {record_count} {sObject} records to reassign.")

            # Prepare for bulk update
            update_payload = [{'Id': rec['Id'], 'OwnerId': replacement_user_id} for rec in records_to_update]
            
            # Use the bulk API for efficiency
            results = sf.bulk.__getattr__(sObject).update(update_payload)
            
            success_count = sum(1 for r in results if r.get('success'))
            if success_count == record_count:
                summary.append(f"✅ Successfully reassigned {record_count} {sObject} records to '{replacement_username}'.")
            else:
                summary.append(f" partial reassignment for {sObject}: {success_count}/{record_count} succeeded.")

        # Finally, deactivate the user
        logger.info(f"Deactivating user {username_to_deactivate}")
        update_result = sf.User.update(user_to_deactivate_id, {'IsActive': False})

        if update_result.get('success', True): # Note: simple-salesforce update returns status_code 204 on success, no body
             summary.append(f"✅ User '{username_to_deactivate}' has been successfully deactivated.")
        else:
             errors = update_result.get('errors', ['Unknown error'])
             summary.append(f"❌ CRITICAL ERROR: Record reassignment may have completed, but failed to deactivate user '{username_to_deactivate}'. Errors: {errors}")

    except Exception as e:
        logger.error(f"Exception during deactivation of {username_to_deactivate}: {e}")
        summary.append(f"❌ An unexpected error occurred during the deactivation process: {e}")

    return "\n".join(summary)


@register_tool
def reset_user_password(username: str) -> str:
    """
    Resets the password for a specified user, triggering a password reset email.
    Args:
        username: The username of the user whose password needs to be reset.
    Returns:
        A confirmation message or an error.
    """
    sf = get_salesforce_connection()
    if not isinstance(sf, object): return sf

    user_id = _find_user_id(sf, username)
    if not user_id:
        return f"❌ User Not Found: Could not find an active user with username '{username}'."

    try:
        # The password reset is done via the Connection object, not a standard DML
        sf.user.password_reset(user_id)
        return f"✅ Password reset initiated for user '{username}'. They will receive an email to set a new password."
    except Exception as e:
        logger.error(f"Password reset failed for {username}: {e}")
        return f"❌ Password reset failed for user '{username}'. Error: {e}"


# --- EXISTING TOOLS (Kept for compatibility and general use) ---
# Note: These are simplified for brevity. The original file had more detailed versions.

@register_tool
def execute_soql_query(soql_query: str) -> str:
    """
    Executes a Salesforce Object Query Language (SOQL) query to retrieve data. Use this for complex questions, filtering (WHERE), sorting (ORDER BY), and limiting (LIMIT) results.
    Args:
        soql_query: Complete, valid SOQL query string to execute.
    Returns:
        Formatted results with record count and data, or a detailed error message.
    """
    sf = get_salesforce_connection()
    if not isinstance(sf, object): return sf
    try:
        result = sf.query_all(soql_query)
        records = result.get('records', [])
        if not records:
            return "No records found."
        # Simple formatting for this example
        return json.dumps(records, indent=2, default=str)
    except Exception as e:
        return f"❌ SOQL Query Error: {e}"

@register_tool
def get_account_details(account_name: str) -> str:
    """
    Retrieves details for a single Salesforce Account by its exact name.
    Args:
        account_name: Exact name of the account to look up.
    Returns:
        Formatted account details or a 'not found' message.
    """
    return execute_soql_query(f"SELECT Id, Name, Industry, AnnualRevenue, Owner.Name FROM Account WHERE Name = '{account_name}' LIMIT 1")
