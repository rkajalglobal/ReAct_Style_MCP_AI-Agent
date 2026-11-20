import os
import base64
import sys
from pathlib import Path
from email.message import EmailMessage

from dotenv import load_dotenv

from mcp.server.fastmcp import FastMCP

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from langchain.chat_models import init_chat_model
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.messages import SystemMessage, HumanMessage


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

mcp = FastMCP("Gmail MCP Server")

HERE = Path(__file__).resolve().parent

CREDENTIALS_FILE = HERE / "credentials.json"

TOKEN_FILE = HERE / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose"
]


# ============================================================
# GMAIL AUTHENTICATION
# ============================================================

def get_gmail_service():

    credentials = None

    if TOKEN_FILE.exists():

        credentials = Credentials.from_authorized_user_file(
            str(TOKEN_FILE),
            SCOPES
        )

    if not credentials or not credentials.valid:

        if credentials and credentials.expired and credentials.refresh_token:

            credentials.refresh(Request())

        else:

            if not CREDENTIALS_FILE.exists():

                raise FileNotFoundError(
                    "credentials.json was not found."
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE),
                SCOPES
            )

            credentials = flow.run_local_server(
                port=0,
                open_browser=True
            )

        TOKEN_FILE.write_text(
            credentials.to_json(),
            encoding="utf-8"
        )

    service = build(
        "gmail",
        "v1",
        credentials=credentials
    )

    return service


# ============================================================
# MCP TOOL 1: CREATE GMAIL DRAFT
# ============================================================

@mcp.tool()
def draft_email(
    recipient: str,
    subject: str,
    body: str
) -> dict:

    """
    Create an actual email draft in Gmail.

    This tool does not send the email.

    Returns the Gmail draft ID and the email content.
    """

    try:

        service = get_gmail_service()

        message = EmailMessage()

        message["To"] = recipient

        message["Subject"] = subject

        message.set_content(body)

        encoded_message = base64.urlsafe_b64encode(
            message.as_bytes()
        ).decode("utf-8")

        draft = service.users().drafts().create(
            userId="me",
            body={
                "message": {
                    "raw": encoded_message
                }
            }
        ).execute()

        return {
            "status": "draft_created",
            "draft_id": draft["id"],
            "recipient": recipient,
            "subject": subject,
            "body": body
        }

    except Exception as error:

        return {
            "status": "error",
            "message": str(error)
        }


# ============================================================
# MCP TOOL 2: SEND EXISTING GMAIL DRAFT
# ============================================================

@mcp.tool()
def send_email(
    draft_id: str
) -> dict:

    """
    Send an existing Gmail draft.

    The calling application must obtain human approval
    before invoking this tool.
    """

    try:

        service = get_gmail_service()

        result = service.users().drafts().send(
            userId="me",
            body={
                "id": draft_id
            }
        ).execute()

        return {
            "status": "sent",
            "message_id": result["id"],
            "thread_id": result.get("threadId"),
            "draft_id": draft_id
        }

    except Exception as error:

        return {
            "status": "error",
            "message": str(error)
        }


@mcp.tool()
async def get_weather_report(city: str) -> str:

    """
    Retrieve current weather and a three-day forecast
    from the Weather MCP server.
    """

    weather_server = os.path.join(
        os.path.dirname(__file__),
        "weather_server.py"
    )

    client = MultiServerMCPClient({

        "weather": {
            "command": sys.executable,
            "args": [weather_server],
            "transport": "stdio"
        }

    })

    tools = await client.get_tools()

    tool_map = {
        tool.name: tool
        for tool in tools
    }

    current = await tool_map["get_current_weather"].ainvoke({
        "city": city
    })

    forecast = await tool_map["get_forecast"].ainvoke({
        "city": city,
        "days": 3
    })

    return f"{current}\n\n{forecast}"


@mcp.tool()
async def improve_language(weather_report: str) -> str:

    """
    Improve the language of a weather report
    without changing the underlying weather information.
    """

    llm = init_chat_model("openai:gpt-4o-mini")

    response = await llm.ainvoke([

        SystemMessage(
            content=(
                "Improve the grammar and readability of "
                "the following weather report. "
                "Do not change temperatures, dates, "
                "wind speeds, humidity, or rain probabilities. "
                "Do not add new weather information. "
                "Return only the improved report."
            )
        ),

        HumanMessage(
            content=weather_report
        )

    ])

    return response.content


# ============================================================
# START MCP SERVER
# ============================================================

if __name__ == "__main__":

    mcp.run(transport="stdio")

