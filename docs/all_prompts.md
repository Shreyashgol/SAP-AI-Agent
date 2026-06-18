In the backend. where does the system prompt is written ??

In this backend, there isn't a single centralized file for system prompts. Instead, each individual agent or service module declares its own system prompt as a private uppercase constant at the module level and passes it directly when invoking the LLM.

Here is the complete list of where each system prompt is defined in the backend:

1. Agents (backend/app/agents/)

--- Intent Classifier Agent:
Defined in 
intent_classifier.py
 as _SYSTEM.
Purpose: Classifies the incoming question into lookup, aggregation, trend, comparative, RCA, document, or hybrid intents.
Context Agent:
Defined in 

--- context_agent.py
 as _CONTEXT_SYSTEM (line 145) and _CONVO_SYSTEM (line 99).
Purpose: _CONTEXT_SYSTEM resolves pronouns and references against history; _CONVO_SYSTEM handles direct conversational chat replies (small talk).
Query Planner Agent:
Defined in 

--- query_planner.py
 as _PARAM_SYSTEM.
Purpose: Matches parameters and binds schema requirements for selecting tool catalog functions.
Text-to-SQL Agent:
Defined in 

--- text_to_sql.py
 as _SYSTEM.
Purpose: Performs natural language to SQL translation when no predefined tool is matched.
RCA (Root Cause Analysis) Agent:
Defined in 

--- rca_agent.py
 as _RCA_SYSTEM.
Purpose: Performs variance analysis and narrative generation comparing current and prior period data.
Trend Agent:
Defined in 

--- trend_agent.py
 as _TREND_SYSTEM.
Purpose: Formulates trend analyses and forecasts from time-series metrics.
Document RAG Agent:
Defined in 

--- document_rag.py
 as _RAG_SYSTEM.
Purpose: Answers queries over uploaded documents using database/vector embeddings context.
Hybrid Agent:
Defined in 

--- hybrid_agent.py
 as _BLEND_SYSTEM.
Purpose: Merges and synthesizes SQL data results with document chunks/retrievals into a unified report.
Web Search Agent:
Defined in 

--- web_search.py
 as _WEB_SYSTEM.
Purpose: Guides web search reasoning and official source citation formatting.
Clarification Agent:
Defined in 

--- clarification_agent.py
 as _CLARIFICATION_SYSTEM.
Purpose: Formulates clear, friendly questions to request missing query parameters from the user.
Response Formatter Agent:
Defined in 

--- response_formatter.py
 as _NARRATIVE_SYSTEM (line 28) and _FOLLOWUP_SYSTEM (line 51).
Purpose: _NARRATIVE_SYSTEM shapes the final markdown analysis output; _FOLLOWUP_SYSTEM generates relevant next questions.


2. Services (backend/app/services/)
AI SQL Generator Service:
Defined in 

--- ai_generator.py
 as _SYSTEM_PROMPT.
Purpose: Creates custom analytical database tools.
AI Metadata Table/Column Mapper Service:
Defined in 

--- ai_mapper.py
 as _SYSTEM_PROMPT.
Purpose: Infers semantic business metadata descriptions, categories, and types for unknown tables.
Custom Tool Builder Service:
Defined in 

custom_builder.py
 as _SYSTEM_PROMPT.
Purpose: Translates user descriptions into parameterised SQL schemas and tools.
