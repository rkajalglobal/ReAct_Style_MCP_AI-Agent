1. How the Project Works

Step 1 — User Questions: The user submits questions about mathematics, weather, or current news.

Step 2 — ReAct-Style AI Agent: The LLM analyzes each question and automatically chooses the appropriate MCP tool.

Step 3 — Tool Execution: Math MCP performs calculations, Weather MCP retrieves data from Open-Meteo, and Tavily MCP searches the web.

Step 4 — Conditional Routing: LangGraph identifies which tools were executed. Only Math and Weather results qualify for email reporting.

Step 5 — Report Generation: Results from eligible questions are collected and combined into one report.

Step 6 — Language Improvement: GPT-4o-mini improves the report's grammar and readability while preserving the original data.

Step 7 — Gmail MCP: The Gmail MCP server creates one draft containing the combined report.

Step 8 — Human-in-the-Loop: The user reviews the email in CMD and enters yes or no.

Step 9 — Email Delivery: If approved, Gmail MCP sends the existing draft. Otherwise, it remains in Gmail Drafts.

2. Key Features
Dynamic tool selection: The LLM decides which MCP tools to call.
Multi-server integration: Connects Math, Weather, Tavily, and Gmail MCP servers.
LangGraph orchestration: Uses nodes, edges, conditional routing, and shared state.
Automated reporting: Combines Math and Weather results into a single email.
LLM-powered language improvement: Makes reports easier to read without intentionally changing factual data.
Human-in-the-Loop approval: Prevents email sending without explicit user confirmation.
Controlled tool access: Gmail drafting and sending are handled by workflow nodes rather than unrestricted LLM tool calls.

                         USER QUESTIONS
                               |
                               ▼
                    LANGGRAPH AI AGENT
                      (GPT-4o-mini)
                               |
                               ▼
                    LLM DECIDES WHICH
                       TOOL TO CALL
                               |
                ┌──────────────┼──────────────┐
                │              │              │
                ▼              ▼              ▼
           MATH MCP       WEATHER MCP     TAVILY SEARCH
           SERVER          SERVER          MCP SERVER
                │              │              │
                ▼              ▼              ▼
          Mathematical     Open-Meteo       Latest Web
          Calculations       API            Information
                │              │              │
                └──────┬───────┘              │
                       │                      │
                       ▼                      ▼
                COLLECT RESULTS           DISPLAY RESULT
                (Math + Weather)          (No Email)
                       │
                       ▼
                COMBINE RESULTS
                INTO ONE REPORT
                       │
                       ▼
                LLM LANGUAGE
                IMPROVEMENT NODE
                       │
                       ▼
                 GMAIL MCP SERVER
                       │
                       ▼
                 CREATE ONE DRAFT
                       │
                       ▼
               HUMAN-IN-THE-LOOP
                  (CMD Approval)
                       │
                ┌──────┴──────┐
                │             │
               YES            NO
                │             │
                ▼             ▼
           GMAIL MCP         END
           SEND EMAIL     (Keep Draft)
                │
                ▼
               END