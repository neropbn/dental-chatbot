"""
Dental Practice Management MCP-Style Server

This server provides tools for interacting with dental practice management systems,
implementing MCP-like patterns using standard Python libraries.
"""

import os
import httpx
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration from environment variables
PBN_APP_DOMAIN = os.getenv("PBN_APP_DOMAIN", "https://devtest.pbn-dev.com")
CHATBOT_AUTH_SECRET_KEY = os.getenv("CHATBOT_AUTH_SECRET_KEY", "")
ORGANIZATION_ID = os.getenv("ORGANIZATION_ID", "1")
DEFAULT_PRACTICE_IDS = os.getenv("DEFAULT_PRACTICE_IDS", "").split(",") if os.getenv("DEFAULT_PRACTICE_IDS") else []

# Authentication token storage
auth_token = None
token_expires_at = None

# Tool registry
tools_registry: Dict[str, Callable] = {}

class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]

class ToolResult(BaseModel):
    success: bool
    result: Any
    error: Optional[str] = None

def tool(name: str, description: str):
    """Decorator to register a tool function"""
    def decorator(func: Callable):
        tools_registry[name] = func
        func._tool_name = name
        func._tool_description = description
        return func
    return decorator

async def get_auth_token() -> Optional[str]:
    """Get or refresh authentication token for PBN API"""
    global auth_token, token_expires_at
    
    # Check if current token is still valid (with 1 hour buffer)
    if auth_token and token_expires_at and datetime.now() < token_expires_at - timedelta(hours=1):
        return auth_token
    
    # Need to get new token
    if not CHATBOT_AUTH_SECRET_KEY or not PBN_APP_DOMAIN:
        print(f"Missing credentials: AUTH_KEY={bool(CHATBOT_AUTH_SECRET_KEY)}, DOMAIN={bool(PBN_APP_DOMAIN)}")
        return None
    
    try:
        async with httpx.AsyncClient() as client:
            # Use the correct PBN authentication endpoint
            auth_url = f"{PBN_APP_DOMAIN}/chatbot/auth/authenticate/"
            
            # Use the correct payload format
            payload = {
                "key": CHATBOT_AUTH_SECRET_KEY,
                "organization_id": int(ORGANIZATION_ID)
            }
            
            print(f"Attempting authentication to: {auth_url}")
            print(f"With organization_id: {ORGANIZATION_ID}")
            
            response = await client.post(
                auth_url,
                json=payload,
                timeout=30.0,
                headers={"Content-Type": "application/json"}
            )
            
            print(f"Auth response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Auth response data: {data}")
                
                # Extract token from response (adjust field name based on actual response)
                auth_token = data.get("token") or data.get("access_token") or data.get("auth_token")
                
                if auth_token:
                    # Token expires in 24 hours
                    token_expires_at = datetime.now() + timedelta(hours=23)
                    print("✅ Authentication successful!")
                    return auth_token
                else:
                    print(f"❌ No token found in response: {data}")
                    return None
            else:
                print(f"❌ Authentication failed with status {response.status_code}: {response.text}")
                return None
                
    except Exception as e:
        print(f"❌ Error getting auth token: {str(e)}")
        return None

async def make_pbn_request(endpoint: str, method: str = "GET", params: Dict = None, data: Dict = None) -> Dict:
    """Make authenticated request to PBN API"""
    token = await get_auth_token()
    if not token:
        return {"error": "Authentication failed - unable to get access token"}
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Use the correct API base URL structure
    if endpoint.startswith("/api/"):
        url = f"{PBN_APP_DOMAIN}{endpoint}"
    else:
        url = f"{PBN_APP_DOMAIN}/api{endpoint}"
    
    print(f"Making request to: {url}")
    
    try:
        async with httpx.AsyncClient() as client:
            if method == "GET":
                response = await client.get(url, headers=headers, params=params, timeout=30.0)
            elif method == "POST":
                response = await client.post(url, headers=headers, json=data, timeout=30.0)
            else:
                return {"error": f"Unsupported HTTP method: {method}"}
            
            print(f"API response status: {response.status_code}")
            
            if response.status_code == 200:
                return response.json()
            else:
                error_msg = f"API request failed with status {response.status_code}: {response.text}"
                print(f"❌ {error_msg}")
                return {"error": error_msg}
                
    except Exception as e:
        error_msg = f"Request failed: {str(e)}"
        print(f"❌ {error_msg}")
        return {"error": error_msg}

@tool("find_patients_by_phone", "Find patients by their phone number")
async def find_patients_by_phone(phone_number: str) -> str:
    """
    Find patients by their phone number.
    
    Args:
        phone_number: The patient's phone number to search for
        
    Returns:
        Patient information including ID, name, and contact details
    """
    if not phone_number.strip():
        return "Error: Phone number is required"
    
    # Clean phone number (remove non-digit characters)
    clean_phone = ''.join(filter(str.isdigit, phone_number))
    
    params = {
        "phone": clean_phone,
        "organization_id": ORGANIZATION_ID
    }
    
    result = await make_pbn_request("/patients/search", params=params)
    
    if "error" in result:
        return f"Error searching for patients: {result['error']}"
    
    patients = result.get("data", [])
    if not patients:
        return f"No patients found with phone number {phone_number}"
    
    # Format patient information
    patient_info = []
    for patient in patients:
        info = f"Patient: {patient.get('first_name', '')} {patient.get('last_name', '')}"
        info += f"\nID: {patient.get('id', 'N/A')}"
        info += f"\nPhone: {patient.get('phone', 'N/A')}"
        info += f"\nEmail: {patient.get('email', 'N/A')}"
        patient_info.append(info)
    
    return f"Found {len(patients)} patient(s):\n\n" + "\n\n".join(patient_info)

@tool("get_patient_appointments", "Get appointments for a specific patient")
async def get_patient_appointments(patient_id: int, limit: int = 10) -> str:
    """
    Get appointments for a specific patient.
    
    Args:
        patient_id: The patient's ID
        limit: Maximum number of appointments to return (default: 10)
        
    Returns:
        List of patient appointments with dates, times, and status
    """
    params = {
        "patient_id": patient_id,
        "limit": limit
    }
    
    result = await make_pbn_request("/appointments", params=params)
    
    if "error" in result:
        return f"Error getting appointments: {result['error']}"
    
    appointments = result.get("data", [])
    if not appointments:
        return f"No appointments found for patient ID {patient_id}"
    
    # Format appointment information
    appointment_info = []
    for apt in appointments:
        info = f"Date: {apt.get('appointment_date', 'N/A')}"
        info += f"\nTime: {apt.get('start_time', 'N/A')} - {apt.get('end_time', 'N/A')}"
        info += f"\nStatus: {apt.get('status', 'N/A')}"
        info += f"\nProvider: {apt.get('provider_name', 'N/A')}"
        info += f"\nVisit Type: {apt.get('visit_type', 'N/A')}"
        appointment_info.append(info)
    
    return f"Found {len(appointments)} appointment(s) for patient ID {patient_id}:\n\n" + "\n\n".join(appointment_info)

@tool("get_available_slots", "Get available appointment slots for a practice")
async def get_available_slots(
    practice_id: int,
    start_date: str,
    end_date: str,
    visit_type_id: Optional[int] = None
) -> str:
    """
    Get available appointment slots for a practice.
    
    Args:
        practice_id: The practice ID to check availability for
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        visit_type_id: Optional visit type ID to filter slots
        
    Returns:
        List of available appointment slots with dates and times
    """
    params = {
        "practice_id": practice_id,
        "start_date": start_date,
        "end_date": end_date
    }
    
    if visit_type_id:
        params["visit_type_id"] = visit_type_id
    
    result = await make_pbn_request("/appointments/available-slots", params=params)
    
    if "error" in result:
        return f"Error getting available slots: {result['error']}"
    
    slots = result.get("data", [])
    if not slots:
        return f"No available slots found for practice {practice_id} between {start_date} and {end_date}"
    
    # Format slot information
    slot_info = []
    for slot in slots:
        info = f"Date: {slot.get('date', 'N/A')}"
        info += f"\nTime: {slot.get('start_time', 'N/A')} - {slot.get('end_time', 'N/A')}"
        info += f"\nProvider: {slot.get('provider_name', 'N/A')}"
        info += f"\nDuration: {slot.get('duration_minutes', 'N/A')} minutes"
        slot_info.append(info)
    
    # Group by date for better readability
    from collections import defaultdict
    slots_by_date = defaultdict(list)
    for i, slot in enumerate(slots):
        date = slot.get('date', 'N/A')
        slots_by_date[date].append(slot_info[i])
    
    formatted_output = []
    for date, date_slots in slots_by_date.items():
        formatted_output.append(f"**{date}**\n" + "\n\n".join(date_slots))
    
    return f"Found {len(slots)} available slot(s):\n\n" + "\n\n".join(formatted_output)

@tool("get_visit_types", "Get available visit types for a practice")
async def get_visit_types(practice_id: int) -> str:
    """
    Get available visit types for a practice.
    
    Args:
        practice_id: The practice ID to get visit types for
        
    Returns:
        List of available visit types with their details
    """
    params = {"practice_id": practice_id}
    
    result = await make_pbn_request("/visit-types", params=params)
    
    if "error" in result:
        return f"Error getting visit types: {result['error']}"
    
    visit_types = result.get("data", [])
    if not visit_types:
        return f"No visit types found for practice {practice_id}"
    
    # Format visit type information
    visit_type_info = []
    for vt in visit_types:
        info = f"Name: {vt.get('name', 'N/A')}"
        info += f"\nID: {vt.get('id', 'N/A')}"
        info += f"\nDuration: {vt.get('duration_minutes', 'N/A')} minutes"
        info += f"\nDescription: {vt.get('description', 'N/A')}"
        visit_type_info.append(info)
    
    return f"Found {len(visit_types)} visit type(s):\n\n" + "\n\n".join(visit_type_info)

@tool("book_appointment", "Book an appointment for a patient")
async def book_appointment(
    patient_id: int,
    practice_id: int,
    provider_id: int,
    visit_type_id: int,
    appointment_date: str,
    start_time: str,
    notes: Optional[str] = None
) -> str:
    """
    Book an appointment for a patient.
    
    Args:
        patient_id: The patient's ID
        practice_id: The practice ID
        provider_id: The provider's ID
        visit_type_id: The visit type ID
        appointment_date: Date in YYYY-MM-DD format
        start_time: Start time in HH:MM format
        notes: Optional appointment notes
        
    Returns:
        Confirmation of the booked appointment
    """
    data = {
        "patient_id": patient_id,
        "practice_id": practice_id,
        "provider_id": provider_id,
        "visit_type_id": visit_type_id,
        "appointment_date": appointment_date,
        "start_time": start_time
    }
    
    if notes:
        data["notes"] = notes
    
    result = await make_pbn_request("/appointments", method="POST", data=data)
    
    if "error" in result:
        return f"Error booking appointment: {result['error']}"
    
    appointment = result.get("data", {})
    
    return f"Appointment successfully booked!\n" \
           f"Appointment ID: {appointment.get('id', 'N/A')}\n" \
           f"Date: {appointment.get('appointment_date', 'N/A')}\n" \
           f"Time: {appointment.get('start_time', 'N/A')}\n" \
           f"Status: {appointment.get('status', 'N/A')}"

@tool("request_otp", "Request OTP verification for a phone number")
async def request_otp(phone_number: str) -> str:
    """
    Request OTP verification for a phone number.
    
    Args:
        phone_number: The phone number to send OTP to
        
    Returns:
        Confirmation that OTP was sent
    """
    # Clean phone number
    clean_phone = ''.join(filter(str.isdigit, phone_number))
    
    data = {
        "phone": clean_phone,
        "organization_id": ORGANIZATION_ID
    }
    
    result = await make_pbn_request("/auth/send-otp", method="POST", data=data)
    
    if "error" in result:
        return f"Error sending OTP: {result['error']}"
    
    return f"OTP has been sent to {phone_number}. Please provide the code to verify your identity."

# MCP-like server interface
class MCPServer:
    def __init__(self, name: str):
        self.name = name
        self.tools = tools_registry
    
    def get_available_tools(self) -> List[str]:
        """Get list of available tool names"""
        return list(self.tools.keys())
    
    def get_tool_definition(self, tool_name: str) -> Optional[ToolDefinition]:
        """Get tool definition"""
        if tool_name not in self.tools:
            return None
        
        func = self.tools[tool_name]
        return ToolDefinition(
            name=tool_name,
            description=getattr(func, '_tool_description', ''),
            parameters={}  # Could be enhanced with function signature inspection
        )
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """Call a tool with given arguments"""
        if tool_name not in self.tools:
            return ToolResult(
                success=False,
                result=None,
                error=f"Tool '{tool_name}' not found"
            )
        
        try:
            func = self.tools[tool_name]
            if asyncio.iscoroutinefunction(func):
                result = await func(**arguments)
            else:
                result = func(**arguments)
            
            return ToolResult(
                success=True,
                result=result,
                error=None
            )
        except Exception as e:
            return ToolResult(
                success=False,
                result=None,
                error=str(e)
            )
    
    def get_status(self) -> Dict[str, Any]:
        """Get server status"""
        config_status = {
            "pbn_domain_configured": bool(PBN_APP_DOMAIN),
            "auth_key_configured": bool(CHATBOT_AUTH_SECRET_KEY),
            "organization_id_configured": bool(ORGANIZATION_ID),
            "default_practices_configured": bool(DEFAULT_PRACTICE_IDS),
            "auth_token_active": bool(auth_token and token_expires_at and datetime.now() < token_expires_at)
        }
        
        return {
            "server": f"Dental Practice Management MCP Server - {self.name}",
            "status": "running",
            "tools_available": len(self.tools),
            "available_tools": list(self.tools.keys()),
            "configuration": config_status,
            "last_updated": datetime.now().isoformat()
        }

# Create server instance
server = MCPServer("Dental Practice Management")

# FastAPI app for HTTP interface (optional)
app = FastAPI(title="Dental MCP Server", description="MCP-style server for dental practice management")

@app.get("/status")
async def get_status():
    """Get server status"""
    return server.get_status()

@app.get("/tools")
async def list_tools():
    """List available tools"""
    return {
        "tools": [
            {
                "name": name,
                "description": getattr(func, '_tool_description', '')
            }
            for name, func in server.tools.items()
        ]
    }

class ToolCallRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]

@app.post("/call-tool")
async def call_tool_endpoint(request: ToolCallRequest):
    """Call a tool via HTTP"""
    result = await server.call_tool(request.tool_name, request.arguments)
    return result

if __name__ == "__main__":
    print(f"Starting {server.name}")
    print(f"Available tools: {server.get_available_tools()}")
    print(f"Server status: {server.get_status()}")
    
    # You can run this as a FastAPI server
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001) 