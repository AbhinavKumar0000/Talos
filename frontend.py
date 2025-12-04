import streamlit as st
import uuid
import asyncio
import backend as bk 
from dotenv import load_dotenv
import os

load_dotenv()

st.set_page_config(page_title="Agentic Chatbot (MCP + RAG)", layout="wide")

# Session State Initialization
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

# Sidebar for RAG
with st.sidebar:
    st.header("Extra Knowledge Base")
    uploaded_file = st.file_uploader("Upload PDF Context", type=["pdf"])
    
    if uploaded_file and st.session_state.get("last_uploaded") != uploaded_file.name:
        with st.spinner("Ingesting PDF to Cloud..."):
            bk.ingest_pdf(uploaded_file.read(), st.session_state.thread_id, uploaded_file.name)
            st.session_state.last_uploaded = uploaded_file.name
            st.success("PDF Indexed to Pinecone!")

# Main Chat Interface
st.title("MCP + RAG Agent")
st.caption("Powered by Gemini 2.0 Flash & LangGraph")

# Display History
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.chat_message("user").write(msg["content"])
    elif msg["role"] == "assistant":
        st.chat_message("assistant").write(msg["content"])
    elif msg["role"] == "tool":
        with st.chat_message("assistant"):
            with st.status(f"Tool Output: {msg['name']}", state="complete"):
                st.code(msg["content"])

# --- Core Async Logic ---
async def run_chat(prompt):
    # 1. Build Graph
    with st.spinner("Connecting to Agent..."):
        try:
            chatbot = await bk.build_graph()
        except Exception as e:
            st.error(f"Backend connection failed: {e}")
            return None

    config = {"configurable": {"thread_id": st.session_state.thread_id}}
    
    final_response_content = None

    # 2. Stream Events (Let the loop finish!)
    async for event in chatbot.astream(
        {"messages": [("user", prompt)]}, 
        config=config, 
        stream_mode="values"
    ):
        if "messages" in event:
            current_message = event["messages"][-1]
            
            # Case A: AI calls a tool
            if current_message.type == "ai" and current_message.tool_calls:
                for tool_call in current_message.tool_calls:
                    with st.status(f"Calling: {tool_call['name']}", state="running") as status:
                        st.write(f"Args: {tool_call['args']}")
                        status.update(label=f"Completed: {tool_call['name']}", state="complete")
            
            # Case B: Tool returns output (Save to history for context)
            elif current_message.type == "tool":
                 st.session_state.messages.append({
                    "role": "tool", 
                    "name": current_message.name, 
                    "content": current_message.content
                })
            
            # Case C: Final AI Response
            elif current_message.type == "ai" and not current_message.tool_calls:
                # Capture content but keep looping until stream ends
                final_response_content = current_message.content

    return final_response_content

# Chat Input Handler
if prompt := st.chat_input("Ask me anything..."):
    # Add User Message
    st.chat_message("user").write(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        
        # Async execution
        try:
            final_response = asyncio.run(run_chat(prompt))
            
            if final_response:
                response_placeholder.markdown(final_response)
                st.session_state.messages.append({"role": "assistant", "content": final_response})
        
        except asyncio.CancelledError:
            pass
        except Exception as e:
            st.error(f"An error occurred: {e}")