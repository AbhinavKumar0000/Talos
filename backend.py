from __future__ import annotations
import os
import tempfile
import requests
from typing import Annotated, Any, Dict, Optional, TypedDict
from dotenv import load_dotenv

load_dotenv()

pinecone_key = os.getenv("PINECONE_API_KEY")
if pinecone_key:
    os.environ["PINECONE_API_KEY"] = pinecone_key

# --- Imports ---
from langchain_pinecone import PineconeVectorStore
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_mcp_adapters.client import MultiServerMCPClient

# --- Config ---
PINECONE_INDEX_NAME = "chatbot-rag"

# --- Tools ---
search_tool = DuckDuckGoSearchRun(region="us-en")
embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")

def ingest_pdf(file_bytes: bytes, thread_id: str, filename: Optional[str] = None):
    """Uploads PDF to Pinecone Cloud."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        temp_file.write(file_bytes)
        temp_path = temp_file.name
    
    try:
        loader = PyPDFLoader(temp_path)
        docs = loader.load()
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = splitter.split_documents(docs)

        # Add Metadata (Tags)
        for doc in chunks:
            doc.metadata["thread_id"] = thread_id
            doc.metadata["filename"] = filename

        # Upload to Pinecone
        PineconeVectorStore.from_documents(
            documents=chunks,
            embedding=embeddings,
            index_name=PINECONE_INDEX_NAME,
            pinecone_api_key=pinecone_key
        )
        return True
    finally:
        try: os.remove(temp_path)
        except: pass

@tool
def calculator(first_num: float, second_num: float, operation: str) -> dict:
    """
    Perform basic arithmetic.
    Accepts Integers and Floats.
    """
    try:
        f = float(first_num)
        s = float(second_num)
        op = operation.lower()
        if op in ["add", "+"]: return {"result": f + s}
        if op in ["sub", "-", "subtract"]: return {"result": f - s}
        if op in ["mul", "*"]: return {"result": f * s}
        if op in ["div", "/"]: return {"result": f / s if s != 0 else "Error"}
        return {"error": "Invalid op"}
    except Exception as e: return {"error": str(e)}

@tool
def get_stock_price(symbol: str) -> dict:
    """
    Get the current stock price for a given symbol.
    """
    api_key = os.getenv("ALPHAVANTAGE_API_KEY", "C9PE94QUEW9VWGFM")
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={api_key}"
    try:
        return requests.get(url).json()
    except Exception as e:
        return {"error": str(e)}

@tool
def rag_tool(query: str, config: RunnableConfig) -> dict:
    """Search Pinecone Cloud for document content."""
    thread_id = config.get("configurable", {}).get("thread_id")
    
    vector_store = PineconeVectorStore.from_existing_index(
        index_name=PINECONE_INDEX_NAME, 
        embedding=embeddings
    )
    
    # Filter by thread_id to ensure privacy
    retriever = vector_store.as_retriever(search_kwargs={'filter': {'thread_id': thread_id}, 'k': 4})
    docs = retriever.invoke(query)
    return {"context": [d.page_content for d in docs] if docs else "No PDF info found."}
# --- Graph ---
class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

async def build_graph():
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", streaming=True)
    
    # MCP Client
    mcp_client = MultiServerMCPClient({
        "system_agent": {
            "command": "C:/Users/abhin/anaconda3/Scripts/uv.exe",
            "args": ["run", "--with", "fastmcp", "--with", "psutil", 
                     "--with", "speedtest-cli", "--with", "pyautogui",
                     "fastmcp", "run",
                     r"C:\Codes\Learning\Model_Cotext_Protocal\AgenSYS\server.py"],
            "transport": "stdio"
        }
    })
    
    try: mcp_tools = await mcp_client.get_tools()
    except: mcp_tools = []

    tools = [search_tool, get_stock_price, calculator, rag_tool] + mcp_tools
    llm_with_tools = llm.bind_tools(tools)

    async def chat_node(state: ChatState, config=None):
        thread_id = config.get("configurable", {}).get("thread_id")
        sys_msg = SystemMessage(content=f"You are a helpful assistant. Thread ID: {thread_id}")
        return {"messages": [await llm_with_tools.ainvoke([sys_msg, *state["messages"]], config=config)]}

    graph = StateGraph(ChatState)
    graph.add_node("chat_node", chat_node)
    graph.add_node("tools", ToolNode(tools))
    
    graph.add_edge(START, "chat_node")
    graph.add_conditional_edges("chat_node", tools_condition)
    graph.add_edge("tools", "chat_node")

    return graph.compile(checkpointer=MemorySaver())