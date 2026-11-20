import asyncio
import os
import sys
import json
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import START, MessagesState, StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph.message import add_messages
from typing import TypedDict, Annotated

load_dotenv()  

MODEL = "openai:gpt-4o-mini"

HERE = os.path.dirname(os.path.abspath(__file__))
MATH_SERVER = os.path.join(HERE, "math_server.py")
WEATHER_SERVER = os.path.join(HERE, "weather_server.py")
GMAIL_SERVER = os.path.join(HERE, "gmail_server.py")

RECIPIENT_EMAIL = "msruchikajal@gmail.com"

# =====================================================
# 1. CONFIGURE MCP SERVERS
# =====================================================

def build_server_config() -> dict:
    """Describe every MCP server the agent should connect to."""
    servers = {
        
        "beginner_tools": {
            "command": sys.executable,
            "args": [MATH_SERVER],
            "transport": "stdio",
        },
        
        "weather": {
            "command": sys.executable,
            "args": [WEATHER_SERVER],
            "transport": "stdio",
        },

            "gmail": {
        "command": sys.executable,
        "args": [GMAIL_SERVER],
        "transport": "stdio",
        }
    }

  
    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key:
        servers["tavily"] = {
            "url": f"https://mcp.tavily.com/mcp/?tavilyApiKey={tavily_key}",
            "transport": "streamable_http",
        }
        
    else:
        print("TAVILY_API_KEY not set - running without web search.")

    return servers


# =====================================================
# 2. SYSTEM INSTRUCTIONS
# =====================================================

SYSTEM_PROMPT = """
You are an AI assistant connected to multiple MCP servers.

Select the appropriate MCP tools based on the user's question.

For mathematics:
Use the math MCP tools.

For weather:
Use the weather MCP tools.

For web searches:
Use Tavily when available.

For email requests:

1. Retrieve the requested information using the appropriate MCP tools.
2. Use the actual tool output.
3. Improve only the language and readability using improve_language.
4. Do not change numerical values or invent information.
5. Create a Gmail draft using draft_email.
6. Never send an email yourself.
7. Human approval is required before sending.

Only create an email draft when the user requests an email.
"""

IMPROVE_PROMPT = """
Improve the grammar, clarity, and readability of this report.

Organize the report into clear sections.

The report may contain:
- Mathematical calculations
- Weather information

Preserve all numerical values, calculations, units,
weather measurements, dates, and factual information.

Do not invent information.
Do not remove important information.

Return only the improved report.
"""

# =====================================================
# 3. LANGGRAPH STATE
# =====================================================

class AgentState(TypedDict, total=False):

    messages: Annotated[list, add_messages]
    question_index: int
    reports: list[str]
    recipient: str
    subject: str
    email_body: str
    draft_id: str
    approved: bool
    email_status: str



# =====================================================
# 4. MCP RESULT PARSER
# =====================================================

def parse_tool_result(result):

    if isinstance(result, dict):
        return result

    if isinstance(result, str):
        return json.loads(result)

    if isinstance(result, list):

        for item in result:

            if isinstance(item, dict):

                if item.get("type") == "text":
                    return json.loads(item["text"])

    raise ValueError(
        f"Unable to parse MCP tool result: {result}"
    )


# =====================================================
# 3. HUMAN APPROVAL FUNCTION
# =====================================================

async def human_approval(state):

    print("\n========== EMAIL PREVIEW ==========")
    print("To:", state["recipient"])
    print("Subject:", state["subject"])
    print("\n", state["email_body"])
    print("===================================")

   
    while True:

        answer = input(
            "\nDo you approve sending this email? (yes/no): "
        ).strip().lower()

        if answer in ("yes", "y"):
            return True

        if answer in ("no", "n"):
            return False

        print("Please enter yes or no.")


# =====================================================
# 5. MAIN FUNCTION
# =====================================================

async def main():
    
    client = MultiServerMCPClient(build_server_config())
    tools = await client.get_tools()
    
    print("Tools loaded from MCP:", [t.name for t in tools])

    tool_map = {t.name: t for t in tools}

    print("\nLoaded MCP tools:")
    print(list(tool_map.keys()))

    gmail_tool_names = {
        "draft_email",
        "send_email",
        "improve_language",
        "get_weather_report",
    }

    # Gmail tools are executed only by dedicated graph nodes.
    agent_tools = [
        t for t in tools
        if t.name not in gmail_tool_names
    ]

    # Names of tools provided by the Weather MCP server.
    weather_tools = {
        "get_current_weather",
        "get_forecast"
    }

    # Replace these with the actual names in math_server.py.
    math_tools = {
        "add",
        "multiply",
        "current_time"
    }

    eligible_tools = weather_tools | math_tools

    llm = init_chat_model(MODEL)
    llm_with_tools = llm.bind_tools(agent_tools)

    async def agent_node(state: AgentState):
        response = await llm_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}


   # -------------------------------------------------
    # NODE 2: COLLECT ELIGIBLE REPORT
    # -------------------------------------------------

    def collect_node(state: AgentState):

        used_tools = set()

        for message in state["messages"]:

            if message.type == "tool":
                used_tools.add(message.name)

        reports = list(state.get("reports", []))

        if used_tools & eligible_tools:

            answer = state["messages"][-1].content

            if not isinstance(answer, str):
                answer = str(answer)

            reports.append(answer)

            print(
                "\nMath/Weather report collected "
                "for the combined email."
            )

        else:

            print(
                "\nNo Math/Weather tool used. "
                "Answer excluded from email."
            )

        return {
            "reports": reports
        }
    

    # =================================================
    # NODE 2: IMPROVE LANGUAGE
    # =================================================

    async def improve_node(state: AgentState):
        combined_report = "\n\n".join(
            state["reports"]
        )
        response = await llm.ainvoke([
            SystemMessage(
                content=( IMPROVE_PROMPT
            )),
            HumanMessage(content=combined_report)
        ])
        return {"email_body": response.content}

    
    # =================================================
    # NODE 3: CREATE GMAIL DRAFT
    # =================================================

    async def draft_node(state: AgentState):

        result = await tool_map["draft_email"].ainvoke({
            "recipient": state["recipient"],
            "subject": state["subject"],
            "body": state["email_body"]
        })

        draft = parse_tool_result(result)

        if draft.get("status") != "draft_created":

            raise RuntimeError(
                f"Gmail draft creation failed: {draft}"
            )

        print(
            "\nGmail draft successfully created."
        )

        print(
            "Draft ID:",
            draft["draft_id"]
        )

        return {
            "draft_id": draft["draft_id"],
            "email_status": "draft_created",
        }


    # =================================================
    # NODE 4: HUMAN APPROVAL
    # =================================================

    async def approval_node(state: AgentState):

        approved = await human_approval(state)

        return {"approved": approved}


    # =================================================
    # NODE 5: SEND EMAIL
    # =================================================

    async def send_node(state: AgentState):

        result = await tool_map["send_email"].ainvoke({
            "draft_id": state["draft_id"]
        })

        send_result = parse_tool_result(result)

        if send_result.get("status") != "sent":

            raise RuntimeError(
                f"Email sending failed: {send_result}"
            )

        print("\nEmail sent successfully.")

        return {
            "email_status": "sent"
        }

        # print("\nEmail result:", result)

        # return {}

    # =================================================
    # CONDITIONAL ROUTING
    # =================================================

    def route_agent(state: AgentState):

        last_message = state["messages"][-1]

        if getattr(last_message, "tool_calls", None):
            return "tools"

        return "collect"

    def route_reports(state: AgentState):

        if state.get("reports"):
            return "improve"

        return "end"

    def route_approval(state: AgentState):

        if state.get("approved", False) is True:
            return "send"

        return "end"


    # =================================================
    # BUILD QUESTION LANGGRAPH
    # =================================================

    question_graph = StateGraph(AgentState)

    question_graph.add_node("agent", agent_node)
    question_graph.add_node("tools", ToolNode(agent_tools))
    question_graph.add_node("collect", collect_node)

    question_graph.add_edge(START, "agent")

    question_graph.add_conditional_edges(
    "agent",
    route_agent,
    {"tools": "tools", "collect": "collect"}
)

    question_graph.add_edge("tools", "agent")
    question_graph.add_edge("collect", END)

    question_app = question_graph.compile()


    # =================================================
    # BUILD EMAIL LANGGRAPH
    # =================================================
   
    email_graph = StateGraph(AgentState)

    email_graph.add_node("check_reports", lambda state: {})
    email_graph.add_node("improve", improve_node)
    email_graph.add_node("draft", draft_node)
    email_graph.add_node("approval", approval_node)
    email_graph.add_node("send", send_node)

    email_graph.add_edge(START, "check_reports")

    email_graph.add_conditional_edges(
    "check_reports",
    route_reports,
    {"improve": "improve", "end": END}
)

    email_graph.add_edge("improve", "draft")
    email_graph.add_edge("draft", "approval")

    email_graph.add_conditional_edges(
         "approval",
         route_approval,
         {"send": "send", "end": END}
        )

    email_graph.add_edge("send", END)

    email_app = email_graph.compile()
    




    
    questions = [
        "What is (30 + 560) multiplied by 1200? Also, what time is it right now?",
        "What's the weather in Houston right now, and will it rain there in the next 3 days?",
        "Search the web: what are the latest updates in AI this month?",
    ]
    
    reports = []

    for question in questions:
        print("\n" + "=" * 70)
        result = await question_app.ainvoke({"messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question}
            ],
              "reports": [],
           })
                      
        for message in result["messages"]:
            message.pretty_print()
        
        reports.extend(
            result.get("reports", [])
        )

    if reports:

        await email_app.ainvoke({
            "reports": reports,
            "recipient": RECIPIENT_EMAIL,
            "subject": "Math and Weather Report",
        })
    else:
        print(
            "\nNo Math or Weather reports collected. "
            "No email created."
        )
    

if __name__ == "__main__":
    asyncio.run(main())