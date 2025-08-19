import os
from typing import Optional
from dotenv import load_dotenv


load_dotenv()


_agent_instance: Optional["Agent"] = None  # type: ignore[name-defined]


def get_agent():
    """Create and cache the Sobrus Agent lazily.

    This function avoids heavy imports and initialization at module import time,
    which is important for serverless runtimes and for `app.py` that imports
    this function inside request handlers.
    """
    global _agent_instance
    if _agent_instance is not None:
        return _agent_instance

    # Lazy imports to keep module import light
    from agno.agent import Agent
    from agno.models.google import Gemini
    from agno.tools.knowledge import KnowledgeTools
    from agno.vectordb.mongodb import MongoDb
    from agno.vectordb.search import SearchType
    from agno.knowledge.text import TextKnowledgeBase
    from agno.document.chunking.agentic import AgenticChunking

    #from agno.document.chunking.semantic import SemanticChunking
    #@from agno.document.chunking.recursive import RecursiveChunking
    from agno.embedder.openai import OpenAIEmbedder
    from agno.storage.mongodb import MongoDbStorage
    from agno.memory.v2.db.mongodb import MongoMemoryDb
    from agno.memory.v2.memory import Memory
    from agno.memory.v2.manager import MemoryManager

    # Memory DB for user profiles
    mongo_url = os.getenv(
        "MONGODB_URI",
        "mongodb+srv://ahmedsadikidev:AlXOKUrrG9CFVd4G@cluster0.ywk7r1l.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0",
    )
    memory_db = MongoMemoryDb(
        db_url=mongo_url,
        db_name="user_data",
        collection_name="user_profiles",
    )

    memory_manager = MemoryManager(
        model=Gemini(id="gemini-2.0-flash-lite"),
        memory_capture_instructions="""
        Collect and store the following user information:
        - User's name (first and last name)
        - User's pharma location (city, country)
        - User's pharma name 
        """,
    )
    memory = Memory(db=memory_db, memory_manager=memory_manager)

    # Vector database
    vector_db = MongoDb(
        collection_name="pharma_platform_docs",
        db_url=mongo_url,
        search_index_name=os.getenv("MONGODB_ATLAS_SEARCH_INDEX", "pharma_vector_index"),
        search_type=SearchType.hybrid,
        embedder=OpenAIEmbedder(),
    )

    knowledge_base = TextKnowledgeBase(
        chunking_strategy=AgenticChunking(),
        path="data/text",
        vector_db=vector_db,
    )

    # Loading may fail on server if local data is excluded; keep resilient
    try:
        knowledge_base.load(recreate=True)
    except Exception as exc:
        print(f"[get_agent] Knowledge base load skipped: {exc}")

    # Tools
    knowledge_tools = KnowledgeTools(
        knowledge=knowledge_base,
        search=True,
        think=True,
        analyze=True,
    )

    # Agent session storage
    db_name = os.getenv("MONGODB_DB", "sobrus_customer_service")
    mongo_storage = MongoDbStorage(
        collection_name="agent_sessions",
        db_url=mongo_url,
        db_name=db_name,
    )

    _agent_instance = Agent(
        model=Gemini(id="gemini-2.5-flash"),
        tools=[knowledge_tools],
        storage=mongo_storage,
        show_tool_calls=True,
        add_history_to_messages=True,
        read_chat_history=True,
        num_history_responses=4,
        memory=memory,
        enable_agentic_memory=True,
        debug_mode=True,
        description=(
            "You are 'Assistant Sobrus,' a specialized support AI. Your persona is professional, warm, "
            "and helpful. You are an expert on the Sobrus, and your single source of truth is the provided "
            "knowledge base. You understand French and Moroccan Darija audio but ALWAYS respond in clear, "
            "conversational French, consistently using 'vous'."
        ),
        instructions=[
            "1.1. Golden Rule of Knowledge: Your ONLY source of information is the provided Sobrus knowledge base. NEVER use external knowledge or pre-trained information to answer questions. If the answer is not in the knowledge base, state that you do not have that specific information and offer to help with a different Sobrus topic.",
            "1.2. Language Protocol: You can understand French and Moroccan Darija (including mixed-language audio), but you MUST ALWAYS respond textually in French (France).",
            "1.3. Tonality and Formality: Maintain a warm, helpful, and professional tone. The use of 'tu' is strictly forbidden; you must ALWAYS address the user with 'vous'.",
            "2.1. Initial Contact: Begin every new conversation by asking a single, specific question to understand the user's need. Example: 'Bonjour ! Comment puis-je vous aider avec la plateforme Sobrus aujourd'hui ?'",
            "2.2. Information Gathering: If the user's query requires specific context (e.g., related to sales, inventory), you must first collect three pieces of information in this precise order, asking ONE question per message: 1. Name ('Quel est votre nom ?'), 2. Pharmacy Location ('Dans quelle ville se trouve votre pharmacie ?'), 3. Pharmacy Name ('Et quel est le nom de la pharmacie ?').",
            "2.3. Conversation Flow: Ask only ONE question at a time and wait for the user's response before proceeding. Remember and use the collected information (like the user's name) to personalize the conversation naturally.",
            "3.1. Conciseness: Each message must be a minimum of 15 words and a maximum of 80 words. The goal is clarity, not length.",
            "3.2. Readability: Use simple, everyday French. Structure responses as flowing sentences. Avoid bullet points or numbered lists unless a procedure is too complex for a simple sentence.",
            "3.3. Procedural Guidance: For 'how-to' questions, explain the steps conversationally. Example: 'Pour enregistrer une vente, il vous suffit d'aller dans la section Ventes, de cliquer sur Nouvelle Vente, puis de sélectionner les produits avant de confirmer.'",
            "3.4. Concluding Interaction: Always end your response by checking for understanding and offering more help. Examples: 'Est-ce que ces étapes sont claires pour vous ?', 'Cela répond-il bien à votre question ? N'hésitez pas si je peux vous aider avec autre chose.'",
            "4.1. Vague Queries: If a query is too broad (e.g., 'comment gérer les ventes'), proactively suggest specific options from the knowledge base to narrow it down. Example: 'Bien sûr. Pour les ventes, je peux vous guider sur les ventes complétées, les retours, ou la facturation. Quel sujet vous intéresse le plus ?'",
            "4.2. General Questions: For questions like 'Que pouvez-vous faire ?', briefly summarize your role as an Assistant Sobrus.",
            "4.3. Off-Topic Questions: If asked anything unrelated to Sobrus, politely decline and pivot back. Example: 'Je suis spécialisé dans l'assistance pour Sobrus. Avez-vous une question concernant la plateforme ?',",
        ],
        markdown=True,
    )

    return _agent_instance


def main():
    print("Welcome to the Sobrus Assistant! Type 'exit' to quit.")
    while True:
        user_input = input("You: ")
        if user_input.lower() in {"exit", "quit"}:
            break
        response = get_agent().run(user_input, user_id="12", session_id="12345")
        agent_message = response.content if hasattr(response, "content") else response
        print(f"Agent: {agent_message}")


if __name__ == "__main__":
    main()
