"""
MCP Client for Dental Practice Management

This module provides a client interface to connect to the Dental MCP-style server
and use its tools within the main FastAPI application.
"""

import asyncio
import json
import httpx
from typing import Dict, List, Optional, Any
from dental_mcp_server import MCPServer, server as dental_server

# MCP Client class to manage connection and tool usage
class DentalMCPClient:
    def __init__(self, server_instance: MCPServer = None, server_url: str = None):
        self.server_instance = server_instance or dental_server
        self.server_url = server_url
        self.connected = True  # Always connected for in-memory server
        self.available_tools = {}
        self._update_available_tools()
    
    def _update_available_tools(self):
        """Update the available tools from the server"""
        if self.server_instance:
            self.available_tools = {
                name: self.server_instance.get_tool_definition(name) 
                for name in self.server_instance.get_available_tools()
            }
    
    async def connect(self) -> bool:
        """Connect to the dental MCP server (always returns True for in-memory server)"""
        if self.server_instance:
            self.connected = True
            self._update_available_tools()
            return True
        
        # If using HTTP connection, test connectivity
        if self.server_url:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{self.server_url}/status", timeout=10.0)
                    if response.status_code == 200:
                        self.connected = True
                        # Get tools from HTTP endpoint
                        tools_response = await client.get(f"{self.server_url}/tools", timeout=10.0)
                        if tools_response.status_code == 200:
                            tools_data = tools_response.json()
                            self.available_tools = {
                                tool["name"]: tool for tool in tools_data.get("tools", [])
                            }
                        return True
            except Exception as e:
                print(f"Failed to connect to HTTP MCP server: {str(e)}")
                self.connected = False
                return False
        
        return False
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool on the MCP server"""
        if not self.connected:
            return "Error: Not connected to MCP server"
        
        if tool_name not in self.available_tools:
            return f"Error: Tool '{tool_name}' not available. Available tools: {list(self.available_tools.keys())}"
        
        try:
            if self.server_instance:
                # Direct in-memory call
                result = await self.server_instance.call_tool(tool_name, arguments)
                if result.success:
                    return str(result.result)
                else:
                    return f"Error: {result.error}"
            
            elif self.server_url:
                # HTTP call
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.server_url}/call-tool",
                        json={"tool_name": tool_name, "arguments": arguments},
                        timeout=30.0
                    )
                    
                    if response.status_code == 200:
                        result_data = response.json()
                        if result_data.get("success"):
                            return str(result_data.get("result", ""))
                        else:
                            return f"Error: {result_data.get('error', 'Unknown error')}"
                    else:
                        return f"HTTP Error: {response.status_code}"
            
        except Exception as e:
            return f"Error calling tool '{tool_name}': {str(e)}"
    
    def get_available_tools(self) -> List[str]:
        """Get list of available tool names"""
        return list(self.available_tools.keys())
    
    def get_tool_info(self, tool_name: str) -> Optional[Dict]:
        """Get information about a specific tool"""
        if tool_name in self.available_tools:
            tool = self.available_tools[tool_name]
            if hasattr(tool, 'name'):
                # ToolDefinition object
                return {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters
                }
            else:
                # Dict from HTTP
                return tool
        return None

# Global MCP client instance (using in-memory server)
dental_mcp_client = DentalMCPClient()

# Convenience functions for common operations
async def find_patient_by_phone(phone_number: str) -> str:
    """Find patients by phone number using MCP"""
    return await dental_mcp_client.call_tool("find_patients_by_phone", {"phone_number": phone_number})

async def get_patient_appointments(patient_id: int, limit: int = 10) -> str:
    """Get patient appointments using MCP"""
    return await dental_mcp_client.call_tool("get_patient_appointments", {"patient_id": patient_id, "limit": limit})

async def get_available_appointment_slots(practice_id: int, start_date: str, end_date: str, visit_type_id: Optional[int] = None) -> str:
    """Get available appointment slots using MCP"""
    args = {
        "practice_id": practice_id,
        "start_date": start_date,
        "end_date": end_date
    }
    if visit_type_id:
        args["visit_type_id"] = visit_type_id
    
    return await dental_mcp_client.call_tool("get_available_slots", args)

async def get_practice_visit_types(practice_id: int) -> str:
    """Get visit types for a practice using MCP"""
    return await dental_mcp_client.call_tool("get_visit_types", {"practice_id": practice_id})

async def book_patient_appointment(
    patient_id: int,
    practice_id: int,
    provider_id: int,
    visit_type_id: int,
    appointment_date: str,
    start_time: str,
    notes: Optional[str] = None
) -> str:
    """Book an appointment using MCP"""
    args = {
        "patient_id": patient_id,
        "practice_id": practice_id,
        "provider_id": provider_id,
        "visit_type_id": visit_type_id,
        "appointment_date": appointment_date,
        "start_time": start_time
    }
    if notes:
        args["notes"] = notes
    
    return await dental_mcp_client.call_tool("book_appointment", args)

async def send_otp_verification(phone_number: str) -> str:
    """Send OTP verification using MCP"""
    return await dental_mcp_client.call_tool("request_otp", {"phone_number": phone_number})

# Function to check MCP server status
async def get_mcp_status() -> Dict[str, Any]:
    """Get the status of the MCP connection and available tools"""
    if not dental_mcp_client.connected:
        return {
            "connected": False,
            "error": "Not connected to MCP server",
            "available_tools": []
        }
    
    return {
        "connected": True,
        "available_tools": dental_mcp_client.get_available_tools(),
        "tool_count": len(dental_mcp_client.available_tools),
        "server_status": dental_mcp_client.server_instance.get_status() if dental_mcp_client.server_instance else None
    }

# Initialize the MCP client connection
async def initialize_mcp_client() -> bool:
    """Initialize the MCP client connection"""
    return await dental_mcp_client.connect()

# Alternative client for HTTP connections
class HTTPMCPClient(DentalMCPClient):
    def __init__(self, server_url: str):
        super().__init__(server_instance=None, server_url=server_url)
        self.connected = False 